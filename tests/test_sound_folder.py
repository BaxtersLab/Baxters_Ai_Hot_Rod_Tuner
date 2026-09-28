"""The Sound Folder button must open a folder the user can drop a .wav into.

Regression test for the 2026-09-27 owner review. The endpoint ran
`explorer <folder>`, which exists only on Windows, so the button failed on
every Linux install. And the folder it named was the payload's `assets/`,
which the .deb installs root-owned under /opt, so even a working opener would
have shown a folder the user cannot write to.

On Linux the button now opens `<state dir>/sounds` with xdg-open, creating it
on first use, and SoundManager reads that folder before the bundled one.
Windows keeps explorer and its original folders.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
ROOT = Path(__file__).resolve().parents[1]

# Calls the real endpoint in a child process with Popen recorded, so no file
# manager window is ever opened by the suite. The child imports app.py, which
# writes its log under HOTROD_STATE_DIR only.
_CHILD = r"""
import json, subprocess, sys
try:
    sys.path.insert(0, sys.argv[1])
    from hotrod_tuner import app as hrt_app
    calls = []
    class _Recorder:
        def __init__(self, argv, *a, **k):
            calls.append(list(argv))
            if sys.argv[2] == "linux-no-opener":
                raise FileNotFoundError(2, "No such file or directory", argv[0])
    subprocess.Popen = _Recorder
    if sys.argv[2] == "win32":
        sys.platform = "win32"
    res = hrt_app.open_sound_folder()
    print(json.dumps({"calls": calls, "res": res}))
except Exception as e:
    print(json.dumps({"child_error": type(e).__name__}))
    sys.exit(1)
