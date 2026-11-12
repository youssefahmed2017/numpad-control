"""NumpadControl Cloud encryption: must match the cloud's reference implementation byte for byte."""

import json
import unittest
from pathlib import Path

from numpadctl import cloud_crypto as cc

V = json.loads((Path(__file__).parent / "fixtures" / "cloud-test-vectors.json").read_text())
ID = "11111111-2222-4333-8444-555555555555"


class VectorsTest(unittest.TestCase):
    """The fixture was produced by the cloud's TypeScript code; if these pass, the two sides agree."""

    def test_the_passphrase_opens_the_vault(self):
        self.assertEqual(cc.unlock_with_passphrase(V["vault"], V["passphrase"]).hex(), V["vault_key_hex"])

    def test_the_recovery_key_opens_the_vault(self):
        self.assertEqual(cc.unlock_with_recovery_key(V["vault"], V["recovery_key"]).hex(), V["vault_key_hex"])

    def test_the_profile_decrypts(self):
        p = V["profile"]
        key = bytes.fromhex(V["vault_key_hex"])
        self.assertEqual(cc.decrypt_profile(key, p["id"], p["rev"], p["ciphertext"], p["nonce"]), p["plaintext"])

    def test_encrypting_again_gives_the_identical_ciphertext(self):
        p = V["profile"]
        key = bytes.fromhex(V["vault_key_hex"])
        nonce = cc.b64d(p["nonce"])
        self.assertEqual(cc.encrypt_profile(key, p["id"], p["rev"], p["plaintext"], rng=lambda n: nonce), (p["ciphertext"], p["nonce"]))

    def test_a_vault_made_with_the_same_random_bytes_is_the_same_vault(self):
        counter = iter(range(1, 100))
        vault, key, recovery = cc.create_vault(V["passphrase"], rng=lambda n: bytes([next(counter)]) * n)
        self.assertEqual(vault, V["vault"])
        self.assertEqual(key.hex(), V["vault_key_hex"])
        self.assertEqual(recovery, V["recovery_key"])


class BehaviourTest(unittest.TestCase):
    def setUp(self):
        self.vault, self.key, self.recovery = cc.create_vault("my passphrase")

    def test_a_wrong_passphrase_or_recovery_key_is_refused_in_words(self):
        with self.assertRaisesRegex(cc.CloudCryptoError, "passphrase is wrong"):
            cc.unlock_with_passphrase(self.vault, "my passphras")
        with self.assertRaisesRegex(cc.CloudCryptoError, "recovery key is wrong"):
            cc.unlock_with_recovery_key(self.vault, cc.format_recovery_key(bytes(32)))
        with self.assertRaisesRegex(cc.CloudCryptoError, "wrong length"):
            cc.unlock_with_recovery_key(self.vault, "ABCD-EFGH")
        with self.assertRaisesRegex(cc.CloudCryptoError, "doesn't look like"):
            cc.unlock_with_recovery_key(self.vault, "ABC")
        with self.assertRaisesRegex(cc.CloudCryptoError, "wrong length"):
            cc.unlock_with_recovery_key(self.vault, "1" * 52)   # digits 0, 1, 8 and 9 aren't in the alphabet: all dropped

    def test_both_ways_in_give_the_same_key(self):
        self.assertEqual(cc.unlock_with_passphrase(self.vault, "my passphrase"), self.key)
        self.assertEqual(cc.unlock_with_recovery_key(self.vault, self.recovery.lower().replace("-", " ")), self.key)

    def test_a_passphrase_typed_with_combining_characters_still_works(self):
        vault, key, _ = cc.create_vault("café")
        self.assertEqual(cc.unlock_with_passphrase(vault, "café"), key)

    def test_the_server_cannot_move_a_profile_to_another_id_or_revision(self):
        ciphertext, nonce = cc.encrypt_profile(self.key, ID, 3, "{}")
        cc.decrypt_profile(self.key, ID, 3, ciphertext, nonce)
        for other_id, other_rev in ((ID.replace("1", "9"), 3), (ID, 2), (ID, 4)):
            with self.assertRaises(cc.CloudCryptoError):
                cc.decrypt_profile(self.key, other_id, other_rev, ciphertext, nonce)

    def test_a_changed_byte_is_noticed(self):
        ciphertext, nonce = cc.encrypt_profile(self.key, ID, 1, "{}")
        raw = bytearray(cc.b64d(ciphertext))
        raw[0] ^= 1
        with self.assertRaises(cc.CloudCryptoError):
            cc.decrypt_profile(self.key, ID, 1, cc.b64e(bytes(raw)), nonce)

    def test_a_vault_with_settings_that_are_too_weak_or_too_heavy_is_refused(self):
        for name, value in (("m", 8), ("m", 10_000_000), ("t", 1), ("t", 500), ("p", 0), ("p", 64), ("m", True), ("m", "65536")):
            vault = json.loads(json.dumps(self.vault))
            vault["kdf"][name] = value
            with self.assertRaisesRegex(cc.CloudCryptoError, "refuses"):
                cc.unlock_with_passphrase(vault, "my passphrase")

    def test_an_incomplete_or_newer_vault_is_refused(self):
        with self.assertRaisesRegex(cc.CloudCryptoError, "incomplete"):
            cc.unlock_with_passphrase({"version": 1}, "x")
        with self.assertRaisesRegex(cc.CloudCryptoError, "newer"):
            cc.unlock_with_passphrase({**self.vault, "version": 2}, "x")

    def test_garbage_in_place_of_base64_is_refused(self):
        for bad in ("not base64!", None, 5, "A"):
            with self.assertRaises(cc.CloudCryptoError):
                cc.b64d(bad)
        with self.assertRaises(cc.CloudCryptoError):
            cc.b64d("AAAA", 12)


if __name__ == "__main__":
    unittest.main()
