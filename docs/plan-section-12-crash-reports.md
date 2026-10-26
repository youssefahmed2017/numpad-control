# 12. Crash reports, not telemetry

*Added Oct 26, 2026. It explains what sections 4 and 9 mean by "optional telemetry and
crash reports", so nobody reads it as Windows-style telemetry that records what you do.*

**Numpad Control collects nothing while it works.** It has no usage statistics, no
analytics, no "phone home" and no account. Its only outgoing report is a crash report,
and only when the user says yes to that specific crash.

## 12.1 What happens when something crashes

1. **It's saved on the user's own computer.** The crash (the error, where in the code it
   happened, the version, the operating system) goes into a file in Numpad Control's
   state folder, with the user name and home folder taken out. Keys typed, settings,
   window titles and file contents are never in it.
2. **A plain system dialog asks:** "Numpad Control crashed. Do you want to report it?
   **[Yes] [No]**". It's the operating system's own basic dialog (Windows' message box;
   on Linux zenity, kdialog or xmessage), not the app's Qt interface, because the
   interface may be what broke. The plain, old-fashioned look is on purpose.
3. **Yes opens a pre-filled GitHub issue in the browser.** The user sees every word
   before deciding to send it, and can add what they were doing. **No** sends nothing;
   the file stays on their computer.

It asks every time; there is no "always send" setting that could send reports silently.

## 12.2 When the crash handler itself is in trouble

Each step falls back to the next, so a crash can't go unnoticed:

| What fails | What happens instead |
|---|---|
| The crashed program can't be trusted to show anything | The dialog runs in its own separate process |
| That process can't start | The crashing process shows the dialog itself |
| No dialog can be shown (no desktop yet, no dialog program) | The report waits and is asked about the next time Numpad Control starts |
| Saving the report fails too | The error is written to the log, and the program's normal error message still appears |
| The same crash keeps repeating (a service restarted again and again) | Each one is saved, but the user is asked only once per hour |
| The dialog's process died before an answer | Asked again later, at most 3 times |

## 12.3 Why this way

- **Trust:** the program sees every key on the numpad. A clear "nothing is sent unless
  you click Yes, and you see it first" promise matters more than collecting more data.
- **Phase 0 (section 8):** crash reports are needed to support hundreds of different numpad
  models. Reports arrive as GitHub issues, where they can be answered, without a server.
- **Later, with the backend (section 11):** reports can go to the open backend instead of
  GitHub, still only after Yes, still showing exactly what is sent.

## 12.4 Changes to the plan

- Section 4, "optional telemetry and crash reports" → **"crash reports, asked about every
  time; no telemetry"**.
- Section 9, privacy risk, mitigation: add "no telemetry; crash reports only on Yes,
  shown before sending".
- Section 8, KPIs: crash-free sessions can't be measured without telemetry, so use
  **crash reports received per 1,000 downloads** (from GitHub issues) instead.
- The privacy policy (section 9) can say plainly: nothing is collected; reports are sent
  only by the user, through GitHub.
