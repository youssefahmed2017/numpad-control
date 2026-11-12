"""Talking to NumpadControl Cloud over HTTPS: one small function per call the server offers.

Strict on purpose, like library.py: https only (plain http just for a server on this very PC, to try things out),
no redirects, a timeout, a cap on how much is read, and every failure turned into a CloudError whose message is
fit to show the user. Nothing here encrypts or decrypts; see cloud_crypto.py (the server only sees ciphertext).
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

DEFAULT_URL = "https://numpad-control-cloud.vercel.app"
TIMEOUT = 20
MAX_RESPONSE = 2_500_000      # the biggest answer is one profile: at most ~1 MB, as base64 text about 1.4 MB
LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]")


def server_url():
    """The cloud address: NUMPADCTL_CLOUD_URL (to try a local copy of the server), else the real one."""
    return os.environ.get("NUMPADCTL_CLOUD_URL") or DEFAULT_URL


class CloudError(Exception):
    """A call failed. `status` is the HTTP status (None: couldn't connect), `code` the server's short reason
    (e.g. "conflict", "plan_limit"), `data` its full JSON answer."""

    def __init__(self, message, status=None, code=None, data=None):
        super().__init__(message)
        self.status, self.code, self.data = status, code, data or {}


_MESSAGES = {
    "unauthorized": "This PC isn't connected to NumpadControl Cloud (it was removed, or never paired). Pair it again.",
    "plan_limit": "Your plan's profile limit is reached. Upgrade to sync more profiles.",
    "plan_required": "That needs a Pro or Team plan.",
    "conflict": "That profile was changed somewhere else first.",
    "vault_exists": "A vault already exists for this account.",
    "no_vault": "There is no vault for this account yet.",
    "not_found": "The cloud doesn't have that.",
    "too_large": "That profile is too big for the cloud.",
}


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None    # the API never redirects; a redirect would be someone steering the token somewhere else


_opener = urllib.request.build_opener(_NoRedirects)


def default_transport(method, url, headers, body):
    """(status, bytes). The tests replace this with a fake server."""
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with _opener.open(request, timeout=TIMEOUT) as response:
            return response.status, response.read(MAX_RESPONSE + 1)
    except urllib.error.HTTPError as e:
        return e.code, e.read(MAX_RESPONSE + 1)
    except (OSError, ValueError) as e:
        reason = getattr(e, "reason", e)
        raise CloudError(f"couldn't reach NumpadControl Cloud ({reason}). Are you online?") from None


def check_url(url):
    parts = urllib.parse.urlsplit(url)
    local = parts.hostname in [h.strip("[]") for h in LOCAL_HOSTS]
    if parts.scheme != "https" and not (parts.scheme == "http" and local):
        raise CloudError("the cloud address must start with https://")
    if not parts.hostname or parts.username or parts.password:
        raise CloudError("that isn't a usable cloud address")
    return url.rstrip("/")


class Api:
    def __init__(self, base_url, token=None, transport=default_transport):
        self.base = check_url(base_url)
        self.token = token
        self.transport = transport

    # ------------------------------------------------------------ plumbing
    def _call(self, method, path, body=None, auth=True):
        headers = {"User-Agent": f"numpad-control/{__version__}", "Accept": "application/json"}
        if auth:
            if not self.token:
                raise CloudError(_MESSAGES["unauthorized"], status=401, code="unauthorized")
            headers["Authorization"] = f"Bearer {self.token}"
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        status, raw = self.transport(method, self.base + path, headers, data)
        if len(raw) > MAX_RESPONSE:
            raise CloudError("the cloud's answer was bigger than expected, so it was refused", status=status)
        try:
            answer = json.loads(raw) if raw else {}
        except ValueError:
            answer = None
        if not isinstance(answer, dict):
            raise CloudError(f"the cloud answered in a way this version doesn't understand ({status})", status=status)
        if status >= 400:
            code = answer.get("error") if isinstance(answer.get("error"), str) else None
            raise CloudError(_MESSAGES.get(code, f"the cloud answered with an error ({status})"), status=status, code=code, data=answer)
        return answer

    # ------------------------------------------------------------ pairing (no token yet)
    def pair_start(self, name, token_hash):
        """Shows the user a code to type into the dashboard: {"code", "expires_at"}."""
        return self._call("POST", "/api/device/pair/start", {"name": name, "token_hash": token_hash}, auth=False)

    def pair_poll(self, token_hash):
        """"pending", "paired" or "expired"."""
        return self._call("POST", "/api/device/pair/poll", {"token_hash": token_hash}, auth=False).get("status")

    # ------------------------------------------------------------ the account
    def me(self):
        return self._call("GET", "/api/device/me")

    def get_vault(self):
        return self._call("GET", "/api/vault")

    def put_vault(self, vault):
        return self._call("PUT", "/api/vault", vault)

    # ------------------------------------------------------------ profiles
    def list_profiles(self):
        items = self._call("GET", "/api/profiles").get("profiles")
        if not isinstance(items, list):
            raise CloudError("the cloud's profile list is in a form this version doesn't understand")
        return items

    def get_profile(self, profile_id):
        return self._call("GET", f"/api/profiles/{_id(profile_id)}")

    def put_profile(self, profile_id, base_rev, ciphertext, nonce, name_hint=""):
        """Creates (base_rev 0) or edits revision `base_rev`. Returns {"rev"}; CloudError code "conflict" when stale."""
        return self._call("PUT", f"/api/profiles/{_id(profile_id)}",
                          {"base_rev": base_rev, "ciphertext": ciphertext, "nonce": nonce, "name_hint": name_hint})

    def delete_profile(self, profile_id):
        return self._call("DELETE", f"/api/profiles/{_id(profile_id)}")

    def list_revisions(self, profile_id):
        return self._call("GET", f"/api/profiles/{_id(profile_id)}/revisions").get("revisions", [])

    def get_revision(self, profile_id, rev):
        return self._call("GET", f"/api/profiles/{_id(profile_id)}/revisions?rev={int(rev)}")


def _id(value):
    """A profile id goes into a URL: only a UUID is allowed, so nothing from outside can add to the path."""
    text = str(value)
    if len(text) != 36 or not all(c in "0123456789abcdef-" for c in text):
        raise CloudError("that isn't a profile id")
    return text
