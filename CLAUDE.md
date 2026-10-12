# CLAUDE.md — Whiteboard-Capture

## Standards

Follow [nilsechterhoff/standards](https://github.com/nilsechterhoff/standards). Link to it, never copy it (STD-000, R4).

| Line # | Standard | Rule here |
|---|---|---|
| 1 | [STD-000](https://github.com/nilsechterhoff/standards/blob/main/meta/standards-governance.md) | No method is applied before a standard defines it (R1). Deviations need an ADR here (R5) |
| 2 | [STD-001](https://github.com/nilsechterhoff/standards/blob/main/methods/adr.md) | Decisions go to `docs/decisions/` from the MADR 4.0.0 `adr-template.md`. Claude writes `proposed`; only Nils sets `accepted` |

Tasks and open ideas go to `docs/backlog.md`, not into ADRs.

## Reading the whiteboard (agent procedure)

| Line # | Step | Detail |
|---|---|---|
| 1 | Read `status.txt` | Not `OK` → tell Nils (camera unplugged, off, or in mass storage mode) |
| 2 | Need a fresh frame? | Create an empty `capture.request`, wait ~2–3 s, re-read until the file is gone |
| 3 | Read `latest.jpg` | Flag it if its timestamp is older than ~1 min |
| 4 | History | `hourly/` (last 12 h), `daily/` (last 7 days) |

Image quality notes: moderate fisheye at the corners; exposure may be dim with a yellow cast when the doorway is in frame.
