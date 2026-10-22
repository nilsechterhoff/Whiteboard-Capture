# Backlog

Tasks and open ideas (not decisions; decisions go to `docs/decisions/` per STD-001).

| Line # | ID | Item | Owner | Status |
|---|---|---|---|---|
| 1 | BL-001 | Build capture script and launchd config | Claude | Done (tested with stub) |
| 2 | BL-002 | On the Mac: install `imagesnap`, check camera name, run `project/setup/install.sh`, grant camera and Nextcloud-folder access ([instructions](handover/claude-code-install-instructions.md)) | Nils + Claude Code | Parked (timed pipeline; MVP B is the main path, ADR-0007 proposed) |
| 3 | BL-003 | Connect the capture folder to the Claude desktop app; test `capture.request` | Nils + Claude | Parked (superseded by the Dropbox loop, ADR-0007 proposed) |
| 4 | BL-004 | Build the arm mount above the board (~1 m); fix exposure with angle or lamp | Nils | Open |
| 5 | BL-005 | Decide: live tier syncs to Nextcloud or stays local | Nils | Done: Nextcloud (ADR-0004) |
| 6 | BL-006 | Review and accept ADR-0001 to ADR-0003 | Nils | Done (2026-10-12) |
| 7 | BL-007 | Session mode: `session.on` → change-only captures | – | Idea |
| 8 | BL-008 | Image cleanup: fisheye/perspective and white balance (OpenCV), only if accuracy suffers | – | Idea |
| 9 | BL-009 | Background analyzer agent on hourly/daily history | – | Idea |
| 10 | BL-010 | Upgrade path: local MCP server `capture_whiteboard` (see ADR-0003) | – | Idea |
| 11 | BL-011 | Review and accept ADR-0004 (Nextcloud storage, 30 s interval) | Nils | Done (2026-10-12) |
| 12 | BL-012 | Choose and set up Nextcloud access for all Claude instances (e.g. Nextcloud MCP server) → ADR | Nils + Claude | Parked (MVP B uses Dropbox) |
| 13 | BL-013 | Remove the earlier test copies in `~/Claude/` | Claude | Done (2026-10-12) |
| 14 | BL-014 | Move the repo to `~/Developer/NE_Whiteboard Capture/` (launchd cannot read `~/Documents`) and reinstall the service | Nils + Claude Code | Open |
| 15 | BL-015 | Review and accept ADR-0005 (20 s interval) | Nils | Done (2026-10-12) |
| 16 | BL-016 | **MVP B:** build the describe step: headless Claude Code takes the photo `Images/image-NNNN.jpg` and writes `Descriptions/description-NNNN.md`; verify image input and subscription use first | Claude Code + Nils | Open (main path, [brief](handover/brief-build-mvp-b-watcher.md)) |
| 17 | BL-017 | **MVP B:** build the watcher (Python, Dropbox API long-poll, takes the photo, uploads it, starts the describe step, writes the description last); background service on the Mac | Claude Code + Nils | Open (main path, [brief](handover/brief-build-mvp-b-watcher.md)) |
| 18 | BL-018 | **MVP B:** measure request-to-description delay end to end; tune the 10 s count | Nils + Claude | Open |
| 19 | BL-019 | Review and accept ADR-0006 and ADR-0007; on acceptance mark ADR-0002, ADR-0003, ADR-0005 as superseded by ADR-0007 | Nils | Done (2026-10-22) |
| 20 | BL-020 | Decide the camera (ADR-0001 names the A70; new camera works) and where raw photos are kept → ADR. Facts so far: [lessons-and-camera-facts](lessons-and-camera-facts.md). The camera ADR will be 0009 once a real photo works | Nils + Claude | Open |
| 21 | BL-021 | MVP B: `mode: diff` (compare with previous request) | – | Idea (placeholder in request format) |
| 22 | BL-022 | **MVP B:** setup script: Dropbox OAuth with refresh token (app "Whiteboard-Capture", app folder); secrets stay out of chat and Git | Claude Code + Nils | Open |
| 23 | BL-023 | **MVP B:** after the first authorization, move `/Whiteboard` into `/Apps/Whiteboard-Capture/`, update `instructions.md` paths, test in voice that the connector reaches the new folder | Nils + Claude | Open |
| 24 | BL-024 | **MVP B:** Windows port to "Terox" (`ffmpeg` camera, Task Scheduler); design for it now, build later | – | Idea |
