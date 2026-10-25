# MVP Alternatives: voice + whiteboard

| Line # | Item | Value |
|---|---|---|
| 1 | Created | 2026-10-22 12:06 (Europe/Copenhagen) |
| 2 | Last updated | 2026-10-22 14:40 (ADR-0008: API watcher takes the photo, YAML, subfolders) |
| 3 | **Current main path** | **MVP B** (Dropbox request/description loop), see [ADR-0006](../docs/decisions/0006-describe-the-board-with-an-image-agent-and-hand-text-to-voice-mode.md) and [ADR-0008](../docs/decisions/0008-run-a-dropbox-api-watcher-that-takes-the-photo-with-yaml-requests-in-numbered-subfolders.md) (both `accepted`, 2026-10-22; ADR-0007 superseded by ADR-0008) |
| 4 | Status | MVP B: voice side built and tested; watcher with camera, describe step and Dropbox store built; one end-to-end run done (2026-10-22). Background service not installed yet |
| 5 | Maintained by | Claude, for Nils |

## Requirement (highest priority)

Nils asks in **live voice mode** (desktop app, Mac), hands-free: no typing, no push-to-talk, no clicks. "Look at the whiteboard" must lead to an answer from the real board.

## Finding that shaped everything

| Line # | Test (Nils, 2026-10-21/22) | Result |
|---|---|---|
| 1 | Google Drive connector, image in voice | Cannot view it |
| 2 | Dropbox connector, image in voice | Cannot view it (could browse files) |
| 3 | JPEG in project files, voice | Saw file and pixel size, not the picture |
| 4 | Local Filesystem extension in voice | Tool missing entirely in voice (text and images) |

**Working assumption:** voice mode cannot view images from any source. So the voice agent never gets the picture; a second agent (the **image agent**) turns the picture into **text**.

## Constraints Nils set for the MVP

| Line # | Constraint |
|---|---|
| 1 | No self-built or self-hosted MCP (local or remote) |
| 2 | No extra connector beyond what exists; **Dropbox only** for now |
| 3 | Event-based, not timed: the camera and image agent do not run 24/7 (tokens) |
| 4 | Good enough for a few months, not a product |
| 5 | Short delay is acceptable |

## Proven so far (voice agent, 2026-10-22)

| Line # | Item | Result |
|---|---|---|
| 1 | Read text from a Dropbox PDF in voice | ✅ |
| 2 | Create a file in Dropbox from voice (`request-0001.txt`) | ✅ Dropbox stamps files to the second (server time, UTC) |
| 3 | Folders carry no timestamps; files do | ✅ checked |
| 4 | Dropbox tools set to "Always allow": list folder, create file, fetch extracted file text | ✅ set by Nils; deletes always need approval; settings reportedly can reset after app updates |
| 5 | User-settings one-liner points voice to `Whiteboard/instructions.md` | ✅ set by Nils, filename matches |
| 6 | Dry run: request-0002 written, counted to 10, no description found, said "not ready" | ✅ voice-side behaviour as specified |
| 7 | Skills tool in voice | ❌ not available, so the procedure lives in the instructions file |
| 8 | Voice agent has no clock or timer | ❌ counting aloud (about 1 s per number) is the stand-in |

## MVP B: Dropbox request/description loop (current main path)

**Idea source:** Nils (flow drawn on his whiteboard, voice chat 2026-10-22), details worked out with Claude. Supersedes MVP A as the working design, because it is event-based.

### Flow

| Line # | Step | Who | Where | Status |
|---|---|---|---|---|
| 1 | Nils says "look at the whiteboard" | Nils | Voice, Mac | ✅ |
| 2 | Voice agent reads `instructions.md` (via settings one-liner), lists `Requests/`, takes highest request number + 1 | Voice agent | Dropbox | ✅ tested (old layout) |
| 3 | Voice agent creates `Requests/request-NNNN.yaml` | Voice agent | Dropbox | `.txt` tested; `.yaml` not yet |
| 4 | Watcher notices the new request (polls `Requests/` every 1 s; long-poll not built yet) | Watcher (Python, no AI) | Mac, later Terox | ✅ built, run once |
| 5 | Watcher takes the photo and uploads `Images/image-NNNN.jpg`, then starts the describe step (`claude -p`, Sonnet) | Watcher, then image agent | Mac | ✅ built, run once |
| 6 | Describe step writes `Descriptions/description-NNNN.md` (same number), last | Watcher | Dropbox | ✅ built, run once |
| 7 | Voice agent counts aloud 1 to 10, then looks once for `Descriptions/description-NNNN.md` | Voice agent | Dropbox | ✅ tested (no-file case) |
| 8 | Found: voice agent answers from it. Missing: says "not ready", no retry, never uses an older description | Voice agent | Voice | ✅ no-file case tested |

