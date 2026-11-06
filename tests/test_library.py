"""The profile library: reading its index and fetching profiles, careful with what comes from outside."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from numpadctl import library, profile_io

PROFILE = {"format": "numpadcontrol-profile", "version": 1, "app_version": "0.3.1",
           "meta": {"author": "someone"},
           "profile": {"name": "Streaming", "match": "obs,obs64",
                       "bindings": {"7": {"tap": {"action": "obs_toggle_streaming", "params": {}}}}}}


def entry(**changes):
    item = {"id": "official/obs-streaming", "path": "profiles/official/obs-streaming.json", "tier": "official",
            "name": "Streaming (OBS)", "match": ["obs", "obs64"], "author": "youssefahmed2017",
            "description": "Go live and record.", "tags": ["streaming", "obs"], "platforms": ["windows", "linux"],
            "requires": ["OBS WebSocket server on"], "min_app_version": "0.3.1", "keys": 10,
            "actions": {"mic_mute": 1}, "risky_actions": []}
    item.update(changes)
    return item


def index(*entries, **changes):
    data = {"format": "numpadcontrol-library-index", "version": 1, "app_version": "0.3.1",
            "count": len(entries), "profiles": list(entries)}
    data.update(changes)
    return json.dumps(data).encode()


class LibraryFolder:
    """A library copy in a temporary folder, the way NUMPADCTL_LIBRARY can point at one."""

    def __init__(self, *entries):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "index.json").write_bytes(index(*entries))
        for e in entries:
            target = self.root / e["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(PROFILE), encoding="utf-8")


class IndexTest(unittest.TestCase):
    def test_reads_entries_official_first(self):
        entries = library.parse_index(index(
            entry(path="profiles/community/ann/zoom.json", name="Zoom", author="ann"),
            entry()))
        self.assertEqual([e.name for e in entries], ["Streaming (OBS)", "Zoom"])
        self.assertEqual(entries[0].tier, "official")
        self.assertEqual(entries[1].tier, "community")
        self.assertEqual(entries[0].match, ["obs", "obs64"])

    def test_tier_comes_from_the_path_not_the_claim(self):
        [e] = library.parse_index(index(entry(path="profiles/community/ann/x.json", tier="official")))
        self.assertEqual(e.tier, "community")

    def test_entries_with_paths_outside_profiles_are_skipped(self):
        bad = ["../secret.json", "profiles/official/../../x.json", "profiles/official/x.py", "/etc/passwd",
               "https://evil.example/x.json", "profiles/x.json", "profiles/community/a/b/c.json",
               "profiles/official/UPPER.json", "profiles\\official\\x.json", 42, None]
        entries = library.parse_index(index(*[entry(path=p) for p in bad], entry()))
        self.assertEqual([e.path for e in entries], ["profiles/official/obs-streaming.json"])

    def test_duplicates_and_nameless_entries_are_skipped(self):
        entries = library.parse_index(index(entry(), entry(), entry(path="profiles/official/b.json", name=" ")))
        self.assertEqual(len(entries), 1)

    def test_odd_fields_are_cut_down_not_trusted(self):
        [e] = library.parse_index(index(entry(name="A\nB" + "x" * 100, keys=True, tags="streaming",
                                              platforms=["windows", "amiga"], min_app_version="soon")))
        self.assertNotIn("\n", e.name)
        self.assertLessEqual(len(e.name), profile_io.MAX_NAME)
        self.assertEqual(e.keys, 0)
        self.assertEqual(e.tags, [])
        self.assertEqual(e.platforms, ["windows"])
        self.assertEqual(e.min_app_version, "")

    def test_refuses_what_is_not_an_index(self):
        for data, words in [(b"not json", "damaged"), (b"[]", "isn't a NumpadControl profile library"),
                            (index(format="other"), "isn't a NumpadControl"),
                            (index(version=2), "newer NumpadControl"), (index(version="1"), "no usable version"),
                            (index(profiles={}), "damaged")]:
            with self.subTest(data[:30]), self.assertRaisesRegex(library.LibraryError, words):
                library.parse_index(data)

    def test_newer_profiles_are_marked(self):
        [e] = library.parse_index(index(entry(min_app_version="99.0.0")))
        self.assertTrue(e.needs_newer_app)
        [e] = library.parse_index(index(entry(min_app_version="0.1.0")))
        self.assertFalse(e.needs_newer_app)

    def test_search(self):
        [e] = library.parse_index(index(entry()))
        self.assertTrue(e.matches(""))
        self.assertTrue(e.matches("OBS stream"))
        self.assertTrue(e.matches("obs64"))
        self.assertFalse(e.matches("blender"))

    def test_platform(self):
        [e] = library.parse_index(index(entry(platforms=["hyprland"])))
        with mock.patch.object(library, "IS_WINDOWS", True):
            self.assertFalse(e.fits_this_computer)
        with mock.patch.object(library, "IS_WINDOWS", False), mock.patch.dict(os.environ, {"HYPRLAND_INSTANCE_SIGNATURE": "x"}):
            self.assertTrue(e.fits_this_computer)


class FolderSourceTest(unittest.TestCase):
    def test_fetches_the_index_and_a_profile_the_importer_accepts(self):
        lib = LibraryFolder(entry())
        self.addCleanup(lib.tmp.cleanup)
        [e] = library.fetch_index(lib.root)
        profile, dropped = profile_io.parse(library.fetch_profile(e, lib.root))
        self.assertEqual(profile["name"], "Streaming")
        self.assertEqual(dropped, [])

    def test_the_environment_variable_picks_the_folder(self):
        lib = LibraryFolder(entry())
        self.addCleanup(lib.tmp.cleanup)
        with mock.patch.dict(os.environ, {"NUMPADCTL_LIBRARY": str(lib.root)}):
            self.assertEqual(len(library.fetch_index()), 1)
            self.assertEqual(library.describe_source(), str(lib.root))
        with mock.patch.dict(os.environ, {"NUMPADCTL_LIBRARY": ""}):
            self.assertEqual(library.source(), library.DEFAULT_SOURCE)
        with mock.patch.dict(os.environ, {"NUMPADCTL_LIBRARY": "http://plain.example/"}):
            with self.assertRaisesRegex(library.LibraryError, "https"):
                library.source()

    def test_a_missing_folder_says_so(self):
        with self.assertRaisesRegex(library.LibraryError, "couldn't read index.json"):
            library.fetch_index(Path(tempfile.gettempdir()) / "no-such-library-here")

    def test_big_files_are_refused(self):
        lib = LibraryFolder(entry())
        self.addCleanup(lib.tmp.cleanup)
        (lib.root / "index.json").write_bytes(b" " * (library.MAX_INDEX_BYTES + 1))
        with self.assertRaisesRegex(library.LibraryError, "bigger than expected"):
            library.fetch_index(lib.root)
        [e] = library.parse_index(index(entry()))
        (lib.root / e.path).write_bytes(b" " * (profile_io.MAX_BYTES + 1))
        with self.assertRaisesRegex(library.LibraryError, "bigger than expected"):
            library.fetch_profile(e, lib.root)

    def test_a_tampered_entry_cannot_leave_the_folder(self):
        [e] = library.parse_index(index(entry()))
        e.path = "../../outside.json"
        with self.assertRaisesRegex(library.LibraryError, "address"):
            library.fetch_profile(e, Path(tempfile.gettempdir()))


class OnlineSourceTest(unittest.TestCase):
    """The network is faked: what matters is the address asked for and how errors read."""

    def test_asks_for_the_file_under_the_library_address(self):
        seen = []

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n):
                return index(entry())

        def urlopen(request, timeout):
            seen.append((request.full_url, request.get_header("User-agent"), timeout))
            return Response()

        with mock.patch.object(library.urllib.request, "urlopen", urlopen):
            library.fetch_index(library.DEFAULT_SOURCE)
        self.assertEqual(seen[0][0], library.DEFAULT_SOURCE + "index.json")
        self.assertTrue(seen[0][1].startswith("numpad-control/"))
        self.assertEqual(seen[0][2], library.TIMEOUT)

    def test_not_found_and_offline_read_plainly(self):
        def not_found(request, timeout):
            raise library.urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

        def offline(request, timeout):
            raise library.urllib.error.URLError("no network")

        with mock.patch.object(library.urllib.request, "urlopen", not_found):
            with self.assertRaisesRegex(library.LibraryError, "isn't available"):
                library.fetch_index(library.DEFAULT_SOURCE)
        with mock.patch.object(library.urllib.request, "urlopen", offline):
            with self.assertRaisesRegex(library.LibraryError, "Are you online"):
                library.fetch_index(library.DEFAULT_SOURCE)


if __name__ == "__main__":
    unittest.main()
