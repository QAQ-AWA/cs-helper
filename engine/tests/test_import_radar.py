import json
import sys
from pathlib import Path

import pytest

ENGINE_DIR = Path(__file__).resolve().parents[1]
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

import import_radar  # noqa: E402


def test_parse_overview_handles_quoted_and_bare_fields():
    quoted = '"pos_x" "-3230.0"\n"pos_y" "1713.0"\n"scale" "5.0"\n'
    bare = "pos_x -3230\npos_y 1713\nscale 5\n"

    assert import_radar.parse_overview(quoted) == {"pos_x": -3230.0, "pos_y": 1713.0, "scale": 5.0}
    assert import_radar.parse_overview(bare) == {"pos_x": -3230.0, "pos_y": 1713.0, "scale": 5.0}


def test_parse_overview_rejects_incomplete_or_zero_scale():
    assert import_radar.parse_overview('"pos_x" "1"\n"pos_y" "2"') is None
    assert import_radar.parse_overview('"pos_x" "1"\n"pos_y" "2"\n"scale" "0"') is None


def test_import_map_writes_expected_layout(tmp_path):
    source = tmp_path / "overviews"
    source.mkdir()
    (source / "de_mirage.png").write_bytes(b"\x89PNG\r\n")
    (source / "de_mirage.txt").write_text('"pos_x" "-3230"\n"pos_y" "1713"\n"scale" "5"\n', encoding="utf-8")

    dest = tmp_path / "maps"
    assert import_radar.import_map(str(source), "de_mirage", str(dest)) is True

    written = dest / "de_mirage"
    assert (written / "radar.png").read_bytes().startswith(b"\x89PNG")
    meta = json.loads((written / "meta.json").read_text(encoding="utf-8"))
    assert meta["transform"] == {"pos_x": -3230.0, "pos_y": 1713.0, "scale": 5.0}


def test_import_map_skips_missing_files(tmp_path):
    source = tmp_path / "overviews"
    source.mkdir()
    assert import_radar.import_map(str(source), "de_nuke", str(tmp_path / "maps")) is False
