# Chores

What to update every time. Two lists: one for every commit, one for every release. They are short on purpose; each line
is something that was forgotten once.

## Every commit

**Before committing**
- [ ] **README.md still tells the truth** (install commands, the one-line description, the tested platforms, the links).
  Other tools and people read the README first. A change to what the app does also goes in `docs/features.md`.
- [ ] **Tests** are added or updated for the change, and pass. A fast loop: `QT_QPA_PLATFORM=offscreen python -m unittest
  discover -s tests -p "test_thing.py"`. Before pushing, run the whole suite (every module, in parallel, offscreen).
  Never open real windows from a test. Windows-only code can only be proved by CI.
- [ ] **Anything that touches the UI is looked at first** (render it offscreen with `tools/docs-screenshots.py`, or open
  it), and not committed until the maintainer has seen it.
- [ ] **No em-dashes or en-dashes anywhere** (code, comments, docs, the site, commit messages). Check:
  `git ls-files -z | xargs -0 grep -lIP '\x{2014}|\x{2013}'` must print nothing.
- [ ] **CHANGELOG.md:** one line under `[Unreleased]` for anything a user, a packager or a contributor would notice.
- [ ] **`graphify update .`** after changing code (it only reads the code, it costs nothing).
- [ ] If the website changed: check the links and the files it needs (the pages' `href`s and `src`s), render it in a
  headless browser at a desktop and a phone width, and in dark mode. In the pages, use `<b>` for emphasis, never `<i>`:
  BeerCSS draws `<i>` as an icon, so text inside it disappears.
- [ ] If the text of the privacy page or the code signing page changed: update its "Last updated" date.

**Committing**
- [ ] Commit straight to `main` (no feature branches), under the maintainer's own git identity, without co-author
  trailers or generated-by lines.
- [ ] `git pull --rebase origin main` before `git push`: the bot commits refreshed screenshots to `main`.
- [ ] Never commit `.env*`, `.vercel/`, `graphify-out/` or a signing key.

**After pushing**
- [ ] The Tests workflow goes green on Linux and Windows. If a run hangs, look at which test is waiting (a test that opens
  a real dialog blocks CI forever: mock `dialogs.ask_save_changes`, `QMessageBox`, and the like).
- [ ] The Docs screenshots workflow ran if `numpadctl_ui/` changed; pull the bot's commit.
- [ ] If the site changed: it is live at both addresses (numpad.ahmedabdou.net on Vercel, and GitHub Pages).

## Every release

Run `tools/release X.Y.Z --key <your key file>`: it checks CI, tags, waits for the build and signs. The list is what
surrounds it.

**Before**
- [ ] CI is green on the commit that will be tagged, and `main` is the same as `origin/main`.
- [ ] `__version__` in `numpadctl/__init__.py` is the new version (`tools/release` sets it when it differs).
- [ ] **CHANGELOG.md:** `[Unreleased]` becomes `[X.Y.Z] - date`, a fresh empty `[Unreleased]` goes on top, and the
  compare links at the bottom are updated.
- [ ] **docs/updates.md:** the longer write-up of the release, in the same style as the older ones.
- [ ] **ROADMAP.md and `site/roadmap.html`:** move what shipped out, and add what is next. The two say the same thing.
- [ ] **README.md and the site** say what is true now: the tested platforms, the install commands, and the pages
  `site/features.html`, `site/download.html` and `site/faq.html` (features, the installer notes, the "Coming" list).
- [ ] `docs/compatibility.md` has the numpads people have reported since the last release.
- [ ] `packaging/aur/PKGBUILD`: `depends` has anything new (a new Python package, for example), `pkgrel` is reset to 1.
- [ ] If the Windows installer got signed (SignPath accepted): remove "not code-signed yet" from the README,
  `site/download.html`, `site/code-signing.html`, `docs/code-signing.md` and `packaging/windows/privacy.txt`.

**The release itself**
- [ ] `tools/release` finishes: the tag, the GitHub release, the Windows installer (and its old `NumpadPilot-Setup` name:
  drop that copy once copies older than 0.3.0 no longer matter), `source.zip` and `release.sig`.
- [ ] Look at what the signing step shows (commit, source hash, installer hash) before typing the tag. The installer hash
  should equal the one GitHub shows for the file.
- [ ] Verify the result the way an installed copy does: `numpadctl.updater.verify_signature(tag, release.sig bytes)` accepts
  the uploaded `release.sig`, and the signed zip hash matches the uploaded `source.zip`.

**After**
- [ ] **GitHub release notes:** the generated notes are only a "full changelog" link, so paste the CHANGELOG entry in.
- [ ] **winget:** the first version is submitted by hand (`packaging/winget/render.py`); after that the release workflow's
  Komac job does it, when the `WINGET_TOKEN` secret is set. Check the pull request and answer the reviewers.
- [ ] **AUR:** the workflow updates it when the `AUR_SSH_KEY` secret is set. Without it, update `pkgver` and the checksum
  by hand (`updpkgsums`) and push to the AUR.
- [ ] The website shows the new version everywhere (download page, footer, docs), and the demo video and the screenshots
  still match the app. Re-record the video if the look of the app changed a lot.
- [ ] The repository's homepage field, social preview and topics are still right.
- [ ] Tell people: the launch posts, and the awesome lists the project is in.

## Secrets and accounts (where each thing lives)

- The **release signing key** stays offline, never in CI or in this repository. Keep a second copy: if it is lost,
  installed copies can no longer update.
- **`WINGET_TOKEN`** (a classic personal access token with `public_repo`) and **`AUR_SSH_KEY`** are repository secrets.
- The website is served by two things, which must both be kept alive: Vercel (project `numpad-control-site`, domain
  numpad.ahmedabdou.net, DNS at Cloudflare, owned by the domain's owner) and GitHub Pages.
