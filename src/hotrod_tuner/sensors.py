"""Hardware sensor polling for Hot Rod Tuner.

Uses psutil for CPU temps/usage, and falls back to WMI +
OpenHardwareMonitor/LibreHardwareMonitor on Windows when psutil
sensors are unavailable (common on Windows desktops).
"""
import platform
import psutil
import time
import threading
import subprocess
import re
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path

# WMI is only available on Windows
_WMI_AVAILABLE = False
if platform.system() == "Windows":
    try:
        import wmi  # type: ignore
        _WMI_AVAILABLE = True
    except ImportError:
        pass

# ── LibreHardwareMonitor launcher ────────────────────────────────────
_lhm_process: Optional[subprocess.Popen] = None

_LHM_VERSION = "v0.9.4"
_LHM_ZIP_URL = f"https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/{_LHM_VERSION}/LibreHardwareMonitor-net472.zip"


def _lhm_vendor_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "vendor" / "lhm"


def _find_lhm_exe() -> Optional[str]:
    """Locate LibreHardwareMonitor.exe — check vendor/lhm first, then common locations."""
    candidates = [_lhm_vendor_dir() / "LibreHardwareMonitor.exe"]
    for base in [Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")),
                 Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")),
                 Path(os.environ.get("LOCALAPPDATA", "")),
                 Path(os.environ.get("APPDATA", ""))]:
        candidates.append(base / "LibreHardwareMonitor" / "LibreHardwareMonitor.exe")
    for p in candidates:
        if p.is_file():
            return str(p)
    return None


def _download_lhm() -> bool:
    """Download LHM portable to vendor/lhm if not present. Returns True on success."""
    dest = _lhm_vendor_dir()
    exe = dest / "LibreHardwareMonitor.exe"
    if exe.is_file():
        return True
    print(f"[HRT] Downloading LibreHardwareMonitor {_LHM_VERSION} (first-time setup)...")
    import zipfile, io, urllib.request
    try:
        resp = urllib.request.urlopen(_LHM_ZIP_URL, timeout=60)
        data = resp.read()
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            zf.extractall(dest)
        print(f"[HRT] LibreHardwareMonitor installed to {dest}")
        return exe.is_file()
    except Exception as e:
        print(f"[HRT] Failed to download LHM: {e}")
        return False


def launch_lhm() -> bool:
    """Start LibreHardwareMonitor headless if not already running. Returns True if running."""
    global _lhm_process
    # Check if already running
    for p in psutil.process_iter(["name"]):
        try:
            if (p.info.get("name") or "").lower() == "librehardwaremonitor.exe":
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    exe = _find_lhm_exe()
    if not exe:
        # First-time setup — try downloading
        if _download_lhm():
            exe = _find_lhm_exe()
        if not exe:
            print("[HRT] LHM not found and auto-download failed — CPU temps unavailable")
            return False
    try:
        import ctypes
        # LHM requires admin privileges to read CPU temperature hardware.
        # Use ShellExecuteW with 'runas' to launch it elevated + hidden.
        SW_HIDE = 0
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, None, str(Path(exe).parent), SW_HIDE
        )
        if ret <= 32:
            print(f"[HRT] ShellExecute returned {ret} — LHM elevation may have been declined")
            return False
        # Give LHM time to start and register its WMI namespace
        for _wait in range(12):
            time.sleep(1)
            for p in psutil.process_iter(["name"]):
                try:
                    if (p.info.get("name") or "").lower() == "librehardwaremonitor.exe":
                        print("[HRT] LibreHardwareMonitor started (elevated)")
                        time.sleep(2)  # extra settle time for WMI registration
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        print("[HRT] LHM process not detected after launch — CPU temps may be unavailable")
        return False
    except Exception as e:
        print(f"[HRT] Failed to start LHM: {e}")
        return False


