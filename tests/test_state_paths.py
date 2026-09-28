"""The installed payload is read-only; nothing may be written beside it.

Regression test for the 2026-09-25 clean-VM finding: run.sh cd's into
/opt/baxters/hot-rod-tuner, which is root-owned, and the app resolved
Path('data') and Path('audit') relative to that CWD. Import raised
PermissionError and the app never started, from the .desktop or otherwise.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
ROOT = Path(__file__).resolve().parents[1]


def test_state_dir_honours_explicit_override(tmp_path, monkeypatch):
    monkeypatch.setenv("HOTROD_STATE_DIR", str(tmp_path / "boxed"))
    sys.path.insert(0, str(SRC))
    from hotrod_tuner import paths
    assert paths.state_dir() == tmp_path / "boxed"
    assert paths.data_dir() == tmp_path / "boxed" / "data"
    assert paths.audit_dir() == tmp_path / "boxed" / "audit"


def test_state_dir_falls_back_to_xdg(tmp_path, monkeypatch):
    monkeypatch.delenv("HOTROD_STATE_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    sys.path.insert(0, str(SRC))
    from hotrod_tuner import paths
    assert paths.state_dir() == tmp_path / "xdg" / "hot-rod-tuner"


def test_no_write_paths_resolve_into_the_cwd(tmp_path, monkeypatch):
    """The real defect: a relative path follows the CWD into the install tree."""
    monkeypatch.setenv("HOTROD_STATE_DIR", str(tmp_path / "state"))
    sys.path.insert(0, str(SRC))
    from hotrod_tuner import paths
    monkeypatch.chdir(tmp_path / "elsewhere" if (tmp_path / "elsewhere").mkdir() or True else tmp_path)
    for p in (paths.data_dir(), paths.audit_dir()):
        assert p.is_absolute(), f"{p} is relative and would follow the CWD"
        assert Path.cwd() not in p.parents, f"{p} resolves inside the CWD"


def test_app_module_declares_no_relative_state_paths():
    """Guard the whole module, not just the two paths that were found."""
    src = (SRC / "hotrod_tuner" / "app.py").read_text(encoding="utf-8")
    for bad in ("Path('data')", 'Path("data")', "Path('audit')", 'Path("audit")'):
        assert bad not in src, f"app.py still builds a relative state path: {bad}"


def test_run_server_is_shipped_by_the_packager():
    """run.sh's default branch execs this file; it was not in the payload."""
    run_sh = (ROOT / "run.sh").read_text(encoding="utf-8")
    execs = [w for w in run_sh.split() if w.endswith(".py")]
    for target in set(execs):
        assert (ROOT / target).is_file(), f"run.sh execs {target}, which does not exist"
    # Parse the PAYLOAD LIST, not the whole file: a first version of this test
    # asserted "run_server.py" appeared anywhere in build_deb.sh, and passed
    # against a packager that did not ship it -- the name also occurs in the
    # comment explaining the guard. A test that cannot fail is not a test.
    build = (ROOT / "build_deb.sh").read_text(encoding="utf-8")
    m = re.search(r"^for item in (.+?); do$", build, re.M)
    assert m, "build_deb.sh has no recognisable payload list"
    payload = m.group(1).split()
    for target in set(execs):
        assert target in payload, (
            f"run.sh execs {target} but build_deb.sh's payload list is {payload}"
        )
