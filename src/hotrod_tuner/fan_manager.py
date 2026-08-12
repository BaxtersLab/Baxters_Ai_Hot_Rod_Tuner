"""Fan manager for Hot Rod Tuner.

Responsibilities:
- Track `aggressiveness` (0-100) requested by the UI
- Sample baseline RPMs from the existing `sensor_poller`
- Compute target RPMs (never below baseline)
- Apply fan PWM via the LHM shim on every bg-loop tick
- Run a background thread to apply targets while aggressiveness > 0
"""
from pathlib import Path
import threading
import time
import os
import logging
from typing import Dict, Any

from .sensors import sensor_poller

_log = logging.getLogger('hrt.fan_manager')


class FanManager:
    def __init__(self, apply_interval: float = 2.0):
        self.aggressiveness = 0  # 0..100, user-controlled
        self._policy_rec = 0    # 0..100, from policy hook (auto-raise only)
        self._last_effective = 0  # for edge-triggered release; see _bg_loop
        self._policy_hook = None  # callable() -> int, set via set_policy_hook()
        self._baseline: Dict[str, float] = {}  # sensor_name -> rpm
        self._last_targets: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self.apply_interval = apply_interval

    # Public API
    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._bg_loop, daemon=True)
        self._thread.start()
        _log.info('FanManager background thread started')

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        # Hand the fans back to firmware. Without this a Linux machine whose
        # pwm nodes we switched to manual keeps that duty cycle after HRT is
        # gone — the EC stops ramping and the box quietly cooks under load.
        if os.name != 'nt':
            try:
                _release_linux_fans()
            except Exception as e:
                _log.critical('FanManager.stop: fan release failed: %s', e)

    def set_aggressiveness(self, value: int) -> dict:
        v = max(0, min(100, int(value)))
        with self._lock:
            self.aggressiveness = v
            # sample baseline immediately when user enables >0
            if v > 0:
                self._sample_baseline()
        return self.get_state()

    def set_policy_hook(self, fn) -> None:
        """Register a zero-argument callable that returns a recommended
        aggressiveness int (0-100).  Called each bg-loop iteration.
        The effective aggressiveness used is max(user, policy_rec)."""
        self._policy_hook = fn

    def get_state(self) -> dict:
        # Count non-GPU fan sensors currently visible in the snapshot
        snap = sensor_poller.snapshot()
        fans_connected = 0
        if snap:
            fans_connected = sum(
                1 for s in snap.sensors
                if s.category == 'fan' and s.value and s.value > 0
                and not _is_gpu_fan(s.name)
            )
        with self._lock:
            return {
                'aggressiveness': self.aggressiveness,
                'policy_rec': self._policy_rec,
                'effective_aggressiveness': max(self.aggressiveness, self._policy_rec),
                'baseline': dict(self._baseline),
                'last_targets': dict(self._last_targets),
                'fans_connected': fans_connected,
                'fan_backend': _BACKEND or 'none',
            }

    # Core computation
    def _sample_baseline(self):
        snap = sensor_poller.snapshot()
        if not snap:
            return
        for s in snap.sensors:
            if s.category == 'fan' and s.value and s.value > 0:
                if _is_gpu_fan(s.name):
                    continue  # GPU fans: never touch
                # set baseline if not present
                if s.name not in self._baseline:
                    self._baseline[s.name] = float(s.value)

    def _compute_targets(self) -> Dict[str, float]:
        snap = sensor_poller.snapshot()
        targets: Dict[str, float] = {}
        if not snap:
            return targets
        for s in snap.sensors:
            if s.category != 'fan':
                continue
            # Never compute targets for GPU fans — GPU drivers manage their own thermals
            if _is_gpu_fan(s.name):
                continue
            curr = float(s.value or 0)
            baseline = self._baseline.get(s.name, curr)
            # if we haven't seen a baseline and current is valid, set it
            if baseline == 0 and curr > 0:
                baseline = curr
                self._baseline[s.name] = baseline

            effective = max(self.aggressiveness, self._policy_rec)
            if effective <= 0:
                target = baseline
            else:
                # simple linear scale: at 100 => 2x baseline (conservative)
                scale = 1.0 + (effective / 100.0)
                target = max(baseline, baseline * scale)

            targets[s.name] = float(round(target, 1))
        return targets

    def apply_once(self) -> Dict[str, Any]:
        with self._lock:
            effective = max(self.aggressiveness, self._policy_rec)

        # Map slider to PWM%:
        #   0  → SetDefault (BIOS takes back control)
        #   1+ → 20% floor so fans never stall, then linear to 100%
        pct = max(20, effective) if effective > 0 else 0

        success = False
        try:
            if os.name == 'nt':
                success = _apply_pct_windows(pct)
            else:
                success = _apply_pct_linux(pct)
        except Exception as e:
            _log.error('FanManager apply failed: %s', e)

        with self._lock:
            self._last_targets = {'pwm_pct': float(pct)}

        return {'ok': bool(success), 'pct': pct}

    # One iteration of the background loop, factored out so the release path
    # can be tested without threads or sleeps.
    #
    # It had to be: the bug this guards against lived here for months while
    # test_zero_returns_control_to_firmware passed, because that test calls
    # _apply_pct_linux(0) directly and never went through the loop. A primitive
    # can be correct and proven while the only path to it is missing.
    #
    # Returns the number of seconds the caller should sleep.
    def _loop_tick(self) -> float:
        # Poll policy hook first (always, so _policy_rec stays fresh)
        if self._policy_hook is not None:
            try:
                rec = int(self._policy_hook() or 0)
                self._policy_rec = max(0, min(100, rec))
            except Exception as _he:
                _log.debug('Policy hook error: %s', _he)

        effective = max(self.aggressiveness, self._policy_rec)
        if effective > 0:
            if not self._baseline:
                self._sample_baseline()
            self.apply_once()
            self._last_effective = effective
            return self.apply_interval

        # Edge-triggered release. apply_once() maps 0 -> SetDefault, handing
        # thermal control back to the firmware — but until 2026-08-11 it was
        # only ever CALLED while effective > 0. Returning the slider to 0 did
        # nothing, and the fans stayed wherever they had last been driven with
        # no way back short of a reboot.
        #
        # Only on the falling edge: re-sending SetDefault every second would
        # fight the firmware's own ramping.
        if self._last_effective:
            _log.info('Fan aggressiveness released — returning control to firmware')
            self.apply_once()
        self._last_effective = 0
        return 1.0

    # Background loop
    def _bg_loop(self):
        while self._running:
            try:
                time.sleep(self._loop_tick())
            except Exception:
                time.sleep(1.0)


