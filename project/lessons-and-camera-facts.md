# Lessons and camera facts

Short note from the old camera work. The full old branch is kept as the tag `archive/open-camera-a70` (commit `3a0a1c4`). Nothing else from it is in `main`.

Legend: **Repo** = written in this repo or the tag. **Chat** = reported by Nils and Claude in chat on 2026-10-21/22, not verified in code. **Guess** = not shown anywhere, needs a test.

## a) Camera facts (from the tag)

| Line # | Item | Status |
|---|---|---|
| 1 | Camera: Logitech C930e, serial `7B5E845E` (spare: `2BE82FAE`) | Repo (ADR-0007 draft, tag) |
| 2 | Name as listed: `Logitech Webcam C930e` | Repo (handoff-2026-10-13, line 78). Source not stated. **Verify** with ffmpeg or imagesnap |
| 3 | ffmpeg command pattern: `ffmpeg -hide_banner -loglevel error -f avfoundation -framerate 30 -video_size 1920x1080 -i "<idx>:none" -vf fps=1 -update 1 -atomic_writing 1 -y <file>` | Repo (tag, `script/wbcapture.sh:96-97`). Never run on the Mac |
| 4 | Single photo with `-frames:v 1` | **Guess.** Untested |
| 5 | "Streamed 15 frames in 15 seconds in two separate runs" | Repo claim (ADR-0007 draft). **No log in the repo** |
| 6 | Camera lookup by `serial:` in the `-list_devices` output | **Guess:** real ffmpeg probably prints only the name, so the lookup may fail. The test stub prints the serial itself |
| 7 | ffmpeg needs its own camera permission | Repo (ADR-0006 draft) |
| 8 | Background (launchd) camera access | **Unverified** (handoff-2026-10-13) |

## b) Old ADR drafts (never accepted)

Both drafts are in the tag only. Their numbers clash with the accepted ADRs on `main`, so they are not reused.

| Line # | Draft | Decision (one line) |
|---|---|---|
| 1 | ADR-0006 "Capture from an open camera stream" (draft) | One long-running ffmpeg stream, published every 20 s, restarted on stall |
| 2 | ADR-0007 "Use the Logitech C930e as the capture camera" (draft) | Replace the APEMAN A70 with the C930e, selected by serial |

On `main`, ADR-0006 is "describe the board with an image agent" and ADR-0007 is "Dropbox request loop". The camera decision will be **ADR-0009**, once a real photo works (see BL-020).

## c) Lessons and dead ends

Source for every row: **Chat**, 2026-10-21/22.

| Line # | Lesson |
|---|---|
| 1 | APEMAN A70: one photo per power-cycle with imagesnap. Cause never proven. Hypotheses: repeated open and close, or the photo function. Replaced by the C930e |
| 2 | Voice mode cannot view images from Google Drive, Dropbox or project files. The local Filesystem extension is not available in voice (text mode only). So a second agent turns the photo into text (ADR-0006) |
| 3 | Skills are not available in voice mode. The voice rules live in `Whiteboard/instructions.md` in Dropbox, referenced by one line in the user settings |
| 4 | The voice agent has no clock or timer. It counts aloud 1 to 10 and looks once (ADR-0008) |
| 5 | The Google Drive connector cannot return images. No public API pushes files into claude.ai storage |
| 6 | Reading and writing text files in Dropbox works in voice (tested 2026-10-22) |
| 7 | Cross-session messaging with Claude Code carries plain text only. A cloud chat is not connected to Remote Control |

Decisions from this work: ADR-0006 and ADR-0008 (`accepted`). Superseded: ADR-0002, ADR-0003, ADR-0005 and ADR-0007.
