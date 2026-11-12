"""Built-in key icons: every action has one, drawn on its key in the window and on the key map overlay.

An icon is a Material Symbol (icons.py) or a brand logo (assets/brands: OBS Studio and Python, from Simple
Icons, CC0), optionally with a small badge in the bottom-right corner that says what it does to that thing:
OBS + a red dot = start recording, OBS + a square = stop recording, Python + ▶ = run Python. A sticker you
chose yourself always wins over the built-in icon, and Settings → Appearance → "Icons for actions" turns them
off. The brand logos are single-colour masks, so they take the theme's colour like the symbols do.
"""

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

from . import icons

BRANDS = Path(__file__).resolve().parent.parent / "assets" / "brands"
RECORD = "record"   # badge colour roles: "record" = the error / recording red, None = the icon's own colour

# action id -> (base, badge, badge colour role). base: a Material Symbol name or "brand:<file>" (assets/brands).
ICONS = {
    "open_browser": ("public", None, None),
    "open_url": ("open_in_new", None, None),
    "open_path": ("folder_open", None, None),
    "launch_app": ("rocket_launch", None, None),
    "copy_text": ("content_copy", None, None),
    "show_notification": ("notifications", None, None),
    "type_text": ("keyboard", None, None),
    "press_keys": ("keyboard_keys", None, None),
    "screenshot_full": ("screenshot_monitor", None, None),
    "screenshot_region": ("screenshot_region", None, None),
    "hypr_workspace": ("space_dashboard", None, None),
    "hypr_move_to_workspace": ("move_group", None, None),
    "hypr_next_workspace": ("space_dashboard", "arrow_forward", None),
    "hypr_prev_workspace": ("space_dashboard", "arrow_back", None),
    "hypr_close": ("close", None, None),
    "hypr_fullscreen": ("fullscreen", None, None),
    "hypr_float": ("picture_in_picture", None, None),
    "focus_window": ("select_window", None, None),
    "hypr_scratchpad": ("stack", None, None),
    "obs_start_recording": ("brand:obs", "fiber_manual_record", RECORD),
    "obs_stop_recording": ("brand:obs", "stop", None),
    "obs_toggle_recording": ("brand:obs", "radio_button_checked", RECORD),
    "obs_toggle_pause_recording": ("brand:obs", "play_pause", None),
    "obs_pause_recording": ("brand:obs", "pause", None),
    "obs_resume_recording": ("brand:obs", "play_arrow", None),
    "obs_start_streaming": ("brand:obs", "sensors", RECORD),
    "obs_stop_streaming": ("brand:obs", "sensors_off", None),
    "obs_toggle_streaming": ("brand:obs", "sensors", None),
    "obs_start_both": ("brand:obs", "add_circle", RECORD),
    "obs_stop_both": ("brand:obs", "stop_circle", None),
    "obs_switch_scene": ("brand:obs", "swap_horiz", None),
    "obs_toggle_source": ("brand:obs", "visibility", None),
    "obs_toggle_mute": ("brand:obs", "mic_off", None),
    "obs_toggle_filter": ("brand:obs", "filter_alt", None),
    "obs_toggle_virtual_cam": ("brand:obs", "videocam", None),
    "obs_toggle_replay_buffer": ("brand:obs", "replay", None),
    "obs_save_replay": ("brand:obs", "save", None),
    "media_play_pause": ("play_pause", None, None),
    "media_stop": ("stop", None, None),
    "media_next": ("skip_next", None, None),
    "media_previous": ("skip_previous", None, None),
    "voice_toggle": ("record_voice_over", None, None),
    "voice_on": ("record_voice_over", None, None),
    "voice_off": ("voice_over_off", None, None),
    "play_sound": ("music_note", None, None),
    "stop_sounds": ("music_off", None, None),
    "volume_up": ("volume_up", None, None),
    "volume_down": ("volume_down", None, None),
    "volume_set": ("speaker", None, None),
    "volume_mute": ("volume_off", None, None),
    "mic_mute": ("mic_off", None, None),
    "app_volume_up": ("apps", "volume_up", None),
    "app_volume_down": ("apps", "volume_down", None),
    "app_volume_set": ("apps", "speaker", None),
    "app_mute": ("apps", "volume_off", None),
    "output_switch": ("speaker_group", None, None),
    "output_next": ("headphones", None, None),
    "dnd_toggle": ("do_not_disturb_on", None, None),
    "lock_screen": ("lock", None, None),
    "privacy_panic": ("privacy_tip", None, None),
    "privacy_restore": ("settings_backup_restore", None, None),
    "force_quit": ("dangerous", None, None),
    "suspend": ("bedtime", None, None),
    "shutdown": ("power_settings_new", None, None),
    "reboot": ("restart_alt", None, None),
    "mode_toggle": ("toggle_on", None, None),
    "mode_on": ("toggle_on", None, None),
    "mode_off": ("toggle_off", None, None),
    "if_mode": ("alt_route", None, None),   # a path that splits: this or that
    "set_switch": ("layers", None, None),
    "set_next": ("layers", "arrow_forward", None),
    "set_previous": ("layers", "arrow_back", None),
    "macro": ("link", None, None),          # a chain of steps
    "run_python": ("brand:python", "play_arrow", None),
}
_masks = {}


