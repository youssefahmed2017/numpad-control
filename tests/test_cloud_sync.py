"""Syncing profiles with NumpadControl Cloud, against a fake cloud kept in memory (no network, no desktop)."""

import copy
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from numpadctl import cloud_crypto as cc, cloud_sync, config, profile_io
from numpadctl.cloud_api import Api, CloudError, check_url


def binding(action="media_next", **params):
    return {"tap": {"action": action, "params": params}}


def profile(name="Streaming", key="1", action="media_next", **params):
    return {"name": name, "match": "", "bindings": {key: binding(action, **params)}, "layer_bindings": {}}


def everything(cfg):
    """Every profile in every set."""
    return [p for item in cfg["sets"] for p in item["profiles"]]


def config_with(*profiles, set_name="Default"):
    return {"sets": [{"name": set_name, "profiles": list(profiles)}]}


class FakeCloud:
    """What the server does, in memory: ciphertext only, revisions, conflicts, a plan limit."""

    def __init__(self, limit=10_000):
        self.items, self.limit, self.calls = {}, limit, []

    def list_profiles(self):
        return [{"id": i, "rev": v["rev"]} for i, v in self.items.items()]

    def get_profile(self, profile_id):
        self.calls.append("get")
        v = self.items[profile_id]
        return {"id": profile_id, "rev": v["rev"], "ciphertext": v["ciphertext"], "nonce": v["nonce"]}

    def put_profile(self, profile_id, base_rev, ciphertext, nonce, name_hint=""):
        self.calls.append("put")
        if base_rev == 0:
            if profile_id in self.items:
                raise CloudError("exists", status=409, code="conflict")
            if len(self.items) >= self.limit:
                raise CloudError("limit", status=402, code="plan_limit", data={"limit": self.limit})
            self.items[profile_id] = {"rev": 1, "ciphertext": ciphertext, "nonce": nonce}
            return {"rev": 1}
        current = self.items.get(profile_id)
        if current is None:
            raise CloudError("nope", status=404, code="not_found")
        if current["rev"] != base_rev:
            raise CloudError("stale", status=409, code="conflict", data={"current_rev": current["rev"]})
        self.items[profile_id] = {"rev": base_rev + 1, "ciphertext": ciphertext, "nonce": nonce}
        return {"rev": base_rev + 1}

    def delete_profile(self, profile_id):
        self.calls.append("delete")
        if self.items.pop(profile_id, None) is None:
            raise CloudError("nope", status=404, code="not_found")
        return {"ok": True}


