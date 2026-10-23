"""Runtime paths and limits for the relay."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_DIR = Path(os.getenv("CS_HELPER_ENGINE_DIR") or (REPO_ROOT / "engine"))
WORK_DIR = Path(os.getenv("CS_HELPER_WORK_DIR") or (REPO_ROOT / ".cache" / "jobs"))
DEMO_DIR = Path(os.getenv("CS_HELPER_DEMO_DIR") or (ENGINE_DIR / "demos_opponents"))
MAPS_DIR = Path(os.getenv("CS_HELPER_MAPS_DIR") or (ENGINE_DIR / "data" / "maps"))

DEMO_MODE = os.getenv("CS_HELPER_DEMO_MODE", "normal")
if DEMO_MODE not in {"normal", "fast"}:
    DEMO_MODE = "normal"


def _int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


DEMO_MAX_DEMOS = _int_env("CS_HELPER_DEMO_MAX_DEMOS", 6, 1, 10)
ARTIFACT_MAX_ITEMS = _int_env("CS_HELPER_ARTIFACT_MAX_ITEMS", 64, 4, 1024)


def job_dir(session_id: str) -> Path:
    """Per-job output directory. Isolation is why the engine runs in a child."""

    path = WORK_DIR / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def maps_ready(map_name: str) -> bool:
    base = MAPS_DIR / map_name
    return (base / "meta.json").is_file() and (base / "radar.png").is_file()
