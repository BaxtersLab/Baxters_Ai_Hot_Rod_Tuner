"""Where Hot Rod Tuner is allowed to write.

The installed package lives at /opt/baxters/hot-rod-tuner and is ROOT-OWNED and
read-only to the user running the app. `run.sh` cd's there before starting, so
every relative path in this project resolved *into the install tree*:
`Path('data')` and `Path('audit')` were created at import time and the app died
with PermissionError before serving a single request.

Found by a clean-VM install on 2026-09-25 (A10). The same defect was fixed in
SOC Ultralight and Baxters Audio Suite the same week; this module is the Hot Rod
Tuner copy of that rule: the payload is read-only, state goes under XDG.
"""
from __future__ import annotations

import os
from pathlib import Path


def state_dir() -> Path:
    """Base directory for everything this app writes.

    HOTROD_STATE_DIR wins, so tests and the harness can redirect writes without
    touching the user's real state. Otherwise XDG_DATA_HOME, else the spec
    default of ~/.local/share.
    """
    override = os.environ.get("HOTROD_STATE_DIR")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_DATA_HOME")
    root = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return root / "hot-rod-tuner"


def data_dir() -> Path:
    return state_dir() / "data"


def audit_dir() -> Path:
    return state_dir() / "audit"


def sounds_dir() -> Path:
    """Where the user drops a .wav to replace the startup chime.

    The bundled assets folder is root-owned once installed, so the Sound Folder
    button opens this one, and SoundManager reads it before the bundled chime.
    """
    return state_dir() / "sounds"
