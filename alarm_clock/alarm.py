"""Alarm data model and validation.

An Alarm is a plain data object: a target wall-clock time (24h ``HH:MM``,
local), a repeat policy, and an enabled flag. No date is stored — the
Scheduler resolves the next occurrence of the time.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum


class Repeat(StrEnum):
    """How often an alarm re-arms after firing."""

    ONCE = "once"
    DAILY = "daily"
    WEEKDAYS = "weekdays"

    @classmethod
    def parse(cls, value: "str | Repeat") -> "Repeat":
        """Coerce a string/Repeat into a Repeat, raising on unknown values."""
        if isinstance(value, cls):
            return value
        try:
            return cls(value)
        except ValueError as exc:
            allowed = ", ".join(r.value for r in cls)
            raise ValidationError(
                f"invalid repeat {value!r}: expected one of {allowed}"
            ) from exc


_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ValidationError(ValueError):
    """Raised when an alarm field fails validation."""


def validate_time(value: str) -> str:
    """Return ``value`` if it is a valid ``HH:MM`` 24-hour time, else raise."""
    if not isinstance(value, str) or not _TIME_RE.match(value):
        raise ValidationError(
            f"invalid time {value!r}: expected 24-hour HH:MM (00:00-23:59)"
        )
    return value


@dataclass
class Alarm:
    """A single alarm.

    Attributes:
        time: Target time as ``HH:MM`` (24-hour, local).
        repeat: A :class:`Repeat` policy.
        enabled: Whether the alarm is active.
        id: UUID4 string, generated on creation.
    """

    time: str
    repeat: Repeat = Repeat.ONCE
    enabled: bool = True
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        validate_time(self.time)
        self.repeat = Repeat.parse(self.repeat)
        self.enabled = bool(self.enabled)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "time": self.time,
            "repeat": self.repeat.value,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Alarm":
        """Build an Alarm from stored JSON, ignoring unknown fields.

        Raises ValidationError if required fields are missing or invalid.
        """
        try:
            time = data["time"]
            repeat = data["repeat"]
        except (KeyError, TypeError) as exc:
            raise ValidationError(f"malformed alarm record: {data!r}") from exc
        alarm = cls(
            time=time,
            repeat=Repeat.parse(repeat),
            enabled=data.get("enabled", True),
        )
        alarm_id = data.get("id")
        if isinstance(alarm_id, str) and alarm_id:
            alarm.id = alarm_id
        return alarm
