---
status: "accepted"
date: 2026-10-12
decision-makers: Nils Echterhoff
consulted: Claude (AI assistant)
---

# Integrate the agent through a shared folder and trigger file

## Context and Problem Statement

During whiteboard sessions Claude runs in the Claude desktop app on the MacBook, with file access and computer use but no shell. The agent must read current frames and ask for a fresh one on demand.
How does the agent get images and request new ones?

## Decision Drivers

* Works with what the current Claude app session has: files, no shell
* Zero clicks for Nils during a session
* Low build effort now, upgrade path later

## Considered Options

* Folder + trigger file (capture folder connected to the Claude desktop app)
* Local MCP server exposing `capture_whiteboard`, plus a custom skill
* Skill + local shell (agent runs `imagesnap` itself)

## Decision Outcome

Chosen option: "Folder + trigger file", because it is the only option that works with file access alone and needs no extra component beyond the capture service.

### Consequences

* Good, because the agent only reads files and creates an empty `capture.request`.
* Good, because the same folder can sync to Nextcloud for other agents.
* Bad, because a fresh frame has ~1–2 s latency and the agent must poll for the request file to disappear.
* Neutral, because the MCP option stays open as the most robust upgrade (~1–2 h).

### Confirmation

With the folder connected: the agent writes `capture.request`, the file disappears within ~2 s, and `latest.jpg` has a newer timestamp.

## Pros and Cons of the Options

### Folder + trigger file

* Good, because no shell and no extra server.
* Bad, because indirect (file-based handshake).

### Local MCP server + skill

* Good, because most robust, a real tool call with a result.
* Bad, because ~1–2 h to build and one more process to run.

### Skill + local shell

* Good, because simplest logic.
* Bad, because the current Claude app session has no shell on the Mac.

## More Information

* Source: [handoff 2026-10-12](../handoff-2026-10-12.md), section 8.
* Agent procedure: `CLAUDE.md`, "Reading the whiteboard".
* Accepted by Nils Echterhoff on 2026-10-12.
