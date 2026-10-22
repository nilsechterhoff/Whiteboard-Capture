# Brief for Claude Code: build the MVP B watcher

Written 2026-10-22 by Claude (text chat) for a **new Claude Code session on Nils's Mac**. Read this file first, then the files in section 2. Everything you need is in the repo; the chat context is not available to you.

## 1. Goal

Nils brainstorms at a 120 × 90 cm whiteboard in Claude's **live voice mode** (hands-free). Voice mode cannot view images, so a plain script plus a headless Claude Code run turns a fresh photo into a text description that the voice agent reads from Dropbox.

**You build:** a Python **setup script** (one-time Dropbox authorization), a **watcher** (notices a request, takes the photo, uploads it, starts the describer, writes the description) and a **describe step**. Mac first; later the same code runs on Nils's Windows PC "Terox".

## 2. Read first

| Line # | File | Why |
|---|---|---|
| 1 | `CLAUDE.md` | Standards and rules |
| 2 | `docs/decisions/0008-*.md` | **The decision you implement** (supersedes ADR-0007) |
| 3 | `docs/decisions/0006-*.md` | Why a text bridge (voice cannot view images) |
| 4 | `project/mvp-alternatives.md` | Flow, request fields, risks |
| 5 | `project/backlog.md` | BL-016, BL-017, BL-018, BL-022 to BL-024 |
| 6 | `project/handover/handoff-2026-10-13.md` | Earlier camera lessons, Mac environment (older timed pipeline, mostly parked) |
| 7 | `script/wbcapture.sh`, `script/tests/` | Old capture loop and its stub-based test style (reuse ideas, not the design) |

## 3. Rules from Nils (follow them)

| Line # | Rule |
|---|---|
| 1 | **Ask Nils** for the exact location and name before creating any file or folder on his Mac (config, credentials, logs, virtual environment, service files) |
| 2 | Standards repo `nilsechterhoff/standards` is **read-only**; never write to it. `dotfiles` is not your business |
| 3 | Code changes: branch → pull request → **ask Nils before merging** |
| 4 | Decisions go to `docs/decisions/` (MADR 4.0.0); you write `proposed`, only Nils sets `accepted` |
| 5 | Never run `imagesnap` or any capture command in the foreground without a time limit (macOS has no `timeout`: run in background, sleep, kill) |
| 6 | No `sudo`. Do not change macOS privacy settings yourself; tell Nils what to click |
| 7 | Request folder access only for the exact folder needed |
| 8 | State only what outputs show. Ask about the rest. No guesses presented as facts |
| 9 | Never commit images, tokens, app key or secret. Never print or log secrets. Nils must not paste secrets into chat |
| 10 | Nils has ADHD: short answers, tables with a "Line #" column, numbered items, at most 5 sentences, key terms in bold. Pure shell commands for his Terminal, no English mixed in |
| 11 | Reliability before cleverness: Nils cannot afford debugging rounds this week. Test first (stubs), then real |

## 4. Architecture (decided in ADR-0008)

```
Voice agent ──creates──▶ Dropbox: Requests/request-NNNN.yaml
                                   │  (long-poll via Dropbox HTTP API)
                                   ▼
                          WATCHER (Python, no AI, runs on Mac, later Terox)
                            1. read request (fields)
                            2. take photo (camera, with time limit)
                            3. upload Images/image-NNNN.jpg
                            4. start DESCRIBE step (headless Claude Code)
                            5. upload Descriptions/description-NNNN.md (LAST)
                                   │
Voice agent ◀──reads after counting 1..10── Descriptions/description-NNNN.md
```

| Line # | Item | Decision |
|---|---|---|
| 1 | Dropbox access | HTTP API with **refresh token**, scoped app, **app folder** access, app name "Whiteboard-Capture"; scopes `files.metadata.read`, `files.content.read`, `files.content.write` |
| 2 | Paths in the API | Relative to the app folder root, for example `/Requests/request-0003.yaml` |
| 3 | Numbers | Four digits, one running number; request, image and description share it |
| 4 | Writing order | Description is uploaded **last**; the voice agent treats its appearance as "done" |
| 5 | Tokens | Only the describe step uses AI |
| 6 | Portability | Python 3, standard library plus the `dropbox` package if it simplifies things (your call, explain why). OS-specific code only in the camera function and the service setup |

### Dropbox folder state today (via the voice connector's Dropbox)

| Line # | Path | Content |
|---|---|---|
| 1 | `/Whiteboard/instructions.md` | Rules for the voice agent (updated 2026-10-22 for ADR-0008) |
| 2 | `/Whiteboard/Requests/` | `request-0001.txt`, `request-0002.txt` (old format, test files) |
| 3 | `/Whiteboard/Images/`, `/Whiteboard/Descriptions/` | Empty |
| 4 | `/Apps/Whiteboard-Capture/` | **Does not exist yet**; Dropbox creates it at the first authorization |

