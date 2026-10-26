# CLAUDE.md — Whiteboard-Capture

## Standards

Follow [nilsechterhoff/standards](https://github.com/nilsechterhoff/standards). Link to it, never copy it (STD-000, R4).

| Line # | Standard | Rule here |
|---|---|---|
| 1 | [STD-000](https://github.com/nilsechterhoff/standards/blob/main/meta/standards-governance.md) | No method is applied before a standard defines it (R1). Deviations need an ADR here (R5) |
| 2 | [STD-001](https://github.com/nilsechterhoff/standards/blob/main/methods/adr.md) | Decisions go to `docs/decisions/` from the MADR 4.0.0 `adr-template.md`. Claude writes `proposed`; only Nils sets `accepted` |

Tasks and open ideas go to `project/backlog.md`, not into ADRs.

## Vocabulary

| Line # | Word | Use for |
|---|---|---|
| 1 | **test** | Build-time work only: test runs we start to learn something or to verify a change, and the test files in the repo. State the hypothesis before each test, and what new hypothesis a failure would trigger. A failed test questions our implementation first, not the underlying concept. |
| 2 | **check** | Anything the finished program does itself at run time, following fixed rules: board check, brightness (dark-frame) check, fill check, status check. A check has a defined result and does not experiment. |

## Locations

| Line # | What | Where |
|---|---|---|
| 1 | Repository on the Mac | `~/Developer/NE_Whiteboard Capture/` |
| 2 | Capture folder (Nextcloud, not in Git) | `~/Library/CloudStorage/Nextcloud-cloud.echterhoff.dk-nilsechterhoff/Services/Whiteboard Capture/` |

Never commit captured images to Git (ADR-0004).

## Current main path

MVP B (Dropbox request/description loop, on demand) is the main path since 2026-10-22: see [project/mvp-alternatives.md](project/mvp-alternatives.md) and ADR-0006/0008 (`accepted`; ADR-0007 superseded), build brief: [project/handover/brief-build-mvp-b-watcher.md](project/handover/brief-build-mvp-b-watcher.md). The voice agent's rules live in `Whiteboard/instructions.md` in Dropbox. The procedure below belongs to the earlier timed pipeline (parked).

## Reading the whiteboard (agent procedure, earlier timed pipeline)

All paths are relative to the capture folder.

| Line # | Step | Detail |
|---|---|---|
| 1 | Read `status.txt` | Not `OK` → tell Nils (camera unplugged, off, or in mass storage mode) |
| 2 | Need a fresh frame? | Create an empty `capture.request`, wait ~2–3 s, re-read until the file is gone (only with write access to the folder) |
| 3 | Read `latest/latest.jpg` | Updated every ~20 s. Flag it if its timestamp is older than ~1 min |
| 4 | History | `hourly/` (last 12 h), `daily/` (last 7 days) |

Image quality notes: moderate fisheye at the corners; exposure may be dim with a yellow cast when the doorway is in frame.
