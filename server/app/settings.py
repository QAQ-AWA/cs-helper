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

# 单人/小队自用场景只需要一个房间；多房间码保留为开关，等真正需要时打开。
ROOM_MODE = (os.getenv("CS_HELPER_ROOM_MODE", "single") or "single").strip().lower()
if ROOM_MODE not in {"single", "multi"}:
    ROOM_MODE = "single"
SINGLE_ROOM_CODE = (os.getenv("CS_HELPER_SINGLE_ROOM_CODE") or "MAIN").strip().upper()[:12] or "MAIN"

# 服务端 AI：任何 OpenAI 兼容端点。没有 key 就跳过 AI 任务，其它功能照常。
AI_BASE_URL = os.getenv("CS_HELPER_AI_BASE_URL", "https://api.deepseek.com/v1")
AI_MODEL = os.getenv("CS_HELPER_AI_MODEL", "deepseek-chat")
AI_KEY = (os.getenv("CS_HELPER_AI_KEY") or "").strip()
AI_TIMEOUT = _int_env("CS_HELPER_AI_TIMEOUT", 60, 5, 300)
AI_MAX_TOKENS = _int_env("CS_HELPER_AI_MAX_TOKENS", 700, 100, 4000)


def job_dir(session_id: str) -> Path:
    """Per-job output directory. Isolation is why the engine runs in a child."""

    path = WORK_DIR / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def maps_ready(map_name: str) -> bool:
    base = MAPS_DIR / map_name
    return (base / "meta.json").is_file() and (base / "radar.png").is_file()
