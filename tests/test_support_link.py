"""The optional tip jar: one address everywhere, honest wording, and the Settings button opens it (offscreen)."""

import os
import re
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from numpadctl import ui_common  # noqa: E402
from numpadctl_ui import dialogs  # noqa: E402
from tests import test_qt_window  # noqa: E402  (module, so its tests are not collected twice)

ROOT = Path(__file__).resolve().parent.parent


class WhereItAppearsTest(unittest.TestCase):
    def test_the_address_is_a_ko_fi_page_over_https(self):
        self.assertRegex(ui_common.SUPPORT_URL, r"^https://ko-fi\.com/[A-Za-z0-9_]+$")

    def test_the_same_page_everywhere(self):
        name = ui_common.SUPPORT_URL.rsplit("/", 1)[1]
        self.assertIn(f"ko_fi: {name}", (ROOT / ".github" / "FUNDING.yml").read_text(encoding="utf-8"))
        self.assertIn(ui_common.SUPPORT_URL, (ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertIn(ui_common.SUPPORT_URL, (ROOT / "site" / "assets" / "site.js").read_text(encoding="utf-8"))
        self.assertIn(ui_common.SUPPORT_URL, (ROOT / "site" / "pricing.html").read_text(encoding="utf-8"))

    def test_the_wording_says_it_is_optional_and_unlocks_nothing(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        section = readme[readme.index("## Support the project"):].split("\n## ", 1)[0]
        self.assertIn("optional", section)
        self.assertIn("unlocks nothing", section)
        self.assertRegex((ROOT / "site" / "pricing.html").read_text(encoding="utf-8"), r"optional and unlocks nothing")

    def test_no_other_payment_or_affiliate_link_slipped_in(self):
        for path in (ROOT / "README.md", ROOT / "site" / "assets" / "site.js", ROOT / "site" / "pricing.html"):
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?i)amzn\.to|tag=[a-z0-9-]+-20|aliexpress\.com/.*aff|paypal\.me")


class SettingsButtonTest(unittest.TestCase):
    def setUp(self):
        test_qt_window.QtWindowTest.setUp(self)   # a real settings window on a temporary config
        self.addCleanup(self.tmp.cleanup)

    def test_the_button_opens_the_tip_jar_and_nothing_else_happens(self):
        dialog = dialogs.SettingsDialog(self.w)
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog.support_button.text(), "Support NumpadControl")
        with mock.patch.object(dialogs.QDesktopServices, "openUrl") as opened:
            dialog.support_button.click()
        self.assertEqual([call.args[0].toString() for call in opened.call_args_list], [ui_common.SUPPORT_URL])
        self.assertIn("Optional", dialog.support_button.toolTip())

    def test_opening_settings_does_not_open_anything(self):
        with mock.patch.object(dialogs.QDesktopServices, "openUrl") as opened:
            dialog = dialogs.SettingsDialog(self.w)
            dialog.deleteLater()
        opened.assert_not_called()


if __name__ == "__main__":
    unittest.main()
