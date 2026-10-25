---
status: "proposed"
date: 2026-10-25
decision-makers: Nils Echterhoff
consulted: Claude (AI assistant)
---

# Agile mode: keep the camera and the describe session open while Nils brainstorms

## Context and Problem Statement

The lean path (ADR-0008) takes one photo per request and starts a new describe process each time. A request takes about 22 to 35 s from request to description file, and most of that is camera start-up and the describe step. Nils wants the board to answer quickly during a brainstorming session. Agile mode keeps the camera stream and, in phase 2, the describe session open. BL-028 and the voice agreement of 2026-10-25 describe the idea. This ADR records the decision and the rules; it does not change ADR-0008 yet.

## Decision Drivers

* Shorter time from request to description during an active session
* Lean stays the default: no open camera and no idle process unless Nils wants it
* Reliability first: any failure falls back to the lean path, and failures stay visible in `status.md`
* The camera light and the camera are shared with other apps while open: a cost to accept, not hide
* Config-driven: every parameter has a documented default

## Considered Options

* Lean only (today)
* Agile mode, phase 1: keep the camera stream open; the describe step as today
* Agile mode, phases 1 and 2: keep the camera stream and a long-lived describe session open
* Proactive capture every few seconds (parked)

## Decision Outcome

Chosen option: "agile mode in two phases, lean as the default", because it shortens the time for an active session while keeping the lean path as the fallback and default.

**Modes and timer**

1. `mode: lean | agile`. Default `lean`. Nils's config stays `lean` until he switches.
2. Agile mode wakes up automatically with a request: if the stream is closed, the request opens it.
3. `agile_idle_timeout_seconds` (default 600, i.e. 10 minutes). Idle means no reset event for that long; then the stream closes and the camera is released.
4. `agile_timer_reset_events`: a map from event name to `yes` or `no`. Only `request` exists now, set to `yes`. Other events (for example proactive capture or change detection) are parked and default to `no` when they are added.

**Fallback**

5. If the open stream or the open session fails (checks, errors, timeouts), agile closes it, runs that request once through the lean path, and a successful lean run starts a new agile session. Failures stay visible in `status.md` with the existing error codes.

**Phases**

6. Phase 1: keep the camera stream open in a background process. `get_newest_frame()` in the camera module is the single access point. Rotation, brightness and board-fill checks apply as in lean mode.
7. Phase 2 (only if a test passes): a long-lived describe session accepts each photo as a new message, with a restart after `agile_session_restart_after_requests` requests (default 20) to limit context growth. Config `agile_session: yes | no`, default `no`.

### Consequences

* Good, because an active session skips the camera start-up and, in phase 2, the describe start-up.
* Good, because lean stays the default and every failure falls back to it.
* Bad, because an open camera blocks other apps from using it, and its light stays on while the stream is open. Nils accepts this.
* Bad, because an open session adds a long-lived process that must be cleaned up on service restart (no orphaned ffmpeg or claude processes).
* Neutral, because the timer reset list is in config, so the rules can change without code changes.

### Confirmation

Phase 1 and phase 2 are each measured with five requests, lean versus agile, in the timing CSV format. No numbers are claimed before they are measured.

## Pros and Cons of the Options

### Lean only

* Good, because simple and proven.
* Bad, because every request pays the camera and describe start-up.

### Agile phase 1 only

* Good, because removes the camera start-up from active requests.
* Bad, because the describe start-up remains.

### Agile phases 1 and 2

* Good, because removes both start-ups from active requests.
* Bad, because more moving parts; phase 2 only if its test passes.

### Proactive capture every few seconds (parked)

* Parked: it would reset the timer by itself, which is not wanted yet (timer reset events stay `request` only).

## More Information

* Related: ADR-0008 (watcher and lean path), ADR-0009 (camera selection), BL-028 (agile mode), BL-027 (rotation and board fill).
* Parked ideas: proactive capture, diff mode, change detection as a timer reset.
* Accepted by Nils Echterhoff: pending.
