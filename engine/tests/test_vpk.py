import json
import struct
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1]
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

import import_radar  # noqa: E402
from vpk import Vpk  # noqa: E402

DIR_ARCHIVE = 0x7FFF


def build_vpk(path: Path, files: dict[str, bytes]) -> Path:
    """Write a minimal v2 VPK whose file data lives in the _dir archive."""

    groups: dict[str, dict[str, dict[str, tuple[int, int]]]] = {}
    cursor = 0
    for full, data in files.items():
        directory, _, filename = full.rpartition("/")
        name, _, ext = filename.rpartition(".")
        if not name:
            name, ext = ext, " "
        directory = directory or " "
        groups.setdefault(ext, {}).setdefault(directory, {})[name] = (len(data), cursor)
        cursor += len(data)

    tree = bytearray()
    for ext, dirs in groups.items():
        tree += ext.encode("utf-8") + b"\x00"
        for directory, names in dirs.items():
            tree += directory.encode("utf-8") + b"\x00"
            for name, (length, offset) in names.items():
                tree += name.encode("utf-8") + b"\x00"
                tree += struct.pack("<IHHIIH", 0, 0, DIR_ARCHIVE, offset, length, 0xFFFF)
            tree += b"\x00"
        tree += b"\x00"
    tree += b"\x00"

    payload = b"".join(files.values())
    # v2 header is 7 uint32s (28 bytes); file data follows the tree immediately.
    header = struct.pack("<IIIIIII", 0x55AA1234, 2, len(tree), len(payload), 0, 0, 0)
    path.write_bytes(header + bytes(tree) + payload)
    return path


OVERVIEW = '"pos_x"\t\t"-3230"\n"pos_y"\t\t"1713"\n"scale"\t\t"5.00"\n'


def test_vpk_reads_text_from_the_dir_archive(tmp_path):
    vpk_path = build_vpk(
        tmp_path / "pak01_dir.vpk",
        {"resource/overviews/de_mirage.txt": OVERVIEW.encode("utf-8")},
    )
    vpk = Vpk(vpk_path)

    assert vpk.version == 2
    assert vpk.has("resource/overviews/de_mirage.txt")
    assert "pos_x" in vpk.read_text("resource/overviews/de_mirage.txt")


def test_import_from_vpk_uses_archive_transform(tmp_path):
    game = tmp_path / "game" / "csgo"
    game.mkdir(parents=True)
    build_vpk(game / "pak01_dir.vpk", {"resource/overviews/de_mirage.txt": OVERVIEW.encode("utf-8")})

    pngs = tmp_path / "pngs"
    pngs.mkdir()
    (pngs / "de_mirage.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    dest = tmp_path / "maps"
    assert import_radar.import_from_vpk(str(tmp_path / "game"), "de_mirage", str(pngs), str(dest))

    meta = json.loads((dest / "de_mirage" / "meta.json").read_text(encoding="utf-8"))
    assert meta["transform"] == {"pos_x": -3230.0, "pos_y": 1713.0, "scale": 5.0}
    assert (dest / "de_mirage" / "radar.png").read_bytes().startswith(b"\x89PNG")


def test_import_from_vpk_skips_missing_map(tmp_path):
    game = tmp_path / "game" / "csgo"
    game.mkdir(parents=True)
    build_vpk(game / "pak01_dir.vpk", {"resource/overviews/de_mirage.txt": OVERVIEW.encode("utf-8")})
    pngs = tmp_path / "pngs"
    pngs.mkdir()
    (pngs / "de_nuke.png").write_bytes(b"\x89PNG")

    assert not import_radar.import_from_vpk(str(tmp_path / "game"), "de_nuke", str(pngs), str(tmp_path / "m"))
