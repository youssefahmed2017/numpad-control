# Windows proof of concept

A small test for the planned Windows version of Numpad Control. It checks one
thing: **can Windows tell the external numpad apart from the main keyboard, and
stop only the numpad from typing?** It uses the free
[Interception](https://github.com/oblitum/Interception) driver (the same one
AutoHotInterception uses).

Nothing here changes your keyboard permanently. Every key keeps typing as usual,
except during the 30-second block test, and only for the keyboard you choose.

## Steps

1. **Install Python** from <https://www.python.org/downloads/>. In the installer,
   tick **"Add python.exe to PATH"**.

2. **Install the Interception driver** (needs admin rights and a reboot):
   1. Download `Interception.zip` from
      <https://github.com/oblitum/Interception/releases/latest> and unzip it.
   2. Open the Start menu, type `cmd`, right-click **Command Prompt** →
      **Run as administrator**.
   3. Go into the unzipped folder's `command line installer` folder, e.g. in
      Command Prompt: `cd "%USERPROFILE%\Downloads\Interception\command line installer"`
      (in PowerShell: `cd "$HOME\Downloads\Interception\command line installer"`)
   4. Run: `install-interception.exe /install`
   5. **Restart the PC.**

3. **Put the files together**: make a folder (e.g. `Desktop\numpad-test`) and copy
   into it:
   - `numpad_poc.py` (from this folder)
   - `interception.dll` from the unzipped `Interception\library\x64\` folder

4. **Watch test**: open a normal (not administrator) PowerShell or Command Prompt in
   that folder (PowerShell: `cd ~\Desktop\numpad-test`; Command Prompt:
   `cd %USERPROFILE%\Desktop\numpad-test`) and run:

       python numpad_poc.py

   It lists the keyboards it sees. Press a few keys on the **numpad** and a few on
   the **main keyboard**; each line says which keyboard the key came from. Press
   **Ctrl+C** on the main keyboard to stop. The summary at the end says which
   keyboard number is the numpad.

5. **Block test**: run it again with that number, e.g. if the numpad is keyboard 2:

       python numpad_poc.py --block 2

   Open Notepad and, within 30 seconds, type on both keyboards. **The numpad should
   type nothing; the main keyboard should type normally.** It stops by itself after
   30 seconds.

6. **Send back** the output of both runs (copy the text from the window, or take a
   screenshot).

## Test 2: the real Windows input backend
After the test above worked, this tries the code Numpad Control itself will use
(`numpadctl/platform/windows_numpad.py`). It only captures the numpad; the main
keyboard isn't touched at all.

1. Get the project (Git is needed; it comes with "Git for Windows"):

       cd ~
       git clone https://github.com/youssefahmed2017/numpad-control
       cd numpad-control

   (These work in PowerShell and Windows Terminal. If it's already there:
   `cd ~\numpad-control` and `git pull`.)
2. Copy `interception.dll` (from the unzipped `Interception\library\x64\` folder)
   into `numpad-control\numpadctl\platform\`.
3. Run:

       python -m numpadctl.platform.windows_numpad

   It lists the keyboards, then shows every numpad key as **pressed** / **released**.
   The numpad's keys don't type while it runs; the main keyboard types as usual.
   Check that holding a key shows **one** "pressed" (not a stream of them), and that
   **unplugging the numpad** stops it with "the numpad was unplugged" within a few
   seconds. Ctrl+C stops it. (The `000` key shows as three `0` presses here; the full
   app turns that burst into one `000` key.)

## Test 3: the whole service
This runs Numpad Control's background service on Windows with a ready-made test
setup ([`windows-test-config.json`](windows-test-config.json)). There's no settings
window on Windows yet; that comes later.

1. Update the project and install what it needs (in PowerShell):

       cd ~\numpad-control
       git pull
       python -m pip install -r requirements.txt

2. Put the test setup where the service looks for its settings:

       New-Item -ItemType Directory -Force "$env:APPDATA\numpad-control" | Out-Null
       Copy-Item tools\windows-poc\windows-test-config.json "$env:APPDATA\numpad-control\config.json"

3. Start the service (it prints a line for every key; Ctrl+C stops it):

       python -m numpadctl run

4. Try the keys:

   | Key | Expected |
   |---|---|
   | 1 | the default browser opens |
   | 2 | the project's GitHub page opens |
   | 3 | a Windows notification "Key 3 works on Windows (time)" |
   | 4 / 6 | volume down / up, with Windows' volume popup; holding repeats |
   | 5 | press: play/pause music; hold: next track |
   | 7 | types "Hello from the numpad!" and the time (click into Notepad first) |
   | 8 | Windows' **Run** box opens (Super+R) |
   | 9 | "Copied by the numpad" is on the clipboard (paste it with Ctrl+V) |
   | 0 | a macro (click into Notepad first): one notification, then after 1 second it **types** "typed by a macro" into Notepad (there's no second notification) |
   | 000 | Explorer opens `C:\` |
   | + then - | `+` turns "Test mode" on/off; `-` says whether it's ON or OFF |
   | * | mutes / unmutes the speakers |
   | / | sets the volume to 30% |
   | Enter | press, hold, and double tap each show a different notification |

5. Send back what didn't work, and the window's text (it shows an error line for
   any key that failed).

## If something goes wrong
- If the keyboard stops responding while the test runs, **close the black window
  with the mouse**; that ends the test and gives the keys back.
- To remove the driver: run `install-interception.exe /uninstall` in an
  administrator Command Prompt (same folder as step 2), then restart.
- Some games' anti-cheat systems don't like the Interception driver. If a game
  complains, uninstall it as above.
