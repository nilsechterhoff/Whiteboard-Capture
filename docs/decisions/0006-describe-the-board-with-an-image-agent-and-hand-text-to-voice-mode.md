---
status: "accepted"
date: 2026-10-22
decision-makers: Nils Echterhoff
consulted: Claude (AI assistant)
---

# Describe the board with an image agent and hand text to voice mode

## Context and Problem Statement

The top requirement is to brainstorm in Claude's **live voice mode** in the desktop app: hands-free, no typing, no push-to-talk, no clicks. Claude must be able to say what the whiteboard shows and give feedback on what Nils just drew.
Voice mode has to receive the board somehow. How does the content of the whiteboard reach the voice agent?

## Decision Drivers

* Voice mode compatibility is the hard requirement (hands-free, no push-to-talk)
* Keep complexity low: no self-built or self-hosted MCP, no extra connectors for the MVP
* Good enough for a few months, not a product
* A short delay is acceptable

## Considered Options

* Give the voice agent the image (via a connector, storage or a local extension)
* Let a separate image agent turn the photo into text; voice reads the text
* Same, but through a self-built remote MCP that calls the Claude API

## Decision Outcome

Chosen option: "Let a separate image agent turn the photo into text; voice reads the text", because every way of handing an **image** to voice mode failed in tests, while reading **text** from a connector works.

The voice agent only **interprets** (feedback, reasoning); the image agent only **describes** (transcribed text, shapes, arrows, relations, short summary).

### Consequences

* Good, because it satisfies the voice requirement with connectors that already exist.
* Good, because the voice agent never needs to see an image.
* Bad, because the voice agent reasons on a second-hand description, not on the board itself.
* Bad, because description quality limits answer quality and is untested on real boards.
* Neutral, because the central assumption ("voice mode cannot view images") rests on three failed tests, not on documentation.

### Confirmation

Nils asks in voice mode about a freshly drawn element and the answer matches the board. Re-check the assumption if Claude's voice mode changes: if voice mode ever views images, this ADR can be revisited.

## Pros and Cons of the Options

### Give the voice agent the image

* Good, because the voice agent would see the board itself.
* Bad, because it failed in every test: Google Drive and Dropbox connectors, a JPEG in project files (file and pixel size visible, picture not), and the local Filesystem extension (not available in voice at all).

### Image agent turns the photo into text

* Good, because text from Dropbox is proven readable in voice (see ADR-0007).
* Bad, because of the second-hand description and the extra agent to run.

### Self-built remote MCP that calls the Claude API

* Good, because it can wait for the result and return it in one call, with a question parameter.
* Bad, because it needs an always-on host and an API key; Nils wants to avoid this for the MVP. Kept as a later option (MVP C in [project/mvp-alternatives.md](../../project/mvp-alternatives.md)).

## More Information

* Tests by Nils on 2026-10-21 and 2026-10-22; details in [project/mvp-alternatives.md](../../project/mvp-alternatives.md).
* Related: ADR-0007 (how request and description travel).
* Accepted by Nils Echterhoff on 2026-10-22.
