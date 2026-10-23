"""Build `data/maps/<map>/{radar.png,meta.json}` without the awpy CDN.

The radar *image* and the *coordinate transform* can come from different places:

* transforms — `resource/overviews/<map>.txt` inside the local CS2 `pak01_dir.vpk`
  (read directly, no Source2Viewer needed), or a plain overviews folder;
* images     — a folder of 1024x1024 `<map>.png` files, or the same overviews
  folder (which pairs `<map>.png` with `<map>.txt`).

    # transforms from the game, images from a folder of PNGs
    python import_radar.py --from-vpk "F:/.../game/csgo" --png-dir ../radar/maps

    # both from a folder holding <map>.png + <map>.txt
    python import_radar.py --from-dir D:/overviews
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys

import config
from vpk import Vpk

DEFAULT_MAPS = [
    "de_mirage",
    "de_inferno",
    "de_nuke",
    "de_overpass",
    "de_ancient",
    "de_anubis",
    "de_dust2",
    "de_train",
]

_FIELD_RE = re.compile(r'"?\b(pos_x|pos_y|scale)\b"?\s+"?(-?\d+(?:\.\d+)?)"?', re.IGNORECASE)


def parse_overview(text: str) -> dict[str, float] | None:
    """Pull pos_x/pos_y/scale out of a Source overview .txt file."""

    values = {key: float(value) for key, value in _FIELD_RE.findall(text)}
    if any(key not in values for key in ("pos_x", "pos_y", "scale")):
        return None
    if values["scale"] == 0:
        return None
    return values


def find_image(src_dir: str, map_name: str) -> str | None:
    for candidate in (f"{map_name}.png", f"{map_name}_radar_psd.png", f"{map_name}_radar.png"):
        path = os.path.join(src_dir, candidate)
        if os.path.isfile(path):
            return path
    return None


def write_map(
    map_name: str,
    transform: dict[str, float],
    image_path: str,
    dest_root: str | None = None,
) -> None:
    out_dir = os.path.join(dest_root or config.MAPS_DIR, map_name)
    os.makedirs(out_dir, exist_ok=True)
    shutil.copyfile(image_path, os.path.join(out_dir, "radar.png"))
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as handle:
        json.dump({"transform": transform}, handle, indent=2)


def import_map(src_dir: str, map_name: str, dest_root: str | None = None) -> bool:
    """Import one map whose PNG and TXT live in the same folder."""

    image = find_image(src_dir, map_name)
    overview = os.path.join(src_dir, f"{map_name}.txt")
    if not image or not os.path.isfile(overview):
        print(f"skip {map_name}: png={bool(image)} txt={os.path.isfile(overview)}")
        return False

    with open(overview, encoding="utf-8", errors="replace") as handle:
        transform = parse_overview(handle.read())
    if transform is None:
        print(f"skip {map_name}: overview has no pos_x/pos_y/scale")
        return False

    write_map(map_name, transform, image, dest_root)
    print(f"imported {map_name} -> {os.path.join(dest_root or config.MAPS_DIR, map_name)}")
    return True


def import_from_vpk(
    game_dir: str,
    map_name: str,
    png_dir: str,
    dest_root: str | None = None,
) -> bool:
    """Transforms from the game archive, image from a PNG folder."""

    image = find_image(png_dir, map_name) if png_dir else None
    if not image:
        print(f"skip {map_name}: no png in {png_dir}")
        return False

    vpk = Vpk(os.path.join(game_dir, "csgo", "pak01_dir.vpk"))
    if not os.path.isfile(vpk.dir_path):
        vpk = Vpk(os.path.join(game_dir, "pak01_dir.vpk"))

    entry = f"resource/overviews/{map_name}.txt"
    if not vpk.has(entry):
        print(f"skip {map_name}: {entry} not in archive")
        return False

    transform = parse_overview(vpk.read_text(entry))
    if transform is None:
        print(f"skip {map_name}: overview has no pos_x/pos_y/scale")
        return False

    write_map(map_name, transform, image, dest_root)
    print(f"imported {map_name} (vpk transform) -> {os.path.join(dest_root or config.MAPS_DIR, map_name)}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build radar assets without the awpy CDN")
    parser.add_argument("--from-dir", default="", help="folder holding <map>.png and <map>.txt")
    parser.add_argument("--from-vpk", default="", help="game dir or csgo dir containing pak01_dir.vpk")
    parser.add_argument("--png-dir", default="", help="folder with 1024x1024 <map>.png (used with --from-vpk)")
    parser.add_argument("--maps", default="", help="comma separated map list (default: active duty)")
    parser.add_argument("--dest", default="", help="destination root (default: engine/data/maps)")
    args = parser.parse_args(argv)

    if not args.from_dir and not args.from_vpk:
        parser.error("pass --from-dir or --from-vpk")

    maps = [item.strip() for item in args.maps.split(",") if item.strip()] or DEFAULT_MAPS
    dest = args.dest or None

    if args.from_vpk:
        if not args.png_dir:
            parser.error("--from-vpk needs --png-dir for the radar images")
        imported = sum(1 for name in maps if import_from_vpk(args.from_vpk, name, args.png_dir, dest))
    else:
        if not os.path.isdir(args.from_dir):
            print(f"source folder not found: {args.from_dir}")
            return 2
        imported = sum(1 for name in maps if import_map(args.from_dir, name, dest))

    print(f"Prepared {imported}/{len(maps)} maps")
    return 0 if imported else 1


if __name__ == "__main__":
    sys.exit(main())