**After the first authorization:** the content of `/Whiteboard` has to move into `/Apps/Whiteboard-Capture/` (Nils or Claude in the text chat via the Dropbox connector), and `instructions.md` paths get updated. The brief's steps below assume this move happens before the first real run. **Unverified:** that the voice agent's Dropbox connector can reach `/Apps/Whiteboard-Capture/`. Tell Nils to test it in voice mode right after the move.

## 5. Request file (YAML)

```yaml
request: "0003"        # required, string, four digits
marker_color: red      # optional: black, red, green, blue (default: all colors)
region_v: top          # optional: top, middle, bottom (default: whole height)
region_h: left         # optional: left, center, right (default: whole width)
mode: snapshot         # optional: snapshot, diff (default: snapshot; diff is a placeholder)
```

- Unknown or invalid values: do not guess. Write a description that says so (see section 8).
- Ignore old `*.txt` requests. Nils decides whether to convert `request-0002.txt` into `request-0002.yaml` for the manual test; **ask him**.

## 6. Description file (Markdown)

Name `Descriptions/description-NNNN.md`. Content, in this order:

1. Request number and the fields used (so the voice agent can verify the pairing)
2. Transcribed text (what is written, grouped by region)
3. Shapes, arrows, relations (what connects to what)
4. Short summary

The describe step **only describes**; the voice agent interprets. Honor `marker_color` and region fields (describe only that part). `mode: diff`: say clearly that diff is not supported yet and give the snapshot.

## 7. Build order (stop after each numbered block and show Nils the result)

| Line # | Step | Done when |
|---|---|---|
| 1 | Read section 2 files. Reply to Nils in a table: what you understood, what you will build, **questions** (locations, camera name, Python version, how Nils wants secrets stored) | Nils confirms |
| 2 | **Tests first with stubs:** fake Dropbox client, fake camera, fake describer. Cover: new request, already-described request skipped, camera failure, describe failure, half-written files never visible, invalid YAML | Tests pass on Mac (and Linux if possible) |
| 3 | **Setup script:** Dropbox OAuth2 code flow with `token_access_type=offline`. Nils enters app key and secret with hidden input (`getpass`); the script prints the authorization URL, Nils pastes the code, the script exchanges it for a refresh token and stores key, secret and refresh token in a config file with mode `600`. Ask Nils where. Never echo secrets. Check by listing the app folder root | Authorization works; `/Apps/Whiteboard-Capture/` exists |
| 4 | Tell Nils to move `/Whiteboard` content into the app folder; wait for confirmation | Folder structure in place |
| 5 | **Camera function** with a hard time limit (Mac: `imagesnap`, camera name from `imagesnap -l`, ask Nils which one is the new camera). Keep the function small so a Windows version (`ffmpeg`) can replace it later | One photo saved locally |
| 6 | **Describe step:** headless Claude Code (`claude -p`) with the photo and the request fields. **Verify first** that it can take an image as input and runs on Nils's subscription without an API key. If not, **stop and ask Nils**; do not switch to an API key on your own | A real description of a real photo |
| 7 | **Manual end-to-end run** on one request (Nils decides which), without the service. Then Nils tests in voice mode that the description is read and used | Voice agent answers from the description |
| 8 | **Watcher as a background service** (Mac: launchd; ask Nils for locations; log file; single-instance lock). Camera permission for a background service is **unverified**: test it | Request in voice mode → description appears without manual steps |
| 9 | **Measure** request-to-description time; report it so Nils can tune the 10 s count in `instructions.md` | Numbers reported |
| 10 | Update docs: README, `project/mvp-alternatives.md`, backlog. PR, **ask before merging** | Merged by Nils's OK |

## 8. Failure handling (proposal: confirm with Nils before building)

If the camera or describe step fails, the watcher still writes `description-NNNN.md` containing `status: error` and a one-line reason, so the voice agent can say what went wrong instead of only "not ready". Never write a partial description. Never answer from an older photo.

## 9. Robustness checklist

| Line # | Item |
|---|---|
| 1 | Single instance (lock); restart-safe (on start, handle requests that have no description yet, oldest first) |
| 2 | Idempotent: a request that already has an image or description is not processed twice |
| 3 | Upload to a temporary name, then rename, so readers never see half files |
| 4 | Time limits on camera and describe step; kill and report on timeout |
| 5 | Token refresh handled by the script; clear error message if the refresh token was revoked |
| 6 | Log to a file (ask where), no secrets in logs |
| 7 | Network loss: retry with backoff; do not crash |

## 10. Out of scope

`mode: diff` (needs comparison with a previous photo), image cleanup, session mode, the old timed pipeline (parked), the Windows port (design for it, do not build it yet).

## 11. Open points to raise with Nils

| Line # | Point |
|---|---|
| 1 | Which camera and its listed name |
| 2 | Where to store config, credentials, logs, virtual environment |
| 3 | Convert `request-0002.txt` to YAML for the first run? |
| 4 | Failure handling proposal (section 8) |
| 5 | Voice connector access to `/Apps/Whiteboard-Capture/` (test in voice after the move) |
