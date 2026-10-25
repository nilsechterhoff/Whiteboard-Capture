---
status: "proposed"
date: 2026-10-25
decision-makers: Nils Echterhoff
consulted: Claude (AI assistant)
---

# Use a time connector as the voice agent's clock

## Context and Problem Statement

The voice agent has no clock or timer. ADR-0007 and ADR-0008 used counting aloud (one number per second) as the stand-in, and the agent checks for the description at 10, 15, ... 40 seconds. Counting is imprecise: in the test of request 0021 the agent counted to 40 while the real description arrived after about 22 seconds, so the count ran slower than the real clock.

Can the voice agent read a real clock, and what does that mean for the "Dropbox only" rule?

## Decision Drivers

* Hands-free voice mode must keep working
* A timer that matches real time, so the check window is reliable
* Few moving parts; no self-hosted connector
* Same setup for a friend or a second machine (user-agnostic, system-agnostic)

## Considered Options

* Keep counting aloud
* Use the hosted "Time Now" connector (`get_current_time`) as the clock
* Self-built time connector

## Decision Outcome

Chosen option: "Use the hosted Time Now connector as the clock", because it was proven in live voice mode on 2026-10-25: the voice agent read the time with seconds, and a "beep, then beep after 10 seconds" test came out at 11 seconds (each lookup takes about 1.5 s).

The voice agent reads the clock right after creating the request (T0) and checks at T0 + 10, 15, 20, ... 40 seconds, without counting aloud. If the connector is unavailable or returns an error, it falls back to counting aloud. The rules live in `instructions.md` in Dropbox (single source of truth).

This bends the earlier constraint "Dropbox only" (mvp-alternatives.md): the Time Now connector becomes a second prerequisite for the voice side, next to the Dropbox connector. It is hosted, read-only and holds no user data, and the counting fallback keeps the system working without it.

### Consequences

* Good, because checks follow real time instead of the speed of speech.
* Good, because the agent can stay quiet while waiting.
* Good, because nothing machine-specific is added: the connector is hosted.
* Bad, because a second connector must be enabled by everyone who sets the tool up (README prerequisites).
* Bad, because each clock read costs about 1.5 s, so a check can be about a second late.
* Neutral, because the 10-to-40 second window is unchanged.

### Confirmation

Run a voice request and check that the agent finds the description without counting and not later than about a second after each check time. Compare with the watcher's stopwatch timings.

## Pros and Cons of the Options

### Keep counting aloud

* Good, because it needs no connector.
* Bad, because the count drifts from real time and the agent keeps talking.

### Hosted Time Now connector

* Good, because it is proven in voice and needs no hosting of our own.
* Bad, because it is another connector prerequisite and each read takes about 1.5 s.

### Self-built time connector

* Good, because it could return exact elapsed time in one call.
* Bad, because it needs hosting; excluded by the MVP constraints.

## More Information

* Tested by Nils and Claude in voice mode on 2026-10-25.
* Related: ADR-0007 (superseded), ADR-0008, `project/mvp-alternatives.md` (constraints).
* Accepted by Nils Echterhoff: pending.