# ── GPU sensor name filter ────────────────────────────────────────────────────
_GPU_KEYWORDS = ('gpu', 'nvidia', 'amd_gpu', 'radeon', 'geforce', 'rx_', 'gtx_', 'rtx_')


def _is_gpu_fan(sensor_name: str) -> bool:
    """Return True if the sensor name looks like a GPU fan — we must never touch these."""
    n = sensor_name.lower()
    return any(kw in n for kw in _GPU_KEYWORDS)


# ── Fan control backend — two paths, auto-detected once at first use ──────────
#
#  PATH A  "lhm"   HrtFanControl.exe  — LibreHardwareMonitor SensorType.Control
#                  Works on most generic/ASUS/MSI/Gigabyte boards.
#                  Probe: run with pct=0; exit 0 (controlled fans) → use it.
#                  Falls back to PATH B if exit 1 (0 controllable sensors).
#
#  PATH B  "dell"  HrtDellFanControl.exe — DellSmbiosBzh kernel driver
#                  Works on Dell Precision / Latitude / XPS where LHM has
#                  no Control-type fan sensors.
#                  Requires bzh_dell_smm_io_x64.sys to load (needs
#                  either test-signing or UpgradedSystem registry key on
#                  some machines).
#
#  _BACKEND is set on first call and cached for the lifetime of the process.
# ─────────────────────────────────────────────────────────────────────────────

import sys as _sys
_VENDOR_DIR = (
    Path(_sys.executable).parent / 'vendor' / 'lhm'
    if getattr(_sys, 'frozen', False)
    else Path(__file__).resolve().parent.parent.parent / 'vendor' / 'lhm'
)
_LHM_EXE   = _VENDOR_DIR / 'HrtFanControl.exe'
_DELL_EXE  = _VENDOR_DIR / 'HrtDellFanControl.exe'

_BACKEND: str | None = None   # 'lhm' | 'dell' | 'none'  — set once


#  PATH C  "hwmon" (Linux) — /sys/class/hwmon/hwmonN/pwmM
#                  The mainline kernel exposes fan PWM directly, so there is no
#                  shim to ship: dell_smm, nct6775, asus_wmi_sensors and friends
#                  all present the same pwmM / pwmM_enable pair.
#                    pwmM_enable = 1  manual, duty from pwmM (0-255)
#                    pwmM_enable = 2  automatic — firmware/EC owns the fan
#                  Nothing here writes without an explicit request, and stop()
#                  always restores mode 2.


