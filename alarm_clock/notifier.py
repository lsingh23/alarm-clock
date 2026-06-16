"""Notification: print a banner and play a sound.

Sound plays in a subprocess so a single Ctrl-C stops it (and, per the
Scheduler, exits the loop). If no sound is configured or no player is
available, fall back to the terminal bell ``\\a``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .alarm import Alarm

# Player command builders, keyed by binary name. Each maps a file path to argv.
_PLAYERS = {
    "afplay": lambda p: ["afplay", p],
    "mpg123": lambda p: ["mpg123", "-q", p],
    "ffplay": lambda p: ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", p],
    "mpv": lambda p: ["mpv", "--no-video", "--really-quiet", p],
    "cvlc": lambda p: ["cvlc", "--play-and-exit", "--intf", "dummy", p],
    "paplay": lambda p: ["paplay", p],
    "aplay": lambda p: ["aplay", "-q", p],
}

# Preference order per platform.
_CANDIDATES = {
    "darwin": ["afplay", "mpg123", "ffplay", "mpv"],
}
_DEFAULT_CANDIDATES = ["mpg123", "ffplay", "mpv", "cvlc", "paplay", "aplay"]


def _resolve_player() -> "list | None":
    candidates = _CANDIDATES.get(sys.platform, _DEFAULT_CANDIDATES)
    for name in candidates:
        if shutil.which(name):
            return _PLAYERS[name]
    return None


class Notifier:
    """Renders an alarm as a banner plus a sound (or bell fallback)."""

    def __init__(self, sound: str | None = None, *, stream=None) -> None:
        self.sound = sound
        self.stream = stream if stream is not None else sys.stdout

    def notify(self, alarm: Alarm) -> None:
        """Show the banner and play the alarm's sound, blocking until done."""
        self._banner(alarm)
        self._play()

    def _banner(self, alarm: Alarm) -> None:
        line = "=" * 44
        print(line, file=self.stream)
        print(f"  ⏰  ALARM  {alarm.time}   ({alarm.repeat.value})", file=self.stream)
        print(f"      id {alarm.id[:8]}", file=self.stream)
        print(line, file=self.stream)
        self.stream.flush()

    def _play(self) -> None:
        builder = _resolve_player()
        sound_ok = bool(self.sound) and Path(self.sound).exists()
        if not (sound_ok and builder):
            self._bell()
            return

        proc = None
        try:
            proc = subprocess.Popen(builder(self.sound))
            proc.wait()
        except (OSError, FileNotFoundError):
            self._bell()
        except KeyboardInterrupt:
            if proc is not None:
                proc.terminate()
            raise

    def _bell(self) -> None:
        self.stream.write("\a")
        self.stream.flush()
