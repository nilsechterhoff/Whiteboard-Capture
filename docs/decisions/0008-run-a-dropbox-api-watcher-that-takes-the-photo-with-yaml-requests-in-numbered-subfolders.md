---
status: "accepted"
date: 2026-10-22
decision-makers: Nils Echterhoff
consulted: Claude (AI assistant)
---

# Run a Dropbox API watcher that takes the photo, with YAML requests in numbered subfolders

## Context and Problem Statement

ADR-0007 defined the Dropbox request/description loop but left the "gap" open: a Mac watcher on the synced Dropbox folder (needing the Dropbox desktop app) would start the image agent, and the image agent would also take the photo. While planning the build, four things came up:

* Reliability matters more than minimal code: Nils cannot afford debugging rounds this week, and the Dropbox desktop app is not installed (and may be stopped or stalled).
* The camera step is repetitive and needs no AI, so it should not cost tokens.
* Request, photo and description need clear, matching names and places.
* The service may later move to the Windows PC "Terox" behind Nils's screen.

How is the loop built, and how are its files named and stored?

## Decision Drivers

* Reliability first; few moving parts that can silently stop
* Tokens only where AI is needed (describing the photo)
* Same design on Mac now and Windows later
* Request, image and description pair by one running number
* Keep what ADR-0007 got right (on demand, Dropbox only, no self-built MCP)

## Considered Options

* Watcher on the synced local Dropbox folder (needs the Dropbox desktop app), image agent takes the photo (ADR-0007 route)
* Watcher uses the Dropbox HTTP API, watcher takes the photo, image agent only describes
* Request files as plain `.txt` (current) versus YAML or JSON

## Decision Outcome

Chosen option: "Watcher uses the Dropbox HTTP API, watcher takes the photo, image agent only describes", because it does not depend on the desktop app running or syncing, behaves the same on Mac and Windows, and spends tokens only on the description.

This **supersedes ADR-0007**. ADR-0006 stays valid.

**Loop**

1. Nils says "look at the whiteboard"; the voice agent follows `instructions.md` and creates `Requests/request-NNNN.yaml`.
2. The watcher (plain Python script, no AI) notices the new request through the Dropbox API (long-poll), takes a photo and uploads it as `Images/image-NNNN.jpg`.
3. The watcher then starts the image agent (headless Claude Code), which describes the photo using the request fields.
4. The description is written last as `Descriptions/description-NNNN.md`.
5. The voice agent counts aloud from 1 to 10, looks once for the description with the same number, and answers or says it is not ready (unchanged from ADR-0007).

**Files**

| Line # | What | Name | Format |
|---|---|---|---|
| 1 | Request | `Requests/request-NNNN.yaml` | YAML (renamed from `.txt`; same fields: `request`, `marker_color`, `region_v`, `region_h`, `mode`) |
| 2 | Photo | `Images/image-NNNN.jpg` | JPEG, same number as the request |
| 3 | Description | `Descriptions/description-NNNN.md` | Markdown (stays Markdown: mostly free text) |
| 4 | Rules for the voice agent | `instructions.md` (top level) | Markdown |

**Dropbox app:** created by Nils in the Dropbox developer console as scoped access, **app folder** (name "Whiteboard-Capture"), permissions `files.metadata.read`, `files.content.read`, `files.content.write`. A refresh token (does not expire unless revoked) is obtained once by a setup script; the short-lived access token is renewed by the script itself. The app folder is `Apps/Whiteboard-Capture`; Dropbox creates it at first authorization, after which the `Whiteboard` folder content moves there and `instructions.md` is updated to the new paths.

**Portability:** Python 3; only the camera call and the background-service setup are OS-specific (Mac: `imagesnap` and launchd; Windows later: `ffmpeg` and Task Scheduler).

### Consequences

* Good, because no Dropbox desktop app is needed and there is no sync stall to debug.
* Good, because photo capture costs no tokens and is more reliable as plain code.
* Good, because one number pairs request, image and description.
* Good, because the same Python core can move to Terox.
* Bad, because a one-time setup is needed (app key and secret entered once into the setup script; never pasted in chat).
* Bad, because the watcher needs the Dropbox API (token handling, long-poll) instead of a folder watcher.
* Bad, because the files must move into `Apps/Whiteboard-Capture` after the first authorization, and `instructions.md` must follow.
* Neutral, because two things are **unverified**: the voice Dropbox connector can reach `Apps/Whiteboard-Capture`; headless Claude Code can take a photo as input on the subscription. (The connector's create-file tool lists `.yaml` among accepted extensions.)

### Confirmation

Manual end-to-end run on a request: request file appears, image and description with the same number appear, the voice agent reads the description and answers. Then measure the delay from request to description.

## Pros and Cons of the Options

### Watcher on the synced local Dropbox folder

* Good, because no token and no API code.
* Bad, because it needs the desktop app (not installed), which can be stopped or stall; Windows needs a separate setup.

### Watcher uses the Dropbox HTTP API

* Good, because one mechanism on every OS, no desktop app, long-poll is near instant.
* Bad, because of the one-time token setup and API code.

### Request file format

* Good (YAML), because the fields already look like YAML and it is a conventional format for settings; the voice agent writes it as plain text.
* Bad (YAML), because it is one more rename (`.txt` test files from earlier stay as they are).
* Neutral (`.txt`, JSON): `.txt` worked in tests; JSON is stricter but harder for the voice agent to write.

## More Information

* Decided in a voice session with Nils on 2026-10-22. Nils pre-approved this ADR in that session ("I will hereby pre-approve everything"); Claude recorded the status on that basis.
* Supersedes ADR-0007 (status changed to "superseded by ADR-0008"; its decision text is unchanged).
* Related: ADR-0006; build brief: [project/handover/brief-build-mvp-b-watcher.md](../../project/handover/brief-build-mvp-b-watcher.md).
