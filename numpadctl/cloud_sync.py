"""Keeping this PC's profiles in step with NumpadControl Cloud.

What is kept here and what isn't: `cloud.json` (next to config.json, readable only by you, like the OBS password in
it) holds the cloud address, this PC's pairing token, the vault key, and for every synced profile the last revision
and content hash that were in step. Profiles themselves stay in config.json; `sync()` edits the config it is given
and the state it is given, and the caller saves both (also when it raised: part of the work may be done).

The rules that keep the cloud from becoming a way onto your PC (docs/SYNC-PROTOCOL.md in the cloud repo, section 5):
everything pulled is untrusted and goes through profile_io.parse(); a pulled profile that brings new risky actions
is shown to the user first; an older version than this PC already saw is refused (a replay); and when both sides
changed, nothing is overwritten: the cloud's version is kept next to yours as "Name (from cloud)".
"""

import hashlib
import json
import os
import re
import secrets
import socket
import uuid
from dataclasses import dataclass, field

from . import __version__, cloud_crypto, config, profile_io
from .cloud_api import CloudError

DEFAULT_SET = "Default"
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


# ---------------------------------------------------------------- the state file
def state_path():
    return config.CONFIG_DIR / "cloud.json"


def _entry(item):
    """One synced profile as stored, or None if the file was edited into nonsense."""
    if not isinstance(item, dict):
        return None
    ok = (isinstance(item.get("set"), str) and isinstance(item.get("name"), str) and isinstance(item.get("hash"), str)
          and isinstance(item.get("id"), str) and _UUID.fullmatch(item["id"])
          and isinstance(item.get("rev"), int) and not isinstance(item["rev"], bool) and item["rev"] >= 1)
    return {k: item[k] for k in ("set", "name", "id", "rev", "hash")} if ok else None


def load_state():
    try:
        data = json.loads(state_path().read_text())
    except (OSError, ValueError):
        data = {}
    data = data if isinstance(data, dict) else {}
    text = lambda key: data[key] if isinstance(data.get(key), str) else ""
    entries = [e for e in map(_entry, data.get("profiles") if isinstance(data.get("profiles"), list) else []) if e]
    excluded = [{"set": e["set"], "name": e["name"]} for e in (data.get("excluded") if isinstance(data.get("excluded"), list) else [])
                if isinstance(e, dict) and isinstance(e.get("set"), str) and isinstance(e.get("name"), str)]
    return {"url": text("url"), "device_name": text("device_name"), "token": text("token"),
            "vault_key": text("vault_key"), "profiles": entries, "excluded": excluded}


