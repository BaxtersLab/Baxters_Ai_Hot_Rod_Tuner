from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import asyncio
import psutil
import json
import time
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel
import os as _os

from .metrics import MetricsStore
from .policies import DecisionEngine, PolicyConfig
from .scheduler import TokenBucketScheduler
from .sound import sound_manager
from .sensors import sensor_poller, launch_lhm, stop_lhm
from .fan_manager import FanManager, reset_fan_backend

app = FastAPI(title="Baxters Hot Rod Tuner")

# ── Crash-resilient file logging ─────────────────────────────────────
import logging as _logging
_CRASH_LOG = Path('data') / 'hrt_server.log'
_CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
_file_handler = _logging.FileHandler(str(_CRASH_LOG), mode='a', encoding='utf-8')
_file_handler.setFormatter(_logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
_hrt_log = _logging.getLogger('hrt')
_hrt_log.setLevel(_logging.DEBUG)
_hrt_log.addHandler(_file_handler)
_hrt_log.info('=== HRT server module loaded ===')

# ── Prevent Windows console events from killing the process ──────────
import platform as _platform
if _platform.system() == 'Windows':
    try:
        import ctypes as _ct
        _HANDLER_TYPE = _ct.WINFUNCTYPE(_ct.c_int, _ct.c_uint)
        @_HANDLER_TYPE
        def _console_handler(event):
            _hrt_log.warning(f'Console control event received: {event}')
            return 1  # Block default handling (which calls ExitProcess)
        _ct.windll.kernel32.SetConsoleCtrlHandler(_console_handler, 1)
        _hrt_log.info('Console ctrl handler installed')
    except Exception as _e:
        _hrt_log.error(f'Failed to install console ctrl handler: {_e}')

# Record server start time for uptime calculation (Seed A1-02)
_SERVER_START_TIME: float = time.monotonic()

# ── Heartbeat watchdog ───────────────────────────────────────────────
# JS pings /api/heartbeat every 3 s while the window is open.
# If no ping arrives for _HB_TIMEOUT seconds the server assumes the
# window is gone and hard-exits, leaving no zombie process behind.
_HB_TIMEOUT: float = 15.0  # seconds before giving up
_last_heartbeat: float = 0.0  # 0 = no ping yet (grace period active)

def _heartbeat_watchdog() -> None:
    """Background thread: exits the process when the UI window disappears."""
    # Grace period: give the browser time to load the page and start pinging.
    time.sleep(_HB_TIMEOUT + 5)
    while True:
        time.sleep(3)
        if _last_heartbeat == 0.0:
            continue  # still in startup, no ping received yet
        age = time.monotonic() - _last_heartbeat
        if age > _HB_TIMEOUT:
            _hrt_log.warning(
                f'Heartbeat timeout ({age:.1f}s) — UI window closed. Exiting.'
            )
            _os._exit(0)

# Global instances
metrics_store = MetricsStore()
policy_config = PolicyConfig()
decision_engine = DecisionEngine(policy_config)
scheduler = TokenBucketScheduler()
fan_manager = FanManager()

# Linked external apps: list of {app_name, exe_path, pid}
_linked_apps: list = []
_LINKED_FILE = Path('data') / 'linked_apps.json'

def _save_linked():
    """Persist linked apps list to disk."""
    try:
        _LINKED_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LINKED_FILE.write_text(json.dumps(_linked_apps, indent=2), encoding='utf-8')
    except Exception as e:
        print(f'[HRT] WARNING: could not save linked apps: {e}')

def _load_linked():
    """Load linked apps from disk and reconnect to live processes by exe name."""
    try:
        if _LINKED_FILE.is_file():
            data = json.loads(_LINKED_FILE.read_text(encoding='utf-8'))
            if isinstance(data, list):
                reconnected = []
                for entry in data:
                    exe_path = entry.get('exe_path', '')
                    exe_name = exe_path.strip().rsplit('\\', 1)[-1].rsplit('/', 1)[-1].lower()
                    if not exe_name:
                        continue
                    # Search for a running process matching this exe name
                    found_pid = None
                    for proc in psutil.process_iter(['pid', 'name', 'exe']):
                        try:
                            pname = (proc.info.get('name') or '').lower()
                            if pname == exe_name:
                                found_pid = proc.info['pid']
                                break
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                    if found_pid:
                        entry['pid'] = found_pid
                        reconnected.append(entry)
                        print(f'[HRT] Reconnected to {entry.get("app_name","?")} (pid={found_pid})')
                    else:
                        print(f'[HRT] {entry.get("app_name","?")} not running — skipped')
                _linked_apps[:] = reconnected
                _save_linked()
                print(f'[HRT] Linked apps: {len(reconnected)} connected, {len(data) - len(reconnected)} not running')
    except Exception as e:
        print(f'[HRT] WARNING: could not load linked apps: {e}')

# Play startup sound on app initialization
sound_manager.play_startup_sound(blocking=False)

# ── Static files + GUI root ──────────────────────────────────────────
import sys as _sys
if getattr(_sys, 'frozen', False):
    _BASE_DIR = Path(_sys._MEIPASS)
else:
    _BASE_DIR = Path(__file__).resolve().parent.parent.parent
_STATIC_DIR = _BASE_DIR / "static"
_ASSETS_DIR = _BASE_DIR / "assets"
if _ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR)), name="assets")
if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.on_event("startup")
def _on_startup():
    _hrt_log.info('FastAPI startup event fired')
    # Silently add Defender exclusion for vendor/lhm so kernel driver .sys files
    # are not quarantined. App already runs elevated (uac_admin=True), so this
    # succeeds without prompting. Safe no-op on non-Windows or non-Defender systems.
    try:
        import sys as _sys
        _vendor_lhm = (
            _os.path.join(_os.path.dirname(_sys.executable), 'vendor', 'lhm')
            if getattr(_sys, 'frozen', False)
            else _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                               '..', '..', '..', 'vendor', 'lhm')
        )
        _vendor_lhm = _os.path.normpath(_vendor_lhm)
        import subprocess as _sp
        _sp.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
             '-Command', f'Add-MpPreference -ExclusionPath "{_vendor_lhm}" -ErrorAction SilentlyContinue'],
            capture_output=True, timeout=10
        )
        _hrt_log.info('Defender exclusion applied for %s', _vendor_lhm)
    except Exception as _e:
        _hrt_log.debug('Defender exclusion skipped: %s', _e)
    # By default HRT will attempt to reconnect to previously linked apps.
    # Set environment variable `HRT_DISABLE_LINKS=1` to skip reconnect (useful
    # when you don't want external chat apps to reappear).
    try:
        disable_links = str(_os.getenv('HRT_DISABLE_LINKS', '')).lower() in ('1', 'true', 'yes')
    except Exception:
        disable_links = False
    if not disable_links:
        _load_linked()
    else:
        _hrt_log.info('Linked-app reconnection disabled via HRT_DISABLE_LINKS')
    launch_lhm()
    sensor_poller.start()
    # Start heartbeat watchdog (daemon — killed automatically if main exits)
    threading.Thread(
        target=_heartbeat_watchdog,
        name='hrt-heartbeat-watchdog',
        daemon=True,
    ).start()
    try:
        fan_manager.start()
        # Auto-raise fans when CPU temps climb — never overrides a higher user setting
        def _fan_policy_hook():
            snap = sensor_poller.snapshot()
            return decision_engine.recommend_fan_aggressiveness(snap) if snap else 0
        fan_manager.set_policy_hook(_fan_policy_hook)
        # Eagerly probe backend so fan icon shows immediately on load
        threading.Thread(
            target=lambda: __import__('hotrod_tuner.fan_manager', fromlist=['_detect_backend'])._detect_backend(),
            name='hrt-fan-backend-probe',
            daemon=True,
        ).start()
    except Exception as _e:
        _hrt_log.error(f'fan_manager.start() failed: {_e}')
    _hrt_log.info('Startup complete: LHM launched, poller started')

