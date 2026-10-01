"""GET /link lists only linked apps that are still running.

Regression test for the 2026-09-30 owner review. HRT kept every app that had
ever linked: after the GGUF Chatbox quit, GET /link still listed it, so the
Master Panel showed the Chatbox RUNNING and connected, HRT's own Linked Apps
list kept a green dot for it, and a Master Panel restarted under a new PID saw
its old entry and never linked again. E-Stop then killed each stale entry by
its old PID, which by then may belong to another process.

HRT now holds a pidfd for each linked process from the moment it links (or is
reconnected at startup). A pidfd names that one process, so a PID the kernel
has handed to another process never reads as the linked app.

Each case runs in a child process with HOTROD_STATE_DIR in a temp folder, so
the user's real linked_apps.json is never read or written, and the startup
hooks (fans, sensors, sound) never run. The stand-in apps are `sleep`
children, and E-Stop's kill is recorded, never performed. Everything is
namespace-safe: no PID is looked up through /proc/<pid> by the test.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

_CHILD = r"""
import json, os, shutil, subprocess, sys, time
kids = []
try:
    sys.path.insert(0, sys.argv[1])
    scenario, work = sys.argv[2], sys.argv[3]
    from fastapi.testclient import TestClient
    from hotrod_tuner import app as hrt
    client = TestClient(hrt.app)  # no `with`: the startup hooks never run

    def spawn(exe=None):
        if exe is None:
            p = subprocess.Popen(["sleep", "300"])
        else:  # a renamed bash, blocked reading a pipe until it is killed
            p = subprocess.Popen([exe, "-c", "read _"], stdin=subprocess.PIPE)
        kids.append(p)
        return p

    def end(p):
        p.kill()
        p.wait()

    def renamed_program(stem):
        # A copy of bash under a name nothing else on the box runs (<= 15
        # chars, so the kernel's process name is the whole of it). Not sleep:
        # here that is a multi-call binary that exits at once under any other
        # name, and a dead copy would only seem to be found.
        exe = os.path.join(work, stem + os.urandom(4).hex())
        shutil.copy("/usr/bin/bash", exe)
        os.chmod(exe, 0o755)
        return exe

    def link(name, pid, exe="/nonexistent/hrt-link-test"):
        r = client.post("/link", json={"app_name": name, "exe_path": exe, "pid": pid})
        return r.status_code

    def listed():
        return {a["app_name"]: a["pid"] for a in client.get("/link").json()["linked_apps"]}

    def open_fds():
        return len(os.listdir("/proc/self/fd"))

    out = {}
    if scenario == "exit":
        a, b = spawn(), spawn()
        out["posts"] = [link("GGUF Chatbox", a.pid), link("Other app", b.pid)]
        out["alive"] = listed()
        end(a)
        out["after"] = listed()
        out["pids"] = [a.pid, b.pid]
    elif scenario == "refuse":
        ghost = spawn()
        end(ghost)
        out["post"] = link("Ghost", ghost.pid)
        out["after"] = listed()
    elif scenario == "relink":
        before = open_fds()
        first = spawn()
        link("GGUF Chatbox", first.pid)
        end(first)
        for _ in range(3):
            again = spawn()
            link("GGUF Chatbox", again.pid)
        out["fds_added"] = open_fds() - before  # Popen without pipes keeps no fd
        out["after"] = listed()
        out["last_pid"] = again.pid
    elif scenario == "estop":
        calls = []
        def recorded_kill(pid):
            calls.append(pid)
            return {"pid": pid, "ok": True, "method": "recorded", "children_killed": 0}
        hrt._safe_kill = recorded_kill
        relaunch_exe = renamed_program("hrtlnk")
        live, gone = spawn(), spawn(relaunch_exe)
        link("Live app", live.pid)
        link("Gone app", gone.pid, exe=relaunch_exe)
        end(gone)
        relaunched = spawn(relaunch_exe)  # the same program again, never linked
        res = client.post("/api/estop", json={"targets": []}).json()
        out["relaunch_running"] = relaunched.poll() is None
        out["ok"] = res.get("ok")
        out["by_pid"] = [r["pid"] for r in res["results"]
                         if r.get("source") == "linked" and r.get("method") == "recorded"]
        out["by_name"] = [r["exe"] for r in res["results"] if r.get("source") == "name_match"]
        out["relaunch_name"] = os.path.basename(relaunch_exe)
        out["pids"] = {"live": live.pid, "gone": gone.pid}
        out["after"] = listed()
        out["saved_after"] = [a["app_name"] for a in
                              json.loads(hrt._LINKED_FILE.read_text(encoding="utf-8"))]
    elif scenario == "reload":
        exe = renamed_program("hrtrel")
        p = spawn(exe)
        time.sleep(0.2)
        out["running_at_reload"] = p.poll() is None
        hrt._LINKED_FILE.parent.mkdir(parents=True, exist_ok=True)
        hrt._LINKED_FILE.write_text(json.dumps([
            {"app_name": "Reloaded", "exe_path": exe, "pid": 1, "linked_at": "earlier"},
            {"app_name": "Not running", "exe_path": exe + "-x", "pid": 1, "linked_at": "earlier"},
        ]), encoding="utf-8")
        hrt._load_linked()
        out["after_reload"] = listed()
        out["pid"] = p.pid
        end(p)
        out["after_exit"] = listed()
    elif scenario == "no_pidfd":
        hrt._pidfd_open = None  # a platform without pidfds (Windows)
        a = spawn()
        out["post"] = link("GGUF Chatbox", a.pid)
        out["alive"] = listed()
        out["pid"] = a.pid
    print(json.dumps(out))
