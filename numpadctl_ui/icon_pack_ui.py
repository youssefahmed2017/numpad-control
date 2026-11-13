"""Installing an icon pack (numpadctl/icon_packs.py): read it strictly, then keep its pictures as small PNGs."""

from dataclasses import dataclass, field

from numpadctl import icon_packs

from . import action_icons, sticker_image


@dataclass
class Installed:
    slug: str
    count: int                                   # pictures kept
    failed: list = field(default_factory=list)   # pictures that couldn't be opened, in words
    missing: list = field(default_factory=list)  # actions the pack has no picture for (they keep the built-in icon)


def install(path, confirm=None):
    """Install the pack at `path` (a zip or a folder). `confirm(pack, missing_action_ids)` is asked first and says yes or no.

    Returns an Installed, or None when `confirm` said no. Raises icon_packs.PackError when the pack can't be used."""
    ids = sorted(action_icons.ICONS)
    pack = icon_packs.read_pack(path, ids)
    missing = [action_id for action_id in ids if action_id not in pack.files]
    if confirm is not None and not confirm(pack, missing):
        return None
    pictures, failed = {}, []
    for action_id, (extension, data) in pack.files.items():
        try:
            pictures[action_id] = sticker_image.png_from_bytes(data, extension, icon_packs.SIDE)
        except sticker_image.StickerError as e:
            failed.append(f"{action_id}: {e}")
    if not pictures:
        raise icon_packs.PackError("none of its pictures could be opened")
    slug = icon_packs.slug_for(pack.name or "pack")
    icon_packs.save(slug, {"name": pack.name or slug, "author": pack.author, "license": pack.license}, pictures)
    return Installed(slug, len(pictures), failed, [a for a in missing])