# ── Linux hwmon fan control ──────────────────────────────────────────────────

_HWMON_ROOT = Path('/sys/class/hwmon')

# Chip names whose fans must never be driven from here. GPU fans are managed by
# the GPU's own thermal firmware, which reacts far faster than a 2s poll loop.
_HWMON_SKIP_CHIPS = ('amdgpu', 'nouveau', 'nvidia', 'radeon')

_linux_pwm_paths: list[Path] | None = None   # discovered pwmM files
_linux_engaged: set = set()                  # pwmM files switched to manual by us
_linux_detect_reason: str = ''               # why detection failed, for the UI

# ── THE SAFETY INVARIANT ─────────────────────────────────────────────────────
#
#   "It's ok to tinker and increase, never ok to decrease."  — operator, and
#   the governing rule for everything below it.
#
#   Fan control may only ever run the fans FASTER than the firmware would.
#   It must never slow one down, at any slider position, at any moment.
#   Tuning upward is free to experiment; downward is not a tuning range at all.
#
# This is not a preference — a laptop whose EC has been told to run the fans at
# 20% while it believes it is still in charge of thermals will cook itself.
#
# What makes it non-trivial: in automatic mode (pwmN_enable = 2) the dell_smm
# driver returns ENODATA for pwmN, so the firmware's CURRENT duty cannot be read
# back. Writing an absolute duty is therefore a blind write — the naive
# `pwm = requested` is exactly how you slow a fan down without meaning to. The
# operator's BIOS profile (quiet / medium / performance) shifts that unknown
# duty around too, so no hardcoded floor is safe either.
#
# What IS readable at all times, in both modes, is fanN_input (RPM). So the
# baseline is knowable in RPM even though it is unknowable in PWM:
#
#   1. While the firmware is in charge, sample RPM  -> baseline_rpm (per fan).
#   2. On first engage, go straight to duty 255. Full speed is unambiguously
#      at or above whatever the firmware was doing, so the invariant holds
#      through the transition itself.
#   3. Measure RPM at 255 -> rpm_max. Fan RPM is monotonic and roughly affine
#      in PWM above the stall point, so the duty that reproduces baseline_rpm
#      is estimated as 255 * baseline_rpm / rpm_max, then inflated by a margin
#      because the real curve is concave (that estimate errs low).
#   4. Every applied duty is max(requested, duty_floor). The floor only ever
#      RISES within a session; nothing can lower it.
#   5. A closed-loop backstop re-reads RPM each cycle. If any fan is measured
#      below its baseline the floor is raised immediately, so an inaccurate
#      estimate self-corrects upward and never downward.
#
# Net effect: the slider means "how much MORE cooling than default", 0 hands
# control back to the firmware, and no path through this module can produce
# less airflow than the BIOS profile the operator chose.

_RPM_SETTLE_S = 2.5     # fans need ~2s to reach a commanded speed
_FLOOR_MARGIN = 1.15    # affine estimate errs low on a concave curve
_FLOOR_PAD    = 12      # absolute PWM pad on top of the proportional margin
_RPM_TOLERANCE = 0.98   # treat >=98% of baseline as "not slower" (sensor noise)

_baseline_rpm: dict = {}     # pwm path -> RPM observed under firmware control
_duty_floor: int = 255       # never apply below this; starts fully safe
_floor_calibrated: bool = False


def _fan_input_for(pwm: Path) -> Path:
    """hwmon pairs pwmN with fanN_input in the same chip directory."""
    return pwm.with_name(pwm.name.replace('pwm', 'fan') + '_input')


def _read_rpm(pwm: Path):
    """Current RPM for the fan driven by `pwm`, or None if unreadable."""
    try:
        return int(_fan_input_for(pwm).read_text().strip())
    except (OSError, ValueError):
        return None


def sample_linux_baseline() -> dict:
    """Record each fan's RPM while the firmware is still in control.

    Only meaningful before we engage manual mode, so it refuses to overwrite a
    baseline once any fan has been engaged — otherwise the "default" would drift
    to whatever WE last commanded, and the invariant would decay to nothing.
    """
    global _baseline_rpm
    if _linux_engaged:
        return dict(_baseline_rpm)
    for pwm in (_linux_pwm_paths or []):
        rpm = _read_rpm(pwm)
        if rpm is not None and rpm > 0:
            # Keep the highest seen: the firmware ramps with load, and the
            # floor must clear the busiest state observed, not the idlest.
            _baseline_rpm[pwm] = max(_baseline_rpm.get(pwm, 0), rpm)
    return dict(_baseline_rpm)


