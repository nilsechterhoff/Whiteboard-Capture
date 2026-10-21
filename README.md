# Whiteboard-Capture

Captures the current state of a **120 × 90 cm whiteboard** so Claude can read, summarize and build on it during and between whiteboard sessions, near-live (every ~20 s).

**Pipeline:** Logitech C930e (USB) → one open ffmpeg stream, supervised by `script/wbcapture.sh` (launchd) → **Nextcloud folder** on the Mac → Nextcloud sync → any Claude instance reads it.

## Status

| Line # | Item | Status |
|---|---|---|
| 1 | Concept and hardware | Chosen and tested (see [handoff](project/handover/handoff-2026-10-12.md)) |
| 2 | Capture service | Rebuilt around one open ffmpeg stream (ADR-0006, proposed); tested with a stubbed ffmpeg (29/29); **not yet run on the Mac** |
| 3 | ADRs 0001–0003 | `accepted` (2026-10-12) |
| 4 | ADR-0004 (Nextcloud storage, 30 s) | `accepted` (2026-10-12) |
| 5 | ADR-0005 (20 s interval) | `accepted` (2026-10-12) |
| 6 | Next steps | [project/backlog.md](project/backlog.md) |

## Where things live

| Line # | What | Where |
|---|---|---|
| 1 | Repository on the Mac | `~/Developer/NE_Whiteboard Capture/` |
| 2 | Captured images | `~/Library/CloudStorage/Nextcloud-cloud.echterhoff.dk-nilsechterhoff/Services/Whiteboard Capture/` |
| 3 | Service log | `~/Library/Logs/whiteboard-capture.log` |

Images are **not** in Git (ADR-0004). The repo is **not** in `~/Documents`: macOS blocks the launchd service from reading files there.

## Quick start (on the Mac)

```sh
brew install ffmpeg
ffmpeg -hide_banner -f avfoundation -list_devices true -i ""   # check the camera serial (C930e: 7B5E845E)
project/setup/install.sh           # default capture folder: the Nextcloud folder above
```

On first start macOS may ask for **camera access** and for **access to Nextcloud files**. Allow both once. Remove with `project/setup/uninstall.sh`. Step-by-step instructions for a Claude Code session: [project/handover/claude-code-install-instructions.md](project/handover/claude-code-install-instructions.md).

## Capture folder

| Line # | Path | Meaning |
|---|---|---|
| 1 | `status.txt` | Read first: `OK 2026-10-12 16:31:05`, or `CAMERA_NOT_FOUND` / `CAPTURE_FAILED` / `STOPPED` + time |
| 2 | `latest/latest.jpg` | One file, overwritten every **20 s** while the camera is present |
| 3 | `hourly/YYYY-MM-DD_HH.jpg` | First frame of each hour, last **12** kept |
| 4 | `daily/YYYY-MM-DD.jpg` | First frame of each day, last **7** kept |
| 5 | `capture.request` | Agent creates it → fresh frame within ~1–2 s → service deletes it |
| 6 | `session.on` | Reserved for session mode (not built yet, see backlog) |

## Configuration

Environment variables, set in the launchd plist (`install.sh` fills folder and paths).

| Line # | Variable | Default | Purpose |
|---|---|---|---|
| 1 | `WBC_DIR` | the Nextcloud folder above | Capture folder |
| 2 | `WBC_CAMERA_SERIAL` | `7B5E845E` | Serial of the camera, as listed by ffmpeg `-list_devices` (the C930e; two are connected) |
| 3 | `WBC_LIVE_INTERVAL` | `20` | Seconds between live frames |
| 4 | `WBC_POLL` | `1` | Loop tick in seconds (trigger-file latency) |
| 5 | `WBC_CAMERA_RETRY` | `5` | Seconds between camera checks when absent |
| 6 | `WBC_KEEP_HOURLY` / `WBC_KEEP_DAILY` | `12` / `7` | Retention per tier |
| 7 | `WBC_FFMPEG` | `ffmpeg` on PATH | ffmpeg binary; set a full path if it is not on PATH |
| 8 | `WBC_STALL_LIMIT` | `60` | ffmpeg is restarted if no new frame arrives within this many seconds |
| 9 | `WBC_FAIL_RETRY` | `30` | Seconds to wait after a failed capture before trying again |
| 10 | `WBC_TMP` | `/tmp` | Scratch folder for the raw frame and the single-instance lock |

## Repository layout

| Line # | Path | Holds |
|---|---|---|
| 1 | `script/` | Capture script `wbcapture.sh` and `tests/` (stubbed camera, runs on Linux or macOS) |
| 2 | `project/setup/` | `install.sh`, `uninstall.sh`, launchd plist template |
| 3 | `project/handover/` | Concept handoff, Claude Code install instructions |
| 4 | `project/backlog.md` | Open items and tasks |
| 5 | `docs/decisions/` | ADRs (location required by STD-001) |

## Standards

This project follows [nilsechterhoff/standards](https://github.com/nilsechterhoff/standards) and links to it instead of copying (STD-000, R4).

| Line # | Standard | Applied as |
|---|---|---|
| 1 | [STD-000 Standards Governance](https://github.com/nilsechterhoff/standards/blob/main/meta/standards-governance.md) | Links, not copies; project instances live here |
| 2 | [STD-001 ADRs (MADR 4.0.0)](https://github.com/nilsechterhoff/standards/blob/main/methods/adr.md) | `docs/decisions/` |

## Decisions

| Line # | ADR | Title | Status |
|---|---|---|---|
| 1 | 0001 | [Capture with the APEMAN A70 over USB on the MacBook](docs/decisions/0001-capture-with-apeman-a70-over-usb-on-the-macbook.md) | accepted |
| 2 | 0002 | [Run capture as a launchd agent with tiered retention](docs/decisions/0002-run-capture-as-a-launchd-agent-with-tiered-retention.md) | accepted |
| 3 | 0003 | [Integrate the agent through a shared folder and trigger file](docs/decisions/0003-integrate-the-agent-through-a-shared-folder-and-trigger-file.md) | accepted |
| 4 | 0004 | [Store captured images in a synced Nextcloud folder](docs/decisions/0004-store-captured-images-in-a-synced-nextcloud-folder.md) | accepted |
| 5 | 0005 | [Capture live frames every 20 seconds](docs/decisions/0005-capture-live-frames-every-20-seconds.md) | accepted |
| 6 | 0006 | [Capture from an open camera stream](docs/decisions/0006-capture-from-an-open-camera-stream.md) | proposed |
