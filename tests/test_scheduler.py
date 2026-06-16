"""Tests for alarm_clock.scheduler."""

from __future__ import annotations

from datetime import datetime

import pytest

from alarm_clock.alarm import Alarm, Repeat
from alarm_clock.scheduler import next_fire_time, run
from alarm_clock.store import State, Store


# 2026-06-16 is a Tuesday; 2026-06-20 a Saturday; 2026-06-21 a Sunday.
TUESDAY_0900 = datetime(2026, 6, 16, 9, 0, 0)


# --- next_fire_time -------------------------------------------------------

def test_time_later_today_fires_today():
    alarm = Alarm(time="17:30", repeat=Repeat.DAILY)
    assert next_fire_time(alarm, TUESDAY_0900) == datetime(2026, 6, 16, 17, 30)


def test_time_already_passed_fires_tomorrow():
    alarm = Alarm(time="08:00", repeat=Repeat.DAILY)
    assert next_fire_time(alarm, TUESDAY_0900) == datetime(2026, 6, 17, 8, 0)


def test_current_minute_fires_now_not_tomorrow():
    # now is 09:00:45 — alarm for 09:00 should still fire in this minute.
    now = datetime(2026, 6, 16, 9, 0, 45)
    alarm = Alarm(time="09:00", repeat=Repeat.DAILY)
    assert next_fire_time(alarm, now) == datetime(2026, 6, 16, 9, 0)


def test_seconds_are_truncated_from_result():
    alarm = Alarm(time="23:59", repeat=Repeat.ONCE)
    result = next_fire_time(alarm, datetime(2026, 6, 16, 9, 0, 30, 123))
    assert result.second == 0 and result.microsecond == 0


def test_once_behaves_like_daily_for_next_occurrence():
    # next_fire_time ignores repeat except for weekday filtering.
    alarm = Alarm(time="08:00", repeat=Repeat.ONCE)
    assert next_fire_time(alarm, TUESDAY_0900) == datetime(2026, 6, 17, 8, 0)


def test_weekdays_skips_to_monday_when_landing_on_saturday():
    # Friday 2026-06-19, 08:00 already passed -> Saturday -> skip to Monday.
    friday = datetime(2026, 6, 19, 9, 0)
    alarm = Alarm(time="08:00", repeat=Repeat.WEEKDAYS)
    assert next_fire_time(alarm, friday) == datetime(2026, 6, 22, 8, 0)


def test_weekdays_on_saturday_fires_monday():
    saturday = datetime(2026, 6, 20, 9, 0)
    alarm = Alarm(time="10:00", repeat=Repeat.WEEKDAYS)
    assert next_fire_time(alarm, saturday) == datetime(2026, 6, 22, 10, 0)


def test_weekdays_later_today_on_a_weekday():
    alarm = Alarm(time="17:00", repeat=Repeat.WEEKDAYS)
    assert next_fire_time(alarm, TUESDAY_0900) == datetime(2026, 6, 16, 17, 0)


def test_midnight_rollover():
    alarm = Alarm(time="00:00", repeat=Repeat.DAILY)
    now = datetime(2026, 6, 16, 23, 30)
    assert next_fire_time(alarm, now) == datetime(2026, 6, 17, 0, 0)


# --- run loop -------------------------------------------------------------

class FakeClock:
    """Yields a fixed sequence of datetimes, one per ``now()`` call."""

    def __init__(self, times):
        self._times = list(times)
        self._i = -1

    def now(self):
        self._i = min(self._i + 1, len(self._times) - 1)
        return self._times[self._i]


def _run_once(store, notify, clock):
    """Drive run() for a single tick, then stop."""
    calls = {"n": 0}

    def stop():
        # False on first check, True after one iteration.
        calls["n"] += 1
        return calls["n"] > 1

    run(store, notify, sleep=lambda _: None, now=clock.now, stop=stop)


def test_run_fires_due_alarm(tmp_path):
    store = Store(tmp_path / "a.json")
    store.save(State(alarms=[Alarm(time="09:00", repeat=Repeat.DAILY)]))
    fired = []
    clock = FakeClock([datetime(2026, 6, 16, 9, 0, 5)])

    _run_once(store, fired.append, clock)

    assert [a.time for a in fired] == ["09:00"]


def test_run_skips_disabled_alarm(tmp_path):
    store = Store(tmp_path / "a.json")
    store.save(State(alarms=[Alarm(time="09:00", repeat=Repeat.DAILY, enabled=False)]))
    fired = []
    clock = FakeClock([datetime(2026, 6, 16, 9, 0, 5)])

    _run_once(store, fired.append, clock)

    assert fired == []


def test_run_skips_alarm_not_due(tmp_path):
    store = Store(tmp_path / "a.json")
    store.save(State(alarms=[Alarm(time="10:00", repeat=Repeat.DAILY)]))
    fired = []
    clock = FakeClock([datetime(2026, 6, 16, 9, 0, 5)])

    _run_once(store, fired.append, clock)

    assert fired == []


def test_once_alarm_disabled_and_persisted_after_firing(tmp_path):
    store = Store(tmp_path / "a.json")
    store.save(State(alarms=[Alarm(time="09:00", repeat=Repeat.ONCE)]))
    clock = FakeClock([datetime(2026, 6, 16, 9, 0, 5)])

    _run_once(store, lambda a: None, clock)

    reloaded = store.load()
    assert reloaded.alarms[0].enabled is False


def test_alarm_fires_only_once_within_same_minute(tmp_path):
    store = Store(tmp_path / "a.json")
    store.save(State(alarms=[Alarm(time="09:00", repeat=Repeat.DAILY)]))
    fired = []
    # Two ticks in the same minute.
    clock = FakeClock([
        datetime(2026, 6, 16, 9, 0, 5),
        datetime(2026, 6, 16, 9, 0, 40),
    ])
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 2

    run(store, fired.append, sleep=lambda _: None, now=clock.now, stop=stop)

    assert len(fired) == 1
