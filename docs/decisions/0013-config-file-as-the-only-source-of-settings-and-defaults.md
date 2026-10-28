---
status: "proposed"
date: 2026-10-28
decision-makers: Nils Echterhoff
consulted: Claude (AI assistant)
---

# Config file as the only source of settings and their defaults

## Context and Problem Statement

Default values lived in two places: as constants in the code and as values in the config file. Changing the JPEG quality from 2 to 4 (test H23, 2026-10-28) showed the problem: the change was first made in the code (PR #32, closed unmerged), although Nils wants every setting managed in the config file only. A user who empties or breaks a value should be able to recover the default without reading the code.

## Decision Drivers

* One source of truth for every setting: the config file
* Recoverable: the default of every setting stays visible next to its value
* Robust: an empty or invalid value never stops the watcher
* Self-explaining file: allowed values written next to each setting
* Extensible: a new setting is one more entry, in the same format

## Considered Options

* Defaults in the code, values in the config (as before)
* Flat config with a separate "defaults" block
* One object per setting with value, default and allowed range (chosen)

## Decision Outcome

Chosen option: "one object per setting", because it keeps value, default and allowed range together and needs no code change when a default changes.

* Every key that has a default has the form `{"value": ..., "default": ..., "allowed": "..."}`; `allowed` is optional.
* An empty or invalid `value` makes the watcher use `default` and write one log line.
* The code holds no default values.
* Secrets and paths without a default stay plain values.
* An old flat config is converted once on start, after a timestamped backup is written next to it. Setup script, example config and README use the new format.
* First use: `jpeg_quality` with value 4, default 4, allowed "2-31".

### Consequences

* Good, because a user changes or restores any setting in one file, without touching code.
* Good, because a broken value degrades to the default instead of stopping the service.
* Bad, because the config file becomes longer, and the one-time conversion must be correct (tested, with a backup).

### Confirmation

Built on branch `feat/batch-1` (backlog BL-040). Confirmed when the automated tests for the conversion and the fallback pass and the watcher runs from a converted config on Nils's Mac.

## More Information

Backlog BL-039 (optional review of `jpeg_quality`), BL-040 (this change). Agreed with Nils in the planning conversation on 2026-10-28.
