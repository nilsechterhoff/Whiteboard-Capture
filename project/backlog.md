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
| 16 | BL-016 | **MVP B:** describe step: headless Claude Code reads the photo, first line `whiteboard: yes/no`, then the description. Image input and subscription use verified (no API key); Sonnet chosen | Claude Code + Nils | Done (2026-10-22, [brief](handover/brief-build-mvp-b-watcher.md)) |
| 17 | BL-017 | **MVP B:** watcher (Python, Dropbox API, cameras by index, describe, description written last, timing block and CSV log). Built and run once end to end. Background service: setup step built (`setup_dropbox.py --service`, needs Nils's yes before files are created); camera under launchd: a one-off launchd job got frames, but the room was dark, so a lit-board check is still open | Claude Code + Nils | In progress (2026-10-22, [brief](handover/brief-build-mvp-b-watcher.md)) |
| 18 | BL-018 | **MVP B:** measure request-to-description delay end to end; tune the 10 s count. First run 2026-10-22: about 34 s, above the 10 s target; tuning needs a decision | Nils + Claude | In progress |
| 19 | BL-019 | Review and accept ADR-0006 and ADR-0007; on acceptance mark ADR-0002, ADR-0003, ADR-0005 as superseded by ADR-0007 | Nils | Done (2026-10-22) |
| 20 | BL-020 | Decide the camera and where raw photos are kept → ADR. Chosen for the watcher: ffmpeg (avfoundation) by index, with the Logitech C930e. ffmpeg, not imagesnap, because imagesnap selects by name only and cannot pick one of two identical cameras. No serial or Unique ID lookup; the last working index is only a hint; each camera is tried at most once per request. On the Windows PC Terox there is only one camera. Facts: [lessons-and-camera-facts](lessons-and-camera-facts.md). The camera ADR will be 0009 once a real photo works | Nils + Claude | In progress |
| 21 | BL-021 | MVP B: `mode: diff` (compare with previous request) | – | Idea (placeholder in request format) |
| 22 | BL-022 | **MVP B:** setup script: Dropbox OAuth with refresh token (app "Whiteboard-Capture", app folder); secrets stay out of chat and Git | Claude Code + Nils | Done (2026-10-22: authorized, app folder exists) |
| 23 | BL-023 | **MVP B:** after the first authorization, move the working folders into `/Apps/Whiteboard-Capture/`, update `instructions.md` paths, test in voice that the connector reaches the new folder. Moved 2026-10-22; `instructions.md` deliberately stays at `/Whiteboard/` (user settings point there). Voice test open | Nils + Claude | In progress |
| 24 | BL-024 | **MVP B:** Windows port to "Terox" (`ffmpeg` camera, Task Scheduler); design for it now, build later. Terox needs the equivalent of the launchd setup step (Task Scheduler), with the same config, the same timing log and the same uninstall option | – | Idea |
| 25 | BL-025 | Idea: a Claude Code session connected to Remote Control sends progress messages to the Claude chat (cross-session messaging, plain text, one way). Untested. Test: ask Claude Code to message the chat session. Not part of the voice loop (voice mode cannot receive messages). Each message starts a turn in the chat and uses usage | – | Idea (2026-10-22) |
| 26 | BL-026 | Idea: cut request-to-description time. (1) Warm camera loop: photo every 20 s for 20 min after the last request, so the camera step (about 6 s) is skipped; needs a rule for photo age ("never answer from an older picture") and a new ADR (touches ADR-0008 "photo on demand"). May also avoid black first frames (request-0005, unverified). (2) Open Claude session in the same window to skip Claude's startup. **First step:** time one trivial `claude -p` call without an image to learn the startup share of the 13.5 s describe; build (2) only if the share is large | Nils + Claude | Idea (2026-10-22) |