def save_state(state):
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # holds the token and the vault key
    with os.fdopen(fd, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


def is_paired(state):
    return bool(state["url"] and state["token"])


def vault_key(state):
    """The vault key kept on this PC, or None when this PC hasn't unlocked the vault yet."""
    try:
        return cloud_crypto.b64d(state["vault_key"], 32) if state["vault_key"] else None
    except cloud_crypto.CloudCryptoError:
        return None


def forget(state):
    """Disconnect this PC: the token, the key and the sync bookkeeping go; profiles on this PC stay."""
    state.update({"token": "", "vault_key": "", "profiles": []})     # the choice of which profiles to sync is kept


def is_synced(state, set_name, name):
    """False for a profile the user chose to keep out of the cloud (on the free plan only one fits)."""
    return {"set": set_name, "name": name} not in state["excluded"]


def set_synced(state, set_name, name, on):
    """Include or leave out a profile. Leaving one out removes its copy from the cloud at the next sync
    (the profile on this PC stays); including it uploads it."""
    entry = {"set": set_name, "name": name}
    present = entry in state["excluded"]
    if on and present:
        state["excluded"].remove(entry)
    elif not on and not present:
        state["excluded"].append(entry)


PLAN_NAMES = {"free": "Free", "pro": "Pro", "team": "Team"}


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def describe_plan(info):
    """One line about the account from the cloud's answer to `Api.me()`: "Free plan: 0 of 1 profile synced."
    Empty when the answer has no plan in it (an older server), so the screen simply shows nothing."""
    name = PLAN_NAMES.get(info.get("plan")) if isinstance(info, dict) else None
    if name is None:
        return ""
    used, limit, history = _count(info.get("profile_count")), _count(info.get("profile_limit")), _count(info.get("history_versions"))
    if used is None:
        return f"{name} plan."
    plural = lambda n: f"{n} profile{'' if n == 1 else 's'}"
    text = f"{name} plan: {used} of {limit} profile{'' if limit == 1 else 's'} synced" if limit is not None \
        else f"{name} plan: {plural(used)} synced (no limit)"
    if history:
        text += f", the last {history} versions of each are kept"
    elif history == 0:
        text += ", no version history"
    return text + "."


def default_device_name():
    name = profile_io._CONTROL.sub(" ", socket.gethostname()).strip()[:60]
    return name or "My PC"


# ---------------------------------------------------------------- connecting this PC
def token_hash(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def start_pairing(api, device_name):
    """(token, code, expires_at). The token stays here; only its hash goes to the server. Show `code` to the user,
    who types it into the dashboard; then poll `api.pair_poll(token_hash(token))` until it says "paired"."""
    token = secrets.token_urlsafe(32)
    answer = api.pair_start(device_name, token_hash(token))
    return token, answer["code"], answer.get("expires_at", "")


def finish_pairing(state, url, device_name, token):
    state.update({"url": url, "device_name": device_name, "token": token})


def create_vault(state, api, passphrase):
    """First PC: makes the vault, uploads it, keeps the key. Returns the recovery key to show (once!)."""
    vault, key, recovery = cloud_crypto.create_vault(passphrase)
    api.put_vault(vault)
    state["vault_key"] = cloud_crypto.b64e(key)
    return recovery


def unlock_vault(state, api, passphrase=None, recovery_key=None):
    """Another PC: unlocks the vault already in the cloud, with the passphrase or else the recovery key."""
    vault = api.get_vault()
    key = (cloud_crypto.unlock_with_passphrase(vault, passphrase) if passphrase is not None
           else cloud_crypto.unlock_with_recovery_key(vault, recovery_key))
    state["vault_key"] = cloud_crypto.b64e(key)


def vault_exists(api):
    try:
        api.get_vault()
        return True
    except CloudError as e:
        if e.code == "no_vault":
            return False
        raise


# ---------------------------------------------------------------- what a profile looks like in the cloud
def _clean_set(value):
    name = profile_io._CONTROL.sub(" ", value).strip()[:profile_io.MAX_NAME] if isinstance(value, str) else ""
    return name or DEFAULT_SET


def _payload(set_name, profile):
    """The text that gets encrypted: a normal profile file, plus the name of the set it lives in."""
    data = profile_io.export_profile(profile, __version__)
    data["set"] = set_name
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _hash(set_name, profile):
    body = profile_io.export_profile(profile)["profile"]
    return hashlib.sha256(json.dumps([set_name, body], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _risky(profile):
    return {label: n for label, n, risky in profile_io.summary(profile) if risky}


def _needs_review(old, new):
    """True when `new` has more of some risky action (run code, press keys, power off, open things) than `old`."""
    before = _risky(old) if old else {}
    return any(n > before.get(label, 0) for label, n in _risky(new).items())


# ---------------------------------------------------------------- one sync
@dataclass
class Report:
    pushed: list = field(default_factory=list)            # edited here, sent
    created: list = field(default_factory=list)           # new here, sent
    pulled: list = field(default_factory=list)            # edited elsewhere, brought here
    created_local: list = field(default_factory=list)     # new elsewhere, added here
    deleted: list = field(default_factory=list)           # deleted here, deleted in the cloud
    unsynced: list = field(default_factory=list)          # left out by the user: its copy was removed from the cloud
    removed: list = field(default_factory=list)           # deleted elsewhere, deleted here (user agreed)
    deleted_elsewhere: list = field(default_factory=list)  # deleted elsewhere; waiting for the user to decide
    conflicts: list = field(default_factory=list)         # both changed: the cloud's copy was saved next to yours
    needs_review: list = field(default_factory=list)      # brings risky actions the user didn't approve
    skipped_limit: list = field(default_factory=list)     # not sent: the plan's profile limit
    problems: list = field(default_factory=list)          # anything else, in words

    def changed(self):
        return any((self.pushed, self.created, self.pulled, self.created_local, self.deleted, self.unsynced, self.removed,
                    self.conflicts))


class _Sync:
    def __init__(self, cfg, state, api, key, confirm, allow_remote_deletes):
        self.cfg, self.state, self.api, self.key = cfg, state, api, key
        self.confirm, self.allow_remote_deletes = confirm, allow_remote_deletes
        self.report = Report()
        self.entries = state["profiles"]
        self.excluded = {(e["set"], e["name"]) for e in state.get("excluded", [])}
        self.remote = {}
        for item in api.list_profiles():
            if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("rev"), int):
                self.remote[item["id"]] = item

    # --- the local side
    def sets(self):
        return self.cfg.setdefault("sets", [{"name": DEFAULT_SET, "profiles": self.cfg.get("profiles", [])}])

    def local(self):
        found = {}
        for item in self.sets():
            for profile in item.get("profiles", []):
                found.setdefault((item["name"], profile.get("name", "")), profile)
        return found

    def add_local(self, set_name, profile):
        for item in self.sets():
            if item["name"] == set_name:
                profile["name"] = profile_io.unique_name(profile["name"], [p.get("name", "") for p in item["profiles"]])
                item["profiles"].append(profile)
                return profile["name"]
        self.sets().append({"name": set_name, "profiles": [profile]})
        return profile["name"]

    def label(self, entry_or_set, name=None):
        set_name, name = (entry_or_set["set"], entry_or_set["name"]) if name is None else (entry_or_set, name)
        return name if len(self.sets()) < 2 else f"{set_name} / {name}"

    # --- steps
    def run(self):
        for entry in list(self.entries):
            self.tracked(entry)
        known = {e["id"] for e in self.entries}
        for rid in [r for r in self.remote if r not in known]:
            self.pull_new(rid)
        self.push_new()
        return self.report

    def tracked(self, entry):
        local = self.local().get((entry["set"], entry["name"]))
        remote = self.remote.get(entry["id"])
        name = self.label(entry)
        if (entry["set"], entry["name"]) in self.excluded:     # the user left it out: take its copy out of the cloud
            if remote is None:
                self.entries.remove(entry)
            else:
                self.delete_remote(entry, name, self.report.unsynced)
            return
        changed_here = local is not None and _hash(entry["set"], local) != entry["hash"]
        if remote is None:                       # gone from the cloud: deleted on another PC
            if local is None or changed_here:    # (changed here: it is uploaded again as a new profile below)
                self.entries.remove(entry)
            elif self.allow_remote_deletes:
                self.remove_local(entry)
                self.report.removed.append(name)
            else:
                self.report.deleted_elsewhere.append((entry["set"], entry["name"]))
            return
        if remote["rev"] < entry["rev"]:
            self.report.problems.append(f"{name}: the cloud has an older version than this PC already had, so it was ignored")
            return
        changed_there = remote["rev"] > entry["rev"]
        if local is None:
            if changed_there:
                self.entries.remove(entry)       # edited elsewhere while deleted here: bring it back, as a new profile
            else:
                self.delete_remote(entry, name, self.report.deleted)
        elif changed_there and not changed_here:
            self.pull_into(entry, local, name)
        elif changed_here and not changed_there:
            self.push(entry, local, name)
        elif changed_here and changed_there:
            self.conflict(entry, local, name)

    def remove_local(self, entry):
        for item in self.sets():
            if item["name"] == entry["set"]:
                item["profiles"][:] = [p for p in item["profiles"] if p.get("name") != entry["name"]]
        self.entries.remove(entry)

    def delete_remote(self, entry, name, into):
        try:
            self.api.delete_profile(entry["id"])
        except CloudError as e:
            if e.code != "not_found":
                raise
        self.entries.remove(entry)
        self.remote.pop(entry["id"], None)       # it is gone now: it must not be pulled back as a "new" profile
        into.append(name)

    def fetch(self, profile_id, name):
        """(rev, set name, cleaned profile) of a profile in the cloud, or None (with the reason in the report)."""
        data = self.api.get_profile(profile_id)
        rev = data.get("rev")
        if not isinstance(rev, int) or isinstance(rev, bool) or rev < 1:
            self.report.problems.append(f"{name}: the cloud sent a profile this version doesn't understand")
            return None
        try:
            text = cloud_crypto.decrypt_profile(self.key, profile_id, rev, data.get("ciphertext"), data.get("nonce"))
            profile, dropped = profile_io.parse(text)
            set_name = _clean_set(json.loads(text).get("set"))
        except (cloud_crypto.CloudCryptoError, profile_io.ProfileFileError, ValueError) as e:
            self.report.problems.append(f"{name}: {e}")
            return None
        if dropped:
            self.report.problems.append(f"{name}: {len(dropped)} things from a newer version were left out")
        return rev, set_name, profile

    def approved(self, name, old, new):
        """A profile with risky actions it didn't have before is applied only if the user says so."""
        if not _needs_review(old, new):
            return True
        if self.confirm and self.confirm(name, profile_io.summary(new)):
            return True
        self.report.needs_review.append(name)
        return False

    def pull_into(self, entry, local, name):
        got = self.fetch(entry["id"], name)
        if got is None:
            return
        rev, _, profile = got
        if not self.approved(name, local, profile):
            return
        for key in ("match", "bindings", "layer_bindings"):
            local[key] = profile[key]
        entry["rev"], entry["hash"] = rev, _hash(entry["set"], local)
        self.report.pulled.append(name)

    def pull_new(self, profile_id):
        got = self.fetch(profile_id, "a new profile")
        if got is None:
            return
        rev, set_name, profile = got
        if not self.approved(profile["name"], None, profile):
            return
        name = self.add_local(set_name, profile)
        self.entries.append({"set": set_name, "name": name, "id": profile_id, "rev": rev, "hash": _hash(set_name, profile)})
        self.report.created_local.append(name)

    def conflict(self, entry, local, name):
        got = self.fetch(entry["id"], name)
        if got is None:
            return
        rev, _, theirs = got
        theirs["name"] = entry["name"]
        theirs_hash = _hash(entry["set"], theirs)
        if theirs_hash != _hash(entry["set"], local):
            copy = dict(theirs)
            copy["name"] = f"{entry['name']} (from cloud)"
            if not self.approved(copy["name"], None, copy):
                return
            self.add_local(entry["set"], copy)
            self.report.conflicts.append(name)
        # either way this PC is now "in step with" the cloud's version; if ours differs, it goes up on top of it
        entry["rev"], entry["hash"] = rev, theirs_hash
        if _hash(entry["set"], local) != theirs_hash:
            self.push(entry, local, name)

    def push(self, entry, local, name):
        try:
            text = _payload(entry["set"], local)
            if len(text.encode("utf-8")) > profile_io.MAX_BYTES:
                self.report.problems.append(f"{name}: too big for the cloud")
                return
            ciphertext, nonce = cloud_crypto.encrypt_profile(self.key, entry["id"], entry["rev"] + 1, text)
            answer = self.api.put_profile(entry["id"], entry["rev"], ciphertext, nonce)
        except CloudError as e:
            if e.code == "conflict":
                self.report.problems.append(f"{name}: it was changed somewhere else while syncing. Sync again.")
                return
            raise
        entry["rev"], entry["hash"] = answer["rev"], _hash(entry["set"], local)
        self.report.pushed.append(name)

    def push_new(self):
        tracked = {(e["set"], e["name"]) for e in self.entries}
        limit_hit = False
        for (set_name, name), profile in self.local().items():
            if (set_name, name) in tracked or (set_name, name) in self.excluded:
                continue
            label = self.label(set_name, name)
            if limit_hit:
                self.report.skipped_limit.append(label)
                continue
            entry = {"set": set_name, "name": name, "id": str(uuid.uuid4()), "rev": 0, "hash": ""}
            try:
                text = _payload(set_name, profile)
                if len(text.encode("utf-8")) > profile_io.MAX_BYTES:
                    self.report.problems.append(f"{label}: too big for the cloud")
                    continue
                ciphertext, nonce = cloud_crypto.encrypt_profile(self.key, entry["id"], 1, text)
                answer = self.api.put_profile(entry["id"], 0, ciphertext, nonce)
            except CloudError as e:
                if e.code == "plan_limit":
                    limit_hit = True
                    self.report.skipped_limit.append(label)
                    continue
                raise
            entry["rev"], entry["hash"] = answer["rev"], _hash(set_name, profile)
            self.entries.append(entry)
            self.report.created.append(label)


def sync(cfg, state, api, key, confirm=None, allow_remote_deletes=False):
    """Brings `cfg` (a loaded config) and the cloud into step. Returns a Report.

    Edits `cfg` and `state` in place; the caller saves them (config.save, save_state), even if this raised.
    `confirm(name, rows)` is asked about a pulled profile that has new risky actions; `rows` is profile_io.summary()."""
    return _Sync(cfg, state, api, key, confirm, allow_remote_deletes).run()


def reupload(state, keys):
    """For profiles the cloud lost (deleted on another PC) that the user wants to keep: forget the link, so the
    next sync uploads them again as new. `keys` are (set, name) pairs from Report.deleted_elsewhere."""
    state["profiles"][:] = [e for e in state["profiles"] if (e["set"], e["name"]) not in set(keys)]
