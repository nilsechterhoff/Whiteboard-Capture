---
status: "proposed"
date: 2026-10-12
decision-makers: Nils Echterhoff
consulted: Claude (AI assistant)
---

# Capture live frames every 20 seconds

## Context and Problem Statement

ADR-0004 set the live capture interval to 30 s for near-live whiteboard sessions, where Claude follows what Nils draws while they talk. Writing one new element (a bullet point, a to-do) takes at least ~20 s, so at 30 s a new element can be up to ~30 s plus sync time old before Claude sees it.
How often should the service write `latest/latest.jpg`?

## Decision Drivers

* Claude should see a new element on the board about as fast as Nils writes it (~20 s)
* Upload volume to Nextcloud stays acceptable on the LAN
* No change to storage size: `latest/` holds one file, hourly/daily tiers are unaffected

## Considered Options

* 20 s
* 30 s (ADR-0004)
* 10 s (ADR-0002)

## Decision Outcome

Chosen option: "20 s", because it matches the time Nils needs to write one element, so each new element is usually visible in the next frame, while upload stays moderate.

This supersedes only the interval in ADR-0004 (30 s). Everything else in ADR-0004 stays valid.

### Consequences

* Good, because new elements reach Claude about one third faster than at 30 s.
* Good, because storage is unchanged: `latest/latest.jpg` is overwritten, tiers are unaffected.
* Bad, because upload during sessions rises by half compared with 30 s (roughly 50–60 MB per hour instead of 30–40 MB).
* Neutral, because Nextcloud still keeps a file version at most every 2 minutes.

### Confirmation

`WBC_LIVE_INTERVAL` defaults to `20` in `script/wbcapture.sh` and in the launchd template; on the Mac, `latest/latest.jpg` changes every ~20 s.

## Pros and Cons of the Options

### 20 s

* Good, because it matches the ~20 s needed to write one element.
* Bad, because more upload than 30 s.

### 30 s

* Good, because less upload.
* Bad, because a new element can be up to one full interval late.

### 10 s

* Good, because closest to live.
* Bad, because three times the upload of 30 s for little gain at the pace of handwriting.

## More Information

* Requested by Nils on 2026-10-12; implemented in PR #6.
* Related: ADR-0002 (capture service), ADR-0004 (Nextcloud storage, 30 s).
