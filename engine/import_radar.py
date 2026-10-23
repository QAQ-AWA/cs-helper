"""Import radar images + transforms from a local overviews directory.

`setup_maps.py` depends on `awpy get maps`, whose CDN is sometimes unavailable
and whose assets are not in the repo. This is the offline alternative: point it
at a directory holding `<map>.png` + `<map>.txt` (the standard Source overview
pair, e.g. extracted from `pak01.vpk` with Source2Viewer) and it writes the
`data/maps/<map>/{radar.png,meta.json}` layout the engine expects.

    python import_radar.py --from-dir D:/overviews
    python import_radar.py --from-dir D:/overviews --maps de_mirage,de_inferno
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys

import config

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


def import_map(src_dir: str, map_name: str, dest_root: str | None = None) -> bool:
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

    out_dir = os.path.join(dest_root or config.MAPS_DIR, map_name)
    os.makedirs(out_dir, exist_ok=True)
    shutil.copyfile(image, os.path.join(out_dir, "radar.png"))
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as handle:
        json.dump({"transform": transform}, handle, indent=2)
    print(f"imported {map_name} -> {out_dir}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import CS2 radar assets from a local folder")
    parser.add_argument("--from-dir", required=True, help="folder holding <map>.png and <map>.txt")
    parser.add_argument("--maps", default="", help="comma separated map list (default: active duty)")
    parser.add_argument("--dest", default="", help="destination root (default: engine/data/maps)")
    args = parser.parse_args(argv)

    maps = [item.strip() for item in args.maps.split(",") if item.strip()] or DEFAULT_MAPS
    if not os.path.isdir(args.from_dir):
        print(f"source folder not found: {args.from_dir}")
        return 2

    imported = sum(
        1 for name in maps if import_map(args.from_dir, name, args.dest or None)
    )
    print(f"Prepared {imported}/{len(maps)} maps")
    return 0 if imported else 1


if __name__ == "__main__":
    sys.exit(main())
