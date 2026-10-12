# CLAUDE.md — Whiteboard-Capture

## Standards

Follow [nilsechterhoff/standards](https://github.com/nilsechterhoff/standards). Link to it, never copy it (STD-000, R4).

| Line # | Standard | Rule here |
|---|---|---|
| 1 | [STD-000](https://github.com/nilsechterhoff/standards/blob/main/meta/standards-governance.md) | No method is applied before a standard defines it (R1). Deviations need an ADR here (R5) |
| 2 | [STD-001](https://github.com/nilsechterhoff/standards/blob/main/methods/adr.md) | Decisions go to `docs/decisions/` from the MADR 4.0.0 `adr-template.md`. Claude writes `proposed`; only Nils sets `accepted` |

Tasks and open ideas go to `project/backlog.md`, not into ADRs.

## Locations

| Line # | What | Where |
|---|---|---|
| 1 | Repository on the Mac | `~/Developer/NE_Whiteboard Capture/` |
| 2 | Capture folder (Nextcloud, not in Git) | `~/Library/CloudStorage/Nextcloud-cloud.echterhoff.dk-nilsechterhoff/Services/Whiteboard Capture/` |

Never commit captured images to Git (ADR-0004).

## Reading the whiteboard (agent procedure)

All paths are relative to the capture folder.

| Line # | Step | Detail |
|---|---|---|
| 1 | Read `status.txt` | Not `OK` → tell Nils (camera unplugged, off, or in mass storage mode) |
| 2 | Need a fresh frame? | Create an empty `capture.request`, wait ~2–3 s, re-read until the file is gone (only with write access to the folder) |
| 3 | Read `latest/latest.jpg` | Updated every ~20 s. Flag it if its timestamp is older than ~1 min |
| 4 | History | `hourly/` (last 12 h), `daily/` (last 7 days) |

Image quality notes: moderate fisheye at the corners; exposure may be dim with a yellow cast when the doorway is in frame.
