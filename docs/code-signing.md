# Code signing (Windows)

NumpadControl watches the keyboard, so an unsigned download gets "Windows protected your PC"
(SmartScreen) and antivirus warnings. This page is the plan for signing, and the steps once it's done.
(Release signing for the updater is a different thing: see [SECURITY.md](../SECURITY.md).)

NumpadControl is entirely free and open source under the GPL-3.0, the settings window included. There is no
paid edition and no private repository, so everything below is about this repository only.

## What gets signed

| File | When |
|---|---|
| `NumpadControl-Setup-X.exe`, the Windows installer built by GitHub Actions from this repository | Every release. This is what matters. |
| `setup.ps1` | Optional. It's run as `irm … \| iex`, which doesn't check signatures, but a signed copy can be run under PowerShell's `AllSigned` policy. |

The Linux install runs from source, so it has no `.exe` to sign.

## The plan: SignPath Foundation

[SignPath Foundation](https://signpath.org) gives free code signing to open-source projects: their certificate is
issued to "SignPath Foundation", and the signing is done by their service, so no key is kept on a personal PC.
Windows then shows the publisher as SignPath Foundation. Their conditions
([terms](https://signpath.org/terms)) and where this project stands:

| Condition | Here |
|---|---|
| OSI-approved licence, no proprietary parts, no commercial dual licensing | GPL-3.0 for everything |
| Actively maintained and already released | Releases since 0.1.0 |
| Functionality described on the download page | [Download page](https://youssefahmed2017.github.io/numpad-control/download.html) and the README |
| Binaries built from source in a verifiable way, from an automated build | The installer is built by GitHub Actions (`packaging/windows/build-installer.ps1`). The keyboard hook DLL it carries is compiled from `numpadctl/platform/numpadhook/numpadhook.c` in that same build, not taken from the committed copy |
| No malware or unwanted software; no hacking tools | The keyboard hook and the optional Interception driver read and block the chosen numpad's keys, and are documented in the README and SECURITY.md |
| Privacy respected, system changes announced, an uninstaller | [Privacy page](https://youssefahmed2017.github.io/numpad-control/privacy.html); the Windows installer has an uninstaller; the Linux udev rule asks first |
| A "Code signing policy" page on the website | [code-signing.html](../site/code-signing.html) |
| Multi-factor authentication, separate author / reviewer / approver roles | To confirm when applying (this is a one-person project) |
| Every release approved by hand before it is signed | Fits: the release workflow waits for the approval |

Apply at <https://signpath.org/apply>. Once accepted, the release workflow gets a step that sends the installer to
SignPath; `tools/sign-release` then signs the release (for the updater) over the *signed* installer's hash.

## Other options (not chosen)

| Option | Why not |
|---|---|
| **Azure Artifact Signing** (Microsoft's service) | Only for organisations in the US, Canada, the EU or the UK (and some individuals in the US and Canada) |
| **OV certificate from a certificate authority** (Certum, Sectigo resellers, SSL.com, …) | About 400 USD a year, and the private key must be on a hardware token or in their cloud, never a file |
| **Open-source certificate** (for example Certum's) | Cheaper, but SignPath's is free |
| EV certificate | Not worth it: since 2024 it no longer skips SmartScreen's reputation building |

Whatever certificate is used, SmartScreen still warns until the signed installer has been downloaded enough times
to build a reputation. A signature makes that reputation build up and stay with every new version; without one,
each version starts over. The Microsoft Store doesn't show the warning at all, but it needs a signed installer too.

## Signing by hand (with an own certificate)

On a PC with a certificate (token plugged in, or the cloud service's tool signed in), with the Windows SDK's
signing tools installed:

    powershell -ExecutionPolicy Bypass -File tools\sign-windows.ps1 dist\NumpadControl-Setup.exe

It finds the code-signing certificate by itself (or takes `-Thumbprint`), signs with SHA-256 and a timestamp (so
signatures stay valid after the certificate expires), and verifies the file afterwards.