Design choices:

| Line # | Choice | Why |
|---|---|---|
| 1 | Unique running number, four digits (0001 to 9999), not a time | Voice agent has no clock; request and description pair by number |
| 2 | One description file per request | Voice agent can never read a stale one by mistake |
| 3 | Retries (12 s, 15 s) removed | Waiting is annoying during tests; check once after 10 s, tune later |
| 4 | Describing and delivering are separate steps | Delivery target can change without touching the description |
| 5 | Image agent only **describes**; voice agent interprets | Keeps the vision step simple and swappable |

### Request file format

`Requests/request-NNNN.yaml`: YAML, one `name: value` per line, `request` as a quoted string ("0003"). Only `request` is required.

| Line # | Field | Allowed values | Default | Meaning |
|---|---|---|---|---|
| 1 | `request` | four digits | n/a | Request number |
| 2 | `marker_color` | black, red, green, blue | all | Only content in that marker color (one color per project on the same board) |
| 3 | `region_v` | top, middle, bottom | whole height | Vertical focus |
| 4 | `region_h` | left, center, right | whole width | Horizontal focus; combines with `region_v` (3 × 3 grid) or stands alone |
| 5 | `mode` | snapshot, diff | snapshot | snapshot: full current state. diff: only what is new since the last request |
| 6 | `model` | short names from the config file (now: haiku, sonnet, opus) | `default_model` in the config (now: haiku) | Model for the describe step. Any other value: error description, no photo |

- Nils speaks casually; the voice agent translates to these exact values.
- **`diff` is a placeholder:** the image agent cannot compare photos yet (it would need the previous photo or description). Do not rely on it.
- Request file = a container: later fields (for example a free question) need no redesign.
- Short names map to model IDs in the config file (`models`), not in the code. A new model is a one-line edit there.

### Upload order and status file (2026-10-25)

Per request: photo, describe, **upload the description**, **upload the image**, write **`status.md`** (app folder root). The description is still the last thing the voice agent needs; the image follows.

| Line # | Rule | Detail |
|---|---|---|
| 1 | Local copy first | Photo and description are saved under the config folder before any upload. A restart never takes a new photo |
| 2 | Description in Dropbox, image missing | One image upload from the local copy (one attempt). If it fails: `IMAGE_UPLOAD_FAILED`, local photo kept, request done |
| 3 | Local copy, no description (crash after describe) | Upload the description from the local copy; no new photo |
| 4 | Image in Dropbox, no description | Older run (image was uploaded first before this change). Error description: "interrupted", code `UNKNOWN_ERROR` |
| 5 | Description upload fails (network) | `DESCRIPTION_UPLOAD_FAILED`; request stays open and the description is retried from the local copy on the next pass |
| 6 | Image upload fails | One retry. If it fails again: `IMAGE_UPLOAD_FAILED`, local copy kept, request done |
| 7 | Any other unexpected exception | `UNKNOWN_ERROR`, request done, status written. A network error (OSError) is not an outcome: the request is tried again |
| 8 | Camera / describe | `CAMERA_FAILED` if no camera gave a photo; `DESCRIBE_FAILED` if a photo was described but no whiteboard was confirmed |

**Status file `status.md`** (rewritten at the end of every request):

```
status: ok
time: 2026-10-25 10:00:00
last request: 0016
description delivered: yes
image saved: yes
```

On error, two more lines: `code: <CODE>` and `message: <one plain sentence>`. Errors reach the user only through this file, which the voice agent reads. No notifications.

**Timing:** the image upload time goes to the local CSV only (`image_upload_s`), not into the description's timing block.

### Description format

`Descriptions/description-NNNN.md`, written last. Order:

