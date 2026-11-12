"""Settings → Cloud: connect this PC to NumpadControl Cloud and keep profiles in step (numpadctl/cloud_sync.py).

Four steps, one screen each: pair this PC (a code you type into the dashboard), create or unlock the vault (the
passphrase that encrypts everything before it leaves this PC), then Sync. Network work and key derivation run in
the background; a question about a risky profile is asked here, on the UI thread, while the sync waits for it.

`window` is the main window (it has `cfg`, `save()`, `toast()`). The other arguments only exist so the tests can
replace the network, the threads, the browser and the pop-ups.
"""

import copy
import threading
import time

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLineEdit, QMessageBox, QStackedWidget, QVBoxLayout, QWidget)

from numpadctl import cloud_api, cloud_crypto, cloud_sync, profile_sets
from numpadctl.cloud_api import CloudError
from .buttons import PushButton
from .checkbox import Switch
from .widgets import Dispatcher, card, label

MIN_PASSPHRASE = 8
INTRO, PAIRING, CHECKING, CREATE, UNLOCK, READY = range(6)


def default_run(work):
    threading.Thread(target=work, daemon=True).start()


def default_open(url):
    QDesktopServices.openUrl(QUrl(url))


def describe(report):
    """What a sync did, in plain words (one line per thing)."""
    lines = []
    for names, text in ((report.created, "Sent"), (report.pushed, "Updated in the cloud"), (report.pulled, "Updated from the cloud"),
                        (report.created_local, "Added from the cloud"), (report.deleted, "Deleted from the cloud"),
                        (report.unsynced, "Taken out of the cloud (still on this PC)"), (report.removed, "Deleted here")):
        if names:
            lines.append(f"{text}: {', '.join(names)}")
    if report.conflicts:
        lines.append("Changed in both places, so both were kept: " + ", ".join(f"“{n}” and “{n} (from cloud)”" for n in report.conflicts))
    if report.needs_review:
        lines.append("Not applied until you approve what they do: " + ", ".join(report.needs_review))
    if report.skipped_limit:
        lines.append("Not synced, because your plan's profile limit is reached: " + ", ".join(report.skipped_limit)
                     + ". Switch off the ones you don't want synced, or upgrade.")
    lines += report.problems
    return "\n".join(lines) if lines else "Everything is up to date."


class RecoveryKeyDialog(QDialog):
    """Shows the recovery key once. It can't be closed until the user says it is saved: it is never shown again."""

    def __init__(self, parent, recovery_key):
        super().__init__(parent)
        self.recovery_key = recovery_key
        self.setWindowTitle("Your recovery key")
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(label("Save your recovery key", "title"))
        layout.addWidget(label("If you forget your passphrase, this key is the only other way to open your vault. Nobody, "
                               "including us, can recover your profiles without one of the two. It is shown only now.",
                               "dim", wrap=True))
        key = label(recovery_key, "heading", wrap=True)
        key.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        layout.addWidget(key)
        copy_button = PushButton("Copy")
        copy_button.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.recovery_key))
        layout.addWidget(copy_button)
        self.saved = Switch("I saved it somewhere safe (a password manager, or on paper)")
        layout.addWidget(self.saved)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        self.ok = self.buttons.button(QDialogButtonBox.Ok)
        self.ok.setEnabled(False)
        self.saved.toggled.connect(self.ok.setEnabled)
        self.buttons.accepted.connect(self.accept)
        layout.addWidget(self.buttons)

    def reject(self):
        if self.saved.isChecked():
            super().reject()


