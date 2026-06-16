# Alarm Clock — SPEC

A simple, local, CLI-only alarm clock. No web UI, no database, no daemon.
This document is the source of truth. Build against it.

## Scope & non-goals

- CLI only, single user, single machine.
- Local wall-clock time only. **No timezones, no DST handling.**
- No background daemon. Alarms only fire while `run` is in the foreground.
- No persistence engine beyond a single JSON file.

## Concepts

### Time model

- Times are stored and entered as `HH:MM` in **24-hour format** (`00:00`–`23:59`).
- All comparisons use the system local clock.
- An alarm has no date. The fire time is always the **next** occurrence of `HH:MM`:
  - If `HH:MM` is still ahead today → fires today.
  - If `HH:MM` has already passed today → fires tomorrow.
- Granularity is one minute. An alarm fires once when local time enters its target minute.

### Alarm

| Field     | Type   | Notes                                            |
|-----------|--------|--------------------------------------------------|
| `id`      | str    | UUID4, generated on add.                         |
| `time`    | str    | `HH:MM`, validated.                              |
| `repeat`  | enum   | `once` \| `daily` \| `weekdays`                  |
| `enabled` | bool   | Default `true`.                                  |

- `weekdays` = Monday–Friday (local day-of-week).
- After a `once` alarm fires, it is set `enabled = false` (kept in the file, not deleted).
- `daily` / `weekdays` re-arm for their next valid occurrence after firing.

### Sound

- One **global** default sound path, stored in the JSON file (see Store).
- If unset, or the file is missing/invalid → fall back to the terminal bell `\a`.

## Modules

### Alarm
- Plain data object + validation.
- `time` must match `^([01]\d|2[0-3]):[0-5]\d$`; otherwise raise a validation error.
- `repeat` must be one of the three enum values.

### Store
- File: `~/alarm_clock.json`.
- Shape:
  ```json
  { "sound": "/path/to/file.mp3", "alarms": [ {alarm}, ... ] }
  ```
- `load()`:
  - Missing file → return empty default (`{"sound": null, "alarms": []}`).
  - Corrupt / unparseable JSON → **do not crash**. Print a clear warning naming the
    file, and treat as empty (do not overwrite the file automatically).
  - Unknown/extra fields are ignored.
- `save()`: atomic write (write temp file, then `os.replace`) to avoid truncation on crash.

### Scheduler
- `next_fire_time(alarm, now) -> datetime`:
  - Pure function. Given an alarm and `now`, return the next local datetime it should fire.
  - Honors `repeat`: `once`/`daily` → next `HH:MM`; `weekdays` → next Mon–Fri `HH:MM`.
- `run()` loop:
  - Foreground, blocking. `sleep(1)` between ticks.
  - On each tick, for every enabled alarm whose target minute == current minute and which
    has not already fired this minute → trigger the Notifier.
  - Track fired alarms within the current minute to avoid re-firing on every 1s tick.
  - Catch-up / missed alarms (laptop asleep, process not running): **out of scope** — only
    fires alarms while the loop is actively running.
  - `Ctrl-C` exits the loop cleanly.

### Notifier
- On trigger:
  - Print a banner line to stdout (alarm id/time/repeat).
  - Play sound as a **subprocess** (e.g. platform audio player on the global mp3).
  - If no sound configured or playback unavailable → terminal bell `\a`.
- `Ctrl-C` during playback stops the sound subprocess (and, per Scheduler, exits the loop).

### CLI (argparse)
Commands:

- `add --time HH:MM --repeat {once,daily,weekdays}`
  - `--repeat` defaults to `once`.
  - Invalid time → print error, exit non-zero, add nothing.
  - Prints the new alarm's id.
- `list`
  - Empty → print a helpful message (e.g. "No alarms set. Add one with `add`.").
  - Otherwise list id (short form ok), time, repeat, enabled.
- `rm <id>`
  - Unknown id → print a friendly message, exit non-zero, change nothing.
  - id may be matched by unique prefix (full UUID need not be typed).
- `mp3 <path>`
  - Sets the global default sound path.
  - Warn if the path does not exist, but still store it.
- `run`
  - Starts the Scheduler loop (foreground).

## Error handling rules

- Invalid time input → clear error message, non-zero exit, no state change.
- Corrupt JSON → warn and continue with empty state; never crash.
- Removing a non-existent id → friendly message, non-zero exit.
- All user-facing errors go to stderr with a non-zero exit code.

## Out of scope (explicit)

- Missed alarms while not running, snooze, multiple sounds, timezones/DST,
  sub-minute precision, concurrent CLI + run editing the file live.
