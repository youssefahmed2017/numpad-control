"""Settings → Cloud: pairing, the vault and syncing, with a fake cloud and a stub window (offscreen, nothing is shown)."""

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from numpadctl import cloud_crypto as cc, cloud_sync, config  # noqa: E402
from numpadctl.cloud_api import CloudError  # noqa: E402
from numpadctl_ui import cloud_page  # noqa: E402
from numpadctl_ui.cloud_page import CREATE, INTRO, READY, UNLOCK, CloudPage, RecoveryKeyDialog, describe  # noqa: E402
from tests.test_cloud_sync import FakeCloud, binding, everything, profile  # noqa: E402  (module-level names, not its tests)

APP = QApplication.instance() or QApplication([])


def at_once(work):
    work()


class FakeApi(FakeCloud):
    """The pieces of the cloud the screen talks to, on top of the profile store."""

    def __init__(self):
        super().__init__()
        self.vault, self.statuses, self.token_hashes = None, ["paired"], []
        self.plan, self.plan_info = "free", True

    def pair_start(self, name, token_hash):
        self.token_hashes.append((name, token_hash))
        return {"code": "ABCD-2345", "expires_at": "later"}

    def pair_poll(self, token_hash):
        return self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]

    def me(self):
        limit = None if self.limit >= 10_000 else self.limit
        info = {"id": "d", "name": "this pc", "plan": self.plan, "profile_count": len(self.items), "profile_limit": limit,
                "history_versions": 0}
        return info if self.plan_info else {"id": "d", "name": "this pc"}

    def get_vault(self):
        if self.vault is None:
            raise CloudError("no vault", status=404, code="no_vault")
        return self.vault

    def put_vault(self, vault):
        self.vault = vault


class StubWindow:
    """What the page needs from the main window."""

    def __init__(self, *profiles):
        items = list(profiles)
        self.cfg = {"sets": [{"name": "Default", "profiles": items}], "profiles": items, "active_set": "Default"}
        self.profile_index = 0
        self.saves, self.toasts, self.redraws = 0, [], 0

    def save(self):
        self.saves += 1
        return True

    def toast(self, text):
        self.toasts.append(text)

    def refresh_profiles(self):
        self.redraws += 1


class PageCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        for patcher in (mock.patch.object(config, "CONFIG_DIR", Path(self.dir.name)),
                        mock.patch.dict(os.environ, {"NUMPADCTL_CLOUD_URL": "https://cloud.test"})):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.dir.cleanup)
        self.cloud = FakeApi()
        self.recoveries, self.reviews = [], []

    def page(self, *profiles, review=lambda name, rows: False, run=at_once, deleted=lambda names: False):
        self.window = StubWindow(*profiles)
        page = CloudPage(self.window, run=run, api_factory=lambda url, token: self.cloud, open_url=lambda url: None,
                         show_recovery=self.recoveries.append, ask_review=review, ask_deleted=deleted,
                         sleep=lambda s: None, poll_seconds=0.01)
        self.addCleanup(page.deleteLater)
        return page

    def connected(self, *profiles, **kwargs):
        """A page that is paired and has a vault, as after the first two steps."""
        page = self.page(*profiles, **kwargs)
        page.pair_button.click()
        page.new_passphrase.setText("a long passphrase")
        page.new_passphrase_again.setText("a long passphrase")
        page.create_button.click()
        self.assertEqual(page.stack.currentIndex(), READY)
        return page


