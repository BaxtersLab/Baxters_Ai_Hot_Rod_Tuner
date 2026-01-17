from fastapi import FastAPI
from pathlib import Path
import psutil
import json
from datetime import datetime, timezone
from typing import Optional

app = FastAPI(title="Baxters Hot Rod Tuner")

@app.get("/status")
def status():
    return {"ok": True, "status": "idle"}

@app.post("/telemetry")
def telemetry(payload: dict):
    # placeholder: validate/store telemetry
    return {"ok": True, "received": True}

@app.post("/preflight")
def preflight(job: dict):
    # placeholder decision logic
    return {"ok": True, "decision": "defer"}


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
