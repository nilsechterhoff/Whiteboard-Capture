---
status: "proposed"
date: 2026-10-21
decision-makers: Nils Echterhoff
consulted: Claude (AI assistant)
---

# Capture from an open camera stream

## Context and Problem Statement

ADR-0002 captures every frame with a new `imagesnap` process, which opens the camera, takes one photo and closes it again. On the APEMAN A70 this failed repeatedly: after a power-cycle the camera delivered one photo, and later runs fell into a state where the next capture failed with `Failed to capture photo.` and Photo Booth showed a black picture until the camera was power-cycled again (tests of 2026-10-12 and 2026-10-13). A single `imagesnap` session that took six photos without closing the camera in between worked. A continuous ffmpeg stream from the A70 stalled after two to three frames. The Logitech C930e, now connected as a second camera, streamed 15 frames in 15 seconds in two separate runs, with no power-cycle needed.
How should the service take a frame every 20 s without opening and closing the camera for each frame?

## Decision Drivers

* The camera must not be opened and closed for every frame (ADR-0002 failure)
* Frames at the live interval of 20 s (ADR-0005), and a fresh frame within about 2 s for `capture.request` (ADR-0003)
* A stall or unplugged camera must be detected and recovered without manual steps
* Keep the existing service pieces: status file, tiers, retention, trigger file, lock, logging (ADR-0002, ADR-0004)
* Minimal new dependencies

## Considered Options

* `imagesnap` per frame, as in ADR-0002 (current; failed in tests)
* `imagesnap` time-lapse: one session, several photos (worked for 6 photos; length of a session not yet tested)
* ffmpeg (avfoundation) as one long-running stream, writing the newest frame to a file (chosen)
* Own Swift helper using `AVCaptureVideoDataOutput` (more work; not needed if ffmpeg holds up)

## Decision Outcome

Chosen option: "ffmpeg as one long-running stream", because it opens the camera once per stream, has already streamed reliably from the C930e, and its frame file can be read at any time. A supervisor script keeps the existing service pieces around it.

Details:

* One ffmpeg process per stream: `avfoundation` input, 1920 × 1080 at 30 fps, filter `fps=1`, `-update 1 -atomic_writing 1`, so the newest frame is always a complete file.
* The camera is found by its serial number (`WBC_CAMERA_SERIAL`), because two C930e units are connected. Device listing does not open the camera.
* The supervisor publishes a frame to `latest/latest.jpg` every `WBC_LIVE_INTERVAL` s, or at once on `capture.request` (within about 1–2 s). The first frame of a new stream is published at once.
* If the stream exits, or no new frame arrives for `WBC_STALL_LIMIT` s (60 s), the supervisor stops it with SIGTERM and restarts it. SIGKILL is only a last resort after `WBC_STOP_GRACE` s, and is logged.
* If the camera is absent, `status.txt` shows `CAMERA_NOT_FOUND` and the supervisor retries every `WBC_CAMERA_RETRY` s.

This supersedes the capture method of ADR-0002 (per-frame `imagesnap`). ADR-0002's service design (launchd, status file, tiers) and ADR-0004's storage stay in force.

### Consequences

* Good, because the camera is opened once per stream instead of once per frame, which is the suspected cause of the failures.
* Good, because a stalled or dead stream is detected and restarted without manual steps.
* Good, because the stream runs at the same 20 s interval, so the upload volume is unchanged (ADR-0005).
* Bad, because the stream is a long-running process: it may need a restart after a macOS update or a camera replug, and it may fail in ways the stub tests do not show. A 30-minute test on the Mac is needed before this is trusted.
* Bad, because ffmpeg needs camera permission of its own (ADR-0002 already notes the permission can need a re-grant after macOS updates).
* Bad, because ffmpeg is not on the default PATH of this Mac (a copy exists at `~/ffmpeg-static/ffmpeg`). The service needs `brew install ffmpeg` or an explicit `WBC_FFMPEG` path, decided by Nils.
* Neutral, because the camera change from the A70 (ADR-0001) to the C930e is required for this design. This ADR records the capture method. The camera choice needs its own decision record if Nils wants it formal.

### Confirmation

`script/tests/test_wbcapture.sh` runs the supervisor against a stubbed ffmpeg and a fake clock: tiers, trigger file, unplugged camera, stream errors, stall restart, single instance and stop (29 checks). On the Mac: install, then 30 minutes running: `status.txt` shows `OK`, `latest/latest.jpg` changes every ~20 s, and a `capture.request` is served within about 2 s.

## Pros and Cons of the Options

### imagesnap per frame (ADR-0002)

* Good, because it is simple and was the first design.
* Bad, because it opens and closes the camera for every frame; the A70 failed after a few captures.

### imagesnap time-lapse

* Good, because one session already took 6 photos.
* Bad, because its length is not known, and it still holds the camera for the whole session.

### ffmpeg long-running stream (chosen)

* Good, because one open camera; the C930e streamed reliably in tests.
* Bad, because it needs a supervisor for restarts and stalls.

### Own Swift helper (`AVCaptureVideoDataOutput`)

* Good, because full control of the capture session.
* Bad, because more code to build and maintain than ffmpeg, which already works.

## More Information

* Related: ADR-0001 (camera choice), ADR-0002 (superseded in its capture method), ADR-0003 (trigger file), ADR-0004 (storage), ADR-0005 (interval).
* Test history: [handoff 2026-10-13](../../project/handover/handoff-2026-10-13.md), section 8 onward, plus the 2026-10-21 runs on the C930e.
