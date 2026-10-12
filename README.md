# Whiteboard-Capture

Captures the current state of a **120 × 90 cm whiteboard** so an agent (Claude) can read, summarize and work with it during and between whiteboard sessions.

**Pipeline:** APEMAN A70 (USB, PC camera mode) → `wbcapture.sh` (launchd, `imagesnap`) → capture folder on the Mac → (optional sync) Nextcloud → agent reads.

## Status

| Line # | Item | Status |
|---|---|---|
| 1 | Concept and hardware | Chosen and tested (see [handoff](docs/handoff-2026-10-12.md)) |
| 2 | Capture service | Built, tested on Linux with a stubbed camera; **not yet run on the Mac** |
| 3 | ADRs 0001–0003 | `accepted` (2026-10-12) |
| 4 | Next steps | [docs/backlog.md](docs/backlog.md) |

## Quick start (on the Mac)

```sh
brew install imagesnap
imagesnap -l                      # check the A70 name (expected: "NOVATEK J1455")
./install.sh                      # default folder: ~/WhiteboardCapture
./install.sh "$HOME/Nextcloud/WhiteboardCapture"   # or: a synced folder
```

On first start macOS asks for **camera permission** (for the shell running the service). Grant it once. Remove with `./uninstall.sh`.

## Capture folder

| Line # | File | Meaning |
|---|---|---|
| 1 | `status.txt` | Read first: `OK 2026-10-12 16:31:05`, or `CAMERA_NOT_FOUND` / `CAPTURE_FAILED` / `STOPPED` + time |
| 2 | `latest.jpg` | Live tier, overwritten every **10 s** while the camera is present |
| 3 | `hourly/YYYY-MM-DD_HH.jpg` | First frame of each hour, last **12** kept |
| 4 | `daily/YYYY-MM-DD.jpg` | First frame of each day, last **7** kept |
| 5 | `capture.request` | Agent creates it → fresh frame within ~1–2 s → service deletes it |
| 6 | `session.on` | Reserved for session mode (not built yet, see backlog) |

## Configuration

Environment variables, set in the launchd plist (`install.sh` fills folder and paths).

| Line # | Variable | Default | Purpose |
|---|---|---|---|
| 1 | `WBC_DIR` | `~/WhiteboardCapture` | Capture folder |
| 2 | `WBC_CAMERA` | `NOVATEK J1455` | Camera name as listed by `imagesnap -l` |
| 3 | `WBC_LIVE_INTERVAL` | `10` | Seconds between live frames |
| 4 | `WBC_POLL` | `1` | Loop tick in seconds (trigger-file latency) |
| 5 | `WBC_CAMERA_RETRY` | `5` | Seconds between camera checks when absent |
| 6 | `WBC_KEEP_HOURLY` / `WBC_KEEP_DAILY` | `12` / `7` | Retention per tier |
| 7 | `WBC_WARMUP` | `1` | `imagesnap -w` warm-up seconds (exposure settle) |

## Repository layout

| Line # | Path | Holds |
|---|---|---|
| 1 | `src/wbcapture.sh` | Capture service |
| 2 | `launchd/` | launchd agent template |
| 3 | `install.sh`, `uninstall.sh` | Set up / remove the service on the Mac |
| 4 | `tests/` | Test with a stubbed `imagesnap` (runs on Linux or macOS) |
| 5 | `docs/decisions/` | ADRs (STD-001) |
| 6 | `docs/backlog.md` | Open items and tasks |
| 7 | `docs/handoff-2026-10-12.md` | Original concept handoff (source of the design) |

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