class PairingTest(PageCase):
    def test_starts_on_the_intro_and_pairing_leads_to_the_vault(self):
        page = self.page()
        self.assertEqual(page.stack.currentIndex(), INTRO)
        self.cloud.statuses = ["pending", "paired"]
        page.pair_button.click()
        self.assertEqual(page.stack.currentIndex(), CREATE)          # paired, and the account has no vault yet
        self.assertEqual(page.pair_code.text(), "ABCD-2345")
        state = cloud_sync.load_state()
        self.assertEqual((state["url"], cloud_sync.is_paired(state)), ("https://cloud.test", True))
        name, token_hash = self.cloud.token_hashes[0]
        self.assertEqual(token_hash, cloud_sync.token_hash(state["token"]))     # only the hash was sent

    def test_an_expired_code_goes_back_with_a_message(self):
        page = self.page()
        self.cloud.statuses = ["expired"]
        page.pair_button.click()
        self.assertEqual(page.stack.currentIndex(), INTRO)
        self.assertIn("expired", page.intro_status.text())
        self.assertFalse(cloud_sync.is_paired(cloud_sync.load_state()))

    def test_an_unreachable_cloud_says_so_and_can_be_tried_again(self):
        page = self.page()
        self.cloud.pair_start = mock.Mock(side_effect=CloudError("couldn't reach NumpadControl Cloud (offline). Are you online?"))
        page.pair_button.click()
        self.assertIn("couldn't reach", page.intro_status.text())
        self.assertTrue(page.pair_button.isEnabled())

    def test_cancel_stops_waiting(self):
        page = self.page(run=lambda work: None)          # the poll never runs
        page.pair_button.click()
        page.cancel_pairing()
        self.assertEqual((page.stack.currentIndex(), page.pairing_token), (INTRO, None))
        page.paired("late")                               # a straggler from the old wait changes nothing
        self.assertFalse(cloud_sync.is_paired(cloud_sync.load_state()))


class VaultTest(PageCase):
    def test_creating_checks_the_passphrase_first(self):
        page = self.page()
        page.pair_button.click()
        page.new_passphrase.setText("short")
        page.create_button.click()
        self.assertIn("at least 8", page.create_status.text())
        page.new_passphrase.setText("long enough passphrase")
        page.new_passphrase_again.setText("different one entirely")
        page.create_button.click()
        self.assertIn("different", page.create_status.text())
        self.assertIsNone(self.cloud.vault)

    def test_creating_uploads_the_vault_and_shows_the_recovery_key_once(self):
        page = self.connected()
        self.assertEqual(len(self.recoveries), 1)
        recovery = self.recoveries[0]
        self.assertEqual(cc.unlock_with_recovery_key(self.cloud.vault, recovery), cloud_sync.vault_key(cloud_sync.load_state()))
        self.assertEqual(page.new_passphrase.text(), "")                      # the passphrase isn't kept in the field
        self.assertNotIn("a long passphrase", Path(cloud_sync.state_path()).read_text())

    def test_a_second_pc_unlocks_with_the_passphrase(self):
        self.cloud.vault, key, recovery = (*cc.create_vault("the right words"),)
        page = self.page()
        page.pair_button.click()
        self.assertEqual(page.stack.currentIndex(), UNLOCK)
        page.unlock_field.setText("the wrong words")
        page.unlock_button.click()
        self.assertIn("passphrase is wrong", page.unlock_status.text())
        self.assertNotEqual(page.stack.currentIndex(), READY)
        page.unlock_field.setText("the right words")
        page.unlock_button.click()
        self.assertEqual(page.stack.currentIndex(), READY)
        self.assertEqual(cloud_sync.vault_key(cloud_sync.load_state()), key)

    def test_or_with_the_recovery_key(self):
        self.cloud.vault, key, recovery = (*cc.create_vault("forgotten"),)
        page = self.page()
        page.pair_button.click()
        page.switch_unlock.click()
        page.unlock_field.setText(recovery.lower())
        page.unlock_button.click()
        self.assertEqual(page.stack.currentIndex(), READY)
        self.assertEqual(cloud_sync.vault_key(cloud_sync.load_state()), key)

    def test_the_recovery_dialog_cannot_be_closed_until_it_is_saved(self):
        dialog = RecoveryKeyDialog(None, "ABCD-EFGH")
        rejected = []
        dialog.rejected.connect(lambda: rejected.append(1))
        self.assertFalse(dialog.ok.isEnabled())
        dialog.reject()
        self.assertEqual(rejected, [])
        dialog.saved.setChecked(True)
        self.assertTrue(dialog.ok.isEnabled())
        dialog.reject()
        self.assertEqual(rejected, [1])


