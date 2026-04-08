#!/usr/bin/env python3
"""
HRT telemetry pipe stub (Seed A1-03).

Opens the Windows named pipe \\.\pipe\hrt_telemetry (write end) and exposes
emit_event() for fire-and-forget JSON telemetry emission.

If the pipe is not connected, all errors are silently logged — HRT never
crashes due to telemetry unavailability.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Windows named pipe path for HRT telemetry
_PIPE_PATH: str = r"\\.\pipe\hrt_telemetry"

# Thread-local pipe handle (opened lazily per thread)
_pipe_lock = threading.Lock()
_pipe_handle = None


def _open_pipe():
    """Attempt to open the named pipe. Returns file object or None."""
    global _pipe_handle
    try:
        # Open in write-binary mode; on Windows this connects to the pipe server
        fh = open(_PIPE_PATH, "wb", buffering=0)  # noqa: WPS515
        logger.debug("hrt_telemetry pipe connected")
        return fh
    except OSError as exc:
        logger.warning("hrt_telemetry pipe not available: %s", exc)
        return None


def emit_event(event_type: str, payload: Dict[str, Any]) -> None:
    """
    Emit a telemetry event to \\.\pipe\hrt_telemetry.

    Serializes to JSON + newline. Fails silently if the pipe is not connected.

    Args:
        event_type: Short event name, e.g. "telemetry_ingested".
        payload:    Arbitrary JSON-serialisable dict.
    """
    global _pipe_handle

    envelope = {
        "event": event_type,
        "ts": datetime.now(timezone.utc).isoformat(),
        **payload,
    }

    try:
        line = json.dumps(envelope, separators=(",", ":")) + "\n"
        data = line.encode("utf-8")
    except (TypeError, ValueError) as exc:
        logger.warning("hrt_telemetry: failed to serialize event %s: %s", event_type, exc)
        return

    with _pipe_lock:
        # Lazy open
        if _pipe_handle is None:
            _pipe_handle = _open_pipe()

        if _pipe_handle is None:
            return  # pipe not available — fail silently

        try:
            _pipe_handle.write(data)
        except OSError as exc:
            logger.warning("hrt_telemetry: pipe write failed (%s), will retry next call", exc)
            try:
                _pipe_handle.close()
            except OSError:
                pass
            _pipe_handle = None
