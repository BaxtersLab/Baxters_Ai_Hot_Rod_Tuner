"""Sound manager for Hot Rod Tuner startup sounds."""
import os
import threading
from pathlib import Path
from typing import Optional

# Try to import playsound, but make it optional
try:
    from playsound import playsound
    PLAYSOUND_AVAILABLE = True
except ImportError:
    PLAYSOUND_AVAILABLE = False
    print("Warning: playsound module not available. Sound functionality will be disabled.")


class SoundManager:
    """Manages playback of WAV sound files for Hot Rod Tuner."""

    def __init__(self, sound_dir: str = "HRT wav sound file"):
        self.sound_dir = Path(sound_dir)
        self._current_thread: Optional[threading.Thread] = None

    def play_startup_sound(self, blocking: bool = False) -> bool:
        """
        Play the first available WAV file from the sound directory.
        Returns True if a sound was played, False otherwise.
        """
        if not PLAYSOUND_AVAILABLE:
            print("Sound playback not available - playsound module not installed")
            return False

        wav_files = list(self.sound_dir.glob("*.wav"))
        if not wav_files:
            print("No WAV files found in sound directory")
            return False

        # Play the first WAV file found
        sound_file = wav_files[0]
        print(f"Playing startup sound: {sound_file}")

        if blocking:
            try:
                playsound(str(sound_file))
                return True
            except Exception as e:
                print(f"Error playing sound: {e}")
                return False
        else:
            # Play in background thread
            self._current_thread = threading.Thread(
                target=self._play_sound_thread,
                args=(str(sound_file),),
                daemon=True
            )
            self._current_thread.start()
            return True

    def _play_sound_thread(self, sound_file: str):
        """Thread function to play sound asynchronously."""
        if not PLAYSOUND_AVAILABLE:
            return

        try:
            playsound(sound_file)
        except Exception as e:
            print(f"Error playing sound in thread: {e}")

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