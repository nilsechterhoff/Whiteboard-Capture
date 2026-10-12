---
status: "proposed"
date: 2026-10-12
decision-makers: Nils Echterhoff
consulted: Claude (AI assistant)
---

# Capture with the APEMAN A70 over USB on the MacBook

## Context and Problem Statement

An agent needs current images of a 120 × 90 cm whiteboard. The images must land in Nextcloud, Google Drive, a network drive or similar; budget is max €60 (tolerance €80); power via USB, PoE or battery; no vendor cloud lock-in.
Which camera and host should capture the board?

## Decision Drivers

* Budget: max €60, hard cut above €80
* Readability: roughly ≥1 px/mm on the board
* No vendor cloud lock-in; images must reach an ordinary folder
* Low setup effort, hardware already at hand preferred
* Whiteboard sessions already run on the MacBook in the Claude app

## Considered Options

* A. Host + existing USB camera (APEMAN A70 on the MacBook)
* B. Raspberry Pi Zero 2 W + Camera Module 3
* C. ESP32-S3 + OV5640 (DIY)
* D. Consumer Wi-Fi camera (Tapo C250) + host grabbing RTSP
* E. PoE IP camera (Reolink RLC-510A)
* F. Spare iPhone with an IP camera app
* G. A70 over its own Wi-Fi hotspot (Novatek HTTP API)

## Decision Outcome

Chosen option: "A. Host + existing USB camera (APEMAN A70 on the MacBook)", because it costs €0, uses hardware already tested (1920×1080 at 20 fps, runs on USB power without a battery), and gives readable normal and small text at ~1 m distance.

### Consequences

* Good, because no purchase and no vendor cloud.
* Good, because the A70 is a standard UVC webcam on macOS, so plain tools (`imagesnap`) work.
* Bad, because capture only runs while the MacBook is on and connected.
* Bad, because the A70 must be switched to "PC Camera" mode; in "Mass Storage" mode it is not seen as a camera.
* Neutral, because fisheye and exposure (doorway in frame) need an angle, a lamp, or later software correction.

### Confirmation

A frame taken at ~1 m from the arm mount shows normal and small text readable across the board.

## Pros and Cons of the Options

### A. A70 on the MacBook

* Good, because €0 and already tested.
* Good, because full HD at 20 fps over USB.
* Bad, because tied to the MacBook being present.

### B. Pi Zero 2 W + Camera Module 3

* Good, because best image quality (12 MP, autofocus) and always-on.
* Bad, because ~€55–60, at the budget limit.

### C. ESP32-S3 + OV5640

* Good, because ~€15–30.
* Bad, because more firmware work and only 5 MP.

### D. Tapo C250

* Good, because ~€37 and 4K.
* Bad, because RTSP only, so a host is still needed to grab frames.

### E. Reolink RLC-510A (PoE)

* Good, because FTP and HTTP snapshot built in.
* Bad, because ~€60–87 plus a PoE injector, at or over the budget edge.

### F. Spare iPhone

* Good, because €0–10.
* Bad, because iOS apps must stay in the foreground; Lite editions watermark frames.

### G. A70 over its Wi-Fi hotspot

* Good, because no cable.
* Bad, because hotspot-only (cannot join the home network), fragile.

## More Information

* Source: [handoff 2026-10-12](../handoff-2026-10-12.md), sections 3–6.
* Fallback: a Pi Zero 2 W (~€30) as always-on host with the same A70. Upgrade path: option B.
* Revisit if the MacBook is often unavailable during sessions, or if readability is not enough.