@app.on_event("shutdown")
def _on_shutdown():
    """Single shutdown handler — log the event then stop hardware polling."""
    import traceback
    _hrt_log.warning('FastAPI shutdown event fired — server is stopping')
    _hrt_log.warning(''.join(traceback.format_stack()))
    try:
        sensor_poller.stop()
    except Exception as _e:
        _hrt_log.error(f'sensor_poller.stop() failed: {_e}')
    try:
        stop_lhm()
    except Exception as _e:
        _hrt_log.error(f'stop_lhm() failed: {_e}')
    try:
        fan_manager.stop()
    except Exception as _e:
        _hrt_log.error(f'fan_manager.stop() failed: {_e}')


@app.get("/", include_in_schema=False)
def serve_gui():
    """Serve the Hot Rod Tuner dashboard."""
    index = _STATIC_DIR / "index.html"
    if index.is_file():
        return FileResponse(str(index))
    return {"error": "GUI not found — place index.html in static/"}


# ── WebSocket: live sensor stream ────────────────────────────────────
@app.websocket("/ws/sensors")
async def ws_sensors(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            snap = sensor_poller.snapshot()
            if snap:
                await websocket.send_json(snap.to_dict())
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# ── API: current sensor snapshot (REST fallback) ─────────────────────
@app.get("/api/sensors")
def api_sensors():
    snap = sensor_poller.snapshot()
    if snap:
        return snap.to_dict()
    return {"timestamp": 0, "sensors": []}


class FanOptimizePayload(BaseModel):
    aggressiveness: int


@app.get('/api/fans')
def api_fans():
    """Return current fan manager state: aggressiveness, baselines, last targets."""
    try:
        return fan_manager.get_state()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/fans/backend')
def api_fans_backend():
    """Return which fan control backend is active on this machine."""
    import hotrod_tuner.fan_manager as _fm
    backend = _fm._BACKEND  # None = not yet detected
    return {'backend': backend or 'unknown', 'detected': backend is not None}


@app.post('/api/fans/backend/reset')
def api_fans_backend_reset():
    """Force re-detection of the fan control backend (e.g. after enabling Dell driver)."""
    reset_fan_backend()
    return {'ok': True, 'message': 'Backend reset — will re-detect on next fan apply'}


@app.post('/api/fans/optimize')
def api_fans_optimize(payload: FanOptimizePayload):
    """Set requested fan aggressiveness (0-100). Server enforces never-below-baseline."""
    try:
        state = fan_manager.set_aggressiveness(payload.aggressiveness)
        # Emit audit event
        audit_event = {
            'type': 'fan_optimize_set',
            'timestamp': now_utc_iso(),
            'aggressiveness': state.get('aggressiveness'),
            'enable_write': state.get('enable_write'),
            'capability': 'fan.optimize'
        }
        write_audit_event(Path('audit') / 'fan_manager.jsonl', audit_event)
        return state
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── API: which monitored processes are running ───────────────────────
@app.get("/api/processes")
def api_processes():
    """Return list of currently-running executable paths (lowercase)."""
    running = set()
    for p in psutil.process_iter(["exe"]):
        try:
            exe = p.info.get("exe")
            if exe:
                running.add(exe.lower())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return {"running": list(running)}


class TelemetryPayload(BaseModel):
    host: str
    timestamp: str
    sensors: Dict[str, Any]


class JobDescriptor(BaseModel):
    job_id: Optional[str] = None
    priority: str = "normal"
    resource_intensity: str = "medium"
    description: Optional[str] = None
    estimated_duration_minutes: Optional[int] = None


class KillPayload(BaseModel):
    path: str
    dry_run: bool = True
    actor: str = "unknown"
    scope: str = "default"
    operation_id: Optional[str] = None


class LinkPayload(BaseModel):
    app_name: str
    exe_path: str
    pid: int


@app.get("/health")
def health():
    """Health check endpoint. Returns 200 with status and uptime_secs (Seed A1-02)."""
    uptime = time.monotonic() - _SERVER_START_TIME
    return {"status": "ok", "uptime_secs": round(uptime, 3)}


@app.post("/api/heartbeat", include_in_schema=False)
def heartbeat():
    """UI liveness ping — resets the watchdog timer."""
    global _last_heartbeat
    _last_heartbeat = time.monotonic()
    return {"ok": True}


@app.get("/status")
def status():
    """Get current governor status."""
    governor_status = decision_engine.get_status()
    scheduler_status = scheduler.get_scheduler_status()
    current_metrics = {}

    # Get current metrics for all hosts
    for host in metrics_store.get_all_hosts():
        current = metrics_store.get_current_status(host)
        if current:
            current_metrics[host] = current

    return {
        "ok": True,
        "status": "active",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "governor": governor_status,
        "scheduler": scheduler_status,
        "current_metrics": current_metrics
    }


@app.post("/telemetry")
def telemetry(payload: TelemetryPayload):
    """Ingest telemetry data."""
    try:
        timestamp = datetime.fromisoformat(payload.timestamp.replace('Z', '+00:00'))
        metrics_store.store_telemetry(payload.host, timestamp, payload.sensors)

        # Emit audit event for telemetry ingestion
        audit_event = {
            'type': 'telemetry_ingested',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'host': payload.host,
            'sensor_count': len(payload.sensors),
            'capability': 'governor.telemetry'
        }
        write_audit_event(Path('audit') / 'hotrod_audit.jsonl', audit_event)

        return {"ok": True, "received": True, "host": payload.host}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid telemetry payload: {str(e)}")


@app.post("/preflight")
def preflight(job: JobDescriptor):
    """Evaluate a job request against current policies."""
    # Get current telemetry for decision making
    current_telemetry = None
    for host in metrics_store.get_all_hosts():
        current_telemetry = metrics_store.get_current_status(host)
        if current_telemetry:
            break  # Use telemetry from first available host

    job_dict = job.dict()
    decision = decision_engine.evaluate_preflight(job_dict, current_telemetry)

    # Emit audit event
    audit_event = {
        'type': 'preflight_decision',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'job_id': job.job_id,
        'decision': decision['decision'],
        'reason': decision.get('reason', ''),
        'capability': 'governor.preflight'
    }
    write_audit_event(Path('audit') / 'hotrod_audit.jsonl', audit_event)

    return decision


@app.post("/schedule")
def schedule_job(job: JobDescriptor):
    """Submit a job to the scheduler."""
    job_id = scheduler.submit_job(job.dict())

    # Emit audit event
    audit_event = {
        'type': 'job_scheduled',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'job_id': job_id,
        'priority': job.priority,
        'resource_intensity': job.resource_intensity,
        'capability': 'scheduler.submit'
    }
    write_audit_event(Path('audit') / 'hotrod_audit.jsonl', audit_event)

    return {"ok": True, "job_id": job_id, "status": "queued"}


@app.post("/approve/{job_id}")
def approve_job(job_id: str):
    """Approve a scheduled job."""
    success = scheduler.approve_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found or not in queued state")

    # Emit audit event
    audit_event = {
        'type': 'job_approved',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'job_id': job_id,
        'capability': 'scheduler.approve'
    }
    write_audit_event(Path('audit') / 'hotrod_audit.jsonl', audit_event)

    return {"ok": True, "job_id": job_id, "status": "approved"}


@app.post("/start/{job_id}")
def start_job(job_id: str):
    """Start execution of an approved job."""
    success = scheduler.start_job(job_id)
    if not success:
        raise HTTPException(status_code=409, detail="Cannot start job - capacity or tokens unavailable")

    # Emit audit event
    audit_event = {
        'type': 'job_started',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'job_id': job_id,
        'capability': 'scheduler.start'
    }
    write_audit_event(Path('audit') / 'hotrod_audit.jsonl', audit_event)

    return {"ok": True, "job_id": job_id, "status": "running"}


@app.post("/complete/{job_id}")
def complete_job(job_id: str, result: Optional[Dict[str, Any]] = None):
    """Mark a job as completed."""
    scheduler.complete_job(job_id, result)
    decision_engine.job_completed(job_id)

    # Emit audit event
    audit_event = {
        'type': 'job_completed',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'job_id': job_id,
        'capability': 'scheduler.complete'
    }
    write_audit_event(Path('audit') / 'hotrod_audit.jsonl', audit_event)

    return {"ok": True, "job_id": job_id, "status": "completed"}


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    """Get status of a specific job."""
    job_status = scheduler.get_job_status(job_id)
    if not job_status:
        raise HTTPException(status_code=404, detail="Job not found")

    return job_status


@app.get("/metrics/{host}")
def get_host_metrics(host: str, minutes: int = 5):
    """Get recent metrics and aggregates for a host."""
    recent = metrics_store.get_recent_metrics(host, minutes)
    aggregates = metrics_store.get_aggregates(host, minutes)

    return {
        "host": host,
        "time_window_minutes": minutes,
        "data_points": len(recent),
        "aggregates": aggregates,
        "recent_metrics": recent[-10:]  # Last 10 points
    }


@app.post("/sound/play")
def play_sound():
    """Play the startup sound."""
    success = sound_manager.play_startup_sound(blocking=False)

    # Emit audit event
    audit_event = {
        'type': 'sound_played',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'success': success,
        'available_sounds': sound_manager.get_available_sounds(),
        'capability': 'sound.play'
    }
    write_audit_event(Path('audit') / 'hotrod_audit.jsonl', audit_event)

    return {"ok": success, "available_sounds": sound_manager.get_available_sounds()}


@app.get("/sound/available")
def get_available_sounds():
    """Get list of available sound files."""
    return {"sounds": sound_manager.get_available_sounds()}


@app.get("/api/sound-folder")
def get_sound_folder():
    """Return the path to the assets/sounds folder."""
    return {"path": str(_ASSETS_DIR)}


@app.post("/api/sound-folder/open")
def open_sound_folder():
    """Open the assets folder in the system file explorer.
    
    When running from the PyInstaller exe, _ASSETS_DIR points to the
    temp extraction folder.  Instead, open the *real* assets folder
    next to the exe (or next to the project root when running from source).
    """
    import subprocess, sys as _s
    if getattr(_s, 'frozen', False):
        # Frozen exe: assets sits next to the exe
        folder = str(Path(_s.executable).parent / "assets")
    else:
        folder = str(_ASSETS_DIR)
    # Create the folder if it doesn't exist yet so explorer doesn't error
    Path(folder).mkdir(parents=True, exist_ok=True)
    try:
        subprocess.Popen(["explorer", folder])
        return {"ok": True, "path": folder}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Link: external app registration ─────────────────────────────────────
@app.post('/link')
def link_app(payload: LinkPayload):
    """Register an external app so HRT can monitor and e-stop it."""
    # Remove any stale entry for the same app
    _linked_apps[:] = [a for a in _linked_apps if a['app_name'] != payload.app_name]
    entry = {
        'app_name': payload.app_name,
        'exe_path': payload.exe_path,
        'pid': payload.pid,
        'linked_at': now_utc_iso(),
    }
    _linked_apps.append(entry)
    _save_linked()
    return {"ok": True, "linked": entry}


@app.get('/link')
def get_linked_apps():
    """Return the list of currently linked external apps."""
    return {"linked_apps": _linked_apps}


@app.post('/api/shutdown')
def shutdown_server():
    """Shut down endpoint — disabled to prevent accidental kills from Edge events."""
    print('[HRT] /api/shutdown called but ignored (disabled)')
    return {"ok": False, "reason": "shutdown_disabled"}


@app.get('/api/protected')
def get_protected_list():
    """Return the list of protected process names that E-Stop will never kill."""
    return {"protected": sorted(_PROTECTED_NAMES)}


class EstopPayload(BaseModel):
    targets: list = []  # exe names or paths from process tray, e.g. ["aismartguy-app.exe", "ollama.exe"]


# Protected system processes that must NEVER be killed
_PROTECTED_NAMES = frozenset([
    "system", "system idle process", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe", "lsaiso.exe",
    "svchost.exe", "dwm.exe", "conhost.exe", "fontdrvhost.exe", "sihost.exe",
    "taskhostw.exe", "explorer.exe", "shellexperiencehost.exe", "startmenuexperiencehost.exe",
    "searchhost.exe", "runtimebroker.exe", "applicationframehost.exe",
    "ctfmon.exe", "dllhost.exe", "dashost.exe", "wudfhost.exe",
    "cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe", "wt.exe",
    "msedge.exe", "msedgewebview2.exe",
    "ntoskrnl.exe", "audiodg.exe", "spoolsv.exe",
    "securityhealthservice.exe", "msmpeng.exe", "nissrv.exe",
    "hot rod tuner.exe",
])


def _is_protected(name: str) -> bool:
    return name.lower() in _PROTECTED_NAMES


_estop_lock = __import__('threading').Lock()

@app.post('/api/estop')
def server_estop(payload: EstopPayload = EstopPayload()):
    """Server-side E-Stop: deterministic exe killer.

    Pauses sensor polling, kills targets, then resumes.
    Only one estop can run at a time (lock-guarded).
    """
    if not _estop_lock.acquire(blocking=False):
        return {"ok": False, "error": "estop_already_running"}

    try:
        # Pause sensor polling so WMI/LHM driver is idle during kills
        try:
            sensor_poller.pause()
        except Exception as pause_err:
            import traceback
            traceback.print_exc()

        results = []
        killed_pids = set()

        print(f'[HRT] E-STOP: linked_apps={len(_linked_apps)}, targets={payload.targets}')

        # 1. Kill all linked apps by PID
        for a in list(_linked_apps):
            pid = a.get('pid')
            if not pid:
                continue
            print(f'[HRT] E-STOP: killing linked app "{a.get("app_name", "?")}" pid={pid}')
            r = _safe_kill(pid)
            r["source"] = "linked"
            r["app"] = a.get("app_name", "?")
            results.append(r)
            print(f'[HRT] E-STOP:   result: {r}')
            if r.get("ok"):
                killed_pids.add(pid)

        # 2. Scan all running processes and kill by exe name match
        target_names = set()
        for t in payload.targets:
            name = t.strip().rsplit("\\", 1)[-1].rsplit("/", 1)[-1].lower()
            if name and not _is_protected(name):
                target_names.add(name)

        # Also add linked app exe names as fallback (handles stale PIDs)
        for a in list(_linked_apps):
            exe_path = a.get('exe_path', '')
            if exe_path:
                name = exe_path.strip().rsplit("\\", 1)[-1].rsplit("/", 1)[-1].lower()
                if name and not _is_protected(name):
                    target_names.add(name)

        print(f'[HRT] E-STOP: scanning for target_names={target_names}')

        if target_names:
            my_pid = __import__('os').getpid()
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    pname = (proc.info.get('name') or '').lower()
                    pid = proc.info.get('pid')
                    if pname in target_names and pid != my_pid and pid not in killed_pids:
                        print(f'[HRT] E-STOP: killing name-match "{pname}" pid={pid}')
                        r = _safe_kill(pid)
                        r["source"] = "name_match"
                        r["exe"] = pname
                        results.append(r)
                        print(f'[HRT] E-STOP:   result: {r}')
                        if r.get("ok"):
                            killed_pids.add(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        print(f'[HRT] E-STOP: done, killed_pids={killed_pids}')

        # Remove killed apps from linked list to prevent re-kill floods
        killed_names = set()
        if killed_pids:
            before = len(_linked_apps)
            for a in _linked_apps:
                if a.get('pid') in killed_pids:
                    ep = a.get('exe_path', '')
                    if ep:
                        killed_names.add(ep.strip().rsplit('\\', 1)[-1].rsplit('/', 1)[-1].lower())
            _linked_apps[:] = [a for a in _linked_apps if a.get('pid') not in killed_pids]
            _save_linked()
            print(f'[HRT] E-STOP: cleaned linked_apps {before} → {len(_linked_apps)}')
        # Also add any name-match kills
        for r in results:
            if r.get('ok') and r.get('source') == 'name_match' and r.get('exe'):
                killed_names.add(r['exe'].lower())

        audit_event = {
            'type': 'server_estop',
            'timestamp': now_utc_iso(),
            'targets': list(target_names),
            'linked_apps_count': len(_linked_apps),
            'results': results,
        }
        write_audit_event(Path('audit') / 'hotrod_audit.jsonl', audit_event)

        return {"ok": True, "killed_count": len(killed_pids), "results": results, "killed_names": sorted(killed_names)}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e)}
    finally:
        # Always resume polling and release lock
        try:
            sensor_poller.resume()
        except Exception:
            pass
        _estop_lock.release()


