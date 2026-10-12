# Claude Code: install and verify the capture service on the Mac (BL-002)

Paste the block below into a Claude Code session in Terminal on the Mac.

```text
Task: install and verify the whiteboard capture service on this Mac (backlog item BL-002).

CONTEXT
- Repo: /Users/nilsechterhoff/Developer/NE_Whiteboard Capture
  (github.com/nilsechterhoff/Whiteboard-Capture, branch main). Read README.md and CLAUDE.md first.
- If that folder does not exist yet, stop and ask me before cloning it.
- Camera: APEMAN A70, USB, in "PC Camera" mode. Expected name in `imagesnap -l`: "J1455".
- Capture folder (Nextcloud, synced; contains spaces, quote it):
  /Users/nilsechterhoff/Library/CloudStorage/Nextcloud-cloud.echterhoff.dk-nilsechterhoff/Services/Whiteboard Capture

RULES
- Do NOT modify, commit to, or push to the "standards" repo (nilsechterhoff/standards). Read-only.
- Do NOT edit, commit or push anything in this repo. If a change seems needed, stop and report the proposed diff.
- Do NOT create files or folders anywhere except inside the capture folder above.
- Do NOT use sudo. Do NOT change macOS privacy settings yourself; if access is denied, stop and tell me what to click.
- Ask before anything not listed in the steps below.

STEPS (run in order, show the output of each)
1. `command -v brew` — if missing, stop and tell me.
2. `command -v imagesnap || brew install imagesnap`
3. `imagesnap -l` — confirm "J1455". If the name differs, use the exact listed name as WBC_CAMERA in step 5.
4. Test shot (macOS may ask for camera access; I will click Allow):
   `imagesnap -w 1 -d "J1455" "/Users/nilsechterhoff/Library/CloudStorage/Nextcloud-cloud.echterhoff.dk-nilsechterhoff/Services/Whiteboard Capture/test-terminal.jpg"`
   Confirm the file exists and is > 50 KB.
5. Install the service (default capture folder is the Nextcloud folder):
   `cd "/Users/nilsechterhoff/Developer/NE_Whiteboard Capture" && project/setup/install.sh`
   (prefix with WBC_CAMERA="<name>" only if step 3 showed a different name)
6. Wait 40 seconds, then check (CAP = the capture folder, quoted):
   a. `cat "$CAP/status.txt"` → expect "OK <timestamp>"
   b. `ls -la "$CAP" "$CAP/latest" "$CAP/hourly" "$CAP/daily"` → expect latest/latest.jpg, one file in hourly/, one in daily/
   c. `tail -30 ~/Library/Logs/whiteboard-capture.log`
   d. `launchctl print gui/$(id -u)/com.nilsechterhoff.whiteboard-capture | head -30`
7. Live check: note the modification time of latest/latest.jpg, wait 25 s, confirm it changed.
8. Trigger check: `touch "$CAP/capture.request"`, wait 3 s, confirm the file is gone and latest/latest.jpg is newer.
9. Open latest/latest.jpg and describe what is visible (whiteboard in frame? text readable?).
10. Ask me whether to delete test-terminal.jpg.

IF status.txt says CAPTURE_FAILED, or nothing is written, while step 4 worked:
- The launchd service likely lacks camera access or access to the Nextcloud folder (macOS grants both per process).
- Do not work around it. Report the log lines, the `launchctl print` output, and whether a macOS prompt appeared. Then stop.

FINAL REPORT (short table)
| Step | Result | Notes |
for steps 1–10, plus the exact camera name and any errors.
```
