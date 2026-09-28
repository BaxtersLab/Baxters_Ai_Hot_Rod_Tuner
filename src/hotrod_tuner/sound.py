"""Sound manager for Hot Rod Tuner startup sounds."""
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

from .paths import sounds_dir as _user_sounds_dir

# Use winsound on Windows (built-in, works in frozen exe).
#
# On Linux, prefer a command-line player over `playsound`: playsound 1.3 has no
# native backend there and reaches audio through GStreamer via PyGObject, which
# is a large binding stack that cannot be installed by pip on a PEP 668 system.
# pw-play (PipeWire) and aplay (ALSA) ship with the desktop, cost one short-
# lived process per sound, and cannot wedge the server if audio is misconfigured.
_LINUX_PLAYER = None
SOUND_BACKEND = None
try:
    import winsound
    SOUND_BACKEND = "winsound"
except ImportError:
    for _cand in ("pw-play", "paplay", "aplay", "ffplay"):
        _path = shutil.which(_cand)
        if _path:
            _LINUX_PLAYER = _path
            SOUND_BACKEND = "command"
            break
    if SOUND_BACKEND is None:
        try:
            from playsound import playsound
            SOUND_BACKEND = "playsound"
        except ImportError:
            print("Warning: no sound backend available. Sound functionality will be disabled.")


def _play_with_backend(sound_file: str) -> bool:
    """Play one file with the detected backend, blocking. True only if it played."""
    try:
        if SOUND_BACKEND == "winsound":
            winsound.PlaySound(sound_file, winsound.SND_FILENAME)
        elif SOUND_BACKEND == "command":
            argv = [_LINUX_PLAYER]
            if _LINUX_PLAYER.endswith("ffplay"):
                argv += ["-nodisp", "-autoexit", "-loglevel", "quiet"]
            # Capped wait: a startup chime is ~2s, and a player left blocked
            # on a dead audio server must not pin this thread forever.
            done = subprocess.run(argv + [sound_file], timeout=30,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # The exit status was ignored, so a player that could not play
            # the file still reported success.
            if done.returncode != 0:
                print(f"Error playing sound: {Path(_LINUX_PLAYER).name} exited "
                      f"{done.returncode} for {sound_file}")
                return False
        elif SOUND_BACKEND == "playsound":
            playsound(sound_file)
        else:
            return False
        return True
    except Exception as e:
        print(f"Error playing sound: {e}")
        return False


class SoundManager:
    """Manages playback of WAV sound files for Hot Rod Tuner."""

    def __init__(self, sound_dir: Optional[str] = None,
                 player: Optional[Callable[[str], bool]] = None):
        # Plays one file, blocking, and says whether it played. Injectable so
        # the test suite never drives the speakers.
        self._player = player
        # An explicit folder is the only folder searched.
        self._explicit = sound_dir is not None
        if sound_dir is not None:
            self.sound_dir = Path(sound_dir)
        else:
            # Resolve assets dir relative to project root (frozen-exe aware)
            if getattr(sys, 'frozen', False):
                # Look next to the exe first (user-accessible), fall back to
                # the bundled _MEIPASS assets
                real_assets = Path(sys.executable).parent / "assets"
                if real_assets.is_dir():
                    self.sound_dir = real_assets
                else:
                    self.sound_dir = Path(sys._MEIPASS) / "assets"
            else:
                base = Path(__file__).resolve().parent.parent.parent
                self.sound_dir = base / "assets"
        self._current_thread: Optional[threading.Thread] = None

    def sound_dirs(self) -> list[Path]:
        """Folders searched for a .wav, in order; the first file found plays.

        Off Windows the bundled assets folder is root-owned under /opt, so the
        user's sounds folder comes first and a .wav dropped there replaces the
        chime. It is resolved per call, so HOTROD_STATE_DIR always applies.
        Windows keeps its single folder, which the user can already write.
        """
        if self._explicit or sys.platform == "win32":
            return [self.sound_dir]
        return [_user_sounds_dir(), self.sound_dir]

    def _wav_files(self) -> list[Path]:
        found: list[Path] = []
        for folder in self.sound_dirs():
            if folder.is_dir():
                found += sorted(folder.glob("*.wav"))
        return found

    def play_startup_sound(self, blocking: bool = False) -> bool:
        """
        Play the first available WAV file from the sound directory.
        Returns True if a sound was played, False otherwise.
        """
        if self._player is None and SOUND_BACKEND is None:
            print("Sound playback not available - no sound backend")
            return False

        wav_files = self._wav_files()
        if not wav_files:
            print(f"No WAV files found in {', '.join(map(str, self.sound_dirs()))}")
            return False

        # Play the first WAV file found
        sound_file = str(wav_files[0])
        print(f"Playing startup sound: {sound_file} (backend: {SOUND_BACKEND})")

        if blocking:
            return self._play_sound(sound_file)
        else:
            self._current_thread = threading.Thread(
                target=self._play_sound,
                args=(sound_file,),
                daemon=True
            )
            self._current_thread.start()
            return True

    def _play_sound(self, sound_file: str) -> bool:
        """Play one file with this manager's player. A file that is not there
        (removed, or a dangling link) is reported and never handed over."""
        if not Path(sound_file).is_file():
            print(f"Sound file missing: {sound_file}")
            return False
        return (self._player or _play_with_backend)(sound_file)

    def get_available_sounds(self) -> list[str]:
        """Get list of available WAV files."""
        return [f.name for f in self._wav_files()]

    def stop_current_sound(self):
        """Stop currently playing sound (if supported by playsound)."""
        # Note: playsound doesn't support stopping, but we can track the thread
        pass


# Global sound manager instance
sound_manager = SoundManager()