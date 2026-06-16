# alarm-clock

A simple, local, CLI-only alarm clock. No web UI, no database, no background
daemon — just a Python package you run in a terminal.

- 24-hour local time (`HH:MM`), no timezones or DST.
- Repeat policies: `once`, `daily`, `weekdays` (Mon–Fri).
- Alarms persist to a single JSON file at `~/alarm_clock.json`.
- Banner + sound notification (custom mp3, falling back to the terminal bell).
- A fast-forward mode with a live ASCII countdown so you can test without
  waiting for real time.

## Requirements

- Python 3.14+
- For mp3 playback, a command-line audio player on `PATH`:
  - macOS: `afplay` (built in)
  - Linux: one of `mpg123`, `ffplay`, `mpv`, `cvlc`, `paplay`, `aplay`

Without a player (or a valid sound file) the alarm falls back to the terminal
bell `\a`.

## Install

No packaging is required — run it as a module from the repo root:

```bash
python -m alarm_clock --help
```

(The repo ships a `.venv`; use `.venv/bin/python -m alarm_clock ...` if you
prefer that interpreter.)

## Usage

```
alarm-clock add --time HH:MM [--repeat {once,daily,weekdays}]
alarm-clock list
alarm-clock rm <id>
alarm-clock mp3 <path>
alarm-clock run [--now HH:MM:SS]
```

### add

```bash
python -m alarm_clock add --time 09:00 --repeat daily
```

`--repeat` defaults to `once`. Invalid times are rejected with an error and a
non-zero exit code; nothing is written.

### list

```bash
python -m alarm_clock list
```

Shows a short id, time, repeat, and status. Prints a helpful message when there
are no alarms.

### rm

```bash
python -m alarm_clock rm 1a2b3c4d
```

Accepts a **unique id prefix**, so you don't have to type the full UUID (copy a
short id from `list`). Unknown or ambiguous ids produce a friendly message and a
non-zero exit code.

### mp3

```bash
python -m alarm_clock mp3 ~/sounds/wake.mp3
```

Sets the single global sound used by all alarms. Warns if the path doesn't
exist but still saves it.

### run

```bash
python -m alarm_clock run
```

Runs the scheduler loop against the system clock (foreground). Polls once per
second and fires due alarms. Press **Ctrl-C** to stop; Ctrl-C also stops a sound
that is currently playing.

#### Fast-forward demo (`--now`)

To test an alarm without waiting for the real time, simulate a starting clock
and let it fast-forward, watching a live ASCII countdown to the next alarm:

```bash
python -m alarm_clock add --time 09:05 --repeat once
python -m alarm_clock run --now 09:03:30
```

```
⏰ next 09:05 (once)  in 00:01:30  [#########---------------]
```

The countdown updates in place; when it reaches zero the banner and sound (or
bell) fire and the simulation exits. Ctrl-C stops at any point.

## How it works

| Module | Responsibility |
|--------|----------------|
| `alarm.py` | `Alarm` data model + `Repeat` enum and validation. |
| `store.py` | Load/save `~/alarm_clock.json` (`Store`/`State`). |
| `scheduler.py` | Pure `next_fire_time(alarm, now)` + the polling `run()` loop. |
| `notifier.py` | Banner + sound subprocess, with bell fallback. |
| `cli.py` | argparse front end, simulated clock, ASCII countdown. |

Behavior notes:

- An alarm has no date. Its fire time is the **next** occurrence of `HH:MM`: if
  the time has already passed today, it rolls to tomorrow (`weekdays` lands on
  the next Mon–Fri).
- A `once` alarm is disabled (kept, not deleted) after it fires; `daily` and
  `weekdays` re-arm for their next occurrence.
- Each alarm fires at most once per minute. State is reloaded each tick, so
  edits made while `run` is active are picked up live.
- Saves are atomic (temp file + replace). A missing store yields empty state; a
  corrupt store yields empty state with a warning and is left untouched so you
  can recover it.

### Storage format

`~/alarm_clock.json`:

```json
{
  "sound": "/path/to/sound.mp3",
  "alarms": [
    { "id": "…uuid…", "time": "09:00", "repeat": "daily", "enabled": true }
  ]
}
```

## Out of scope

Missed alarms while not running, snooze, multiple/per-alarm sounds, timezones
and DST, and sub-minute precision are intentionally not supported.

## Tests

```bash
.venv/bin/python -m pytest
```

Scheduler tests cover `next_fire_time` (today vs. tomorrow, current-minute edge,
midnight rollover, weekday skipping) and the `run` loop (firing, disabled/not-due
skips, once-disable persistence, and the once-per-minute guard).
