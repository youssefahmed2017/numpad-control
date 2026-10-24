"""OBS control over obs-websocket v5 (built into OBS 28+).

Enable it in OBS: Tools -> WebSocket Server Settings -> Enable WebSocket server.
"""

import logging

import obsws_python

logging.getLogger("obsws_python").setLevel(logging.CRITICAL)


class OBSError(Exception):
    pass


def _client(settings):
    try:
        return obsws_python.ReqClient(
            host=settings.get("host", "localhost"),
            port=int(settings.get("port", 4455)),
            password=settings.get("password") or None,
            timeout=3,
        )
    except ConnectionRefusedError:
        raise OBSError("OBS is not running or its WebSocket server is disabled")
    except Exception as e:
        raise OBSError(f"could not connect to OBS: {e}")


def _recording(c):
    return c.get_record_status().output_active


def _streaming(c):
    return c.get_stream_status().output_active


# Every command returns a short message for the on-screen confirmation.

def start_recording(s):
    c = _client(s)
    if _recording(c):
        return "Already recording"
    c.start_record()
    return "Recording"


def stop_recording(s):
    c = _client(s)
    if not _recording(c):
        return "Not recording"
    c.stop_record()
    return "Recording stopped"


def toggle_recording(s):
    active = _client(s).toggle_record().output_active
    return "Recording" if active else "Recording stopped"


def pause_recording(s):
    _client(s).pause_record()
    return "Recording paused"


def resume_recording(s):
    _client(s).resume_record()
    return "Recording resumed"


def start_streaming(s):
    c = _client(s)
    if _streaming(c):
        return "Already live"
    c.start_stream()
    return "Live"


def stop_streaming(s):
    c = _client(s)
    if not _streaming(c):
        return "Not streaming"
    c.stop_stream()
    return "Stream ended"


def toggle_streaming(s):
    active = _client(s).toggle_stream().output_active
    return "Live" if active else "Stream ended"


def start_both(s):
    c = _client(s)
    if not _streaming(c):
        c.start_stream()
    if not _recording(c):
        c.start_record()
    return "Live + recording"


def stop_both(s):
    c = _client(s)
    if _streaming(c):
        c.stop_stream()
    if _recording(c):
        c.stop_record()
    return "Stream + recording stopped"


def switch_scene(s, scene):
    _client(s).set_current_program_scene(scene)
    return f"Scene: {scene}"


def toggle_mute(s, source):
    muted = _client(s).toggle_input_mute(source).input_muted
    return f"{source} {'muted' if muted else 'unmuted'}"


def save_replay(s):
    _client(s).save_replay_buffer()
    return "Replay saved"


def test_connection(s):
    return _client(s).get_version().obs_version


def toggle_virtual_cam(s):
    active = _client(s).toggle_virtual_cam().output_active
    return "Virtual camera on" if active else "Virtual camera off"


def toggle_replay_buffer(s):
    active = _client(s).toggle_replay_buffer().output_active
    return "Replay buffer on" if active else "Replay buffer off"


def toggle_source(s, scene, source):
    c = _client(s)
    item = c.get_scene_item_id(scene, source).scene_item_id
    enabled = c.get_scene_item_enabled(scene, item).scene_item_enabled
    c.set_scene_item_enabled(scene, item, not enabled)
    return f"{source} {'hidden' if enabled else 'shown'}"


def toggle_filter(s, source, filter):
    c = _client(s)
    enabled = c.get_source_filter(source, filter).filter_enabled
    c.set_source_filter_enabled(source, filter, not enabled)
    return f"{filter} {'off' if enabled else 'on'}"


# Name lists for the settings window's pickers. Lists inside responses keep
# OBS's camelCase keys (only top-level fields are converted by obsws-python).

def list_scenes(s):
    scenes = _client(s).get_scene_list().scenes
    return [scene["sceneName"] for scene in reversed(scenes)]  # OBS's top-to-bottom order


def list_scene_sources(s, scene):
    if not scene:
        raise OBSError("enter the scene name first")
    return [item["sourceName"] for item in _client(s).get_scene_item_list(scene).scene_items]


def list_inputs(s):
    return [item["inputName"] for item in _client(s).get_input_list().inputs]


def list_audio_inputs(s):
    c = _client(s)
    names = []
    for item in c.get_input_list().inputs:
        try:
            c.get_input_mute(item["inputName"])  # only works for inputs with audio
        except Exception:
            continue
        names.append(item["inputName"])
    return names


def list_filters(s, source):
    if not source:
        raise OBSError("enter the source name first")
    return [f["filterName"] for f in _client(s).get_source_filter_list(source).filters]
