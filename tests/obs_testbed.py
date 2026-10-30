"""A private OBS for end-to-end tests: its own config folder, its own WebSocket port, and a headless compositor (cage), so
nothing shows on your screen and your real OBS, its scenes and its settings are never touched.

    with ObsTestbed() as bed:
        bed.cfg   # {"host": "localhost", "port": 4466, "password": ""}  (the same shape as the "obs" setting)
        bed.client  # an obsws_python ReqClient for checking what happened

Needs: obs, cage, obsws-python. `ObsTestbed.available()` says whether they are there.
"""

import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path

PORT = 4466  # not 4455: that is OBS's own, where a real OBS may be listening


def _free(port):
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) != 0


class ObsTestbed:
    startup_seconds = 40

    def __init__(self, record_quality="Small", record_format="mkv"):
        """The recording settings go into the profile before OBS starts: it builds its outputs then, and ignores
        later changes. "Small" + "mkv" is a recording that can be paused ("Same as stream" and Hybrid MP4 cannot)."""
        self.record_quality, self.record_format = record_quality, record_format

    @staticmethod
    def available():
        try:
            import obsws_python  # noqa: F401
        except ImportError:
            return "the Python package obsws-python is missing"
        for tool in ("obs", "cage"):
            if not shutil.which(tool):
                return f"{tool} is not installed"
        return ""

    def __enter__(self):
        problem = self.available()
        if problem:
            raise RuntimeError(problem)
        if not _free(PORT):
            raise RuntimeError(f"port {PORT} is already in use")
        self.dir = Path(tempfile.mkdtemp(prefix="numpad-obs-"))
        self.recordings = self.dir / "recordings"
        self.recordings.mkdir()
        self.write_config()
        self.processes = []
        self.client = None
        try:
            self.start()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc):
        if self.client is not None:
            try:
                self.client.base_client.ws.close()
            except Exception:
                pass
        for process in reversed(self.processes):  # only the processes this testbed started
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(process.pid, sig)
                except ProcessLookupError:
                    break
                try:
                    process.wait(timeout=8)
                    break
                except subprocess.TimeoutExpired:
                    continue
        shutil.rmtree(self.dir, ignore_errors=True)

    @property
    def cfg(self):
        return {"host": "localhost", "port": PORT, "password": ""}

    def write_config(self):
        obs = self.dir / "xdg" / "obs-studio"
        (obs / "plugin_config/obs-websocket").mkdir(parents=True)
        (obs / "plugin_config/obs-websocket/config.json").write_text(json.dumps({
            "alerts_enabled": False, "auth_required": False, "first_load": False, "server_enabled": True,
            "server_password": "", "server_port": PORT}))
        for name in ("global.ini", "user.ini"):  # no first-run wizard, no update checks, no exit questions
            (obs / name).write_text("[General]\nFirstRun=true\nConfirmOnExit=false\nEnableAutoUpdates=false\n"
                                    "[BasicWindow]\nSysTrayEnabled=false\n[Basic]\nSceneCollection=Test\n"
                                    "Profile=Test\nProfileDir=Test\n")
        (obs / "basic/profiles/Test").mkdir(parents=True)
        (obs / "basic/profiles/Test/basic.ini").write_text(
            "[General]\nName=Test\n[Output]\nMode=Simple\n"
            f"[SimpleOutput]\nFilePath={self.recordings}\nRecFormat2={self.record_format}\nRecQuality={self.record_quality}\n"
            "RecEncoder=x264\nRecRB=true\nRecRBTime=10\nRecRBSize=512\n"
            "[Video]\nBaseCX=640\nBaseCY=360\nOutputCX=640\nOutputCY=360\nFPSType=0\nFPSCommon=30\n"
            "[Audio]\nSampleRate=48000\nChannelSetup=Stereo\n")

    def start(self):
        env = dict(os.environ)
        env.update({"XDG_CONFIG_HOME": str(self.dir / "xdg"), "WLR_BACKENDS": "headless", "WLR_RENDERER": "pixman",
                    "WLR_LIBINPUT_NO_DEVICES": "1", "QT_QPA_PLATFORM": "wayland", "LIBGL_ALWAYS_SOFTWARE": "1"})
        env.pop("WAYLAND_DISPLAY", None)  # cage makes its own display; never the one your desktop uses
        env.pop("DISPLAY", None)
        log = open(self.dir / "obs.log", "wb")
        self.processes.append(subprocess.Popen(
            ["cage", "--", "obs", "--disable-shutdown-check", "--disable-missing-files-check", "--collection", "Test",
             "--profile", "Test"],
            env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True))
        import obsws_python
        deadline = time.monotonic() + self.startup_seconds
        while time.monotonic() < deadline:
            if self.processes[0].poll() is not None:
                raise RuntimeError("OBS stopped while starting:\n" + self.log_tail())
            if _free(PORT):  # nothing listens yet: don't make the client library complain about it
                time.sleep(0.3)
                continue
            try:
                self.client = obsws_python.ReqClient(host="localhost", port=PORT, password=None, timeout=3)
                self.client.get_version()
                return
            except Exception:
                time.sleep(0.5)
        raise RuntimeError("OBS never answered on its WebSocket:\n" + self.log_tail())

    def log_tail(self, lines=25):
        try:
            return "\n".join((self.dir / "obs.log").read_text(errors="replace").splitlines()[-lines:])
        except OSError:
            return ""

    # ---------------------------------------------------------------- scene helpers
    def build_scenes(self, audio_device=None):
        """Scenes "Test" (a red background + an audio input "Mic") and "Other" (a blue one), a recording folder."""
        c = self.client
        c.set_record_directory(str(self.recordings))
        for name in ("Test", "Other"):
            c.create_scene(name)
        c.create_input("Test", "Background", "color_source_v3", {"color": 4278190335, "width": 640, "height": 360}, True)
        c.create_input("Other", "Blue", "color_source_v3", {"color": 4294901760, "width": 640, "height": 360}, True)
        if audio_device:
            c.create_input("Test", "Mic", "pulse_input_capture", {"device_id": audio_device}, True)
        c.set_current_program_scene("Test")

    def wait_for(self, check, seconds=10, what="the state"):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if check():
                return True
            time.sleep(0.2)
        raise AssertionError(f"timed out waiting for {what}")
