---
status: "proposed"
date: 2026-10-23
decision-makers: Nils Echterhoff
consulted: Claude (AI assistant)
---

# Camera-agnostic capture: try all cameras, remember the last working one

## Context and Problem Statement

ADR-0008 runs a Dropbox API watcher that takes the photo on the Mac. It names `imagesnap` for the camera step. In tests, `imagesnap` selects a camera only by name, and two Logitech C930e units are connected, so it cannot tell them apart. A plan to find the whiteboard camera by serial number and Unique ID was rejected: the Unique ID is tied to the USB port, and the ffmpeg index changed between runs without a replug. The camera therefore has to be chosen from what the picture shows, not from an ID.

How does the watcher find the camera that sees the whiteboard, without a stable ID, and keep the time per request low?

## Decision Drivers

* Reliability first: no photo from the wrong camera, no silent fallback
* No ID or serial lookup, no extra software (no Swift helper, no PyObjC)
* Works on the Mac now and on the Windows PC "Terox" (one camera there)
* Short time per request (the voice agent waits 10 s, then looks once)
* Each request tried at most once per camera (no loops)

## Considered Options

* Choose the camera by serial number and Unique ID (rejected: the mapping to the ffmpeg index changed without a replug)
* Use `imagesnap` by name (rejected: two identical names)
* Try all cameras in order, remember the last working index as a hint, check each picture (chosen)

## Decision Outcome

Chosen option: "Try all cameras in order, remember the last working index as a hint, check each picture", because it needs no ID, works with identical camera names, and still returns the whiteboard even when the index changes.

The rules:

1. List the video devices with ffmpeg (avfoundation). An optional config setting `camera_name` filters by name (set to "Logitech" now). Empty means all cameras count. Screen capture is not a camera and is ignored.
2. Keep the index of the last camera that showed the whiteboard in `last_camera.json` (config folder). It is only a hint: it is tried first, and it is never trusted blindly.
3. Per request: try the remembered camera first, then the others in listing order. Each camera is tried once per request; after a dark frame the same camera is reopened at once, up to 2 times, before the next camera.
4. Per try: take the first frame (no warm-up), rotate 180° (config, default true), then check brightness. A near-black frame is a dark frame: the camera is closed and reopened at once, up to 2 reopens per camera, then the next camera. Measured: a working camera is bright at the first frame, and a dark start stays dark for about 10 s but is fixed by reopening.
5. The describe step must start its answer with `whiteboard: yes` or `whiteboard: no`. `no` moves on to the next camera. `yes` saves that camera as the last working one and writes the description.
6. If all cameras fail: one description with `status: error` and one reason line per camera.
7. Only the image of the successful camera is uploaded.

With `camera_name` empty, the code is the same and works for any camera set. The Windows port uses the same rules with `ffmpeg` and one camera.

### Consequences

* Good, because no serial, USB location or Unique ID is needed, and the code stays camera-agnostic.
* Good, because a wrong camera gives a rejected try, not a wrong photo: the describe step has to answer `whiteboard: yes`.
* Good, because the remembered camera is usually first, so most requests need one photo.
* Bad, because every camera that is tried costs time (a dark try takes about 6 s, a camera that hangs takes the 25 s limit).
* Bad, because a dark start costs one or two reopens (about 5 to 7 s each) before the picture is bright (measured below).
* Neutral, because the `Logitech` filter is a config setting, so the set of cameras can change without a code change.

### Confirmation

Fresh plug, 2026-10-24, before the reopen change (request 0012, warm-up version, both cameras reconnected): first try of camera 1 dark (brightness 0.8, photo 6.4 s), retry bright (127.1, photo 4.4 s, describe 11.4 s), total before the description upload 26.6 s, request to description file 35.6 s.

Cold and warm test, 2026-10-23 (service paused, 5 minutes idle before each cold run, frames every 0.5 s for 10 s, mean brightness per frame):

| Line # | Run | Brightness at 0 s | At 10 s | First at or above 20 | Stable (under 5 % change for 1.5 s) |
|---|---|---|---|---|---|
| 1 | Camera 1, cold 1 | 9 | 9 | never in 10 s | never |
| 2 | Camera 1, cold 2 | 7 | 8 | never in 10 s | never |
| 3 | Camera 1, cold 3 | 134 | 139 | 0.0 s | 0.5 s |
| 4 | Camera 1, warm | 142 | 138 | 0.0 s | 0.5 s |
| 5 | Camera 0, cold 1 to 3 and warm | 128 to 136 | 136 to 137 | 0.0 s in all four | 0.5 s in all four |

Real requests on the service after the reopen change, 2026-10-24, 10 minutes idle between them (requests 0013 to 0015): each first try dark (brightness 0.6 to 0.8), the one reopen bright (124.5 to 130.0), all status ok. Total before the description upload 22.3 to 22.4 s; request to description file 34.6, 33.9 and 33.0 s.

Camera 1 was dark for the whole 10 s in 2 of 4 runs. Its dark frames have no room or board structure, which fits a covered lens or a dark scene; the frames alone cannot tell which. Camera 0 was never dark in these runs.


Measured on the Mac, launchd service, 2026-10-23, three real requests with 10 minutes idle between them (requests 0009 to 0011):

| Line # | Request | Status | Camera 1, first try | Camera 1, retry | Total before description upload | Seconds to description (request to file) |
|---|---|---|---|---|---|---|
| 1 | 0009 | ok | dark, brightness 1.5, photo 5.7 s | ok, brightness 130.3, photo 4.1 s, describe 10.8 s | 25.9 s | 35.3 s |
| 2 | 0010 | ok | dark, brightness 1.3, photo 5.9 s | ok, brightness 130.0, photo 4.2 s, describe 10.5 s | 27.9 s | 38.0 s |
| 3 | 0011 | ok | dark, brightness 1.4, photo 5.6 s | ok, brightness 129.9, photo 4.1 s, describe 8.5 s | 24.5 s | 34.0 s |

Every first try was dark, and every retry gave a bright, upright whiteboard. Camera 0 was never needed. The time to the description is above the 10 s target; tuning is open (BL-018).

## Pros and Cons of the Options

### Choose the camera by serial number and Unique ID

* Good, because the serial is stable across replugs.
* Bad, because the Unique ID is tied to the USB port, and the ffmpeg index did not follow it.

### Use imagesnap by name

* Good, because it is the simplest command.
* Bad, because two cameras have the same name, and imagesnap cannot select one.

### Try all cameras, remember the last working one (chosen)

* Good, because it needs no ID, works with identical names, and uses a picture check instead of a lookup.
* Bad, because a failed try costs seconds, and the first frame is often dark.

## More Information

* Related: ADR-0006 (describe step and voice text), ADR-0008 (watcher; this ADR changes its camera step only).
* Backlog: BL-020 (camera decision), BL-018 (time to description), BL-024 (Terox port, Task Scheduler).
* Not decided here: whether to keep a warm camera loop (BL-026) or reduce the first-try cost further.
* Accepted by Nils Echterhoff: pending.
