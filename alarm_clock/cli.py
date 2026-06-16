"""Command-line interface: add / list / rm / mp3 / run.

``run`` polls the real clock. ``run --now HH:MM:SS`` fast-forwards a simulated
clock so alarms can be demoed without waiting, drawing a live ASCII countdown
to the next alarm.

Manual testing
--------------
The store lives at ``~/alarm_clock.json``. To avoid touching your real file,
point HOME at a throwaway directory for the whole session::

    export HOME=$(mktemp -d)
    PY=.venv/bin/python      # interpreter with this package importable

Run commands as a module::

    $PY -m alarm_clock list                      # -> "No alarms set." message
    $PY -m alarm_clock add --time 09:00 --repeat daily
    $PY -m alarm_clock add --time 25:99          # -> error, exit code 2
    $PY -m alarm_clock add --time 07:30          # repeat defaults to once
    $PY -m alarm_clock list                       # shows short ids + status
    $PY -m alarm_clock rm 1a2b3c                   # prefix of an id from `list`
    $PY -m alarm_clock rm nope                     # -> friendly error, exit 1
    $PY -m alarm_clock mp3 /path/to/sound.mp3      # warns if path missing

Fast-forward demo (no waiting for wall-clock time). Add an alarm a minute or
two after your chosen --now, then watch the ASCII countdown tick down and fire::

    $PY -m alarm_clock add --time 09:05 --repeat once
    $PY -m alarm_clock run --now 09:03:30

The countdown updates in place; the banner + sound (or terminal bell) fire when
it reaches zero, then the simulation exits. Ctrl-C stops at any point.

Real-time mode just runs the loop against the system clock::

    $PY -m alarm_clock run            # Ctrl-C to stop
"""

from __future__ import annotations

import argparse
import sys
import time as _time
from datetime import datetime, timedelta

from .alarm import Alarm, Repeat, ValidationError
from .notifier import Notifier
from .scheduler import next_fire_time, run
from .store import State, Store

# Real seconds slept per simulated tick in --now mode (keeps the demo snappy).
_SIM_REAL_SLEEP = 0.03


# --- simulated clock & countdown -----------------------------------------

class SimulatedClock:
    """Advances by a fixed step every time it is read."""

    def __init__(self, start: datetime, step_seconds: int = 1) -> None:
        self._t = start
        self._step = timedelta(seconds=step_seconds)

    def now(self) -> datetime:
        t = self._t
        self._t = t + self._step
        return t


class CountdownRenderer:
    """Draws an in-place ASCII countdown to the soonest enabled alarm."""

    _BAR_WIDTH = 24

    def __init__(self, stream=None) -> None:
        self.stream = stream if stream is not None else sys.stdout
        self._total: timedelta | None = None
        self._drew = False

    def __call__(self, current: datetime, state: State) -> None:
        upcoming = [a for a in state.alarms if a.enabled]
        if not upcoming:
            self._write("\r(no enabled alarms — waiting)        ")
            return

        target, fire_at = min(
            ((a, next_fire_time(a, current)) for a in upcoming),
            key=lambda pair: pair[1],
        )
        remaining = fire_at - current
        if remaining.total_seconds() < 0:
            remaining = timedelta(0)

        if self._total is None or remaining > self._total:
            self._total = remaining if remaining.total_seconds() else timedelta(seconds=1)

        elapsed = self._total - remaining
        frac = max(0.0, min(1.0, elapsed / self._total)) if self._total else 1.0
        filled = int(round(frac * self._BAR_WIDTH))
        bar = "#" * filled + "-" * (self._BAR_WIDTH - filled)

        self._write(
            f"\r⏰ next {target.time} ({target.repeat.value})  "
            f"in {_fmt(remaining)}  [{bar}]"
        )

    def finish(self) -> None:
        if self._drew:
            self.stream.write("\n")
            self.stream.flush()

    def _write(self, text: str) -> None:
        self.stream.write(text)
        self.stream.flush()
        self._drew = True