def _calibrate_duty_floor() -> int:
    """Estimate the lowest duty that still matches firmware airflow.

    Runs at full speed, so the fans are never slower than baseline while this
    is measuring. Returns a PWM value in 0-255.
    """
    global _duty_floor, _floor_calibrated

    ratios = []
    for pwm in list(_linux_engaged):
        base = _baseline_rpm.get(pwm)
        rpm_max = _read_rpm(pwm)
        if base and rpm_max and rpm_max > 0:
            ratios.append(min(1.0, base / rpm_max))

    if not ratios:
        # No usable RPM feedback: stay at full speed. Loud, but the invariant
        # is not negotiable and there is no evidence any lower duty is safe.
        _duty_floor = 255
        _floor_calibrated = True
        _log.warning('Fan [hwmon] no RPM feedback — duty floor pinned at 255')
        return _duty_floor

    worst = max(ratios)                       # the fan needing the most duty
    est = int(255 * worst * _FLOOR_MARGIN) + _FLOOR_PAD
    _duty_floor = max(1, min(255, est))
    _floor_calibrated = True
    _log.info('Fan [hwmon] duty floor calibrated to %d/255 '
              '(worst baseline/max ratio %.2f)', _duty_floor, worst)
    return _duty_floor


def _enforce_floor_from_rpm() -> None:
    """Backstop: raise the floor if any fan is measured below its baseline.

    The affine estimate can be wrong on an unusual fan curve. This only ever
    increases the floor, so a bad estimate converges upward to safety instead
    of leaving the machine under-cooled.
    """
    global _duty_floor
    for pwm in list(_linux_engaged):
        base = _baseline_rpm.get(pwm)
        rpm = _read_rpm(pwm)
        if not base or rpm is None:
            continue
        if rpm < base * _RPM_TOLERANCE:
            bumped = min(255, _duty_floor + 16)
            if bumped != _duty_floor:
                _log.warning(
                    'Fan [hwmon] %s at %d RPM is below its %d RPM baseline — '
                    'raising duty floor %d -> %d', pwm.name, rpm, base,
                    _duty_floor, bumped)
                _duty_floor = bumped


def _discover_linux_pwms() -> list[Path]:
    """Every controllable pwmM file on the system, excluding GPU chips."""
    found: list[Path] = []
    if not _HWMON_ROOT.is_dir():
        return found
    for hw in sorted(_HWMON_ROOT.glob('hwmon*')):
        try:
            chip = (hw / 'name').read_text().strip().lower()
        except OSError:
            continue
        if any(skip in chip for skip in _HWMON_SKIP_CHIPS):
            _log.info('Fan backend: skipping GPU chip %s (%s)', chip, hw.name)
            continue
        for pwm in sorted(hw.glob('pwm[0-9]')):
            if pwm.with_name(pwm.name + '_enable').exists():
                found.append(pwm)
    return found


def _detect_backend_linux() -> str:
    """Return 'hwmon' if this machine exposes writable fan PWM, else 'none'.

    Writability is the deciding test, not mere presence. hwmon pwm nodes are
    root-owned 0644 by default, so an unprivileged HRT can read every fan RPM
    yet drive none of them. Reporting 'hwmon' in that state would give the UI a
    live slider that silently does nothing.
    """
    global _linux_pwm_paths, _linux_detect_reason

    _linux_pwm_paths = _discover_linux_pwms()
    if not _linux_pwm_paths:
        _linux_detect_reason = (
            'No hwmon pwm nodes found. The CPU/chassis fans are not exposed by any '
            'loaded sensor driver, so only fan RPM monitoring is possible.'
        )
        _log.warning('Fan backend: %s', _linux_detect_reason)
        return 'none'

    writable = [p for p in _linux_pwm_paths if os.access(p, os.W_OK)]
    if not writable:
        _linux_detect_reason = (
            f'Found {len(_linux_pwm_paths)} pwm node(s) but none are writable by uid '
            f'{os.getuid()}; they are root-owned. Fan monitoring works; fan CONTROL '
            f'needs a udev rule granting group write on /sys/class/hwmon/*/pwm*, or '
            f'running HRT as root. On Dell hardware the dell-smm-hwmon module may '
            f'also need restricted=0 before it accepts writes.'
        )
        _log.warning('Fan backend: %s', _linux_detect_reason)
        return 'none'

    _linux_pwm_paths = writable
    _linux_detect_reason = ''
    _log.info('Fan backend: hwmon — %d writable pwm node(s): %s',
              len(writable), ', '.join(str(p) for p in writable))
    return 'hwmon'


