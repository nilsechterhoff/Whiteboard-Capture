# Handover: Whiteboard Capture, session 2026-10-12 (evening)

Paste this whole file as the first message of the new Claude Code session, or tell the session to read it.

---

## 1. Context

| Line # | Item | Value |
|---|---|---|
| 1 | Owner | Nils (engineer, ADHD: short answers, tables, numbered lines, no long prose) |
| 2 | Goal | Near-live photos of a 120 × 90 cm whiteboard so Claude can follow brainstorming sessions (incl. voice mode) |
| 3 | Repo (GitHub) | `nilsechterhoff/Whiteboard-Capture`, branch `main` |
| 4 | Repo on the Mac | `/Users/nilsechterhoff/Developer/NE_Whiteboard Capture` (moved out of `~/Documents`: launchd cannot read there) |
| 5 | Capture folder (Nextcloud, not in Git) | `/Users/nilsechterhoff/Library/CloudStorage/Nextcloud-cloud.echterhoff.dk-nilsechterhoff/Services/Whiteboard Capture` (spaces: always quote) |
| 6 | Standards | `nilsechterhoff/standards`: **read-only, never write to it**. STD-000 (link, don't copy; define before apply), STD-001 (MADR ADRs in `docs/decisions/`, Claude writes `proposed`, only Nils sets `accepted`) |
| 7 | Read first | `README.md`, `CLAUDE.md`, `project/backlog.md`, `docs/decisions/0001`–`0005` |

## 2. Rules learned in this session (follow them)

| Line # | Rule |
|---|---|
| 1 | **Ask Nils** for the exact location and name before creating any file or folder on his Mac |
| 2 | **Do not assume.** State only what outputs and screenshots show; ask about everything else. Check earlier results before asking for a new test |
| 3 | When Nils's own experience contradicts docs or the environment, his experience wins |
| 4 | Commands meant for Nils's Terminal must be **pure shell**, never mixed with English instructions |
| 5 | **Never** run `imagesnap` or a capture command in the foreground without a time limit (it can hang and freeze the window). macOS has no `timeout`: `cmd > /tmp/x.out 2>&1 & p=$!; sleep 15; kill $p 2>/dev/null` |
| 6 | Code changes: branch → PR → **ask Nils before merging** |
| 7 | Re-check current settings before quoting numbers (interval is **20 s**, ADR-0005) |
| 8 | Fix own errors before pursuing new paths |

## 3. Current state

| Line # | Item | State |
|---|---|---|
| 1 | `main` | `b25645a` (PR #9 merged: script error fixes, tests 29/29) |
| 2 | Service (launchd) | **Not installed** (uninstalled; no plist, no processes) |
| 3 | Mac tools | Homebrew `/opt/homebrew` (in `~/.zprofile`), `imagesnap` 0.3.0.2. `ffmpeg`: not checked |
| 4 | Camera | APEMAN A70, USB, PC Camera mode, listed as **`J1455`** |
| 5 | Camera permission | `imagesnap` and Terminal: on (System Settings → Privacy & Security → Camera) |
| 6 | Capture folder | `latest/`, `hourly/`, `daily/` empty; `test-terminal.jpg` (Nils decides whether to delete) |
| 7 | Leftovers on the Mac | `/tmp/camtest-report.txt`, `/tmp/camtest-err.log`, `/tmp/camtest-driver.out`, `/tmp/wbc-run.log` (ask before deleting) |

## 4. Findings (facts)

| Line # | Finding |
|---|---|
| 1 | After a **power-cycle** of the A70, imagesnap delivers **one** photo, then fails until the next power-cycle (seen 3×: 18:16, 19:06, 20:50) |
| 2 | Failures happen from **Terminal too** (camera permission fine), so launchd is **not** the cause |
| 3 | The MacBook's FaceTime camera works with the same imagesnap command → problem is **A70-specific** |
| 4 | Warm-up 1/3/5/8 s: all fail. Temp file name, Nextcloud folder, double runs: ruled out |
| 5 | QuickTime and Photo Booth show the A70's **video** fine. While QuickTime shows it, it holds the camera exclusively |
| 6 | imagesnap 0.3 (Swift rewrite, Jan 2026) **opens and closes the camera for every photo** and uses Apple's **photo function** (`AVCapturePhotoOutput`, preset `.photo`), not the video stream |
| 7 | Error "Capture error: The operation could not be completed" = camera reported an error; only "Failed to capture photo." = no answer within imagesnap's own 10 s limit |
| 8 | `imagesnap -l` only lists devices (does not open the camera) |

## 5. Hypotheses (not proven)

| Line # | Hypothesis |
|---|---|
| 1 | **Main:** the A70 gets stuck from being **opened and closed repeatedly** (the per-photo design, ADR-0002) |
| 2 | **Alternative:** the A70 cannot serve the **photo function** reliably, only its video stream |
| 3 | Either way the fix is: **open the camera once** and grab frames from the running video |

## 6. Next steps

| Line # | Step | Detail |
|---|---|---|
| 1 | Power-cycle the A70 | Nils: unplug, wait 10 s, plug in, select PC Camera |
| 2 | Time-lapse test (camera opened **once**) | `imagesnap -w 3 -t 20 -n 6 -d J1455 /tmp/tl.jpg; ls -la /tmp/tl*.jpg; rm -f /tmp/tl*.jpg` (about 2 min; run in background with a time limit) |
| 3 | Read result | All 6 work → hypothesis 1 confirmed. Stops after first → hypothesis 2 |
| 4 | If needed: video-stream test | Check `command -v ffmpeg` (ask Nils before `brew install ffmpeg`); list modes: `ffmpeg -hide_banner -f avfoundation -list_devices true -i ""`; continuous grab, e.g. `ffmpeg -f avfoundation -framerate <mode> -video_size <mode> -i "J1455" -vf fps=1/20 -update 1 -y /tmp/live.jpg` for 2 min |
| 5 | Decide | ADR-0006 (`proposed`): keep the camera open (supersedes ADR-0002's per-photo capture). Nils accepts |
| 6 | Rebuild | Script keeps one long-running capture process; tiers, status, trigger file stay. Tests first, then PR |
| 7 | Verify under launchd | Camera access for the new tool from the background service is **unverified** |

## 7. Open backlog items

BL-002/BL-014 (install and verify on the Mac), BL-003 (connect capture folder, test `capture.request`), BL-004 (arm mount), BL-012 (Nextcloud access for all Claude instances), plus ideas BL-007 to BL-010. See `project/backlog.md`.