def _fmt(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


# --- commands -------------------------------------------------------------

def _cmd_add(args: argparse.Namespace, store: Store) -> int:
    try:
        alarm = Alarm(time=args.time, repeat=Repeat.parse(args.repeat))
    except ValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    state = store.load()
    state.alarms.append(alarm)
    store.save(state)
    print(f"added alarm {alarm.id}  {alarm.time}  ({alarm.repeat.value})")
    return 0


def _cmd_list(args: argparse.Namespace, store: Store) -> int:
    state = store.load()
    if not state.alarms:
        print("No alarms set. Add one with:  alarm-clock add --time HH:MM")
        return 0

    print(f"{'ID':10}  {'TIME':5}  {'REPEAT':8}  STATUS")
    for a in state.alarms:
        status = "on" if a.enabled else "off"
        print(f"{a.id[:8]:10}  {a.time:5}  {a.repeat.value:8}  {status}")
    return 0


def _cmd_rm(args: argparse.Namespace, store: Store) -> int:
    state = store.load()
    matches = [a for a in state.alarms if a.id.startswith(args.id)]

    if not matches:
        print(f"no alarm matches id '{args.id}'. Try `list` to see ids.", file=sys.stderr)
        return 1
    if len(matches) > 1:
        ids = ", ".join(a.id[:8] for a in matches)
        print(f"id '{args.id}' is ambiguous: matches {ids}", file=sys.stderr)
        return 1

    target = matches[0]
    state.alarms = [a for a in state.alarms if a.id != target.id]
    store.save(state)
    print(f"removed alarm {target.id}  {target.time}")
    return 0


def _cmd_mp3(args: argparse.Namespace, store: Store) -> int:
    state = store.load()
    state.sound = args.path
    store.save(state)
    print(f"sound set to {args.path}")
    from pathlib import Path

    if not Path(args.path).exists():
        print(f"warning: {args.path} does not exist yet", file=sys.stderr)
    return 0


def _cmd_run(args: argparse.Namespace, store: Store) -> int:
    notifier = Notifier(store.load().sound)
    renderer = CountdownRenderer()

    if args.now is not None:
        try:
            t = datetime.strptime(args.now, "%H:%M:%S").time()
        except ValueError:
            print(f"error: invalid --now '{args.now}': expected HH:MM:SS", file=sys.stderr)
            return 2
        start = datetime.combine(datetime.now().date(), t)
        clock = SimulatedClock(start)
        fired = {"done": False}

        def notify(alarm: Alarm) -> None:
            renderer.finish()
            notifier.notify(alarm)
            fired["done"] = True

        print(f"simulating from {args.now} (fast-forward)...")
        try:
            run(
                store, notify,
                sleep=lambda _: _time.sleep(_SIM_REAL_SLEEP),
                now=clock.now,
                stop=lambda: fired["done"],
                on_tick=renderer,
            )
        except KeyboardInterrupt:
            renderer.finish()
            print("stopped.")
        return 0

    # Real-time mode.
    print("alarm-clock running. Press Ctrl-C to stop.")
    try:
        run(store, notifier.notify, on_tick=renderer)
    except KeyboardInterrupt:
        renderer.finish()
        print("stopped.")
    return 0


# --- argument parsing -----------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alarm-clock", description="A simple CLI alarm clock.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="add an alarm")
    p_add.add_argument("--time", required=True, help="24-hour HH:MM")
    p_add.add_argument(
        "--repeat", default=Repeat.ONCE.value,
        choices=[r.value for r in Repeat], help="repeat policy (default: once)",
    )
    p_add.set_defaults(func=_cmd_add)

    sub.add_parser("list", help="list alarms").set_defaults(func=_cmd_list)

    p_rm = sub.add_parser("rm", help="remove an alarm by id (prefix ok)")
    p_rm.add_argument("id", help="alarm id or unique prefix")
    p_rm.set_defaults(func=_cmd_rm)

    p_mp3 = sub.add_parser("mp3", help="set the default sound file")
    p_mp3.add_argument("path", help="path to an mp3 (or other) sound file")
    p_mp3.set_defaults(func=_cmd_mp3)

    p_run = sub.add_parser("run", help="run the scheduler loop")
    p_run.add_argument(
        "--now", metavar="HH:MM:SS",
        help="simulate from this time and fast-forward (for testing)",
    )
    p_run.set_defaults(func=_cmd_run)

    return parser


def main(argv: "list | None" = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = Store()
    return args.func(args, store)


if __name__ == "__main__":
    sys.exit(main())
