"""The fan-control safety invariant: never slower than the firmware baseline.

These tests drive the hwmon backend against a fake sysfs tree, because the real
pwm nodes are root-owned and because the failure being guarded against — a fan
commanded below what the BIOS was running — is not something to reproduce on
real hardware to see whether it works.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hotrod_tuner import fan_manager as fm  # noqa: E402


class FakeFan:
    """A pwm/fan pair backed by real files, with a plausible PWM->RPM curve."""

    def __init__(self, root: Path, idx: int, max_rpm: int, auto_rpm: int):
        self.pwm = root / f"pwm{idx}"
        self.enable = root / f"pwm{idx}_enable"
        self.fan = root / f"fan{idx}_input"
        self.max_rpm = max_rpm
        self.auto_rpm = auto_rpm
        self.enable.write_text("2\n")
        self.pwm.write_text("0\n")
        self.fan.write_text(f"{auto_rpm}\n")

    def refresh(self):
        """Recompute RPM from the current mode/duty, as the EC would."""
        if self.enable.read_text().strip() == "2":
            rpm = self.auto_rpm
        else:
            duty = int(self.pwm.read_text().strip())
            rpm = int(self.max_rpm * duty / 255)
        self.fan.write_text(f"{rpm}\n")
        return rpm


@pytest.fixture
def rig(tmp_path, monkeypatch):
    """Fake hwmon chip plus a reset of the module's global calibration state."""
    chip = tmp_path / "hwmon0"
    chip.mkdir()
    (chip / "name").write_text("dell_smm\n")
    fans = [FakeFan(chip, 1, max_rpm=5000, auto_rpm=2800),
            FakeFan(chip, 2, max_rpm=5200, auto_rpm=2950)]

    monkeypatch.setattr(fm, "_HWMON_ROOT", tmp_path)
    monkeypatch.setattr(fm, "_RPM_SETTLE_S", 0)      # no real waiting in tests
    monkeypatch.setattr(fm, "_BACKEND", None)
    monkeypatch.setattr(fm, "_linux_pwm_paths", None)
    monkeypatch.setattr(fm, "_linux_engaged", set())
    monkeypatch.setattr(fm, "_baseline_rpm", {})
    monkeypatch.setattr(fm, "_duty_floor", 255)
    monkeypatch.setattr(fm, "_floor_calibrated", False)
    # Real hardware's RPM follows the commanded duty within a second or two.
    # Reading a stale fan*_input file would make calibration measure the fans'
    # pre-engage speed as if it were their speed at full duty, so the fake has
    # to recompute on read the way the EC does.
    def live_rpm(pwm_path):
        for f in fans:
            if f.pwm == pwm_path:
                return f.refresh()
        return None

    monkeypatch.setattr(fm, "_read_rpm", live_rpm)

    def refresh_all():
        return [f.refresh() for f in fans]

    return {"chip": chip, "fans": fans, "refresh": refresh_all}


def test_detects_writable_hwmon(rig):
    assert fm._detect_backend_linux() == "hwmon"
    assert len(fm._linux_pwm_paths) == 2


def test_gpu_chips_are_never_driven(tmp_path, monkeypatch):
    """GPU thermal firmware reacts faster than a 2s loop; we must not fight it."""
    gpu = tmp_path / "hwmon0"
    gpu.mkdir()
    (gpu / "name").write_text("amdgpu\n")
    (gpu / "pwm1").write_text("0\n")
    (gpu / "pwm1_enable").write_text("2\n")
    monkeypatch.setattr(fm, "_HWMON_ROOT", tmp_path)
    assert fm._discover_linux_pwms() == []


def test_low_request_never_drops_below_baseline(rig):
    """The headline case: BIOS on 'medium', operator asks for 20%.

    A naive implementation writes 20% duty and slows the fans down. The floor
    must override the request so measured RPM stays at or above baseline.
    """
    fm._detect_backend_linux()
    baseline = [f.auto_rpm for f in rig["fans"]]

    assert fm._apply_pct_linux(20) is True
    rpms = rig["refresh"]()

    for rpm, base in zip(rpms, baseline):
        assert rpm >= base, f"fan slowed to {rpm} from baseline {base}"


def test_floor_overrides_every_request_below_it(rig):
    fm._detect_backend_linux()
    fm._apply_pct_linux(50)               # calibrates
    floor = fm._duty_floor

    for pct in (1, 5, 10, 20, 30):
        fm._apply_pct_linux(pct)
        applied = int(rig["fans"][0].pwm.read_text().strip())
        assert applied >= floor
        assert rig["refresh"]()[0] >= rig["fans"][0].auto_rpm


def test_high_request_is_honoured(rig):
    """Above the floor the slider must still do what it says."""
    fm._detect_backend_linux()
    fm._apply_pct_linux(100)
    assert int(rig["fans"][0].pwm.read_text().strip()) == 255
    assert rig["refresh"]()[0] == rig["fans"][0].max_rpm


