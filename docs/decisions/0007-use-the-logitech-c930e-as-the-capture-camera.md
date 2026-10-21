---
status: "proposed"
date: 2026-10-21
decision-makers: Nils Echterhoff
consulted: Claude (AI assistant)
---

# Use the Logitech C930e as the capture camera

## Context and Problem Statement

ADR-0001 chose the APEMAN A70 as the capture camera because it was already owned. In tests on 2026-10-12 and 2026-10-13 the A70 failed repeatedly: after a few captures it stopped delivering photos and Photo Booth showed a black picture until it was power-cycled (see [ADR-0006](0006-capture-from-an-open-camera-stream.md)). A continuous ffmpeg stream from the A70 stalled after two to three frames. A Logitech C930e, already connected to the Mac, streamed 15 frames in 15 seconds in two separate runs.
Which camera should capture the whiteboard?

## Decision Drivers

* A camera that delivers frames reliably over a long session
* No purchase within the budget of €60 (maximum €80) (ADR-0001)
* Readable text across the board at about 1 m (ADR-0001)
* The camera must work with the ffmpeg stream design (ADR-0006)

## Considered Options

* Keep the APEMAN A70 (ADR-0001)
* Logitech C930e (already owned, connected to the Mac)
* Raspberry Pi Zero 2 W + Camera Module 3 (fallback named in ADR-0001, about €55–60)

## Decision Outcome

Chosen option: "Logitech C930e", because it costs nothing, it is already connected, and it streamed reliably in the tests where the A70 failed.

Details:

* The camera is selected by its serial number, `7B5E845E`, because a second C930e (`2BE82FAE`) is also connected. It stays as a spare.
* The capture settings are 1920 × 1080 at 30 fps (the C930e's full-HD mode).
* The A70 is no longer used for capture. It stays as a spare.

This supersedes the camera choice of ADR-0001 (the A70). ADR-0001's decision to use a host computer over USB, and its fallback options, stay in force.

### Consequences

* Good, because no new hardware is needed.
* Good, because it has streamed reliably in the tests so far.
* Bad, because the C930e is a webcam, not a fixed mount camera. Its field of view and focus at about 1 m over a 120 × 90 cm board are not yet checked. A test frame from the arm mount is needed.
* Bad, because it needs the MacBook to be connected and running, as ADR-0001 already states.
* Neutral, because the C930e's mount and position (BL-004) still need to be decided.

### Confirmation

A test frame from the planned mount position shows normal and small text readable across the whole board. This is checked on the Mac before the camera is accepted.

## Pros and Cons of the Options

### Keep the APEMAN A70

* Good, because already owned.
* Bad, because it failed repeatedly in tests (ADR-0006).

### Logitech C930e

* Good, because owned, already connected, and it streamed reliably in tests.
* Bad, because it is a webcam, not a fixed mount camera, and its readability at 1 m is not yet checked.

### Raspberry Pi Zero 2 W + Camera Module 3

* Good, because best image quality and always-on operation (ADR-0001).
* Bad, because about €55–60, at the budget limit, and it needs new software set up.

## More Information

* Related: ADR-0001 (camera choice, superseded here for the camera), ADR-0006 (capture method).
* The A70 failure details are in the handoff of 2026-10-13, section 10.
* Accepted by Nils Echterhoff: pending.
