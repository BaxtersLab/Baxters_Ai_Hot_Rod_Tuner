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
                _log.warning('Fan PWM control is Windows-only')
        except Exception as e:
            _log.error('FanManager apply failed: %s', e)

        with self._lock:
            self._last_targets = {'pwm_pct': float(pct)}

        return {'ok': bool(success), 'pct': pct}

    # Background loop
    def _bg_loop(self):
        while self._running:
            try:
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
                    time.sleep(self.apply_interval)
                else:
                    time.sleep(1.0)
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


def _detect_backend() -> str:
    """Probe both shims once and return which backend to use."""
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


def reset_fan_backend() -> None:
    """Force re-detection of the fan control backend on next apply.
    Useful if the user installs/enables the Dell driver at runtime."""
    global _BACKEND
    _BACKEND = None
    _log.info('Fan backend reset — will re-detect on next apply')


__all__ = ['FanManager', 'reset_fan_backend']