def test_engage_goes_to_full_speed_before_calibrating(rig):
    """The handover itself must not dip: calibration happens at 255."""
    fm._detect_backend_linux()
    seen = []
    real_write = fm._write_duty

    def spy(pwm, duty):
        seen.append(duty)
        return real_write(pwm, duty)

    fm._write_duty = spy
    try:
        fm._apply_pct_linux(10)
    finally:
        fm._write_duty = real_write

    assert seen[0] == 255, f"first write was {seen[0]}, not full speed"


def test_backstop_raises_floor_when_rpm_lags(rig):
    """A wrong estimate must converge upward, never leave the box under-cooled."""
    fm._detect_backend_linux()
    fm._apply_pct_linux(100)
    before = fm._duty_floor

    # Simulate a fan reading below its baseline despite the commanded duty.
    fm._baseline_rpm[fm._linux_pwm_paths[0]] = 9999
    fm._enforce_floor_from_rpm()

    assert fm._duty_floor > before


def test_floor_never_decreases_within_a_session(rig):
    fm._detect_backend_linux()
    fm._apply_pct_linux(100)
    fm._duty_floor = 200
    fm._apply_pct_linux(1)                # a minimal request must not lower it
    assert fm._duty_floor >= 200


def test_zero_returns_control_to_firmware(rig):
    fm._detect_backend_linux()
    fm._apply_pct_linux(80)
    assert rig["fans"][0].enable.read_text().strip() == "1"

    fm._apply_pct_linux(0)
    for f in rig["fans"]:
        assert f.enable.read_text().strip() == "2"
    assert rig["refresh"]()[0] == rig["fans"][0].auto_rpm


def test_release_resets_calibration(rig):
    """BIOS profile can change between engagements, so the floor must not persist."""
    fm._detect_backend_linux()
    fm._apply_pct_linux(50)
    assert fm._floor_calibrated is True

    fm._release_linux_fans()
    assert fm._floor_calibrated is False
    assert fm._duty_floor == 255
    assert fm._baseline_rpm == {}


def test_baseline_is_not_overwritten_once_engaged(rig):
    """Otherwise 'default' drifts to whatever we last commanded."""
    fm._detect_backend_linux()
    fm.sample_linux_baseline()
    captured = dict(fm._baseline_rpm)

    fm._apply_pct_linux(100)
    rig["refresh"]()
    fm.sample_linux_baseline()            # must be a no-op now

    assert fm._baseline_rpm == captured


def test_no_rpm_feedback_pins_floor_at_full(rig, monkeypatch):
    """With no evidence a lower duty is safe, stay loud rather than risk it."""
    fm._detect_backend_linux()
    monkeypatch.setattr(fm, "_read_rpm", lambda _p: None)
    fm._apply_pct_linux(10)
    assert fm._duty_floor == 255


# ── Release path: the loop, not just the primitive ──────────────────────────
#
# test_zero_returns_control_to_firmware above calls _apply_pct_linux(0)
# directly, and passed for months while the feature was broken: the loop that
# should have called it only ever ran while aggressiveness > 0, so returning
# the slider to 0 did nothing and the fans stayed elevated until reboot.
#
# These drive _loop_tick(), which is the path a user actually takes. A proven
# primitive with no reachable caller is not a working feature.

def _manager(rig):
    fm._detect_backend_linux()
    m = fm.FanManager()
    m.apply_interval = 0.01
    m._baseline = {}
    return m


def test_release_actually_reaches_the_firmware(rig):
    """Slider up, then back to 0 -> SetDefault is sent, fans return to auto."""
    m = _manager(rig)

    m.aggressiveness = 80
    m._loop_tick()
    assert rig["fans"][0].enable.read_text().strip() == "1", "engage should take manual control"

    m.aggressiveness = 0
    m._loop_tick()
    for f in rig["fans"]:
        assert f.enable.read_text().strip() == "2", (
            "returning to 0 must hand control back to the firmware — this is the "
            "regression that left fans stuck at an elevated rate"
        )


def test_release_is_edge_triggered_not_repeated(rig):
    """SetDefault fires once on the falling edge, not every second.

    Re-sending it continuously would fight the firmware's own ramping.
    """
    m = _manager(rig)
    m.aggressiveness = 60
    m._loop_tick()

    calls = []
    real = fm._apply_pct_linux
    fm._apply_pct_linux = lambda pct: (calls.append(pct), real(pct))[1]
    try:
        m.aggressiveness = 0
        m._loop_tick()          # falling edge -> should apply
        m._loop_tick()          # already released -> should not
        m._loop_tick()
    finally:
        fm._apply_pct_linux = real

    assert calls == [0], f"expected exactly one release, got {calls}"


def test_policy_hook_cannot_pin_fans_on(rig):
    """A policy recommendation returning to 0 must also release.

    effective = max(slider, policy). If the policy hook drops to 0 while the
    slider is already 0, that is still a falling edge and must release.
    """
    m = _manager(rig)
    rec = {"v": 70}
    m.set_policy_hook(lambda: rec["v"])

    m._loop_tick()
    assert rig["fans"][0].enable.read_text().strip() == "1"

    rec["v"] = 0
    m._loop_tick()
    for f in rig["fans"]:
        assert f.enable.read_text().strip() == "2"
