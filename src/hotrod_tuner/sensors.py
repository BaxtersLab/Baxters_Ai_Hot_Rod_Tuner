"""Hardware sensor polling for Hot Rod Tuner.

Uses psutil for CPU temps/usage, and falls back to WMI +
OpenHardwareMonitor/LibreHardwareMonitor on Windows when psutil
sensors are unavailable (common on Windows desktops).
"""
import platform
import psutil
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# WMI is only available on Windows
_WMI_AVAILABLE = False
if platform.system() == "Windows":
    try:
        import wmi  # type: ignore
        _WMI_AVAILABLE = True
    except ImportError:
        pass


@dataclass
class SensorReading:
    """A single sensor reading."""
    name: str
    label: str
    value: float
    unit: str  # "°C", "%", "MHz", "RPM"
    category: str  # "temperature", "usage", "clock", "fan"


@dataclass
class HardwareSnapshot:
    """Complete hardware state at a point in time."""
    timestamp: float = 0.0
    sensors: List[SensorReading] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "sensors": [
                {
                    "name": s.name,
                    "label": s.label,
                    "value": round(s.value, 1),
                    "unit": s.unit,
                    "category": s.category,
                }
                for s in self.sensors
            ],
        }


class SensorPoller:
    """Polls hardware sensors at a configurable interval."""

    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self._latest: Optional[HardwareSnapshot] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._wmi_conn = None
        if _WMI_AVAILABLE:
            try:
                self._wmi_conn = wmi.WMI(namespace="root\\OpenHardwareMonitor")
            except Exception:
                try:
                    self._wmi_conn = wmi.WMI(namespace="root\\LibreHardwareMonitor")
                except Exception:
                    self._wmi_conn = None

    # ── public API ──────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def snapshot(self) -> Optional[HardwareSnapshot]:
        with self._lock:
            return self._latest

    # ── internal ────────────────────────────────────────────────

    def _poll_loop(self):
        while self._running:
            snap = self._read_all()
            with self._lock:
                self._latest = snap
            time.sleep(self.interval)

    def _read_all(self) -> HardwareSnapshot:
        snap = HardwareSnapshot(timestamp=time.time())

        # ── CPU usage per-core ──
        per_cpu = psutil.cpu_percent(interval=0, percpu=True)
        for i, pct in enumerate(per_cpu):
            snap.sensors.append(SensorReading(
                name=f"cpu_core_{i}_usage",
                label=f"CPU Core {i}",
                value=pct,
                unit="%",
                category="usage",
            ))
        # overall CPU
        snap.sensors.append(SensorReading(
            name="cpu_total_usage",
            label="CPU Total",
            value=psutil.cpu_percent(interval=0),
            unit="%",
            category="usage",
        ))

        # ── Memory ──
        mem = psutil.virtual_memory()
        snap.sensors.append(SensorReading(
            name="ram_usage",
            label="RAM",
            value=mem.percent,
            unit="%",
            category="usage",
        ))

        # ── Temperatures via psutil (Linux, some Windows) ──
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for chip, entries in temps.items():
                    for entry in entries:
                        label = entry.label or chip
                        snap.sensors.append(SensorReading(
                            name=f"temp_{chip}_{label}".replace(" ", "_").lower(),
                            label=f"{label} ({chip})",
                            value=entry.current,
                            unit="°C",
                            category="temperature",
                        ))
        except AttributeError:
            # psutil.sensors_temperatures() not available on this platform
            pass

        # ── Temperatures via WMI (Windows with OHM/LHM) ──
        if self._wmi_conn and not any(s.category == "temperature" for s in snap.sensors):
            self._read_wmi_sensors(snap)

        # ── Fan speeds via psutil ──
        try:
            fans = psutil.sensors_fans()
            if fans:
                for chip, entries in fans.items():
                    for entry in entries:
                        label = entry.label or chip
                        snap.sensors.append(SensorReading(
                            name=f"fan_{chip}_{label}".replace(" ", "_").lower(),
                            label=f"{label} ({chip})",
                            value=entry.current,
                            unit="RPM",
                            category="fan",
                        ))
        except AttributeError:
            pass

        # ── GPU via psutil (NVIDIA on Linux only) ──
        # If no GPU temp found, try nvidia-smi as a last resort
        if not any("gpu" in s.name for s in snap.sensors):
            self._try_nvidia_smi(snap)

        return snap

    def _read_wmi_sensors(self, snap: HardwareSnapshot):
        """Read sensors from OpenHardwareMonitor / LibreHardwareMonitor via WMI."""
        if not self._wmi_conn:
            return
        try:
            for sensor in self._wmi_conn.Sensor():
                s_type = sensor.SensorType.lower() if sensor.SensorType else ""
                value = sensor.Value
                if value is None:
                    continue
                name_raw = (sensor.Name or "unknown").replace(" ", "_").lower()
                parent = (sensor.Parent or "").replace("/", "_").strip("_")

                if s_type == "temperature":
                    snap.sensors.append(SensorReading(
                        name=f"temp_{parent}_{name_raw}",
                        label=f"{sensor.Name} ({parent})",
                        value=float(value),
                        unit="°C",
                        category="temperature",
                    ))
                elif s_type == "load":
                    snap.sensors.append(SensorReading(
                        name=f"load_{parent}_{name_raw}",
                        label=f"{sensor.Name} ({parent})",
                        value=float(value),
                        unit="%",
                        category="usage",
                    ))
                elif s_type == "fan":
                    snap.sensors.append(SensorReading(
                        name=f"fan_{parent}_{name_raw}",
                        label=f"{sensor.Name} ({parent})",
                        value=float(value),
                        unit="RPM",
                        category="fan",
                    ))
                elif s_type == "clock":
                    snap.sensors.append(SensorReading(
                        name=f"clk_{parent}_{name_raw}",
                        label=f"{sensor.Name} ({parent})",
                        value=float(value),
                        unit="MHz",
                        category="clock",
                    ))
        except Exception:
            pass

    def _try_nvidia_smi(self, snap: HardwareSnapshot):
        """Try reading GPU temp from nvidia-smi."""
        import subprocess
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu,name",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                for i, line in enumerate(result.stdout.strip().splitlines()):
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 2:
                        gpu_name = parts[2] if len(parts) >= 3 else f"GPU {i}"
                        snap.sensors.append(SensorReading(
                            name=f"gpu_{i}_temp",
                            label=f"{gpu_name} Temp",
                            value=float(parts[0]),
                            unit="°C",
                            category="temperature",
                        ))
                        snap.sensors.append(SensorReading(
                            name=f"gpu_{i}_usage",
                            label=f"{gpu_name} Load",
                            value=float(parts[1]),
                            unit="%",
                            category="usage",
                        ))
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            pass


# Module-level singleton
sensor_poller = SensorPoller(interval=1.0)