1. First line `status: ok` or `status: error` (the voice agent checks this line).
2. `request: "NNNN"` and `fields: ...` (including `model=...`), or for an error one `reason:` line per camera or cause.
3. Body: text by region, shapes and arrows, short summary (ok only). The `whiteboard: yes/no` line from the describe step is not in the file.
4. A blank line and the marker line `--- timing, do not read aloud ---`, then a short timing block (machine, model, detect, camera list, each camera try, image upload, total before the description upload).

**Marker rule:** everything below the marker line is for the logs, not for reading aloud. `instructions.md` in Dropbox tells the voice agent to ignore it. The final upload of the description is not in the block. It goes only to the local CSV log.

### Stopwatch and voice check window

| Line # | Item | Value |
|---|---|---|
| 1 | Timing log (one row per request) | `~/Library/Logs/whiteboard-watcher-timings.csv`. Columns: when, request, machine, model, outcome, detect_s, camera_list_s, tries (`index:result:photo_s:brightness:describe_s`), image_upload_s, describe_upload_s, total_s. No whiteboard content |
| 2 | Voice check window | First check at 10 s, then every 5 s until 40 s |
| 3 | `instructions.md` (Dropbox) | Updated by Claude in the chat, not by the watcher and not by Nils's script. It holds the marker rule and the `model` field |

### Where the rules live

`/Whiteboard/instructions.md` in Dropbox is the single source of truth (trigger, procedure, fields, description format). One line in Nils's user settings points to it, so it works in every project.

**Deviation from the brief (decided by Nils, 2026-10-22):** `instructions.md` stays at `/Whiteboard/`, because the user settings point there. Its paths now point into `/Apps/Whiteboard-Capture/`, where `Requests/`, `Images/` and `Descriptions/` now are. The Dropbox copy is authoritative; this document only summarizes it.

### The gap: solved by design in ADR-0008 (not built)

Nils chose the **Dropbox HTTP API with a refresh token** (app "Whiteboard-Capture", app folder access) over the desktop-app folder watcher: no desktop app to stall, same on Mac and Windows. The watcher (plain Python) also takes the photo, so only the description costs tokens. Options considered earlier:

| Line # | Option | Verdict |
|---|---|---|
| 1 | Watcher on the synced Dropbox folder (needs the desktop app) | Replaced by the API watcher (ADR-0008) |
| 2 | Same with Google Drive | Works in principle, less proven, adds a connector |
| 3 | Gmail as trigger | Extra connector, slower, clunky; against constraint 2 |
| 4 | Custom connector with a "request" tool (can also wait and return the text) | Cleanest, but needs hosting; against constraint 1 |
| 5 | Cross-session messaging with a Claude Code session | Unproven from voice; plain text only |

### Watcher and image agent (built 2026-10-22, [brief](handover/brief-build-mvp-b-watcher.md))

| Line # | Piece | Note |
|---|---|---|
| 1 | Setup script | One-time Dropbox authorization, stores the refresh token (BL-022) |
| 2 | Watcher + camera | Polls `Requests/`; camera by index with ffmpeg avfoundation (no serial or ID lookup); `camera_name` in config (now `Logitech`, so FaceTime and iPhone are skipped; empty means all cameras); warm-up: first 1.5 s discarded (3 frames at 2 fps), photo is the 4th frame; a dark frame is retried once after the warm-up, then the next camera; last working index as a hint; each camera at most once per request after its retry; rotate 180° (config); uploads only the image of the camera that shows the whiteboard |
| 3 | Describe step | Headless Claude Code (`claude -p`, Sonnet, Read only) with the photo and the request fields. First line `whiteboard: yes` or `whiteboard: no`; `no` moves on to the next camera. Refuses to run if an API key is set |
| 4 | Deliver step | Write `Descriptions/description-NNNN.md` last (temporary name, then rename); contains request number, fields used, transcribed text, shapes, arrows, relations, short summary. If every camera fails: one error file with one line per camera. The `whiteboard:` line is not in the published file |

### Measured (2026-10-22, first end-to-end run, request-0003)

| Line # | Step | Time |
|---|---|---|
| 1 | Dropbox reads (list, exists, modified, read request) | 4.1 s |
| 2 | Camera list (ffmpeg, index only) | 0.35 s |
| 3 | Camera try, dark frame or wrong camera (not described) | 6.3 s |
| 4 | Camera try, photo taken (rotated, brightness ok) | 4.9 s |
| 5 | Describe step (Sonnet, `claude -p`) | 11.9 s |
| 6 | Uploads and renames of image and description | 5.8 s |
| 7 | Pass total (watcher log) | 32.1 s |
| 8 | Request created to description (Dropbox server time) | about 34 s |