def _safe_kill(pid: int) -> dict:
    """Kill a single process by PID using psutil only (no taskkill subprocess).
    Tries graceful terminate first, then force-kills after 3 seconds.
    Refuses to kill HRT itself, HRT's parent, or any protected process."""
    import os as _os
    # ── EARLY BAIL: if PID doesn't exist, return immediately ──
    # This prevents ANY psutil system calls on dead/reused PIDs.
    # Critical for avoiding BSODs when LHM kernel driver is loaded.
    if not psutil.pid_exists(pid):
        print(f'[HRT] _safe_kill({pid}): already dead, bailing')
        return {"pid": pid, "ok": True, "method": "already_dead", "children_killed": 0}
    my_pid = _os.getpid()
    if pid == my_pid:
        return {"pid": pid, "ok": False, "error": "refused_self"}
    # Guard: never kill our parent process
    try:
        my_parent = psutil.Process(my_pid).ppid()
        if pid == my_parent:
            return {"pid": pid, "ok": False, "error": "refused_parent"}
    except Exception:
        pass
    try:
        proc = psutil.Process(pid)
        pname = (proc.name() or '').lower()
        if _is_protected(pname):
            return {"pid": pid, "ok": False, "error": f"protected:{pname}"}
    except psutil.NoSuchProcess:
        return {"pid": pid, "ok": True, "method": "already_dead", "children_killed": 0}
    except psutil.AccessDenied:
        pass  # still try

    # Collect child processes BEFORE killing the main PID
    # (Tauri/Electron apps spawn children that survive parent death)
    children = []
    try:
        proc = psutil.Process(pid)
        children = proc.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    # Kill non-protected children first
    children_killed = 0
    terminated_children = []
    for child in children:
        try:
            cname = (child.name() or '').lower()
            if _is_protected(cname):
                continue
            child.terminate()
            terminated_children.append(child)
            children_killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    # Give terminated children a moment to exit, then force-kill stragglers
    if terminated_children:
        try:
            _, alive = psutil.wait_procs(terminated_children, timeout=2)
            for c in alive:
                try:
                    c.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass

    # Graceful terminate main process, then force kill if needed
    try:
        proc = psutil.Process(pid)
        proc.terminate()  # sends WM_CLOSE / SIGTERM
        try:
            proc.wait(timeout=3)
            return {"pid": pid, "ok": True, "method": "terminate", "children_killed": children_killed}
        except psutil.TimeoutExpired:
            proc.kill()  # force kill
            proc.wait(timeout=3)
            return {"pid": pid, "ok": True, "method": "kill", "children_killed": children_killed}
    except psutil.NoSuchProcess:
        return {"pid": pid, "ok": True, "method": "already_dead", "children_killed": children_killed}
    except psutil.AccessDenied:
        return {"pid": pid, "ok": False, "error": "access_denied", "children_killed": children_killed}
    except Exception as e:
        return {"pid": pid, "ok": False, "error": str(e), "children_killed": children_killed}


