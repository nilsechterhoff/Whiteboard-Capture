---
status: "superseded by ADR-0008"
date: 2026-10-22
decision-makers: Nils Echterhoff
consulted: Claude (AI assistant)
---

# Use a Dropbox request and description loop, on demand

## Context and Problem Statement

ADR-0006 puts an image agent between the board and the voice agent. Voice mode can only act through remote connectors, and the voice agent has no clock and no timer. The camera and image agent must not run all the time (token cost); they should run when Nils asks.
How does a spoken request reach the image agent, and how does the answer get back to voice mode?

## Decision Drivers

* Only the existing Dropbox connector (no new connector, no self-built MCP)
* Event-based, not timed
* The voice agent cannot be pushed to: it acts only when Nils speaks
* The voice agent has no reliable clock, so request and answer must pair without times
* Hands-free: the Dropbox tools used in operation must not ask for approval each time

## Considered Options

* Dropbox request file plus a Mac watcher; description file back in Dropbox
* Google Drive instead of Dropbox
* Gmail as the trigger
* Self-built remote MCP with a "request" tool that waits and returns the text
* Cross-session messaging with a Claude Code session
* Keep the timed capture loop (ADR-0002, ADR-0005) and read the latest description

## Decision Outcome

Chosen option: "Dropbox request file plus a Mac watcher; description file back in Dropbox", because Dropbox reading and writing are proven in voice, it needs no hosting, and it runs only on request.

The loop, in the folder `/Whiteboard` in Dropbox:

1. Nils says "look at the whiteboard". The voice agent follows `/Whiteboard/instructions.md` (one line in Nils's user settings points to it).
2. The voice agent creates `request-NNNN.txt` (running four-digit number, highest existing plus one) with optional fields `marker_color`, `region_v`, `region_h`, `mode`.
3. A watcher on the Mac starts the image agent on the new request: fresh photo, description, then `description-NNNN.md` with the same number, written last.
4. The voice agent counts aloud from 1 to 10, looks once for `description-NNNN.md`, answers from it, or says it is not ready. No retries; it never answers from an older description.

The field definitions live in `instructions.md` in Dropbox (single source of truth); [project/mvp-alternatives.md](../../project/mvp-alternatives.md) summarizes them.

### Consequences

* Good, because it needs only Dropbox and a local script, nothing hosted.
* Good, because nothing runs between requests.
* Good, because one number pairs each request with exactly one description.
* Bad, because the watcher (the "gap") and the image agent are **not built yet**.
* Bad, because Dropbox sync latency eats into the 10 s window; counting aloud is an imprecise timer.
* Bad, because the Dropbox app must run and the Mac must be awake.
* Neutral, because `mode: diff` is only a placeholder; the image agent cannot compare photos yet.

### Confirmation

Tested on 2026-10-22 (voice side only): read a Dropbox file, created `request-0001.txt`, ran the full procedure on `request-0002.txt` and correctly reported "not ready" because no description existed. Still to confirm: the full loop with a real description, the end-to-end delay, and that the "Always allow" setting for list folder, create file and fetch extracted file text holds.

## Pros and Cons of the Options

### Dropbox request file plus a Mac watcher

* Good, because it is proven on the voice side and needs no hosting.
* Bad, because of sync latency and a watcher to build.

### Google Drive instead of Dropbox

* Good, because the same idea works.
* Bad, because it is less proven here and would add a second connector.

### Gmail as the trigger

* Good, because Gmail already works in voice.
* Bad, because it adds a connector, is slower and clunkier.

### Self-built remote MCP with a waiting "request" tool

* Good, because it is the cleanest: one call that waits and returns the text, no counting.
* Bad, because it needs hosting; excluded for the MVP.

### Cross-session messaging with a Claude Code session

* Good, because it is elegant.
* Bad, because it is unproven from voice, and the docs say it carries plain text only.

### Keep the timed capture loop

* Good, because it exists and is tested with a stub.
* Bad, because it runs all the time (token cost) and the description can be stale.

## More Information

* Decided in a voice session with Nils on 2026-10-22.
* **Supersedes:** ADR-0002 (timed launchd capture), ADR-0003 (shared folder and trigger file in Nextcloud), ADR-0005 (20 s interval). Their status changed to "superseded by ADR-0007" when Nils accepted this ADR.
* **Not decided here:** where raw photos are kept (ADR-0004's rule "no images in Git" stays), and the camera (ADR-0001 named the A70; Nils now has a new camera that works).
* Related: ADR-0006.
* Accepted by Nils Echterhoff on 2026-10-22.
* Superseded by ADR-0008 on 2026-10-22 (status change only; the decision text above is unchanged).
