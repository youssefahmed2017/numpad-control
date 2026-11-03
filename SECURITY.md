# Security

## Reporting a problem

Please report a vulnerability privately, through GitHub: this repository's **Security** tab →
**Report a vulnerability**. Don't open a public issue for it. A fix and a new release come first,
and the details are public afterwards.

## What is protected, and how

- **Updates.** Releases are signed offline with an Ed25519 key (`numpadctl/release_key.py` has the
  public half; `tools/sign-release` signs). The updater checks the signature, then that the commit
  (git copies), the `source.zip` hash (zip copies) or the Windows installer's hash (installer copies,
  which update by running the new Setup silently) is exactly what was signed, before it changes or runs
  anything. The installer is built by CI and signed after you have looked at the run. A stolen GitHub account, a moved tag or a swapped download is therefore refused. It does
  **not** protect against a stolen *signing key* (keep it offline, with a second copy) or against
  code you sign by mistake. The first signed release is the one that starts this: earlier copies trusted
  GitHub alone.
- **Run Python.** Snippets are checked before saving and before running, run in a separate process with
  CPU, memory, file and process limits, and can only *ask* the app to open a web page or show a
  notification (a few times, with short text). It is a guardrail, not a perfect jail: don't run
  snippets from people you don't trust. The restrictions are tested with real escape attempts
  (`tests/test_sandbox.py`).
- **The service's connection.** Linux: a socket only your user can open. Windows: a localhost port
  that needs a random key kept in a file only your user can read. It accepts at most 16 clients
  and ignores or drops anything malformed. It can't run actions or change settings; only report keys.
- **Crash reports.** Nothing is sent by itself. You read the pre-filled GitHub issue before sending it.
- **Commands.** Every program NumpadControl starts gets its arguments as a list (never through a shell),
  with text kept apart from options.

## Limits you should know about

- **Anything running as you can do what you can do.** NumpadControl doesn't try to protect itself from
  other programs running as the same user: they can edit `config.json`, whose actions run as you.
  Treat a settings file from someone else like a script from someone else.
  The same goes for an imported profile (*Profile ⋯ → Import profile…*): it is checked and you see what it does before
  it is added, but its actions then run as you.
- **The Windows keyboard hook DLL** (`numpadhook.dll`) is loaded into other programs and sits in the
  per-user install folder (`%LOCALAPPDATA%\Programs\NumpadControl`), which your account can write. So
  malware already running as you could replace it, and the same malware could equally replace
  NumpadControl's own files; a per-user install can't prevent either. What would: installing for all
  users (so the files need administrator rights to change) and signing the DLL with a code-signing
  certificate (see [docs/code-signing.md](docs/code-signing.md)). Neither is done yet. The DLL in the Windows installer is
  compiled from `numpadhook.c` in the CI build (not the copy committed to git, which is for installs from source).
- **Extra keyboards (Linux).** Letting NumpadControl use a whole keyboard as a pad installs a udev rule
  that lets every program you run read that keyboard. The app asks before it does so, **Remove this
  keyboard** offers to take it away, and the uninstall removes them all. Don't allow a keyboard you
  type passwords on.
- **First install.** `curl … | bash` and `irm … | iex` trust GitHub and this repository at the moment
  you run them (they install the newest release, not unfinished work). Later updates are signed.