def action_of(slots):
    """The action a key's icon shows: its Press action, else Hold, else Double tap (None if it does nothing)."""
    for slot in ("tap", "hold", "double"):
        binding = (slots or {}).get(slot) or {}
        action = binding.get("action")
        if action and action != "none":
            return action
    return None


def has_icon(action_id):
    return action_id in ICONS


def _brand(name, color, px, ratio):
    """A brand logo mask (black on transparent) painted in `color`."""
    if name not in _masks:
        mask = QImage(str(BRANDS / f"{name}.png"))
        _masks[name] = mask if not mask.isNull() else None
    mask = _masks[name]
    size = round(px * ratio)
    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    if mask is None:
        return image
    painter = QPainter(image)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    margin = size * 0.08   # logos fill their box; symbols have Material's own padding: match it
    painter.drawImage(QRectF(margin, margin, size - 2 * margin, size - 2 * margin), mask)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(image.rect(), QColor(color))
    painter.end()
    return image


def pixmap(action_id, color, px=28, behind=None, record="#e53935", ratio=2.0):
    """The icon for an action (or None): `color` for the icon, `behind` = the colour it sits on (the badge is cut
    out of the icon with a ring of it), `record` = the red of recording / going live."""
    spec = ICONS.get(action_id)
    if spec is None:
        return None
    base, badge, role = spec
    size = round(px * ratio)
    canvas = QPixmap(size, size)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    if base.startswith("brand:"):
        painter.drawImage(QRectF(0, 0, size, size), _brand(base[6:], color, px, ratio))
    else:
        painter.drawPixmap(QRectF(0, 0, size, size), icons.pixmap(base, color, px, ratio=ratio),
                           QRectF(0, 0, size, size))
    if badge:
        radius = size * 0.27
        centre = QPointF(size - radius, size - radius)
        painter.setPen(Qt.NoPen)
        if behind:   # a ring in the key's colour, so the badge reads as separate from the logo under it
            painter.setBrush(QColor(behind))
        else:
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.setBrush(Qt.black)
        painter.drawEllipse(centre, radius + size * 0.05, radius + size * 0.05)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        tint = record if role == RECORD else color
        mark = icons.pixmap(badge, tint, max(8, round(px * 0.62)), ratio=ratio, fill=1.0)
        side = mark.width()
        painter.drawPixmap(QRectF(centre.x() - side / 2, centre.y() - side / 2, side, side), mark,
                           QRectF(0, 0, side, side))
    painter.end()
    canvas.setDevicePixelRatio(ratio)
    return canvas