def stop_lhm():
    """Terminate LHM if we started it."""
    for p in psutil.process_iter(["name"]):
        try:
            if (p.info.get("name") or "").lower() == "librehardwaremonitor.exe":
                p.terminate()
                p.wait(timeout=5)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
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
        self._paused = False
        self._pause_event = threading.Event()   # clear = paused, set = running
        self._pause_event.set()
        self._thread: Optional[threading.Thread] = None
        # WMI connection is created lazily in the poll thread
        # (COM objects are thread-bound on Windows)
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
        self._pause_event.set()  # unblock if paused so thread can exit

    def pause(self):
        """Pause sensor polling. Non-blocking — poll loop will stop at next iteration."""
        self._pause_event.clear()
        self._paused = True

    def resume(self):
        """Resume sensor polling."""
        self._paused = False
        self._pause_event.set()

    def snapshot(self) -> Optional[HardwareSnapshot]:
        with self._lock:
            return self._latest

    # ── internal ────────────────────────────────────────────────

    def _poll_loop(self):
        # Initialize COM in this thread — required for WMI on Windows
        _com_init = False
        if _WMI_AVAILABLE:
            try:
                import pythoncom
                pythoncom.CoInitialize()
                _com_init = True
            except Exception:
                pass
        try:
            while self._running:
                # Wait here if paused (blocks until resume or stop)
                self._pause_event.wait()
                if not self._running:
                    break
                # Lazy-retry WMI connection until we get real data
                if _WMI_AVAILABLE and not self._wmi_conn:
                    self._try_connect_wmi()
                snap = self._read_all()
                # If WMI connected but returned zero temp sensors, LHM
                # may not be ready yet — reset so we retry next cycle
                if self._wmi_conn and not any(
                    s.category == "temperature" and s.name.startswith("cpu_core_")
                    for s in snap.sensors
                ):
                    self._wmi_conn = None
                with self._lock:
                    self._latest = snap
                time.sleep(self.interval)
        finally:
            if _com_init:
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    def _try_connect_wmi(self):
        try:
            self._wmi_conn = wmi.WMI(namespace="root\\LibreHardwareMonitor")
        except Exception:
            try:
                self._wmi_conn = wmi.WMI(namespace="root\\OpenHardwareMonitor")
            except Exception:
                pass

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
        # Always query WMI if available — it provides CPU temps that psutil/nvidia-smi cannot
        if self._wmi_conn:
            self._read_wmi_sensors(snap)

        # ── Duplicate physical-core temps to hyperthreaded siblings ──
        # psutil reports N logical cores but LHM only has temps for
        # N/2 physical cores.  Map logical core K (K >= phys_count)
        # to the same temp as core K - phys_count.
        logical_count = psutil.cpu_count(logical=True) or 0
        physical_count = psutil.cpu_count(logical=False) or logical_count
        if physical_count and logical_count > physical_count:
            existing_temps = {
                s.name: s for s in snap.sensors
                if s.name.startswith("cpu_core_") and s.name.endswith("_temp")
            }
            for li in range(physical_count, logical_count):
                ht_name = f"cpu_core_{li}_temp"
                if ht_name not in existing_temps:
                    phys_idx = li - physical_count
                    src = existing_temps.get(f"cpu_core_{phys_idx}_temp")
                    if src:
                        snap.sensors.append(SensorReading(
                            name=ht_name,
                            label=f"CPU Core {li}",
                            value=src.value,
                            unit="°C",
                            category="temperature",
                        ))

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

        # ── Dedup by sensor name (keep first occurrence) ──
        # Handles: cpu_total_temp from both "CPU Package" and "Core Average",
        # and any WMI GPU sensors overlapping with nvidia-smi readings.
        seen: set = set()
        deduped: List[SensorReading] = []
        for s in snap.sensors:
            if s.name not in seen:
                seen.add(s.name)
                deduped.append(s)
        snap.sensors = deduped

        return snap

    def _read_wmi_sensors(self, snap: HardwareSnapshot):
        """Read sensors from OpenHardwareMonitor / LibreHardwareMonitor via WMI.

        Only emits sensors relevant to the HRT dashboard:
        - CPU core temperatures  → cpu_core_N_temp
        - CPU package/total temp → cpu_total_temp
        - GPU core temperature   → gpu_N_temp
        - GPU core load          → gpu_N_usage
        Other WMI sensors (HDD, NIC, voltage, power, clocks) are skipped
        to keep the compact 200×400 UI uncluttered.
        """
        if not self._wmi_conn:
            return

        _gpu_index_cache: Dict[str, int] = {}  # parent string → GPU index
        _next_gpu = [0]

        def _gpu_index(parent_raw: str) -> int:
            """Assign a stable integer index per unique GPU parent path."""
            key = parent_raw.lower()
            if key not in _gpu_index_cache:
                _gpu_index_cache[key] = _next_gpu[0]
                _next_gpu[0] += 1
            return _gpu_index_cache[key]

        logged_once = getattr(self, '_wmi_logged', False)

        try:
            for sensor in self._wmi_conn.Sensor():
                s_type = sensor.SensorType.lower() if sensor.SensorType else ""
                value = sensor.Value
                if value is None:
                    continue
                name_raw = (sensor.Name or "unknown").replace(" ", "_").lower()
                parent = (sensor.Parent or "").replace("/", "_").strip("_")
                parent_orig = sensor.Parent or ""  # e.g. "/gpu-nvidia/0"
                is_gpu = 'gpu' in parent.lower()
                is_cpu = 'cpu' in parent.lower()

                if not logged_once:
                    print(f"[HRT-WMI] {s_type:12s} | {parent:30s} | {sensor.Name:30s} | {value}")

                # ── Temperature sensors ──────────────────────────────
                if s_type == "temperature":
                    # Skip inverse/margin readings
                    if 'distance' in name_raw or 'tjmax' in name_raw:
                        continue

                    if is_cpu:
                        # CPU core temps → cpu_core_N_temp
                        # LHM names: "Core #1", "CPU Core #1", etc.
                        m = re.search(r'(?:cpu_)?core_#?(\d+)', name_raw)
                        if m:
                            idx = int(m.group(1)) - 1
                            snap.sensors.append(SensorReading(
                                name=f"cpu_core_{idx}_temp",
                                label=f"CPU Core {idx}",
                                value=float(value),
                                unit="°C",
                                category="temperature",
                            ))
                        elif 'package' in name_raw or 'core_average' in name_raw:
                            snap.sensors.append(SensorReading(
                                name="cpu_total_temp",
                                label="CPU Package",
                                value=float(value),
                                unit="°C",
                                category="temperature",
                            ))
                        # Skip core_max or other CPU temp aggregates
                        continue

                    if is_gpu:
                        # GPU core temp → gpu_N_temp
                        gi = _gpu_index(parent_orig)
                        snap.sensors.append(SensorReading(
                            name=f"gpu_{gi}_temp",
                            label=f"GPU {gi}",
                            value=float(value),
                            unit="°C",
                            category="temperature",
                        ))
                        continue

                    # Skip non-CPU, non-GPU temps (e.g. HDD, chipset)

                # ── Load sensors ─────────────────────────────────────
                elif s_type == "load":
                    if is_gpu and ('gpu_core' in name_raw or name_raw == 'core'):
                        # GPU core utilisation → gpu_N_usage
                        gi = _gpu_index(parent_orig)
                        snap.sensors.append(SensorReading(
                            name=f"gpu_{gi}_usage",
                            label=f"GPU {gi} Load",
                            value=float(value),
                            unit="%",
                            category="usage",
                        ))
                    # Skip all other WMI load sensors (CPU load already
                    # comes from psutil; HDD/NIC/memory load is noise)

                # Skip fan, clock, voltage, power — not needed in dashboard

        except Exception:
            self._wmi_conn = None  # Reset so we retry next poll

        if not logged_once:
            self._wmi_logged = True
            # Count how many cpu temps we got from this pass
            cpu_temps_found = sum(
                1 for s in snap.sensors
                if s.name.startswith("cpu_core_") and s.name.endswith("_temp")
            )
            print(f"[HRT-WMI] Sensor discovery complete — {cpu_temps_found} CPU core temps found")
            if cpu_temps_found == 0:
                print("[HRT-WMI] No CPU temps yet — will keep retrying WMI")
                self._wmi_conn = None  # force reconnect next cycle
                self._wmi_logged = False  # re-log on next successful attempt

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
