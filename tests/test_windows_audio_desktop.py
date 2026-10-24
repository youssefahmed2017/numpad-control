"""Windows audio (with a fake pycaw) and Windows window actions (with fake window data)."""

import enum
import os
import sys
import types
import unittest
from unittest import mock

from numpadctl import actions
from numpadctl.platform import windows_audio as wa, windows_desktop as wd


class FakeVolume:
    def __init__(self, level, mute=False):
        self.level, self.mute = level, mute

    def GetMasterVolume(self):
        return self.level

    def SetMasterVolume(self, level, context):
        self.level = level

    def GetMute(self):
        return self.mute

    def SetMute(self, mute, context):
        self.mute = bool(mute)


class FakeSession:
    def __init__(self, exe, level):
        self.Process = types.SimpleNamespace(name=lambda: exe) if exe else None
        self.SimpleAudioVolume = FakeVolume(level)


class FakeDevice:
    def __init__(self, id_, name):
        self.id, self.FriendlyName = id_, name
        self.EndpointVolume = FakeVolume(1.0)


class FakePycaw:
    """Stands in for comtypes + pycaw: Spotify (2 sessions), Firefox, System sounds; 2 outputs."""

    def __init__(self):
        self.sessions = [FakeSession("Spotify.exe", 0.40), FakeSession("Spotify.exe", 0.30),
                         FakeSession("firefox.exe", 0.98), FakeSession(None, 1.0)]
        self.devices = [FakeDevice("{speakers}", "Speakers (Realtek(R) Audio)"),
                        FakeDevice("{headset}", "Headphones (WH-1000XM4)")]
        self.default, self.microphone = "{speakers}", FakeDevice("{mic}", "Microphone")
        self.com = 0
        fake = self
        constants = types.SimpleNamespace(
            EDataFlow=enum.Enum("EDataFlow", {"eRender": 0, "eCapture": 1}),
            DEVICE_STATE=enum.Enum("DEVICE_STATE", {"ACTIVE": 1}),
            ERole=enum.Enum("ERole", {"eConsole": 0, "eMultimedia": 1, "eCommunications": 2}))

        class AudioUtilities:
            GetAllSessions = staticmethod(lambda: fake.sessions)
            GetAllDevices = staticmethod(lambda flow, state: fake.devices if (flow, state) == (0, 1) else [])
            GetSpeakers = staticmethod(lambda: next(d for d in fake.devices if d.id == fake.default))
            GetMicrophone = staticmethod(lambda: "raw microphone")
            CreateDevice = staticmethod(lambda raw: fake.microphone)

            @staticmethod
            def SetDefaultDevice(dev_id, roles):
                fake.default, fake.roles = dev_id, roles

        self.modules = {
            "comtypes": types.SimpleNamespace(CoInitialize=self._init, CoUninitialize=self._uninit),
            "pycaw": types.ModuleType("pycaw"),
            "pycaw.constants": constants,
            "pycaw.pycaw": types.SimpleNamespace(AudioUtilities=AudioUtilities)}

    def _init(self):
        self.com += 1

    def _uninit(self):
        self.com -= 1


class WindowsAudioTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakePycaw()
        patch = mock.patch.dict(sys.modules, self.fake.modules)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(lambda: self.assertEqual(self.fake.com, 0, "COM set up and torn down per call"))

    def test_playing_apps(self):
        self.assertEqual(wa.playing_apps(), ["firefox", "Spotify"])

    def test_app_volume_changes_every_session_and_is_capped(self):
        self.assertEqual(wa.change_app_volume("spotify", 5), "Spotify 45%")
        self.assertEqual([round(s.SimpleAudioVolume.level, 2) for s in self.fake.sessions[:2]], [0.45, 0.35])
        self.assertEqual(wa.change_app_volume("Firefox", 5), "firefox 100%")

    def test_mute_and_quiet_app(self):
        self.assertEqual(wa.toggle_app_mute("spotify"), "Spotify muted")
        self.assertTrue(all(s.SimpleAudioVolume.mute for s in self.fake.sessions[:2]))
        with self.assertRaisesRegex(wa.AudioError, "Discord isn't playing any sound"):
            wa.toggle_app_mute("Discord")

    def test_microphone(self):
        self.assertEqual(wa.toggle_microphone_mute(), "Microphone muted")
        self.assertEqual(wa.toggle_microphone_mute(), "Microphone unmuted")

    def test_outputs_switch_and_cycle(self):
        self.assertEqual(wa.outputs(), ["Speakers (Realtek(R) Audio)", "Headphones (WH-1000XM4)"])
        self.assertEqual(wa.switch_output("wh-1000xm4"), "Headphones (WH-1000XM4)")
        self.assertEqual(self.fake.default, "{headset}")
        self.assertEqual(len(self.fake.roles), 3, "calls and games move too")
        self.assertEqual(wa.next_output(), "Speakers (Realtek(R) Audio)")
        with self.assertRaisesRegex(wa.AudioError, "no output device called 'HDMI'"):
            wa.switch_output("HDMI")

    def test_through_the_action_list(self):
        with mock.patch.object(actions, "audio", wa):
            self.assertEqual(actions.run({"feedback": False}, {"action": "app_volume_set",
                                                               "params": {"app": "spotify", "percent": "20"}}),
                             "Spotify 20%")
            with self.assertRaisesRegex(actions.ActionError, "isn't playing any sound"):
                actions.run({}, {"action": "app_mute", "params": {"app": "obs64"}})


class WindowsDesktopTest(unittest.TestCase):
    WINDOWS = [(1, "obs64", "OBS 30.2 - Profile: Untitled"), (2, "firefox", "YouTube"),
               (3, "firefox", "GitHub"), (4, "", "No program")]

    def test_open_windows_one_per_program(self):
        with mock.patch.object(wd, "_windows", return_value=self.WINDOWS):
            self.assertEqual(wd.open_windows(), [("obs64", "OBS 30.2 - Profile: Untitled"), ("firefox", "YouTube")])

    def test_focus_window_by_program_ignoring_case(self):
        with mock.patch.object(wd, "_windows", return_value=self.WINDOWS), \
                mock.patch.object(wd, "_bring_to_front") as front:
            wd.focus_window("OBS64")
            front.assert_called_once_with(1)
            with self.assertRaisesRegex(wd.DesktopError, "no kitty window is open"):
                wd.focus_window("kitty")

    def test_profiles_see_the_program_name(self):
        with mock.patch.object(wd, "_foreground", return_value=7), mock.patch.object(wd, "_program", return_value="obs64"):
            self.assertEqual(wd.active_window_class(), "obs64")

    def test_desktops_next_previous_and_unsupported(self):
        from numpadctl.platform import windows_system
        with mock.patch.object(windows_system, "press_keys") as keys:
            wd.step_workspace(1)
            wd.step_workspace(-1)
        self.assertEqual(keys.call_args_list[0].args[0], [["LEFTCTRL", "LEFTMETA", "RIGHT"]])
        self.assertEqual(keys.call_args_list[1].args[0], [["LEFTCTRL", "LEFTMETA", "LEFT"]])
        for unsupported in (lambda: wd.go_to_workspace(2), lambda: wd.move_window_to_workspace(2),
                            wd.toggle_dnd, wd.toggle_floating):
            with self.assertRaises(wd.DesktopError):
                unsupported()

    def test_region_screenshot_opens_snipping(self):
        with mock.patch.object(os, "startfile", create=True) as startfile:
            self.assertIsNone(wd.screenshot("x.png", region=True))
        startfile.assert_called_once_with("ms-screenclip:")


if __name__ == "__main__":
    unittest.main()