class SyncTest(PageCase):
    def test_sync_sends_profiles_and_saves_the_config_first_and_after(self):
        page = self.connected(profile("Streaming"))
        saves = self.window.saves
        page.sync_button.click()
        self.assertEqual(len(self.cloud.items), 1)
        self.assertIn("Sent: Streaming", page.sync_status.text())
        self.assertGreaterEqual(self.window.saves - saves, 2)        # before (what the cloud gets is valid) and after
        self.assertTrue(page.sync_button.isEnabled())
        self.assertEqual(self.window.toasts[-1], "Synced with NumpadControl Cloud")
        page.sync_button.click()
        self.assertEqual(page.sync_status.text(), "Everything is up to date.")

    def test_sync_does_not_start_when_the_config_can_not_be_saved(self):
        page = self.connected(profile("Streaming"))
        self.window.save = lambda: False
        page.sync_button.click()
        self.assertEqual(self.cloud.items, {})

    def test_profiles_from_another_pc_arrive_and_the_window_is_redrawn(self):
        page = self.connected(profile("Mine"))
        key = cloud_sync.vault_key(page.state)
        other = {"sets": [{"name": "Default", "profiles": [profile("From other PC", key="4")]}]}
        cloud_sync.sync(other, {"url": "u", "device_name": "d", "token": "t", "vault_key": "", "profiles": [], "excluded": []}, self.cloud, key)
        page.sync_button.click()
        self.assertEqual(sorted(p["name"] for p in self.window.cfg["profiles"]), ["From other PC", "Mine"])
        self.assertIs(self.window.cfg["profiles"], self.window.cfg["sets"][0]["profiles"])    # still the same list
        self.assertGreater(self.window.redraws, 0)

    def test_switching_a_profile_off_keeps_it_out_and_removes_its_cloud_copy(self):
        page = self.connected(profile("Streaming"), profile("Private", key="2"))
        page.sync_button.click()
        self.assertEqual(len(self.cloud.items), 2)
        private = next(s for s in (page.switches_holder.itemAt(i).widget() for i in range(2)) if s.text() == "Private")
        private.setChecked(False)
        page.sync_button.click()
        self.assertEqual(len(self.cloud.items), 1)
        self.assertEqual(len(self.window.cfg["profiles"]), 2)                # still on this PC
        self.assertIn("Taken out of the cloud", page.sync_status.text())
        self.assertFalse(cloud_sync.is_synced(cloud_sync.load_state(), "Default", "Private"))   # remembered

    def test_the_plan_limit_is_explained(self):
        self.cloud.limit = 1
        page = self.connected(profile("A"), profile("B", key="2"))
        page.sync_button.click()
        self.assertIn("plan's profile limit", page.sync_status.text())
        self.assertIn("B", page.sync_status.text())

    def test_a_risky_profile_from_the_cloud_is_only_applied_when_approved(self):
        page = self.connected(review=lambda name, rows: False)
        key = cloud_sync.vault_key(page.state)
        other = {"sets": [{"name": "Default", "profiles": [profile("Tools", action="open_url", url="https://example.org")]}]}
        cloud_sync.sync(other, {"url": "u", "device_name": "d", "token": "t", "vault_key": "", "profiles": [], "excluded": []}, self.cloud, key)
        page.sync_button.click()
        self.assertEqual(everything(self.window.cfg), [])
        self.assertIn("Not applied until you approve", page.sync_status.text())
        page.ask_review = lambda name, rows: True
        page.sync_button.click()
        self.assertEqual([p["name"] for p in everything(self.window.cfg)], ["Tools"])

    def test_a_pc_removed_in_the_dashboard_is_forgotten_with_an_explanation(self):
        page = self.connected(profile("A"))
        self.cloud.list_profiles = mock.Mock(side_effect=CloudError("This PC isn't connected to NumpadControl Cloud (it was removed, "
                                                                    "or never paired). Pair it again.", status=401, code="unauthorized"))
        page.sync_button.click()
        self.assertEqual(page.stack.currentIndex(), INTRO)
        self.assertIn("Pair it again", page.intro_status.text())
        self.assertFalse(cloud_sync.is_paired(cloud_sync.load_state()))

    def test_a_network_failure_leaves_the_button_usable_and_the_profiles_alone(self):
        page = self.connected(profile("A"))
        self.cloud.list_profiles = mock.Mock(side_effect=CloudError("couldn't reach NumpadControl Cloud (offline). Are you online?"))
        page.sync_button.click()
        self.assertIn("couldn't reach", page.sync_status.text())
        self.assertTrue(page.sync_button.isEnabled())
        self.assertEqual([p["name"] for p in everything(self.window.cfg)], ["A"])

    def test_a_bug_in_the_middle_does_not_lose_what_was_already_sent(self):
        page = self.connected(profile("A"), profile("B", key="2"))
        real = self.cloud.put_profile
        calls = []

        def flaky(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("boom")
            return real(*args, **kwargs)
        self.cloud.put_profile = flaky
        page.sync_button.click()
        self.assertIn("boom", page.sync_status.text())
        self.assertEqual(len(cloud_sync.load_state()["profiles"]), 1)        # the first one is remembered, so it isn't sent twice
        self.cloud.put_profile = real
        page.sync_button.click()
        self.assertEqual(len(self.cloud.items), 2)

    def test_profiles_deleted_elsewhere_are_asked_about(self):
        asked = []
        page = self.connected(profile("Gone"), deleted=lambda names: asked.append(names) or True)
        page.sync_button.click()
        self.cloud.items.clear()
        page.sync_button.click()
        self.assertEqual(asked, [["Gone"]])
        self.assertEqual(self.window.cfg["profiles"], [])
        page2 = self.connected(profile("Kept"), deleted=lambda names: False)
        page2.sync_button.click()
        self.cloud.items.clear()
        page2.sync_button.click()
        self.assertEqual([p["name"] for p in self.window.cfg["profiles"]], ["Kept"])
        self.assertEqual(len(self.cloud.items), 1)                           # uploaded again

    def test_a_question_from_the_sync_thread_is_answered_on_the_ui_thread(self):
        answers = []
        threads = []

        def review(name, rows):
            threads.append(threading.current_thread())
            answers.append(name)
            return True
        page = self.connected(review=review)
        page.run = lambda work: threading.Thread(target=work, daemon=True).start()     # a real thread this time
        key = cloud_sync.vault_key(page.state)
        other = {"sets": [{"name": "Default", "profiles": [profile("Tools", action="open_url", url="https://example.org")]}]}
        cloud_sync.sync(other, {"url": "u", "device_name": "d", "token": "t", "vault_key": "", "profiles": [], "excluded": []}, self.cloud, key)
        page.sync_button.click()
        deadline = time.time() + 10
        while page.busy and time.time() < deadline:
            APP.processEvents()
            time.sleep(0.01)
        self.assertFalse(page.busy)
        self.assertEqual(answers, ["Tools"])
        self.assertIs(threads[0], threading.main_thread())
        self.assertEqual([p["name"] for p in everything(self.window.cfg)], ["Tools"])


class PlanTest(PageCase):
    def test_the_plan_is_shown_when_connected_and_after_each_sync(self):
        self.cloud.limit = 1
        page = self.connected(profile("Streaming"))
        self.assertEqual(page.plan_label.text(), "Free plan: 0 of 1 profile synced, no version history.")
        page.sync_button.click()
        self.assertEqual(page.plan_label.text(), "Free plan: 1 of 1 profile synced, no version history.")

    def test_a_server_that_does_not_report_a_plan_shows_nothing(self):
        self.cloud.plan_info = False
        page = self.connected()
        self.assertEqual(page.plan_label.text(), "")

    def test_the_plan_not_loading_is_not_an_error_on_screen(self):
        page = self.connected()
        self.cloud.me = mock.Mock(side_effect=CloudError("couldn't reach NumpadControl Cloud (offline). Are you online?"))
        page.refresh_plan()
        self.assertEqual(page.plan_label.text(), "")
        self.assertEqual(page.stack.currentIndex(), READY)

    def test_a_removed_pc_is_noticed_while_reading_the_plan(self):
        page = self.connected()
        self.cloud.me = mock.Mock(side_effect=CloudError("removed", status=401, code="unauthorized"))
        page.refresh_plan()
        self.assertEqual(page.stack.currentIndex(), INTRO)


class DescribePlanTest(unittest.TestCase):
    def test_wording(self):
        d = cloud_sync.describe_plan
        self.assertEqual(d({"plan": "free", "profile_count": 0, "profile_limit": 1, "history_versions": 0}),
                         "Free plan: 0 of 1 profile synced, no version history.")
        self.assertEqual(d({"plan": "pro", "profile_count": 3, "profile_limit": None, "history_versions": 50}),
                         "Pro plan: 3 profiles synced (no limit), the last 50 versions of each are kept.")
        self.assertEqual(d({"plan": "team", "profile_count": 1, "profile_limit": None, "history_versions": 200}),
                         "Team plan: 1 profile synced (no limit), the last 200 versions of each are kept.")
        self.assertEqual(d({"plan": "free", "profile_count": 2, "profile_limit": 5}), "Free plan: 2 of 5 profiles synced.")

    def test_anything_odd_shows_nothing_or_only_the_plan(self):
        d = cloud_sync.describe_plan
        for junk in (None, [], "free", {}, {"plan": "gold"}, {"plan": 5}):
            self.assertEqual(d(junk), "")
        self.assertEqual(d({"plan": "pro"}), "Pro plan.")
        self.assertEqual(d({"plan": "free", "profile_count": True, "profile_limit": "1"}), "Free plan.")
        self.assertEqual(d({"plan": "free", "profile_count": -1}), "Free plan.")


class LeavingTest(PageCase):
    def test_disconnecting_forgets_this_pc_but_not_the_profiles(self):
        page = self.connected(profile("A"))
        page.sync_button.click()
        with mock.patch.object(QMessageBox, "exec", return_value=QMessageBox.Ok):
            page.disconnect_button.click()
        self.assertEqual(page.stack.currentIndex(), INTRO)
        state = cloud_sync.load_state()
        self.assertEqual((state["token"], state["vault_key"], state["profiles"]), ("", "", []))
        self.assertEqual(len(self.window.cfg["profiles"]), 1)
        self.assertEqual(len(self.cloud.items), 1)

    def test_cancelling_the_disconnect_question_changes_nothing(self):
        page = self.connected()
        with mock.patch.object(QMessageBox, "exec", return_value=QMessageBox.Cancel):
            page.disconnect_button.click()
        self.assertEqual(page.stack.currentIndex(), READY)

    def test_closing_settings_stops_a_pairing_that_is_waiting(self):
        page = self.page(run=lambda work: None)
        page.pair_button.click()
        page.shutdown()
        self.assertTrue(page.closed)
        page.paired(page.pairing_token or "x")
        self.assertFalse(cloud_sync.is_paired(cloud_sync.load_state()))


class DescribeTest(unittest.TestCase):
    def test_plain_words(self):
        report = cloud_sync.Report(created=["A"], conflicts=["B"], skipped_limit=["C"], problems=["D: odd"])
        text = describe(report)
        for part in ("Sent: A", "both were kept", "limit is reached: C", "D: odd"):
            self.assertIn(part, text)
        self.assertEqual(describe(cloud_sync.Report()), "Everything is up to date.")


if __name__ == "__main__":
    unittest.main()