except Exception as e:
    print(json.dumps({"child_error": f"{type(e).__name__}: {e}"}))
    sys.exit(1)
finally:
    for k in kids:
        if k.poll() is None:
            k.kill()
            k.wait()
"""


def _run(tmp_path: Path, scenario: str) -> dict:
    work = tmp_path / "work"
    work.mkdir()
    env = dict(os.environ, HOTROD_STATE_DIR=str(tmp_path / "state"))
    out = subprocess.run(
        [sys.executable, "-c", _CHILD, str(SRC), scenario, str(work)],
        env=env, capture_output=True, text=True, timeout=120,
    )
    lines = [l for l in out.stdout.splitlines() if l.startswith("{")]
    assert lines, f"child printed no result (exit {out.returncode}): {out.stderr[-2000:]}"
    got = json.loads(lines[-1])
    assert "child_error" not in got, got["child_error"]
    return got


def test_an_app_that_has_exited_is_no_longer_listed(tmp_path):
    got = _run(tmp_path, "exit")
    chatbox, other = got["pids"]
    assert got["posts"] == [200, 200]
    # Control: both are listed while they run, so the check is not "list nothing".
    assert got["alive"] == {"GGUF Chatbox": chatbox, "Other app": other}
    assert got["after"] == {"Other app": other}


def test_a_link_naming_no_running_process_is_refused(tmp_path):
    got = _run(tmp_path, "refuse")
    assert got["post"] == 422
    assert got["after"] == {}


def test_relinking_replaces_the_entry_and_keeps_one_handle(tmp_path):
    got = _run(tmp_path, "relink")
    assert got["after"] == {"GGUF Chatbox": got["last_pid"]}
    # One pidfd for the one linked app; the replaced ones were closed.
    assert got["fds_added"] <= 1


def test_estop_never_kills_an_exited_link_by_its_old_pid(tmp_path):
    got = _run(tmp_path, "estop")
    assert got["ok"] is True
    # Control: the running linked app IS killed by its PID.
    assert got["by_pid"] == [got["pids"]["live"]]
    assert got["pids"]["gone"] not in got["by_pid"]
    # The exited app's program name still reaches the name scan, so a
    # relaunched copy that has not linked yet is stopped as before. (It was
    # running when E-Stop scanned: the kill is only recorded.)
    assert got["relaunch_running"] is True
    assert got["relaunch_name"] in got["by_name"]
    assert got["after"] == {}
    # The exited entry is dropped, not just hidden, so it is not saved for the
    # next start or reported again by the next E-Stop.
    assert got["saved_after"] == []


def test_startup_reconnect_tracks_the_process_it_found(tmp_path):
    got = _run(tmp_path, "reload")
    assert got["running_at_reload"] is True
    # The number is this namespace's PID for the process, the one HRT can act on.
    assert got["after_reload"] == {"Reloaded": got["pid"]}
    assert got["after_exit"] == {}


def test_without_pidfds_linking_still_works(tmp_path):
    got = _run(tmp_path, "no_pidfd")
    assert got["post"] == 200
    assert got["alive"] == {"GGUF Chatbox": got["pid"]}
