"""End-to-end encryption for NumpadControl Cloud: the cloud only ever stores what this module encrypted.

A random 32-byte *vault key* encrypts every profile (AES-256-GCM). The server keeps that key wrapped twice, once
under a key made from the user's passphrase (Argon2id) and once under a *recovery key* shown to the user a single
time, so a new PC can unlock the vault and the server can never read or forge a profile. A profile's id and
revision are bound into its ciphertext, so the server can't hand one profile's data back as another's.

The exact scheme is written down in numpad-control-cloud/docs/SYNC-PROTOCOL.md, with test vectors that the cloud's
own implementation and this one must both reproduce (tests/fixtures/cloud-test-vectors.json).
"""

import base64
import os
import re
import unicodedata

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

KDF = {"alg": "argon2id", "m": 65536, "t": 3, "p": 1}      # m is in KiB: 64 MiB
KDF_LIMITS = {"m": (19456, 262144), "t": (2, 10), "p": (1, 4)}   # what we accept from the server (see unlock)
AAD_VAULT = b"numpadcloud/vault/v1"
AAD_RECOVERY = b"numpadcloud/recovery/v1"
_B64 = re.compile(r"[A-Za-z0-9_-]*")


class CloudCryptoError(Exception):
    """Something couldn't be encrypted or decrypted; the message says why, in plain words."""


# ---------------------------------------------------------------- base64url, without padding
def b64e(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64d(text, length=None):
    """The bytes of a base64url string; refuses anything else (and, when `length` is given, any other size)."""
    if not isinstance(text, str) or not _B64.fullmatch(text) or len(text) % 4 == 1:
        raise CloudCryptoError("the cloud sent data in an unexpected form")
    raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    if length is not None and len(raw) != length:
        raise CloudCryptoError("the cloud sent data of the wrong size")
    return raw


# ---------------------------------------------------------------- keys
def _passphrase_key(passphrase, salt, params):
    # NFKC, so the same passphrase typed on Linux and on Windows makes the same key
    secret = unicodedata.normalize("NFKC", passphrase).encode("utf-8")
    return Argon2id(salt=salt, length=32, iterations=params["t"], lanes=params["p"], memory_cost=params["m"]).derive(secret)


def format_recovery_key(raw):
    """32 bytes as groups of four base32 letters/digits: ABCD-EFGH-..."""
    text = base64.b32encode(raw).decode("ascii").rstrip("=")
    return "-".join(text[i:i + 4] for i in range(0, len(text), 4))


def parse_recovery_key(text):
    clean = "".join(c for c in str(text).upper() if c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")
    try:
        raw = base64.b32decode(clean + "=" * (-len(clean) % 8))
    except ValueError:
        raise CloudCryptoError("that doesn't look like a recovery key") from None
    if len(raw) != 32:
        raise CloudCryptoError("that recovery key is the wrong length")
    return raw


def create_vault(passphrase, rng=os.urandom):
    """First PC. (vault record to upload, vault key to keep on this PC, recovery key text to show once).

    `rng` is only replaced by the tests, with a predictable one."""
    vault_key = rng(32)
    recovery = rng(32)
    salt, wrap_nonce, recovery_nonce = rng(16), rng(12), rng(12)
    vault = {
        "version": 1,
        "kdf": {**KDF, "salt": b64e(salt)},
        "wrapped_key": b64e(AESGCM(_passphrase_key(passphrase, salt, KDF)).encrypt(wrap_nonce, vault_key, AAD_VAULT)),
        "wrap_nonce": b64e(wrap_nonce),
        "recovery_wrapped_key": b64e(AESGCM(recovery).encrypt(recovery_nonce, vault_key, AAD_RECOVERY)),
        "recovery_nonce": b64e(recovery_nonce),
    }
    return vault, vault_key, format_recovery_key(recovery)


def _check_vault(vault):
    try:
        kdf = vault["kdf"]
        params = {name: kdf[name] for name in ("m", "t", "p")}
        if vault.get("version") != 1 or kdf.get("alg") != "argon2id":
            raise CloudCryptoError("this vault was made by a newer NumpadControl: update it first")
        for name, (low, high) in KDF_LIMITS.items():
            # a server could name settings that are cheap to crack, or so heavy they freeze this PC
            if not isinstance(params[name], int) or isinstance(params[name], bool) or not low <= params[name] <= high:
                raise CloudCryptoError("the vault uses key settings this version refuses")
        return params, b64d(kdf["salt"], 16), b64d(vault["wrap_nonce"], 12), b64d(vault["wrapped_key"], 48)
    except (KeyError, TypeError, AttributeError):
        raise CloudCryptoError("the cloud's vault record is incomplete") from None


def unlock_with_passphrase(vault, passphrase):
    """Another PC: the vault key, or CloudCryptoError when the passphrase is wrong."""
    params, salt, nonce, wrapped = _check_vault(vault)
    try:
        return AESGCM(_passphrase_key(passphrase, salt, params)).decrypt(nonce, wrapped, AAD_VAULT)
    except InvalidTag:
        raise CloudCryptoError("that passphrase is wrong") from None


def unlock_with_recovery_key(vault, recovery_key):
    try:
        return AESGCM(parse_recovery_key(recovery_key)).decrypt(
            b64d(vault["recovery_nonce"], 12), b64d(vault["recovery_wrapped_key"], 48), AAD_RECOVERY)
    except InvalidTag:
        raise CloudCryptoError("that recovery key is wrong") from None
    except (KeyError, TypeError):
        raise CloudCryptoError("the cloud's vault record is incomplete") from None


# ---------------------------------------------------------------- profiles
def _profile_aad(profile_id, rev):
    return f"numpadcloud/profile/v1|{profile_id}|{rev}".encode("utf-8")


def encrypt_profile(vault_key, profile_id, rev, text, rng=os.urandom):
    """(ciphertext, nonce) as base64url text. `rev` is the revision the server will give this upload (base + 1)."""
    nonce = rng(12)
    return b64e(AESGCM(vault_key).encrypt(nonce, text.encode("utf-8"), _profile_aad(profile_id, rev))), b64e(nonce)


def decrypt_profile(vault_key, profile_id, rev, ciphertext, nonce):
    """The profile text; CloudCryptoError if it was altered, or is for another profile or revision."""
    try:
        return AESGCM(vault_key).decrypt(b64d(nonce, 12), b64d(ciphertext), _profile_aad(profile_id, rev)).decode("utf-8")
    except (InvalidTag, UnicodeDecodeError):
        raise CloudCryptoError("a profile from the cloud failed its integrity check (wrong key, or it was tampered with)") from None