**Worst case, request-0004 (all five cameras tried, room dark):** 46.5 s in total. One camera hit the 25 s limit. Each dark try costs about 5 to 6 s. The request was closed with one error description, no describe call.

**Above the 10 s target.** The describe step and the uploads are the largest parts. Tuning is open (BL-018); the voice side waits 10 s and then looks once.

**Model choice (describe, same photo, 2 runs each):** Sonnet 10.8 s per run; Haiku 10.6 s and 14.9 s. Both read the layout and the same unclear words. Sonnet chosen by the rule "fastest that reads correctly". Haiku is about 30 times cheaper per the CLI estimate ($0.002 to $0.005 against $0.046 to $0.076 per call).

**Camera findings:** the index of the whiteboard camera changed between runs with no replug. The FaceTime camera hit the 25 s hard limit. Dark frames (closed lid) are rejected by brightness (threshold 20).

### Warm-up and retry (2026-10-23, requests 0009 to 0011, launchd service)

| Line # | Request | Status | Camera 1, first try | Camera 1, retry | Total before description upload | Request to description file |
|---|---|---|---|---|---|---|
| 1 | 0009 | ok | dark (brightness 1.5), photo 5.7 s | bright (130.3), photo 4.1 s, describe 10.8 s | 25.9 s | 35.3 s |
| 2 | 0010 | ok | dark (1.3), photo 5.9 s | bright (130.0), photo 4.2 s, describe 10.5 s | 27.9 s | 38.0 s |
| 3 | 0011 | ok | dark (1.4), photo 5.6 s | bright (129.9), photo 4.1 s, describe 8.5 s | 24.5 s | 34.0 s |

Warm-up: the first 1.5 s are discarded (3 frames at 2 fps), the 4th frame is the photo. A dark first try is retried once. Every first try was dark, so the retry is what gets the picture. Still above the 10 s target (BL-018).

### Open risks and tests

| Line # | Risk | Test |
|---|---|---|
| 1 | Dropbox sync latency eats the 10 s window | Measure request-to-description time end to end, then tune the count |
| 2 | Dropbox app must run and the Mac must be awake | Check once the watcher exists |
| 3 | Counting aloud is an imprecise timer | Compare against real time in a test |
| 4 | Voice agent may not follow the settings one-liner every time | Test over several sessions |
| 5 | "Always allow" may reset after updates | Re-check if approval prompts return |
| 5a | Voice connector may not reach `Apps/Whiteboard-Capture/` after the move | Test in voice right after the move (BL-023) |
| 6 | Headless Claude Code with images on the subscription | One-off run with a test photo |
| 7 | Description quality for real brainstorming | Real board, real questions |
| 8 | Full loop with a hand-written `description-0002.md` | Optional; Nils trusts the read works |

## MVP A: continuous description, text file as bridge (earlier idea, fallback)

**Idea source:** Claude (voice chat, 2026-10-22).

| Line # | Step | Where |
|---|---|---|
| 1 | Camera photographs the board regularly (old `wbcapture.sh` loop) | Mac |
| 2 | If the board changed, headless Claude Code describes it | Mac |
| 3 | Result saved to one text file in Dropbox | Cloud |
| 4 | "Look at the board": voice reads the file | Voice |

| Line # | Pros | Cons |
|---|---|---|
| 1 | No new infrastructure; reuses the capture script | Timed running conflicts with constraint 3 (tokens) |
| 2 | No trigger gap | Description can be 20 to 30 s old, no focus fields |

## Other ideas (not MVP A or B)

| Line # | Idea | Status |
|---|---|---|
| 1 | **MVP C placeholder**: remote MCP connector calls the Claude API itself and returns text; can wait for the result; question parameter | Needs hosting and an API key; against constraints 1 and 3 for now |
| 2 | Time MCP server (hosted ones exist) for a clock | Gives a time, still no timer; untested |
| 3 | Reciting a public-domain line instead of counting | Nils: keep counting for now |
| 4 | Filesystem extension returns the image (text mode only) | Fails the voice requirement |
| 5 | Remote Control or cloud Code session with voice | Undocumented, untested |

## Next steps

See [backlog.md](backlog.md): BL-016 to BL-024.
