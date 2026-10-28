# 11. Open-core model: what is open, what is closed

*Added Oct 26, 2026. It settles the licensing question in section 10 ("closed
commercial, or open-core") in favour of open-core, and replaces the single Free / Pro
split of section 6 with two products: an open, raw edition and a closed, polished one.*

**Decision:** everything stays usable as open source, but "raw": you compile it, set it
up through a settings file, and host any servers yourself. People pay for the
convenience: a signed installer, the polished settings app, and the hosted cloud
services. The engine and the backend are open; the user interface is closed.

## 11.1 The two editions

| | Open edition (free, GitHub) | NumpadPilot app (paid, closed) |
|---|---|---|
| Who it's for | Developers, Linux enthusiasts, people who audit what reads their keyboard | Streamers, editors and everyone else who wants it to just work |
| How you get it | Clone the repository and run it from source | Signed installer (website, Steam, Microsoft Store), automatic updates |
| Numpad engine (input, keys, macros, actions, OBS, per-app profiles) | Yes, all of it | Yes, the same engine |
| Setup | Edit a JSON settings file; command line; tray icon | Setup wizard (numpad ready in two minutes), drag-and-drop settings window |
| On-screen display of what each key does (HUD) | No | Yes |
| Profile library | Your own server (self-host the open backend), or import profile files by hand | Built in, on the official hosted library |
| Profile sync between computers | Your own server | Included |
| Support | GitHub issues, community Discord | Priority support, refund guarantee |
| Price | Free | Free tier (1 device, 1 profile, 9 keys), Pro unlock 9.99 USD (launch 6.99, local prices 3.99–5.99) |

The paid app keeps section 6's Free / Pro tiers: the free download has the limits, and
a Pro license key unlocks them. The open edition has no limits, but also no polished UI.
People who build from source were never likely buyers, and they are the ones who
review the code, report bugs and write plugins.

## 11.2 Which parts are open and which are closed

| Part | License | Why |
|---|---|---|
| Numpad engine (`numpadctl/`: input backends, service, actions, config) | Open: AGPL-3.0 | It sees every key the user types. Open code proves it logs nothing and shows anti-cheat-sensitive users exactly what it does (section 9: privacy and anti-cheat risks). |
| Command line, settings file, tray icon | Open: AGPL-3.0 | They make the open edition fully usable without the UI. |
| Cloud backend (profile library, sync, accounts) | Open: AGPL-3.0, in `backend/` (like everything open) | The value is the community's profiles on the official server, not the code. A self-hosted copy starts empty and needs its own servers. AGPL stops anyone from running an improved closed copy as a competing service. |
| Settings app, setup wizard, HUD, profile editor | **Closed** (proprietary, private repository) | This is what buyers actually pay for: the ease of use the free alternatives lack (section 3). |
| Installer, code signing, auto-update, license keys | **Closed** | Part of the polished product; also needed against Windows SmartScreen (section 9). |
| Plugin SDK (later) | Open (license to decide: see 11.4) | So the community can build integrations (section 4). |

**Why the UI and not the backend:** closing the backend would cripple the open edition
(no profile library) while protecting little, because the backend's value is its data,
not its code. Closing the UI costs the open edition only convenience, and convenience
is exactly what is being sold.

## 11.3 How the code is split

- The settings app already talks to the background service over a local connection
  (`numpadctl/platform/ipc.py`) rather than running inside it. A closed program that
  only talks to an AGPL program this way is generally not considered part of it, so the
  closed app can sit next to the open engine. The engine's IPC messages become a
  documented, stable API.
- The Qt settings window (`numpadctl/qt/`) moves to a private repository
  (`private-numpadctl-ui`). The open repository keeps a fallback: `numpad-control gui`
  opens the settings file in a text editor when the app isn't installed.
- The cloud backend lives in `backend/` in the open repository. The whole open
  repository is AGPL-3.0 (one license for everything open, so nobody has to wonder
  which part is under what); versions before October 27, 2026 were GPL-3.0.
- Closed Python code is compiled (e.g. with Nuitka) for the installer, which makes it
  much harder to recover from the shipped files. At this price, that is enough.

## 11.4 Legal points to settle first

1. **What was already published stays open.** Earlier versions of the Qt window were
   released under GPL-3.0 and remain so forever; anyone can fork them. Only new UI
   work is closed.
2. **Contributor agreement (CLA).** All code so far was written by the project owner,
   so relicensing it is the owner's decision. Before accepting outside contributions,
   require a CLA, or contributed code will lock the engine to AGPL-only.
3. **Plugin SDK license (to decide).** Under the AGPL, plugins that run inside the
   engine would likely have to be AGPL too, which rules out closed paid plugins
   (section 6). Options: a permissive license (MIT) for the SDK alone, or a written
   plugin exception to the AGPL.
4. **Dependencies.** PySide6 (LGPL) may be used in a closed app if it is linked
   dynamically and users can replace it. The Interception driver is no longer needed
   (Windows now uses Raw Input), which removes its non-commercial license problem.
5. **Trademarks.** The open edition can't stop forks, but the product name and logo can
   be protected: register the trademark and say in the README that forks must use
   another name.

## 11.5 Changes to the plan

| Phase (section 8) | Addition |
|---|---|
| 0. Technical de-risking | Done: Windows reads the numpad without a driver; the UI moved to the private repository (`private-numpadctl-ui`); the engine–app API is documented ([ipc-api.md](ipc-api.md)). |
| 1. Demand validation | Landing page shows both editions; GitHub stars and open-edition downloads count as demand signals. |
| 2. Productisation | Build the wizard, HUD and licensing in the closed app only. |
| 3. Public launch | Launch on Hacker News / Reddit with the open source story ("audit what reads your keyboard"), alongside the paid app. |
| 4. Scaling | Build the backend (profile library, sync) in the open, AGPL; host the official instance. |

**New risk:** a fork polishes the open edition and gives it away. **Mitigation:** the
closed UI, the hosted library and the trademark are not in the open code; staying ahead
on polish and support is the defence, as with the free alternatives in section 3.
