---
status: "proposed"
date: 2026-10-12
decision-makers: Nils Echterhoff
consulted: Claude (AI assistant)
---

# Run capture as a launchd agent with tiered retention

## Context and Problem Statement

The A70 is attached to the MacBook over USB (ADR-0001). Frames must be taken automatically, stay current during sessions, keep some history, and not fill the disk or the Nextcloud quota. The camera may be unplugged, switched off or in mass storage mode at any time.
How should frames be captured, stored and pruned on the Mac?

## Decision Drivers

* Runs unattended from login, survives the camera coming and going
* The agent must see whether capture works before trusting an image
* Bounded storage (about 20 files), no manual cleanup
* Minimal dependencies, quick to set up (~15–20 min)

## Considered Options

* launchd agent running a shell loop with `imagesnap`, GFS-style tiers
* ffmpeg (avfoundation) instead of `imagesnap`
* A70's built-in timelapse to its SD card, copied off periodically
* cron / launchd `StartInterval` job (one shot per run)

## Decision Outcome

Chosen option: "launchd agent running a shell loop with `imagesnap`, GFS-style tiers", because it is the only option that combines always-on, a ~1 s reaction to trigger files, a status file, and automatic pruning with a single Homebrew dependency.

Tiers: `latest.jpg` every 10 s; `hourly/` first frame per hour, keep 12; `daily/` first frame per day, keep 7; pruned after each save. `status.txt` states `OK`, `CAMERA_NOT_FOUND` or `CAPTURE_FAILED` with a timestamp.

### Consequences

* Good, because the service restarts itself (`KeepAlive`) and idles while the camera is absent.
* Good, because storage stays at about 20 files.
* Bad, because `latest.jpg` every 10 s means ~100 MB/hour of upload if the live tier syncs to Nextcloud (acceptable on LAN; open in backlog).
* Bad, because the camera permission is granted to the shell/process, which can need a re-grant after macOS updates.

### Confirmation

`tests/test_wbcapture.sh` runs the service against a stubbed `imagesnap` and checks the tiers, pruning, trigger file and status. On the Mac: unplug the camera → `status.txt` shows `CAMERA_NOT_FOUND` within ~5 s.

## Pros and Cons of the Options

### launchd + shell loop + `imagesnap`

* Good, because one small dependency and native macOS service management.
* Bad, because the loop keeps a process running at all times (negligible load).

### ffmpeg (avfoundation)

* Good, because powerful (could also crop or correct later).
* Bad, because heavier and more complex for single frames.

### A70 timelapse to SD card

* Good, because no host software for capturing.
* Bad, because files sit on the SD card; only reachable in mass storage mode, which disables PC camera mode.

### One-shot launchd/cron job

* Good, because no long-running process.
* Bad, because no fast reaction to `capture.request` (minimum interval too coarse).

## More Information

* Source: [handoff 2026-10-12](../handoff-2026-10-12.md), section 7.
* Session mode (`session.on`, change-only captures) and image correction (OpenCV) are deferred to the backlog.
