import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import settings as app_settings
from app.main import create_app

REPO = Path(__file__).resolve().parents[2]
REPLAY_CORE = REPO / "server" / "static" / "replay-core.js"


@pytest.fixture()
def client():
    app = create_app(secret="test-secret", demo_runner=None, room_mode="multi")
    with TestClient(app) as test_client:
        yield test_client


def test_shell_is_modular_and_has_a_canvas(client):
    html = client.get("/").text
    assert "/static/mobile.js" in html
    assert 'type="module"' in html
    assert 'id="replay"' in html


def test_static_assets_are_served(client):
    for path in (
        "/static/mobile.css",
        "/static/mobile.js",
        "/static/replay-core.js",
        "/static/icon.svg",
    ):
        response = client.get(path)
        assert response.status_code == 200, path


def test_pwa_entry_points(client):
    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert "manifest" in manifest.headers["content-type"]
    assert manifest.json()["start_url"] == "/"

    worker = client.get("/sw.js")
    assert worker.status_code == 200
    assert "/api/" in worker.text  # live data must bypass the cache


def test_map_assets_are_served_but_sandboxed(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_settings, "MAPS_DIR", tmp_path)
    (tmp_path / "de_mirage").mkdir()
    (tmp_path / "de_mirage" / "radar.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    assert client.get("/maps/de_mirage/radar.png").status_code == 200
    assert client.get("/maps/de_other/radar.png").status_code == 404
    # Only the two known files, and only inside MAPS_DIR.
    assert client.get("/maps/de_mirage/secret.txt").status_code == 404
    assert client.get("/maps/..%2Fapp/radar.png").status_code == 404


NODE_CHECK = """
import { gameToPixel, sampleAt, matchesFilter, roundEnd } from '__URL__';

const fail = (msg) => { console.error(msg); process.exit(1); };
const transform = { pos_x: -100, pos_y: 100, scale: 2 };

const [px, py] = gameToPixel(transform, 0, 100);
if (px !== 50 || py !== 0) fail(`gameToPixel ${px},${py}`);

const path = [[0, 0, 0], [10, 100, 20]];
const mid = sampleAt(path, 5);
if (Math.abs(mid[1] - 50) > 1e-9 || Math.abs(mid[2] - 10) > 1e-9) fail('interpolation');

if (!matchesFilter({ side: 'CT', rtype: 'Buy' }, 'CT', null)) fail('side filter');
if (matchesFilter({ side: 'T', rtype: 'Buy' }, 'CT', null)) fail('side mismatch');
if (!matchesFilter({ side: 'T', rtype: 'Pistol' }, null, 'Pistol')) fail('rtype filter');
if (roundEnd({ path }) !== 10) fail('roundEnd');

console.log('ok');
"""


def test_replay_core_math(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")

    script = tmp_path / "check.mjs"
    script.write_text(NODE_CHECK.replace("__URL__", REPLAY_CORE.as_uri()), encoding="utf-8")
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


RENDER_CHECK = """
import { ReplayPlayer } from '__URL__';

// Minimal DOM stubs: we only assert the renderer draws without throwing.
globalThis.window = { devicePixelRatio: 1 };
globalThis.requestAnimationFrame = () => 1;
globalThis.cancelAnimationFrame = () => {};
globalThis.Image = class {};

const calls = [];
const ctx = new Proxy({}, {
  get: (_target, key) => (...args) => { calls.push(key); return undefined; },
  set: () => true,
});
const canvas = {
  width: 0, height: 0,
  getContext: () => ctx,
  getBoundingClientRect: () => ({ width: 320 }),
};

const rounds = [
  { side: 'CT', rtype: 'Buy', round_id: 1, path: [[0, 0, 0], [10, 500, 500]], grenades: [] },
  { side: 'T', rtype: 'Pistol', round_id: 2, path: [[0, 900, 900]], grenades: [
      { type: 'smoke', throw_t: 1, land_t: 2, arc: [[1, 0, 0]], land: [10, 10], expire_t: 19 },
  ] },
];

const player = new ReplayPlayer(canvas, {
  radar: '/maps/de_mirage/radar.png',
  transform: { pos_x: -100, pos_y: 100, scale: 2 },
  rounds,
  autoplay: false,
});

if (player.duration !== 10) { console.error(`duration ${player.duration}`); process.exit(1); }
if (player.activeRounds !== 2) { console.error('activeRounds'); process.exit(1); }

calls.length = 0;
player.seek(3);
if (!calls.includes('arc')) { console.error('no arc drawn'); process.exit(1); }
if (!calls.includes('lineTo')) { console.error('no path drawn'); process.exit(1); }

player.setFilter('CT', null);
if (player.activeRounds !== 1) { console.error('filter'); process.exit(1); }

calls.length = 0;
player.seek(5);
if (calls.includes('fillText')) { console.error('unexpected placeholder'); process.exit(1); }

player.destroy();
console.log('ok');
"""


def test_replay_core_draws_without_dom(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")

    script = tmp_path / "render.mjs"
    script.write_text(RENDER_CHECK.replace("__URL__", REPLAY_CORE.as_uri()), encoding="utf-8")
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_module_scripts_parse(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")

    for name in ("mobile.js", "replay-core.js"):
        source = REPO / "server" / "static" / name
        copy = tmp_path / (source.stem + ".mjs")
        copy.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        result = subprocess.run([node, "--check", str(copy)], capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, f"{name}: {result.stderr}"
