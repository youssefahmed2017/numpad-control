# Code signing (Windows)

Phase 0 of the plan asks for code signing from day one: NumpadPilot watches the
keyboard, so an unsigned download gets "Windows protected your PC" (SmartScreen) and
antivirus warnings. This page is the decision to make and the steps once it's made.

## What gets signed

| File | When |
|---|---|
| The paid app's compiled `.exe` and its installer (private repository) | Every release. This is what matters most. |
| `setup.ps1` (this repository) | Optional. It's run as `irm … \| iex`, which doesn't check signatures, but a signed copy can be run under PowerShell's `AllSigned` policy. |

The open edition is run from source, so it has no `.exe` to sign.

## Choosing a certificate

Since June 2023, every code-signing certificate's private key must be on a hardware
token or in a cloud signing service, never a plain file. So signing happens on your PC
(with the token or the service's tool), not in GitHub Actions.

| Option | Fits? | Notes |
|---|---|---|
| **Azure Artifact Signing** (Microsoft's service, cheapest monthly) | **No, for now** | Only for organisations in the US, Canada, the EU or the UK (and some individuals in the US and Canada). Possible later if a company is registered in an eligible country (plan, section 9). |
| **OV certificate from a certificate authority** (Certum, Sectigo resellers, SSL.com, …) on a token or their cloud signing | **Yes**: the plan's choice (about 400 USD a year in section 5) | Available to individuals in most countries after an identity check. Cloud signing (e.g. Certum SimplySign, SSL.com eSigner) avoids shipping a USB token to Egypt. |
| **Open-source code-signing certificate** (e.g. Certum's) | Only for the open engine | Cheaper, but only for open-source software, so it can't sign the closed paid app. |
| EV certificate | Not worth it | More expensive, and since 2024 it no longer skips SmartScreen's reputation building. |

Whatever certificate is used, SmartScreen still warns until the signed app has been
downloaded enough times to build a reputation. A signature makes that reputation
build up and stay with every new version; without one, each version starts over.
Steam and the Microsoft Store (plan, section 6) don't show the warning at all.

**Before buying, check:** the current price and whether it accepts individuals in Egypt,
the identity documents it needs, and whether it offers cloud signing.

## Signing

On the PC with the certificate (token plugged in, or the cloud service's tool signed in),
with the Windows SDK's signing tools installed:

    powershell -ExecutionPolicy Bypass -File tools\sign-windows.ps1 dist\NumpadControl.exe dist\NumpadControl-Setup.exe

It finds the code-signing certificate by itself (or takes `-Thumbprint`), signs with
SHA-256 and a timestamp (so signatures stay valid after the certificate expires), and
verifies each file afterwards. Sign the app first, then build the installer around the
signed app, then sign the installer.