def empty_state():
    return {"url": "https://x.test", "device_name": "t", "token": "t", "vault_key": "", "profiles": [], "excluded": []}


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.cloud = FakeCloud()
        self.key = os.urandom(32)

    def sync(self, cfg, state, **kwargs):
        return cloud_sync.sync(cfg, state, self.cloud, self.key, **kwargs)

    def first_pc(self, *profiles):
        cfg, state = config_with(*profiles), empty_state()
        self.sync(cfg, state)
        return cfg, state

    def second_pc(self):
        cfg, state = {"sets": []}, empty_state()     # a PC with nothing yet: the sets come from the cloud
        report = self.sync(cfg, state)
        return cfg, state, report

    # --- the basics
    def test_new_profiles_are_sent_encrypted(self):
        cfg, state = self.first_pc(profile("Streaming"), profile("Gaming", key="2"))
        self.assertEqual(len(self.cloud.items), 2)
        self.assertEqual([e["rev"] for e in state["profiles"]], [1, 1])
        blob = json.dumps(self.cloud.items)
        self.assertNotIn("Streaming", blob)
        self.assertNotIn("media_next", blob)

    def test_nothing_changed_nothing_sent(self):
        cfg, state = self.first_pc(profile())
        self.cloud.calls.clear()
        report = self.sync(cfg, state)
        self.assertFalse(report.changed())
        self.assertEqual(self.cloud.calls, [])

    def test_an_edit_here_is_sent_as_the_next_revision(self):
        cfg, state = self.first_pc(profile())
        cfg["sets"][0]["profiles"][0]["bindings"]["2"] = binding("media_previous")
        report = self.sync(cfg, state)
        self.assertEqual(report.pushed, ["Streaming"])
        self.assertEqual(state["profiles"][0]["rev"], 2)

    def test_a_second_pc_receives_everything_and_is_then_in_step(self):
        cfg_a, _ = self.first_pc(profile("Streaming"), profile("Gaming", key="2"))
        cfg_b, state_b, report = self.second_pc()
        self.assertEqual(sorted(report.created_local), ["Gaming", "Streaming"])
        self.assertEqual({p["name"]: p["bindings"] for p in cfg_b["sets"][0]["profiles"]},
                         {p["name"]: p["bindings"] for p in cfg_a["sets"][0]["profiles"]})
        self.assertFalse(self.sync(cfg_b, state_b).changed())

    def test_an_edit_on_another_pc_is_pulled(self):
        cfg_a, state_a = self.first_pc(profile())
        cfg_b, state_b, _ = self.second_pc()
        cfg_b["sets"][0]["profiles"][0]["bindings"]["5"] = binding("media_previous")
        self.sync(cfg_b, state_b)
        report = self.sync(cfg_a, state_a)
        self.assertEqual(report.pulled, ["Streaming"])
        self.assertIn("5", cfg_a["sets"][0]["profiles"][0]["bindings"])

    def test_sets_are_kept_apart(self):
        cfg = {"sets": [{"name": "Desk", "profiles": [profile("A")]}, {"name": "Laptop", "profiles": [profile("A", key="3")]}]}
        self.sync(cfg, empty_state())
        cfg_b, _, _ = self.second_pc()
        self.assertEqual(sorted(s["name"] for s in cfg_b["sets"]), ["Desk", "Laptop"])
        self.assertEqual(cfg_b["sets"][1]["profiles"][0]["bindings"].keys(), {"3"})

    # --- both sides changed
    def test_a_conflict_keeps_both_versions(self):
        cfg_a, state_a = self.first_pc(profile())
        cfg_b, state_b, _ = self.second_pc()
        cfg_a["sets"][0]["profiles"][0]["bindings"]["7"] = binding("media_next")
        cfg_b["sets"][0]["profiles"][0]["bindings"]["8"] = binding("media_previous")
        self.sync(cfg_b, state_b)                       # B gets there first
        report = self.sync(cfg_a, state_a)              # A then finds both changed
        self.assertEqual(report.conflicts, ["Streaming"])
        names = [p["name"] for p in cfg_a["sets"][0]["profiles"]]
        self.assertEqual(names, ["Streaming", "Streaming (from cloud)"])
        self.assertIn("8", cfg_a["sets"][0]["profiles"][1]["bindings"])     # B's version, kept
        self.assertIn("7", cfg_a["sets"][0]["profiles"][0]["bindings"])     # A's own, untouched
        self.assertEqual(state_a["profiles"][0]["rev"], 3)                  # and A's went up on top of B's
        self.assertFalse(self.sync(cfg_a, state_a).conflicts)               # no conflict again afterwards

    def test_both_sides_making_the_same_edit_is_not_a_conflict(self):
        cfg_a, state_a = self.first_pc(profile())
        cfg_b, state_b, _ = self.second_pc()
        for cfg in (cfg_a, cfg_b):
            cfg["sets"][0]["profiles"][0]["bindings"]["9"] = binding("media_previous")
        self.sync(cfg_b, state_b)
        report = self.sync(cfg_a, state_a)
        self.assertEqual((report.conflicts, len(cfg_a["sets"][0]["profiles"])), ([], 1))

    # --- what a hostile or broken cloud can try
    def test_an_older_version_than_this_pc_already_had_is_refused(self):
        cfg, state = self.first_pc(profile())
        cfg["sets"][0]["profiles"][0]["bindings"]["2"] = binding("media_previous")
        self.sync(cfg, state)                           # rev 2 on this PC
        only = next(iter(self.cloud.items))
        self.cloud.items[only]["rev"] = 1               # the cloud "goes back"
        before = copy.deepcopy(cfg)
        report = self.sync(cfg, state)
        self.assertTrue(any("older version" in p for p in report.problems))
        self.assertEqual(cfg, before)

    def test_a_tampered_profile_is_reported_and_not_applied(self):
        cfg_a, _ = self.first_pc(profile())
        only = next(iter(self.cloud.items))
        raw = bytearray(cc.b64d(self.cloud.items[only]["ciphertext"]))
        raw[3] ^= 1
        self.cloud.items[only]["ciphertext"] = cc.b64e(bytes(raw))
        cfg_b, state_b, report = self.second_pc()
        self.assertEqual(everything(cfg_b), [])
        self.assertTrue(any("integrity" in p for p in report.problems))

    def test_a_profile_swapped_in_from_another_id_is_refused(self):
        self.first_pc(profile("One"), profile("Two", key="2"))
        one, two = list(self.cloud.items)
        self.cloud.items[one] = dict(self.cloud.items[two])        # the server answers for "one" with "two"'s data
        cfg_b, _, report = self.second_pc()
        self.assertEqual([p["name"] for p in cfg_b["sets"][0]["profiles"]], ["Two"])
        self.assertTrue(any("integrity" in p for p in report.problems))

    def test_a_pulled_profile_with_new_risky_actions_waits_for_the_user(self):
        self.first_pc(profile("Tools", action="open_url", url="https://example.org"))
        asked = []
        cfg_b, state_b, report = self.second_pc_with(lambda name, rows: asked.append((name, rows)) or False)
        self.assertEqual(report.needs_review, ["Tools"])
        self.assertEqual(everything(cfg_b), [])
        self.assertEqual(asked[0][0], "Tools")
        self.assertTrue(any(risky for _, _, risky in asked[0][1]))
        # the user agrees: now it is applied
        cfg_c, _, report = self.second_pc_with(lambda name, rows: True)
        self.assertEqual(report.created_local, ["Tools"])

    def second_pc_with(self, confirm):
        cfg, state = {"sets": []}, empty_state()
        return cfg, state, self.sync(cfg, state, confirm=confirm)

    def test_without_anyone_to_ask_a_risky_profile_is_never_applied(self):
        self.first_pc(profile("Tools", action="open_url", url="https://example.org"))
        cfg_b, _, report = self.second_pc()
        self.assertEqual((everything(cfg_b), report.needs_review), ([], ["Tools"]))

    def test_harmless_profiles_need_no_question(self):
        self.first_pc(profile())
        _, _, report = self.second_pc_with(lambda name, rows: self.fail("nobody should be asked"))
        self.assertEqual(report.created_local, ["Streaming"])

    # --- deleting
    def test_deleting_here_deletes_in_the_cloud(self):
        cfg, state = self.first_pc(profile())
        cfg["sets"][0]["profiles"].clear()
        report = self.sync(cfg, state)
        self.assertEqual((report.deleted, self.cloud.items, state["profiles"]), (["Streaming"], {}, []))

    def test_deleted_elsewhere_is_only_reported_until_the_user_agrees(self):
        cfg_a, state_a = self.first_pc(profile())
        self.cloud.items.clear()
        report = self.sync(cfg_a, state_a)
        self.assertEqual(report.deleted_elsewhere, [("Default", "Streaming")])
        self.assertEqual(len(cfg_a["sets"][0]["profiles"]), 1)
        report = self.sync(cfg_a, state_a, allow_remote_deletes=True)
        self.assertEqual((report.removed, cfg_a["sets"][0]["profiles"]), (["Streaming"], []))

    def test_keeping_a_profile_deleted_elsewhere_uploads_it_again(self):
        cfg, state = self.first_pc(profile())
        self.cloud.items.clear()
        cloud_sync.reupload(state, self.sync(cfg, state).deleted_elsewhere)
        report = self.sync(cfg, state)
        self.assertEqual((report.created, len(self.cloud.items)), (["Streaming"], 1))

    def test_a_profile_changed_here_but_deleted_elsewhere_is_not_lost(self):
        cfg, state = self.first_pc(profile())
        self.cloud.items.clear()
        cfg["sets"][0]["profiles"][0]["bindings"]["4"] = binding("media_previous")
        report = self.sync(cfg, state)
        self.assertEqual((report.created, len(cfg["sets"][0]["profiles"]), len(self.cloud.items)), (["Streaming"], 1, 1))

    # --- choosing what to sync
    def test_a_profile_left_out_is_never_sent(self):
        state = empty_state()
        cloud_sync.set_synced(state, "Default", "Private", False)
        cfg = config_with(profile("Streaming"), profile("Private", key="2"))
        report = self.sync(cfg, state)
        self.assertEqual((report.created, report.skipped_limit, len(self.cloud.items)), (["Streaming"], [], 1))

    def test_leaving_a_synced_profile_out_removes_its_cloud_copy_but_keeps_it_here(self):
        cfg, state = self.first_pc(profile("Streaming"), profile("Private", key="2"))
        cloud_sync.set_synced(state, "Default", "Private", False)
        report = self.sync(cfg, state)
        self.assertEqual((report.unsynced, len(self.cloud.items), len(cfg["sets"][0]["profiles"])), (["Private"], 1, 2))
        self.assertFalse(self.sync(cfg, state).changed())          # and it stays that way
        cloud_sync.set_synced(state, "Default", "Private", True)   # changed my mind
        self.assertEqual(self.sync(cfg, state).created, ["Private"])

    def test_which_profiles_to_sync_is_remembered_and_survives_disconnecting(self):
        state = empty_state()
        cloud_sync.set_synced(state, "Default", "A", False)
        cloud_sync.set_synced(state, "Default", "A", False)       # twice is the same as once
        self.assertEqual(state["excluded"], [{"set": "Default", "name": "A"}])
        cloud_sync.forget(state)
        self.assertFalse(cloud_sync.is_synced(state, "Default", "A"))
        self.assertTrue(cloud_sync.is_synced(state, "Default", "B"))

    # --- the plan
    def test_the_free_limit_sends_what_fits_and_reports_the_rest(self):
        self.cloud.limit = 1
        cfg = config_with(profile("A"), profile("B", key="2"), profile("C", key="3"))
        report = self.sync(cfg, empty_state())
        self.assertEqual((report.created, report.skipped_limit), (["A"], ["B", "C"]))
        self.assertEqual(len(cfg["sets"][0]["profiles"]), 3)      # nothing is taken away locally
        self.assertEqual(self.cloud.calls.count("put"), 2)        # B was tried, C was not (the limit was known)


class StateFileTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        patcher = mock.patch.object(config, "CONFIG_DIR", Path(self.dir.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.dir.cleanup)

    def test_saved_privately_and_read_back(self):
        state = cloud_sync.load_state()
        state.update(url="https://x.test", token="secret", vault_key=cc.b64e(bytes(32)))
        cloud_sync.set_synced(state, "Default", "Private", False)
        cloud_sync.save_state(state)
        self.assertEqual(stat.S_IMODE(cloud_sync.state_path().stat().st_mode), 0o600)
        again = cloud_sync.load_state()
        self.assertEqual((again["token"], cloud_sync.vault_key(again), cloud_sync.is_paired(again)), ("secret", bytes(32), True))
        self.assertFalse(cloud_sync.is_synced(again, "Default", "Private"))

    def test_a_missing_or_damaged_file_means_not_connected(self):
        self.assertFalse(cloud_sync.is_paired(cloud_sync.load_state()))
        for junk in ("not json", "[]", '{"profiles": "x", "token": 5, "excluded": 3}', '{"profiles": [1, {"id": "../x", "rev": 1}], "excluded": [1, {"set": 2}]}'):
            cloud_sync.state_path().write_text(junk)
            state = cloud_sync.load_state()
            self.assertEqual((state["profiles"], state["excluded"], cloud_sync.is_paired(state)), ([], [], False))

    def test_forget_disconnects_but_keeps_the_address(self):
        state = {"url": "https://x.test", "device_name": "pc", "token": "t", "vault_key": "k", "profiles": [{"id": "x"}], "excluded": []}
        cloud_sync.forget(state)
        self.assertEqual((state["token"], state["vault_key"], state["profiles"], state["url"]), ("", "", [], "https://x.test"))


class ApiTest(unittest.TestCase):
    def api(self, status=200, body=b"{}", token="tok"):
        self.seen = []
        def transport(method, url, headers, data):
            self.seen.append((method, url, headers, data))
            return status, body
        return Api("https://x.test/", token, transport)

    def test_the_token_goes_in_a_header_and_never_in_the_url_or_body(self):
        api = self.api(body=b'{"profiles": []}')
        api.list_profiles()
        method, url, headers, data = self.seen[0]
        self.assertEqual((method, url, headers["Authorization"]), ("GET", "https://x.test/api/profiles", "Bearer tok"))
        self.assertNotIn("tok", url)

    def test_pairing_sends_only_the_hash(self):
        api = self.api(body=b'{"code": "ABCD-2345", "expires_at": "x"}', token=None)
        token, code, _ = cloud_sync.start_pairing(api, "My PC")
        body = json.loads(self.seen[0][3])
        self.assertEqual(body, {"name": "My PC", "token_hash": cloud_sync.token_hash(token)})
        self.assertNotIn(token, self.seen[0][3].decode())
        self.assertNotIn("Authorization", self.seen[0][2])
        self.assertEqual(code, "ABCD-2345")

    def test_server_errors_become_readable_messages_with_a_code(self):
        api = self.api(status=401, body=b'{"error": "unauthorized"}')
        with self.assertRaises(CloudError) as caught:
            api.me()
        self.assertEqual((caught.exception.status, caught.exception.code), (401, "unauthorized"))
        self.assertIn("Pair it again", str(caught.exception))

    def test_answers_that_are_not_json_objects_are_refused(self):
        for body in (b"<html>", b"[1]", b'"x"'):
            with self.assertRaises(CloudError):
                self.api(body=body).me()

    def test_an_oversized_answer_is_refused(self):
        with self.assertRaisesRegex(CloudError, "bigger than expected"):
            self.api(body=b"x" * 2_600_000).me()

    def test_only_https_is_allowed_except_for_a_server_on_this_pc(self):
        for bad in ("http://example.org", "ftp://example.org", "https://user:pw@example.org", "example.org", "https://"):
            with self.assertRaises(CloudError):
                check_url(bad)
        self.assertEqual(check_url("http://localhost:3000/"), "http://localhost:3000")
        self.assertEqual(check_url("https://example.org/"), "https://example.org")

    def test_a_profile_id_cannot_add_to_the_path(self):
        api = self.api()
        for bad in ("../vault", "x" * 36, "ABCDEFAB-1111-2222-3333-444444444444", "1111/2222"):
            with self.assertRaises(CloudError):
                api.get_profile(bad)
        self.assertEqual(self.seen, [])

    def test_calls_without_a_token_do_not_even_reach_the_network(self):
        api = self.api(token=None)
        with self.assertRaises(CloudError):
            api.list_profiles()
        self.assertEqual(self.seen, [])


class VaultFlowTest(unittest.TestCase):
    def test_first_pc_creates_the_vault_and_a_second_unlocks_it(self):
        sent = {}

        class Api2:
            def put_vault(self, vault): sent["vault"] = vault
            def get_vault(self): return sent["vault"]

        a, b = empty_state(), empty_state()
        recovery = cloud_sync.create_vault(a, Api2(), "my passphrase")
        cloud_sync.unlock_vault(b, Api2(), passphrase="my passphrase")
        self.assertEqual(cloud_sync.vault_key(a), cloud_sync.vault_key(b))
        c = empty_state()
        cloud_sync.unlock_vault(c, Api2(), recovery_key=recovery)
        self.assertEqual(cloud_sync.vault_key(c), cloud_sync.vault_key(a))
        with self.assertRaises(cc.CloudCryptoError):
            cloud_sync.unlock_vault(empty_state(), Api2(), passphrase="wrong")
        self.assertEqual(profile_io.MAX_BYTES, 1_000_000)   # the cloud's size limit is built on this number


if __name__ == "__main__":
    unittest.main()