"""


def _press_the_button(state: Path, platform: str) -> dict:
    env = dict(os.environ, HOTROD_STATE_DIR=str(state))
    out = subprocess.run(
        [sys.executable, "-c", _CHILD, str(SRC), platform],
        env=env, capture_output=True, text=True, timeout=60,
    )
    lines = [l for l in out.stdout.splitlines() if l.startswith("{")]
    assert lines, f"child printed no result (exit {out.returncode})"
    got = json.loads(lines[-1])
    assert "child_error" not in got, f"child raised {got['child_error']}"
    return got


def test_linux_button_opens_the_user_sound_folder_with_xdg_open(tmp_path):
    state = tmp_path / "state"
    got = _press_the_button(state, "linux")
    want = state / "sounds"
    assert got["calls"] == [["xdg-open", str(want)]], got["calls"]
    assert got["res"] == {"ok": True, "path": str(want)}, got["res"]
    assert want.is_dir(), "the folder must exist before the file manager opens it"
    assert ROOT not in want.parents, "the opened folder is inside the payload"


def test_windows_button_still_uses_explorer_on_the_assets_folder(tmp_path):
    """Control: the Linux fix must not reach the Windows branch."""
    got = _press_the_button(tmp_path / "state", "win32")
    assert got["calls"] == [["explorer", str(ROOT / "assets")]], got["calls"]
    assert got["res"]["ok"] is True


def test_a_desktop_without_xdg_open_gets_a_message_not_a_crash(tmp_path):
    state = tmp_path / "state"
    got = _press_the_button(state, "linux-no-opener")
    res = got["res"]
    assert res["ok"] is False
    assert res["path"] == str(state / "sounds"), "the user still learns where to put a .wav"
    assert "xdg-open" in res["error"] and str(state / "sounds") in res["error"], res


def _fresh_manager(monkeypatch, state: Path):
    monkeypatch.setenv("HOTROD_STATE_DIR", str(state))
    sys.path.insert(0, str(SRC))
    from hotrod_tuner.sound import SoundManager
    return SoundManager()


def test_a_wav_in_the_user_folder_replaces_the_bundled_sound(tmp_path, monkeypatch):
    m = _fresh_manager(monkeypatch, tmp_path / "state")
    # Control: with no user folder, the packaged chime is the only sound.
    assert m.get_available_sounds() == ["hrt sound.wav"]

    user = tmp_path / "state" / "sounds"
    user.mkdir(parents=True)
    (user / "mine.wav").write_bytes(b"RIFF")
    names = m.get_available_sounds()
    assert names[0] == "mine.wav", names
    assert "hrt sound.wav" in names, "the bundled chime must still be listed"

    # The file the player receives is the one the UI label shows (names[0]).
    played = []
    m._player = lambda f: played.append(f) or True
    assert m.play_startup_sound(blocking=True) is True
    assert played == [str(user / "mine.wav")], played


def test_the_status_endpoint_names_the_folder_the_button_opens(tmp_path, monkeypatch):
    state = tmp_path / "state"
    got = _press_the_button(state, "linux")
    env = dict(os.environ, HOTROD_STATE_DIR=str(state))
    code = (
        "import json,sys\n"
        "try:\n"
        f"    sys.path.insert(0, {str(SRC)!r})\n"
        "    from hotrod_tuner import app as a\n"
        "    print(json.dumps(a.get_sound_folder()))\n"
        "except Exception as e:\n"
        "    print(json.dumps({'child_error': type(e).__name__})); sys.exit(1)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], env=env,
                         capture_output=True, text=True, timeout=60)
    lines = [l for l in out.stdout.splitlines() if l.startswith("{")]
    assert lines, f"child printed no result (exit {out.returncode})"
    assert json.loads(lines[-1]) == {"path": got["res"]["path"]}


def test_windows_manager_still_reads_only_the_bundled_folder(tmp_path, monkeypatch):
    """Control: a Windows install writes next to its own exe; no user folder."""
    m = _fresh_manager(monkeypatch, tmp_path / "state")
    user = tmp_path / "state" / "sounds"
    user.mkdir(parents=True)
    (user / "mine.wav").write_bytes(b"RIFF")
    monkeypatch.setattr(sys, "platform", "win32")
    assert m.get_available_sounds() == ["hrt sound.wav"]


def _recording_manager(monkeypatch, state: Path, **kw):
    monkeypatch.setenv("HOTROD_STATE_DIR", str(state))
    sys.path.insert(0, str(SRC))
    from hotrod_tuner.sound import SoundManager
    played = []
    return SoundManager(player=lambda f: played.append(f) or True, **kw), played


def test_the_user_folder_plays_before_the_bundled_chime(tmp_path, monkeypatch):
    m, played = _recording_manager(monkeypatch, tmp_path / "state")
    user = tmp_path / "state" / "sounds"
    assert m.play_startup_sound(blocking=True)          # no user folder yet
    user.mkdir(parents=True)
    (user / "mine.wav").write_bytes(b"RIFF")
    assert m.play_startup_sound(blocking=True)          # the user's sound
    (user / "mine.wav").unlink()
    assert m.play_startup_sound(blocking=True)          # back to the chime
    assert [Path(f).name for f in played] == ["hrt sound.wav", "mine.wav", "hrt sound.wav"]
    assert Path(played[1]).parent == user


def test_a_missing_sound_file_is_reported_and_never_played(tmp_path, monkeypatch, capsys):
    m, played = _recording_manager(monkeypatch, tmp_path / "state")
    user = tmp_path / "state" / "sounds"
    user.mkdir(parents=True)
    gone = user / "a.wav"                               # sorts first
    gone.symlink_to(tmp_path / "deleted.wav")           # a dangling link
    (user / "mine.wav").write_bytes(b"RIFF")
    assert m.get_available_sounds()[0] == "a.wav", "premise: the missing file is chosen"
    assert m.play_startup_sound(blocking=True) is False
    assert played == []
    assert f"Sound file missing: {gone}" in capsys.readouterr().out


def test_no_sound_anywhere_names_the_folders_searched(tmp_path, monkeypatch, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    m, played = _recording_manager(monkeypatch, tmp_path / "state", sound_dir=str(empty))
    assert m.play_startup_sound(blocking=True) is False
    assert played == []
    assert f"No WAV files found in {empty}" in capsys.readouterr().out


def test_a_player_that_fails_is_reported_as_a_failure(tmp_path, monkeypatch):
    """The default player: the command's exit status decides. `false` and
    `true` stand in for pw-play, so nothing reaches the speakers."""
    import shutil
    monkeypatch.setenv("HOTROD_STATE_DIR", str(tmp_path / "state"))
    sys.path.insert(0, str(SRC))
    from hotrod_tuner import sound
    monkeypatch.setattr(sound, "SOUND_BACKEND", "command")
    monkeypatch.setattr(sound, "_LINUX_PLAYER", shutil.which("false"))
    assert sound.SoundManager().play_startup_sound(blocking=True) is False
    # Control: a player that succeeds is reported as success.
    monkeypatch.setattr(sound, "_LINUX_PLAYER", shutil.which("true"))
    assert sound.SoundManager().play_startup_sound(blocking=True) is True



def test_an_injected_player_needs_no_detected_backend(tmp_path, monkeypatch):
    m, played = _recording_manager(monkeypatch, tmp_path / "state")
    from hotrod_tuner import sound
    monkeypatch.setattr(sound, "SOUND_BACKEND", None)
    assert m.play_startup_sound(blocking=True) is True
    assert [Path(f).name for f in played] == ["hrt sound.wav"]
    # Control: with no player and no backend, nothing plays.
    assert sound.SoundManager().play_startup_sound(blocking=True) is False