@app.post('/kill')
@app.post('/api/kill')
def kill_process(payload: KillPayload):
    """Kill processes matching a binary path. Payload: {path, dry_run=true, actor, scope, operation_id}

    This endpoint writes a minimal audit event to `audit/hotrod_audit.jsonl` in the repo root.
    """
    result = _kill_by_path(payload.path, dry_run=payload.dry_run)

    # emit simple audit event
    audit_event = {
        'type': 'governor_kill_executed' if result.get('ok') else 'governor_kill_failed',
        'timestamp': now_utc_iso(),
        'actor': payload.actor,
        'operation_id': payload.operation_id or f"hotrod-{datetime.now(timezone.utc).timestamp()}",
        'scope': payload.scope,
        'capability': 'governor.kill',
        'details': {'payload': {'path': payload.path, 'dry_run': payload.dry_run}, 'result': result},
    }
    write_audit_event(Path('audit') / 'hotrod_audit.jsonl', audit_event)

    return result


class KillPidPayload(BaseModel):
    pid: int
    actor: str = "unknown"
    scope: str = "default"


@app.post('/api/kill-pid')
def kill_by_pid(payload: KillPidPayload):
    """Kill a process by PID directly (used for linked-app e-stop)."""
    result = {"ok": False, "error": "unknown"}
    try:
        proc = psutil.Process(payload.pid)
        proc_name = proc.name()
    except psutil.NoSuchProcess:
        result = {"ok": False, "error": "no_such_process"}
        _audit_kill_pid(payload, result)
        return result
    except psutil.AccessDenied:
        proc_name = "unknown"

    try:
        proc = psutil.Process(payload.pid)
        proc.terminate()
        try:
            proc.wait(timeout=3)
            result = {"ok": True, "killed": [payload.pid], "method": "terminate"}
        except psutil.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
            result = {"ok": True, "killed": [payload.pid], "method": "kill"}
    except psutil.NoSuchProcess:
        result = {"ok": True, "killed": [payload.pid], "method": "already_dead"}
    except Exception as e:
        result = {"ok": False, "error": str(e)}

    _audit_kill_pid(payload, result)
    return result


def _audit_kill_pid(payload, result):
    audit_event = {
        'type': 'governor_kill_pid',
        'timestamp': now_utc_iso(),
        'actor': payload.actor,
        'scope': payload.scope,
        'pid': payload.pid,
        'result': result,
    }
    write_audit_event(Path('audit') / 'hotrod_audit.jsonl', audit_event)


def now_utc_iso():
    return datetime.now(timezone.utc).isoformat()


def write_audit_event(log_path: Path, event: dict):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _kill_by_path(path: str, dry_run: bool = True):
    target = str(Path(path).resolve()).lower()
    matches = []
    for p in psutil.process_iter(['pid', 'exe']):
        try:
            exe = p.info.get('exe') or ''
            if exe and str(Path(exe).resolve()).lower() == target:
                matches.append(p.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if not matches:
        return {"ok": False, "error": "no_matching_process"}
    if dry_run:
        return {"ok": True, "matches": matches, "dry_run": True}
    killed = []
    for pid in matches:
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
            killed.append(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if killed:
        return {"ok": True, "killed": killed}
    return {"ok": False, "error": "all_kill_attempts_failed"}