def _write_duty(pwm: Path, duty: int) -> bool:
    """Put one fan into manual mode at `duty`. Reverts it on any failure."""
    enable = pwm.with_name(pwm.name + '_enable')
    try:
        enable.write_text('1\n')              # manual
        pwm.write_text(f'{duty}\n')
        _linux_engaged.add(pwm)
        return True
    except OSError as e:
        _log.error('Fan [hwmon] %s: write failed (%s) — reverting to automatic',
                   pwm, e)
        try:
            enable.write_text('2\n')
            _linux_engaged.discard(pwm)
        except OSError:
            _log.critical('Fan [hwmon] %s: could NOT restore automatic control', pwm)
        return False


def _apply_pct_linux(pct: int) -> bool:
    """Raise the fans to `pct`, or hand control back to firmware at 0.

    Upholds the never-slower-than-firmware invariant documented at the top of
    the hwmon section. `pct` is a request, not a command: the value actually
    written is max(requested, duty_floor), and the floor is derived from
    measured RPM rather than assumed.

    First engage runs a calibration pass at full speed. That ordering is the
    whole trick — the fans are never below baseline even while we are working
    out where the floor is.
    """
    global _BACKEND

    if _BACKEND is None:
        _BACKEND = _detect_backend()
    if _BACKEND != 'hwmon' or not _linux_pwm_paths:
        return False

    if pct <= 0:
        return _release_linux_fans()

    requested = max(1, min(255, round(pct * 255 / 100)))

    if not _floor_calibrated:
        # Capture what the firmware was doing BEFORE taking over; once we are
        # driving, the "default" is no longer observable.
        sample_linux_baseline()
        # Full speed first: unambiguously >= whatever the firmware was doing,
        # so the invariant holds across the handover itself.
        engaged = [p for p in _linux_pwm_paths if _write_duty(p, 255)]
        if not engaged:
            return False
        time.sleep(_RPM_SETTLE_S)
        _calibrate_duty_floor()
    else:
        _enforce_floor_from_rpm()

    duty = max(requested, _duty_floor)
    if duty != requested:
        _log.info('Fan [hwmon] request %d/255 raised to floor %d/255 '
                  '(never below firmware baseline)', requested, duty)

    ok_any = False
    for pwm in _linux_pwm_paths:
        if _write_duty(pwm, duty):
            ok_any = True
    if ok_any:
        _log.info('Fan [hwmon] pct=%d duty=%d applied to %d fan(s)',
                  pct, duty, len(_linux_engaged))
    return ok_any


def _release_linux_fans() -> bool:
    """Return every fan we switched to manual back to firmware control.

    Called on slider-zero and from FanManager.stop(). Leaving a laptop latched
    in manual mode after HRT exits would mean the EC never ramps the fans again
    under load, so this must run even on a failing path.
    """
    global _duty_floor, _floor_calibrated, _baseline_rpm
    if not _linux_engaged:
        return True
    ok = True
    for pwm in list(_linux_engaged):
        try:
            pwm.with_name(pwm.name + '_enable').write_text('2\n')
            _linux_engaged.discard(pwm)
        except OSError as e:
            ok = False
            _log.critical('Fan [hwmon] %s: failed to restore automatic control: %s', pwm, e)
    if ok:
        _log.info('Fan [hwmon] all fans returned to firmware control')

    # Drop the calibration so the next engage re-measures from scratch and
    # starts again at full speed. The firmware baseline is not a constant: the
    # operator can change the BIOS fan profile (quiet / medium / performance)
    # between engagements, and a floor calibrated against "quiet" would be below
    # the real baseline under "medium" — the exact failure this must not have.
    _duty_floor = 255
    _floor_calibrated = False
    _baseline_rpm = {}
    return ok


def _detect_backend() -> str:
    """Probe the available fan-control paths and cache which one to use.

    Caching the result here, rather than only inside _apply_pct_*, is what makes
    the startup warm-up thread useful: it previously called this and discarded
    the answer, so _BACKEND stayed None and /api/fans/backend reported "unknown"
    until the operator first moved the slider — exactly when a clear answer
    matters least.
    """
    global _BACKEND
    _BACKEND = _detect_backend_linux() if os.name != 'nt' else _detect_backend_windows()
    return _BACKEND