class CloudPage(QWidget):
    changed = Signal()

    def __init__(self, window, run=None, api_factory=None, open_url=None, show_recovery=None, ask_review=None,
                 ask_deleted=None, sleep=time.sleep, poll_seconds=2.0):
        super().__init__()
        self.window = window
        self.run = run or default_run
        self.api_factory = api_factory or cloud_api.Api
        self.open_url = open_url or default_open
        self.show_recovery = show_recovery or self._show_recovery
        self.ask_review = ask_review or self._ask_review
        self.ask_deleted = ask_deleted or self._ask_deleted
        self.sleep, self.poll_seconds = sleep, poll_seconds
        self.dispatch = Dispatcher()
        self.state = cloud_sync.load_state()
        self.closed = self.busy = False
        self.pairing_token = None
        self.pending = (cloud_api.server_url(), cloud_sync.default_device_name())
        self.unlock_with_recovery = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)
        self.stack.addWidget(self._build_intro())
        self.stack.addWidget(self._build_pairing())
        self.stack.addWidget(self._build_checking())
        self.stack.addWidget(self._build_create())
        self.stack.addWidget(self._build_unlock())
        self.stack.addWidget(self._build_ready())
        self.show_step()

    # ---------------------------------------------------------------- the screens
    def _page(self, title, text):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)
        frame, box = card()
        box.addWidget(label(title, "heading"))
        if text:
            box.addWidget(label(text, "dim", wrap=True))
        layout.addWidget(frame)
        layout.addStretch()
        return page, box, layout

    def _status(self):
        widget = label("", "small", wrap=True)
        widget.hide()
        return widget

    def say(self, status, text):
        status.setText(text)
        status.setVisible(bool(text))

    def _build_intro(self):
        page, box, _ = self._page("NumpadControl Cloud", "Keep your profiles in step between your PCs. They are encrypted on this "
                                  "PC before they leave it, so the cloud only stores data it can't read. The free plan syncs 1 "
                                  "profile. This is optional: NumpadControl works the same without it.")
        self.pair_button = PushButton("Pair this PC…")
        self.pair_button.setObjectName("primary")
        self.pair_button.clicked.connect(self.start_pairing)
        box.addWidget(self.pair_button)
        self.intro_status = self._status()
        box.addWidget(self.intro_status)
        return page

    def _build_pairing(self):
        page, box, _ = self._page("Pair this PC", "")
        self.pair_instructions = label("", "dim", wrap=True)
        box.addWidget(self.pair_instructions)
        self.pair_code = label("", "title")
        self.pair_code.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(self.pair_code)
        box.addWidget(label("Waiting for you to enter the code…", "small"))
        row = QHBoxLayout()
        self.dashboard_button = PushButton("Open the dashboard")
        self.dashboard_button.clicked.connect(lambda: self.open_url(self.state["url"] + "/dashboard"))
        row.addWidget(self.dashboard_button)
        cancel = PushButton("Cancel")
        cancel.clicked.connect(self.cancel_pairing)
        row.addWidget(cancel)
        row.addStretch()
        box.addLayout(row)
        return page

    def _build_checking(self):
        page, box, _ = self._page("Checking your account…", "")
        self.checking_status = self._status()
        box.addWidget(self.checking_status)
        self.retry_button = PushButton("Try again")
        self.retry_button.clicked.connect(self.show_step)
        self.retry_button.hide()
        box.addWidget(self.retry_button)
        return page

    def _passphrase_field(self, placeholder):
        field = QLineEdit()
        field.setEchoMode(QLineEdit.Password)
        field.setPlaceholderText(placeholder)
        return field

    def _build_create(self):
        page, box, _ = self._page("Create your vault", "Choose a passphrase. It encrypts your profiles on this PC, and you type it "
                                  "on each new PC you connect. We never see it, so we can't reset it: you also get a recovery key.")
        self.new_passphrase = self._passphrase_field(f"Passphrase (at least {MIN_PASSPHRASE} characters; a sentence works well)")
        self.new_passphrase_again = self._passphrase_field("Type it again")
        box.addWidget(self.new_passphrase)
        box.addWidget(self.new_passphrase_again)
        self.create_button = PushButton("Create vault")
        self.create_button.setObjectName("primary")
        self.create_button.clicked.connect(self.create_vault)
        box.addWidget(self.create_button)
        self.create_status = self._status()
        box.addWidget(self.create_status)
        return page

    def _build_unlock(self):
        page, box, _ = self._page("Unlock your vault", "This account already has a vault. Enter its passphrase to read your profiles "
                                  "on this PC.")
        self.unlock_field = self._passphrase_field("Passphrase")
        box.addWidget(self.unlock_field)
        row = QHBoxLayout()
        self.unlock_button = PushButton("Unlock")
        self.unlock_button.setObjectName("primary")
        self.unlock_button.clicked.connect(self.unlock_vault)
        row.addWidget(self.unlock_button)
        self.switch_unlock = PushButton("Use my recovery key instead")
        self.switch_unlock.clicked.connect(self.toggle_recovery)
        row.addWidget(self.switch_unlock)
        row.addStretch()
        box.addLayout(row)
        self.unlock_status = self._status()
        box.addWidget(self.unlock_status)
        return page

    def _build_ready(self):
        page, box, layout = self._page("Connected", "")
        self.ready_title = box.itemAt(0).widget()
        self.ready_info = label("", "small", wrap=True)
        box.addWidget(self.ready_info)
        self.plan_label = label("", "dim", wrap=True)
        box.addWidget(self.plan_label)
        row = QHBoxLayout()
        self.sync_button = PushButton("Sync now")
        self.sync_button.setObjectName("primary")
        self.sync_button.clicked.connect(self.sync_now)
        row.addWidget(self.sync_button)
        self.disconnect_button = PushButton("Disconnect this PC")
        self.disconnect_button.clicked.connect(self.disconnect)
        row.addWidget(self.disconnect_button)
        row.addStretch()
        box.addLayout(row)
        self.sync_status = self._status()
        box.addWidget(self.sync_status)
        frame, self.profile_box = card()
        self.profile_box.addWidget(label("Profiles to sync", "heading"))
        self.profile_box.addWidget(label("Switch off a profile to keep it out of the cloud. On the free plan only 1 profile fits.",
                                         "small", wrap=True))
        self.switches_holder = QVBoxLayout()
        self.profile_box.addLayout(self.switches_holder)
        layout.insertWidget(1, frame)
        return page

    # ---------------------------------------------------------------- which screen
    def api(self):
        return self.api_factory(self.state["url"] or cloud_api.server_url(), self.state["token"] or None)

    def show_step(self):
        if not cloud_sync.is_paired(self.state):
            self.stack.setCurrentIndex(INTRO)
        elif cloud_sync.vault_key(self.state) is None:
            self.stack.setCurrentIndex(CHECKING)
            self.say(self.checking_status, "")
            self.retry_button.hide()
            self.background(lambda: cloud_sync.vault_exists(self.api()), self.vault_checked, self.check_failed)
        else:
            self.show_ready()

    def show_ready(self):
        self.ready_title.setText(f"Connected as “{self.state['device_name']}”")
        self.ready_info.setText(f"{self.state['url']}. Your profiles are encrypted before they leave this PC.")
        self.refresh_switches()
        self.stack.setCurrentIndex(READY)
        self.refresh_plan()

    def refresh_plan(self):
        """Ask the cloud which plan this account is on and how much of it is used (shown under the PC's name)."""
        self.background(lambda: self.api().me(), lambda info: self.plan_label.setText(cloud_sync.describe_plan(info)),
                        self.plan_failed)

    def plan_failed(self, error):
        if not self.removed_by_server(error):
            self.plan_label.setText("")     # the plan is a nicety: when it can't be read, show nothing rather than an error

    def refresh_switches(self):
        while self.switches_holder.count():
            item = self.switches_holder.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        sets = self.window.cfg.get("sets") or [{"name": cloud_sync.DEFAULT_SET, "profiles": self.window.cfg.get("profiles", [])}]
        for item in sets:
            for profile in item["profiles"]:
                name = profile.get("name", "")
                switch = Switch(name if len(sets) < 2 else f"{item['name']} / {name}")
                switch.setChecked(cloud_sync.is_synced(self.state, item["name"], name))
                switch.toggled.connect(lambda on, s=item["name"], n=name: self.toggle_profile(s, n, on))
                self.switches_holder.addWidget(switch)

    def toggle_profile(self, set_name, name, on):
        cloud_sync.set_synced(self.state, set_name, name, on)
        cloud_sync.save_state(self.state)

    # ---------------------------------------------------------------- background work
    def background(self, work, done, failed):
        def go():
            try:
                result = work()
            except Exception as e:      # CloudError, CloudCryptoError, or a bug: say so, never freeze or crash the window
                self.dispatch(self._finish, failed, e)
            else:
                self.dispatch(self._finish, done, result)
        self.run(go)

    def _finish(self, fn, value):
        if not self.closed:
            fn(value)

    def shutdown(self, *_):
        """The settings window closed: stop waiting for anything."""
        self.closed = True
        self.pairing_token = None

    def explain(self, error):
        if isinstance(error, (CloudError, cloud_crypto.CloudCryptoError)):
            return str(error)
        return f"something went wrong ({error})"

    def removed_by_server(self, error):
        """A 401 means this PC was removed in the dashboard: forget it, and say so."""
        if isinstance(error, CloudError) and error.code == "unauthorized":
            cloud_sync.forget(self.state)
            cloud_sync.save_state(self.state)
            self.show_step()
            self.say(self.intro_status, str(error))
            return True
        return False

    # ---------------------------------------------------------------- step 1: pairing
    def start_pairing(self):
        self.pair_button.setEnabled(False)
        self.say(self.intro_status, "Contacting NumpadControl Cloud…")
        name = cloud_sync.default_device_name()
        url = cloud_api.server_url()
        self.background(lambda: (url, name, *cloud_sync.start_pairing(self.api_factory(url, None), name)),
                        self.pairing_started, self.pairing_failed)

    def pairing_failed(self, error):
        self.pair_button.setEnabled(True)
        self.say(self.intro_status, self.explain(error))

    def pairing_started(self, result):
        url, name, token, code, _expires = result
        self.pair_button.setEnabled(True)
        self.say(self.intro_status, "")
        self.pairing_token = token
        self.pending = (url, name)
        self.pair_instructions.setText(f"Open {url}/dashboard, sign in (or create an account), and type this code. "
                                       "It works for 10 minutes.")
        self.pair_code.setText(code)
        self.stack.setCurrentIndex(PAIRING)
        hashed = cloud_sync.token_hash(token)
        api = self.api_factory(url, None)

        def poll():
            for _ in range(int(600 / max(self.poll_seconds, 0.001)) + 1):
                if self.closed or self.pairing_token != token:
                    return
                try:
                    status = api.pair_poll(hashed)
                except Exception:        # a bad moment on the network: try again on the next round
                    status = "pending"
                if status == "paired":
                    self.dispatch(self._finish, self.paired, token)
                    return
                if status == "expired":
                    self.dispatch(self._finish, self.pairing_expired, token)
                    return
                self.sleep(self.poll_seconds)
            self.dispatch(self._finish, self.pairing_expired, token)
        self.run(poll)

    def pairing_expired(self, token):
        if self.pairing_token == token:
            self.pairing_token = None
            self.stack.setCurrentIndex(INTRO)
            self.say(self.intro_status, "That code expired. Start again to get a new one.")

    def cancel_pairing(self):
        self.pairing_token = None
        self.stack.setCurrentIndex(INTRO)

    def paired(self, token):
        if self.pairing_token != token:
            return
        url, name = self.pending
        self.pairing_token = None
        cloud_sync.finish_pairing(self.state, url, name, token)
        cloud_sync.save_state(self.state)
        self.show_step()

    # ---------------------------------------------------------------- step 2: the vault
    def vault_checked(self, exists):
        self.stack.setCurrentIndex(UNLOCK if exists else CREATE)

    def check_failed(self, error):
        if self.removed_by_server(error):
            return
        self.say(self.checking_status, self.explain(error))
        self.retry_button.show()

    def create_vault(self):
        first, again = self.new_passphrase.text(), self.new_passphrase_again.text()
        if len(first) < MIN_PASSPHRASE:
            return self.say(self.create_status, f"Use at least {MIN_PASSPHRASE} characters.")
        if first != again:
            return self.say(self.create_status, "The two passphrases are different.")
        self.create_button.setEnabled(False)
        self.say(self.create_status, "Creating your vault…")
        state = copy_state(self.state)
        self.background(lambda: (cloud_sync.create_vault(state, self.api(), first), state), self.vault_created, self.create_failed)

    def create_failed(self, error):
        self.create_button.setEnabled(True)
        if not self.removed_by_server(error):
            self.say(self.create_status, self.explain(error))

    def vault_created(self, result):
        recovery, state = result
        self.state["vault_key"] = state["vault_key"]
        cloud_sync.save_state(self.state)
        self.new_passphrase.clear()
        self.new_passphrase_again.clear()
        self.create_button.setEnabled(True)
        self.say(self.create_status, "")
        self.show_recovery(recovery)        # shown once; the dialog can't be closed until it is saved
        self.show_step()

    def toggle_recovery(self):
        self.unlock_with_recovery = not self.unlock_with_recovery
        self.unlock_field.setPlaceholderText("Recovery key (ABCD-EFGH-…)" if self.unlock_with_recovery else "Passphrase")
        self.unlock_field.setEchoMode(QLineEdit.Normal if self.unlock_with_recovery else QLineEdit.Password)
        self.switch_unlock.setText("Use my passphrase instead" if self.unlock_with_recovery else "Use my recovery key instead")
        self.unlock_field.clear()

    def unlock_vault(self):
        secret = self.unlock_field.text()
        if not secret:
            return self.say(self.unlock_status, "Type your recovery key." if self.unlock_with_recovery else "Type your passphrase.")
        self.unlock_button.setEnabled(False)
        self.say(self.unlock_status, "Unlocking…")
        state = copy_state(self.state)
        by_key = self.unlock_with_recovery
        self.background(lambda: cloud_sync.unlock_vault(state, self.api(), None if by_key else secret, secret if by_key else None) or state,
                        self.vault_unlocked, self.unlock_failed)

    def unlock_failed(self, error):
        self.unlock_button.setEnabled(True)
        if not self.removed_by_server(error):
            self.say(self.unlock_status, self.explain(error))

    def vault_unlocked(self, state):
        self.state["vault_key"] = state["vault_key"]
        cloud_sync.save_state(self.state)
        self.unlock_field.clear()
        self.unlock_button.setEnabled(True)
        self.say(self.unlock_status, "")
        self.show_step()

    # ---------------------------------------------------------------- step 3: syncing
    def sync_now(self, allow_remote_deletes=False):
        if self.busy:
            return
        if not self.window.save():           # what the cloud gets must be valid, and on disk before it changes anything
            return
        self.busy = True
        self.sync_button.setEnabled(False)
        self.say(self.sync_status, "Syncing…")
        cfg, state = copy.deepcopy(self.window.cfg), copy_state(self.state)
        key, api = cloud_sync.vault_key(state), self.api()

        def work():
            # Never raises: a sync that stopped half way has still changed things, and both sides must be kept.
            try:
                return cfg, state, cloud_sync.sync(cfg, state, api, key, confirm=self.confirm_from_worker,
                                                   allow_remote_deletes=allow_remote_deletes), None
            except Exception as e:
                return cfg, state, None, e
        self.background(work, self.synced, lambda e: self.synced((cfg, state, None, e)))

    def synced(self, result):
        cfg, state, report, error = result
        self.busy = False
        self.sync_button.setEnabled(True)
        self.adopt(cfg, state)
        if error is not None:
            if not self.removed_by_server(error):
                self.say(self.sync_status, self.explain(error))
            return
        text = describe(report)
        if report.deleted_elsewhere:
            names = [n for _, n in report.deleted_elsewhere]
            if self.ask_deleted(names):
                self.say(self.sync_status, text)
                return self.sync_now(allow_remote_deletes=True)
            cloud_sync.reupload(self.state, report.deleted_elsewhere)    # keep them: they are uploaded again
            cloud_sync.save_state(self.state)
            self.say(self.sync_status, text)
            return self.sync_now()
        self.say(self.sync_status, text)
        self.window.toast("Synced with NumpadControl Cloud" if report.changed() else "Already up to date")
        self.refresh_switches()
        self.refresh_plan()                 # the number of profiles synced may have changed

    def adopt(self, cfg, state):
        """Take the synced copy of the profiles and the sync bookkeeping, save both, and redraw the main window."""
        mine = self.window.cfg
        mine["sets"] = cfg["sets"]
        active = profile_sets.pick(mine["sets"], mine.get("active_set"))
        mine["active_set"], mine["profiles"] = active["name"], active["profiles"]
        self.state.update({k: state[k] for k in ("profiles", "excluded")})
        cloud_sync.save_state(self.state)
        if hasattr(self.window, "profile_index"):
            self.window.profile_index = max(0, min(self.window.profile_index, len(mine["profiles"]) - 1))
        self.window.save()
        for step in ("refresh_profiles", "refresh_pad", "build_editor"):
            getattr(self.window, step, lambda: None)()

    def confirm_from_worker(self, name, rows):
        """Asked by the sync thread: show the question on the UI thread and wait for the answer."""
        if QThread.currentThread() is self.thread():
            return self.ask_review(name, rows)
        answer, done = {}, threading.Event()

        def ask():
            answer["yes"] = self.ask_review(name, rows)
            done.set()
        self.dispatch(ask)
        while not done.wait(0.2):
            if self.closed:
                return False
        return answer.get("yes", False)

    def _ask_review(self, name, rows):
        lines = [f"{'⚠ ' if risky else '   '}{text}" + (f"  ×{n}" if n > 1 else "") for text, n, risky in rows]
        box = QMessageBox(self)
        box.setWindowTitle("Profile from your cloud")
        box.setText(f"Apply “{name}” from your cloud?")
        box.setInformativeText("It would do:\n\n" + "\n".join(lines)
                               + "\n\n⚠ marks actions that run programs, press keys for you or power the PC off. They would run "
                                 "on this PC as you. It was encrypted by one of your own PCs, but check it is what you expect.")
        box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
        box.button(QMessageBox.Ok).setText("Apply")
        box.setDefaultButton(QMessageBox.Cancel)
        return box.exec() == QMessageBox.Ok

    def _ask_deleted(self, names):
        box = QMessageBox(self)
        box.setWindowTitle("Deleted on another PC")
        box.setText("These profiles were deleted from your cloud on another PC:\n\n" + "\n".join(names)
                    + "\n\nDelete them on this PC too?")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.button(QMessageBox.Yes).setText("Delete here too")
        box.button(QMessageBox.No).setText("Keep them (upload again)")
        box.setDefaultButton(QMessageBox.No)
        return box.exec() == QMessageBox.Yes

    def _show_recovery(self, recovery_key):
        RecoveryKeyDialog(self, recovery_key).exec()

    # ---------------------------------------------------------------- leaving
    def disconnect(self):
        box = QMessageBox(self)
        box.setWindowTitle("Disconnect this PC")
        box.setText("Disconnect this PC from NumpadControl Cloud?")
        box.setInformativeText("Your profiles stay on this PC and in the cloud. To use the cloud again you pair this PC again and "
                               "enter your passphrase. To stop another PC from syncing, remove it in the dashboard.")
        box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
        box.button(QMessageBox.Ok).setText("Disconnect")
        box.setDefaultButton(QMessageBox.Cancel)
        if box.exec() == QMessageBox.Ok:
            self.forget_pc()

    def forget_pc(self):
        cloud_sync.forget(self.state)
        cloud_sync.save_state(self.state)
        self.say(self.sync_status, "")
        self.show_step()


def copy_state(state):
    return copy.deepcopy(state)
