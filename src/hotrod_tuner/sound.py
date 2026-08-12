"""Sound manager for Hot Rod Tuner startup sounds."""
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

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


class SoundManager:
    """Manages playback of WAV sound files for Hot Rod Tuner."""

    def __init__(self, sound_dir: Optional[str] = None):
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

    def play_startup_sound(self, blocking: bool = False) -> bool:
        """
        Play the first available WAV file from the sound directory.
        Returns True if a sound was played, False otherwise.
        """
        if SOUND_BACKEND is None:
            print("Sound playback not available - no sound backend")
            return False

        wav_files = list(self.sound_dir.glob("*.wav"))
        if not wav_files:
            print(f"No WAV files found in {self.sound_dir}")
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
        """Play a sound file using the available backend."""
        try:
            if SOUND_BACKEND == "winsound":
                winsound.PlaySound(sound_file, winsound.SND_FILENAME)
            elif SOUND_BACKEND == "command":
                argv = [_LINUX_PLAYER]
                if _LINUX_PLAYER.endswith("ffplay"):
                    argv += ["-nodisp", "-autoexit", "-loglevel", "quiet"]
                # Capped wait: a startup chime is ~2s, and a player left blocked
                # on a dead audio server must not pin this thread forever.
                subprocess.run(argv + [sound_file], timeout=30,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif SOUND_BACKEND == "playsound":
                playsound(sound_file)
            return True
        except Exception as e:
            print(f"Error playing sound: {e}")
            return False

    def get_available_sounds(self) -> list[str]:
        """Get list of available WAV files."""
        if not self.sound_dir.exists():
            return []

        return [f.name for f in self.sound_dir.glob("*.wav")]

    def stop_current_sound(self):
        """Stop currently playing sound (if supported by playsound)."""
        # Note: playsound doesn't support stopping, but we can track the thread
        pass


# Global sound manager instance
sound_manager = SoundManager()