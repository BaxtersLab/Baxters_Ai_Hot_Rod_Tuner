from fastapi import FastAPI, HTTPException
from pathlib import Path
import psutil
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel

from .metrics import MetricsStore
from .policies import DecisionEngine, PolicyConfig
from .scheduler import TokenBucketScheduler
from .sound import sound_manager

app = FastAPI(title="Baxters Hot Rod Tuner")

# Global instances
metrics_store = MetricsStore()
policy_config = PolicyConfig()
decision_engine = DecisionEngine(policy_config)
scheduler = TokenBucketScheduler()

# Play startup sound on app initialization
sound_manager.play_startup_sound(blocking=False)


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


@app.post('/kill')
def kill(payload: KillPayload):
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


def now_utc_iso():
    return datetime.now(timezone.utc).isoformat()


def write_audit_event(log_path: Path, event: dict):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _kill_by_path(path: str, dry_run: bool = True):
    target = Path(path).resolve()
    matches = []
    for p in psutil.process_iter(['pid', 'exe']):
        try:
            exe = p.info.get('exe') or ''
            if exe and Path(exe).resolve() == target:
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
            proc.wait(timeout=5)
            killed.append(pid)
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": True, "killed": killed}


@app.post('/kill')
def kill(payload: dict):
    """Kill processes matching a binary path. Payload: {path, dry_run=true, actor, scope, operation_id}

    This endpoint writes a minimal audit event to `audit/hotrod_audit.jsonl` in the repo root.
    """
    path = payload.get('path')
    dry_run = bool(payload.get('dry_run', True))
    actor = payload.get('actor', 'unknown')
    scope = payload.get('scope', 'default')
    operation_id = payload.get('operation_id') or f"hotrod-{datetime.now(timezone.utc).timestamp()}"

    result = _kill_by_path(path, dry_run=dry_run)

    # emit simple audit event
    audit_event = {
        'type': 'governor_kill_executed' if result.get('ok') else 'governor_kill_failed',
        'timestamp': now_utc_iso(),
        'actor': actor,
        'operation_id': operation_id,
        'scope': scope,
        'capability': 'governor.kill',
        'details': {'payload': {'path': path, 'dry_run': dry_run}, 'result': result},
    }
    write_audit_event(Path('audit') / 'hotrod_audit.jsonl', audit_event)

    return result
