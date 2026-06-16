"""Persistence to a single JSON file at ``~/alarm_clock.json``.

File shape::

    {"sound": "/path/to/file.mp3" | null, "alarms": [ {alarm}, ... ]}

Corruption is handled gracefully: a missing file yields empty state, and an
unparseable file yields empty state with a warning (the file is left untouched
so the user can recover it).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .alarm import Alarm, ValidationError

DEFAULT_PATH = Path.home() / "alarm_clock.json"


@dataclass
class State:
    """In-memory view of the store file."""

    sound: str | None = None
    alarms: list[Alarm] = field(default_factory=list)


class Store:
    """Loads and saves :class:`State` to a JSON file."""

    def __init__(self, path: Path | str = DEFAULT_PATH) -> None:
        self.path = Path(path)

    def load(self) -> State:
        """Return the stored state, or empty state if missing/corrupt."""
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return State()
        except OSError as exc:
            self._warn(f"could not read {self.path}: {exc}; starting empty")
            return State()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            self._warn(
                f"{self.path} is not valid JSON ({exc}); "
                "starting empty (file left untouched)"
            )
            return State()

        if not isinstance(data, dict):
            self._warn(f"{self.path} has unexpected shape; starting empty")
            return State()

        sound = data.get("sound")
        if not isinstance(sound, str):
            sound = None

        alarms: list[Alarm] = []
        for record in data.get("alarms", []) or []:
            try:
                alarms.append(Alarm.from_dict(record))
            except ValidationError as exc:
                self._warn(f"skipping invalid alarm in {self.path}: {exc}")
        return State(sound=sound, alarms=alarms)

    def save(self, state: State) -> None:
        """Atomically write ``state`` to disk (temp file + replace)."""
        payload = {
            "sound": state.sound,
            "alarms": [a.to_dict() for a in state.alarms],
        }
        text = json.dumps(payload, indent=2)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_name = tempfile.mkstemp(
            dir=self.path.parent, prefix=self.path.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self.path)
        except BaseException:
            # Don't leave a stray temp file behind on failure.
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    @staticmethod
    def _warn(message: str) -> None:
        print(f"warning: {message}", file=sys.stderr)
