# MVP Alternatives: voice + whiteboard

| Line # | Item | Value |
|---|---|---|
| 1 | Created | 2026-10-22 12:06 (Europe/Copenhagen) |
| 2 | Last updated | 2026-10-22 14:40 (ADR-0008: API watcher takes the photo, YAML, subfolders) |
| 3 | **Current main path** | **MVP B** (Dropbox request/description loop), see [ADR-0006](../docs/decisions/0006-describe-the-board-with-an-image-agent-and-hand-text-to-voice-mode.md) and [ADR-0008](../docs/decisions/0008-run-a-dropbox-api-watcher-that-takes-the-photo-with-yaml-requests-in-numbered-subfolders.md) (both `accepted`, 2026-10-22; ADR-0007 superseded by ADR-0008) |
| 4 | Status | MVP B: voice side built and partly tested; image agent and trigger **not built** |
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
| 4 | **Gap:** watcher notices the new request (Dropbox API long-poll) | Watcher (Python, no AI) | Mac, later Terox | ❌ not built |
| 5 | Watcher takes the photo and uploads `Images/image-NNNN.jpg`, then starts the image agent to describe it | Watcher, then image agent | Mac | ❌ not built |
| 6 | Image agent runs "deliver whiteboard description": writes `Descriptions/description-NNNN.md` (same number) | Image agent | Dropbox | ❌ not built |
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

- Nils speaks casually; the voice agent translates to these exact values.
- **`diff` is a placeholder:** the image agent cannot compare photos yet (it would need the previous photo or description). Do not rely on it.
- Request file = a container: later fields (for example a free question) need no redesign.

### Where the rules live

`/Whiteboard/instructions.md` in Dropbox is the single source of truth (trigger, procedure, fields, description format). One line in Nils's user settings points to it, so it works in every project. The Dropbox copy is authoritative; this document only summarizes it.

### The gap: solved by design in ADR-0008 (not built)

Nils chose the **Dropbox HTTP API with a refresh token** (app "Whiteboard-Capture", app folder access) over the desktop-app folder watcher: no desktop app to stall, same on Mac and Windows. The watcher (plain Python) also takes the photo, so only the description costs tokens. Options considered earlier:

| Line # | Option | Verdict |
|---|---|---|
| 1 | Watcher on the synced Dropbox folder (needs the desktop app) | Replaced by the API watcher (ADR-0008) |
| 2 | Same with Google Drive | Works in principle, less proven, adds a connector |
| 3 | Gmail as trigger | Extra connector, slower, clunky; against constraint 2 |
| 4 | Custom connector with a "request" tool (can also wait and return the text) | Cleanest, but needs hosting; against constraint 1 |
| 5 | Cross-session messaging with a Claude Code session | Unproven from voice; plain text only |

### Watcher and image agent, to build ([brief](handover/brief-build-mvp-b-watcher.md))

| Line # | Piece | Note |
|---|---|---|
| 1 | Setup script | One-time Dropbox authorization, stores the refresh token (BL-022) |
| 2 | Watcher + camera | Long-polls `Requests/`; takes one photo on demand (new camera; `imagesnap` on Mac, `ffmpeg` on Windows later); uploads the image |
| 3 | Describe step | Headless Claude Code with the photo and the request fields; subscription use and image input **to verify** (the only part that costs tokens) |
| 4 | Deliver step | Write `Descriptions/description-NNNN.md` last (never a half-written file); contains request number, fields used, transcribed text, shapes, arrows, relations, short summary |

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
