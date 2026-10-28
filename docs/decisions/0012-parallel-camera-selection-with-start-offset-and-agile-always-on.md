---
status: "accepted"
date: 2026-10-28
decision-makers: Nils Echterhoff
consulted: Claude (AI assistant)
---

# Parallel camera selection with a start offset and frame delay; agile always on

## Context and Problem Statement

The watcher must find the board camera among the Logitech cameras, and the two camera indices change between runs. ADR-0009 finds the camera by checking one index after another (the remembered one first). ADR-0011 keeps the camera open in agile mode, but as an option that Nils switches on, and lean stays the default. The lab tests of 2026-10-27 (h13 to h18) showed three things:

* Two streams started at the same instant often attach to the same camera: 9 of 15 runs without an offset.
* A start offset of 0.1 s separates the cameras: 0 collisions in 40 runs, including 10 quick reopens with a 1 s pause. A 0.5 s offset gave 1 collision in 30 runs.
* The first frame after opening is often soft or blurry (4 of 10 board frames fell below 70 % of the median sharpness in h18), so the frame used for selection must come some time after the stream starts.

Nils asked for parallel selection with the streams open, and for agile to be the normal path.

## Decision Drivers

* The request should return a board answer within about 25 s after a (re)start and within about 11 s with the streams open
* No camera collision: both streams must not end up on the same camera
* The frame used for the board check must be sharp enough to read
* No new mode for Nils to choose: the config keeps its values, and the old switches are ignored with one warning
* Lean stays only as the internal fall back when the streams cannot start

## Considered Options

* Sequential selection (ADR-0009): one index after another, one frame each
* Parallel capture of both cameras with no offset (tested 2026-10-25, then rejected)
* Parallel selection with a start offset and a frame delay (chosen)
* Keep agile optional (ADR-0011 as it was)

## Decision Outcome

Chosen option: "parallel selection with a start offset and a frame delay; agile always on", because the lab showed that a 0.1 s offset separates the cameras and that a frame taken a couple of seconds after the start is sharp enough.

**Selection at stream start**

1. `camera_name` must equal the device name exactly. A substring is not enough. If nothing matches exactly, the error names every device found, so the config can be corrected.
2. One ffmpeg stream per matching camera, each one `start_offset_seconds` (default 0.1) after the previous one.
3. A frame is checked `selection_frame_delay_seconds` (default 2) after its own stream started, so autofocus and exposure have settled.
4. Dark frames are skipped without a describe call (existing dark check).
5. Frames are checked one by one in the check order; the first board frame wins, and the other streams close at once. The passing stream stays open.
6. Check order: with exactly two matching cameras, the camera that did not hold the board last time goes first. Otherwise the last index in the listing goes first, and the rest keep the listing order. Each selection logs whether that first guess was right.

**Requests**

7. A request reads the newest frame of the open stream and runs the board check. If it fails, the streams close and selection runs again.

**Retry**

8. If no frame passes, all streams close, the watcher waits `retry_pause_seconds` (default 1), and selection runs again, at most `capture_retries` times (default 2). After the last try the existing error code and message are used, and the rejected photos are kept as before.

**Logging**

9. Each selection logs the camera list, the start times of the streams, the order checked, brightness and sharpness of each frame, the result, the retries, and whether the guess was right or wrong. The sharpness score is the variance of the 3x3 Laplacian on a 480 x 270 grayscale copy of the frame.

**Agile always on**

10. `agile_enabled` is removed. The old `mode` key and `agile_enabled` are ignored, and the log warns once if either is present. The lean path stays only as the fall back when the streams cannot start.
11. `min_board_fill_percent` defaults to 50 in the code (Nils's config is set to 50; 0 means off).

**Relation to earlier decisions**

* This ADR replaces the sequential camera step of ADR-0009 (the check order is kept as a first guess only).
* This ADR changes ADR-0011: lean is no longer a mode that Nils chooses; it is the fall back only.

## Consequences

* Good: the camera collision seen in the lab is avoided at a 0.1 s offset; a board answer comes from a sharp frame; the streams stay open, so later requests are fast.
* Good: the config has no mode to choose; the settings that matter are listed in the README table.
* Bad: while the streams are open, the camera light and the camera are in use by the watcher. This was already the case with agile, and idle timeout still closes the streams after 10 minutes.
* Bad: the sharpness threshold is not used yet. The log reports the score for each frame, so a threshold can be chosen from real runs.
* Bad: the selection can still fail if both cameras are pointed at the wrong view; the error then lists each frame's reason.