def _detect_backend_windows() -> str:
    """Probe both Windows shims once and return which backend to use."""
    import subprocess

    # ── Try LHM first ────────────────────────────────────────────────────────
    if _LHM_EXE.is_file():
        try:
            r = subprocess.run(
                [str(_LHM_EXE), '0'],       # SetDefault probe
                capture_output=True, text=True, timeout=10
            )
            if r.returncode == 0:           # exit 0 = found + set ≥1 sensor
                _log.info('Fan backend: LHM (HrtFanControl.exe) — found controllable sensors')
                return 'lhm'
            # exit 1 = ran fine but 0 sensors found — board not supported by LHM
            _log.info('Fan backend: LHM probe returned 0 controllable sensors, trying Dell path')
        except Exception as e:
            _log.warning('Fan backend: LHM probe failed (%s), trying Dell path', e)
    else:
        _log.info('Fan backend: HrtFanControl.exe not found, skipping LHM probe')

    # ── Try Dell SMM ─────────────────────────────────────────────────────────
    if _DELL_EXE.is_file():
        dll = _DELL_EXE.parent / 'DellSmbiosBzhLib.dll'
        sys = _DELL_EXE.parent / 'bzh_dell_smm_io_x64.sys'
        if dll.is_file() and sys.is_file():
            try:
                r = subprocess.run(
                    [str(_DELL_EXE), '0'],  # restore-default probe
                    capture_output=True, text=True, timeout=10,
                    cwd=str(_DELL_EXE.parent)
                )
                if r.returncode == 0:
                    _log.info('Fan backend: Dell SMM (HrtDellFanControl.exe)')
                    return 'dell'
                _log.warning('Fan backend: Dell SMM probe exit=%d stderr=%s',
                             r.returncode, r.stderr.strip())
            except Exception as e:
                _log.warning('Fan backend: Dell SMM probe failed (%s)', e)
        else:
            _log.warning('Fan backend: Dell shim present but DLL/SYS missing')
    else:
        _log.info('Fan backend: HrtDellFanControl.exe not found')

    _log.warning('Fan backend: no working fan control found — slider disabled')
    return 'none'


def _apply_pct_windows(pct: int) -> bool:
    """Dispatch fan PWM percent to whichever backend this machine supports.

    pct == 0  → hand control back to BIOS/EC firmware
    pct 1-100 → set fans to that duty cycle (LHM: continuous; Dell: 3 levels)
    """
    global _BACKEND
    import subprocess

    if _BACKEND is None:
        _BACKEND = _detect_backend()

    if _BACKEND == 'none':
        return False

    exe = _LHM_EXE if _BACKEND == 'lhm' else _DELL_EXE
    try:
        r = subprocess.run(
            [str(exe), str(pct)],
            capture_output=True, text=True, timeout=10,
            cwd=str(exe.parent)
        )
        _log.info('Fan [%s] pct=%d exit=%d out=%s', _BACKEND, pct, r.returncode, r.stdout.strip())
        if r.stderr:
            _log.warning('Fan [%s] stderr: %s', _BACKEND, r.stderr.strip())
        return r.returncode in (0, 1)
    except Exception as e:
        _log.error('Fan [%s] execution failed: %s', _BACKEND, e)
        return False


if os.name != 'nt':
    # Safety net for the ordinary exit paths (SystemExit, an unhandled
    # exception, uvicorn shutdown). It does NOT cover os._exit(), which run_server
    # uses when the app window closes — that path releases the fans explicitly
    # before calling it.
    import atexit as _atexit
    _atexit.register(_release_linux_fans)


def release_fans_now() -> None:
    """Public, exception-proof fan release for hard-exit paths."""
    if os.name == 'nt':
        return
    try:
        _release_linux_fans()
    except Exception as e:      # never let cleanup block process teardown
        _log.critical('release_fans_now failed: %s', e)


def reset_fan_backend() -> None:
    """Force re-detection of the fan control backend on next apply.
    Useful if the user installs/enables the Dell driver at runtime."""
    global _BACKEND
    _BACKEND = None
    _log.info('Fan backend reset — will re-detect on next apply')


__all__ = ['FanManager', 'reset_fan_backend', 'release_fans_now']
