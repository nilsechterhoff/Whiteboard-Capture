---
status: "proposed"
date: 2026-10-12
decision-makers: Nils Echterhoff
consulted: Claude (AI assistant)
---

# Store captured images in a synced Nextcloud folder

## Context and Problem Statement

The main use case is near-live: Nils brainstorms at the whiteboard while talking to Claude (for example in voice mode), and Claude must see what was just drawn to follow, correct and build on it. Writing one new element (a bullet point, a to-do) takes at least ~20 s.
The images must be readable by every Claude instance: Claude Code in the terminal, Claude Code in the cloud, and Claude chat/voice in the desktop and mobile apps. ADR-0002 kept them in a local folder on the Mac, which only a session on that Mac can read.
Where should the captured images live so that every Claude instance can read the latest frame, and at what interval?

## Decision Drivers

* Every Claude instance reads the latest frame the same way
* Near-live: a new element on the board is visible within ~30 s
* Keep complexity low; reuse what already runs (Nextcloud desktop client on the Mac)
* Storage stays bounded for years; no ever-growing history

## Considered Options

* Synced Nextcloud folder, written by the capture script
* Images committed to the GitHub repository (every frame, or a separate `captures` branch)
* Images pushed to GitHub only on change (pixel-difference detection), on request, or hourly
* Local folder on the Mac only (status quo of ADR-0002)

## Decision Outcome

Chosen option: "Synced Nextcloud folder, written by the capture script", because it is the only option that gives every Claude instance the latest frame while keeping storage bounded and adding no new software: the Nextcloud desktop client already syncs the folder.

Details:

* Capture folder: `~/Library/CloudStorage/Nextcloud-cloud.echterhoff.dk-nilsechterhoff/Services/Whiteboard Capture/`
* Three parallel subfolders with the same structure: `latest/` (one file, `latest.jpg`, overwritten), `hourly/` (keep 12), `daily/` (keep 7). `status.txt` and `capture.request` stay at the folder root.
* Live interval: **30 s** (was 10 s in ADR-0002).
* Images stay **out of version control**; the repository holds only code and documents.
* Claude instances read the folder through Nextcloud, for example via a Nextcloud MCP server (to be decided separately).

This changes two details of ADR-0002 (interval 10 s → 30 s; `latest.jpg` moves into `latest/`) and its storage location. ADR-0002's service design (launchd, `imagesnap`, tiers, status file) is unchanged.

### Consequences

* Good, because any device or service with Nextcloud access sees the latest frame within ~30 s plus sync time.
* Good, because storage stays at about 20 files; Nextcloud prunes its own file versions automatically.
* Good, because the Git repository stays small and only holds code and documents.
* Bad, because cloud Claude instances need a way into Nextcloud (an MCP server or similar), which is not set up yet.
* Bad, because sync adds a few seconds of delay, and the launchd service may need a one-time macOS permission to write into the Nextcloud folder.
* Neutral, because Nextcloud keeps a version of `latest.jpg` at most every 2 minutes; upload during sessions is ~30–40 MB per hour, fine on the LAN.

### Confirmation

On the Mac: after install, `status.txt` shows `OK` and `latest/latest.jpg` updates every ~30 s; the same file appears in the Nextcloud web interface within seconds. The repository contains no image files.

## Pros and Cons of the Options

### Synced Nextcloud folder

* Good, because no new software: the Nextcloud desktop client already runs and syncs the folder.
* Good, because only the latest frame plus a small bounded history exist.
* Bad, because cloud Claude instances need a separate way into Nextcloud.

### Images in the GitHub repository

* Good, because every Claude instance already reaches GitHub.
* Bad, because Git never forgets: at 30 s, a two-hour session adds over 100 MB of permanent history, past GitHub's comfort zone within weeks.
* Bad, because there is no way to keep a file in the repository but out of version control; workarounds (force-overwriting a branch) fight the tool.

### GitHub push on change, on request or hourly

* Good, because far fewer commits.
* Bad, because change detection cannot reliably tell writing from light changes (sun, clouds, people walking past) without extra complexity.
* Bad, because frames are up to an hour old, which fails the near-live use case.

### Local folder only

* Good, because simplest.
* Bad, because only a Claude session on the Mac can read the images.

## More Information

* Decided in the session of 2026-10-12, after comparing GitHub and Nextcloud options.
* Related: ADR-0002 (capture service), ADR-0003 (folder + trigger file).
* Follow-up in the backlog: choose and set up the Nextcloud access for Claude instances (MCP server).
