"""Scheduling: compute the next fire time and run the polling loop.

All times are local wall-clock with one-minute granularity. No timezone or
DST handling (per SPEC).
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Callable

from .alarm import Alarm, Repeat
from .store import Store

# weekday() values 0-4 are Mon-Fri.
_LAST_WEEKDAY = 4


def next_fire_time(alarm: Alarm, now: datetime) -> datetime:
    """Return the next local datetime (minute-precision) the alarm should fire.

    The result is always ``>= now`` truncated to the minute. If the alarm's
    time has already passed in the current minute, it rolls to the next valid
    day. For ``weekdays`` alarms, the result lands on Mon-Fri.

    This is a pure function of ``alarm`` and ``now`` (enabled state is ignored).
    """
    hour, minute = (int(part) for part in alarm.time.split(":"))
    now_minute = now.replace(second=0, microsecond=0)
    candidate = now_minute.replace(hour=hour, minute=minute)

    if candidate < now_minute:
        candidate += timedelta(days=1)

    if alarm.repeat is Repeat.WEEKDAYS:
        while candidate.weekday() > _LAST_WEEKDAY:
            candidate += timedelta(days=1)

    return candidate


def run(
    store: Store,
    notify: Callable[[Alarm], None],
    *,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = datetime.now,
    stop: Callable[[], bool] = lambda: False,
) -> None:
    """Poll once per second and fire due alarms until ``stop()`` is true.

    State is reloaded each tick so edits made by the CLI are picked up live.
    A ``once`` alarm is disabled and persisted after it fires. Each alarm fires
    at most once per minute (tracked by ``(id, minute)``).

    Injectable ``sleep``/``now``/``stop`` make the loop testable.
    """
    last_fired: dict[str, datetime] = {}

    while not stop():
        current = now().replace(second=0, microsecond=0)
        state = store.load()
        dirty = False

        for alarm in state.alarms:
            if not alarm.enabled:
                continue
            if next_fire_time(alarm, current) != current:
                continue
            if last_fired.get(alarm.id) == current:
                continue

            notify(alarm)
            last_fired[alarm.id] = current

            if alarm.repeat is Repeat.ONCE:
                alarm.enabled = False
                dirty = True

        if dirty:
            store.save(state)

        sleep(1)
