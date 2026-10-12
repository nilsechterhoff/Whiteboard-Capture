# Backlog

Tasks and open ideas (not decisions; decisions go to `docs/decisions/` per STD-001).

| Line # | ID | Item | Owner | Status |
|---|---|---|---|---|
| 1 | BL-001 | Build capture script and launchd config | Claude | Done (tested with stub) |
| 2 | BL-002 | On the Mac: install `imagesnap`, check camera name, run `project/setup/install.sh`, grant camera and Nextcloud-folder access ([instructions](handover/claude-code-install-instructions.md)) | Nils + Claude Code | Open |
| 3 | BL-003 | Connect the capture folder to the Claude desktop app; test `capture.request` | Nils + Claude | Open |
| 4 | BL-004 | Build the arm mount above the board (~1 m); fix exposure with angle or lamp | Nils | Open |
| 5 | BL-005 | Decide: live tier syncs to Nextcloud or stays local | Nils | Done: Nextcloud (ADR-0004) |
| 6 | BL-006 | Review and accept ADR-0001 to ADR-0003 | Nils | Done (2026-10-12) |
| 7 | BL-007 | Session mode: `session.on` → change-only captures | – | Idea |
| 8 | BL-008 | Image cleanup: fisheye/perspective and white balance (OpenCV), only if accuracy suffers | – | Idea |
| 9 | BL-009 | Background analyzer agent on hourly/daily history | – | Idea |
| 10 | BL-010 | Upgrade path: local MCP server `capture_whiteboard` (see ADR-0003) | – | Idea |
| 11 | BL-011 | Review and accept ADR-0004 (Nextcloud storage, 30 s interval) | Nils | Done (2026-10-12) |
| 12 | BL-012 | Choose and set up Nextcloud access for all Claude instances (e.g. Nextcloud MCP server) → ADR | Nils + Claude | Open |
| 13 | BL-013 | Remove the earlier test copies in `~/Claude/` | Claude | Done (2026-10-12) |
| 14 | BL-014 | Move the repo to `~/Developer/NE_Whiteboard Capture/` (launchd cannot read `~/Documents`) and reinstall the service | Nils + Claude Code | Open |
| 15 | BL-015 | Review and accept ADR-0005 (20 s interval) | Nils | Done (2026-10-12) |
