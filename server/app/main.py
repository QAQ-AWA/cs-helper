"""CS Helper relay server (P1).

Scope: rooms, match upload, profile broadcast, WebSocket fan-out.
Demo parsing and AI orchestration plug into ``RoomHub.report_match`` later.
"""

from __future__ import annotations

import asyncio
import contextlib
import gzip
import hashlib
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, Header, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import devtools, events, settings
from .adapters import demo_targets, resolve_side
from .ai import OpenAiClient, config_from_settings
from .artifacts import ArtifactStore
from .engine_runner import DemoRunner, SubprocessDemoRunner
from .events import Action
from .home_enrich import SubprocessHomeClient
from .hub import RoomHub, RoomNotFound
from .identity import IdentityStore
from .models import (
    AnalysisSideRequest,
    DevParseRequest,
    IdentityLearnRequest,
    MatchReport,
    PostMatchReport,
    RoomCreate,
    RoomJoin,
)
from .persistence import SessionRepository
from .security import JoinLimiter, TokenService, lan_addresses
from .store import Store
from .ws import Connection, ConnectionManager

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(levelname)s %(message)s")
log = logging.getLogger("cs-helper")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class ApiError(Exception):
    def __init__(self, message: str, code: int = 1000, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


def ok(data: dict | None = None) -> JSONResponse:
    return JSONResponse({"code": 0, "message": "ok", "data": data or {}})


def create_app(
    *,
    secret: str | None = None,
    store: Store | None = None,
    room_ttl: int | None = None,
    demo_runner: DemoRunner | None | str = "auto",
    artifacts: ArtifactStore | None = None,
    room_mode: str | None = None,
    ai_client: object | None | str = "auto",
    # Off unless asked, exactly like persistence: tests and embedders must not
    # hit 5E just by creating an app.
    home_client: object | None | str = None,
    persist_dir: str | Path | None = None,
    gc_interval: float | None = None,
    history_days: int | None = None,
    session_memory_max: int | None = None,
) -> FastAPI:
    store_kwargs: dict[str, object] = {}
    if room_ttl:
        store_kwargs["room_ttl"] = room_ttl
    if session_memory_max:
        store_kwargs["session_max"] = session_memory_max
    store = store or Store(**store_kwargs)  # type: ignore[arg-type]
    tokens = TokenService(secret)
    ws_manager = ConnectionManager()
    # Durable history is opt-in: `app.main:app` enables it from settings, while
    # tests and embedders get a pure in-memory relay unless they ask for a dir.
    repository = SessionRepository(persist_dir) if persist_dir else None
    if artifacts is None and repository is not None:
        artifact_store = ArtifactStore(directory=repository.artifacts_dir)
    else:
        artifact_store = artifacts or ArtifactStore()
    if demo_runner == "auto":
        demo_runner = (
            SubprocessDemoRunner()
            if os.getenv("CS_HELPER_DEMO", "1").strip() not in {"0", "false", "no"}
            else None
        )
    if ai_client == "auto":
        ai_config = config_from_settings()
        ai_client = OpenAiClient(ai_config) if ai_config else None
    if home_client == "auto":
        home_client = SubprocessHomeClient() if settings.HOME_ENABLED else None
    # The ID library lives beside the history so a restart does not forget who
    # "we" are; without persistence it degrades to in-memory.
    identity = IdentityStore(
        (repository.root / "identity.json") if repository is not None else None
    )
    hub = RoomHub(  # type: ignore[arg-type]
        store,
        tokens,
        ws_manager,
        artifacts=artifact_store,
        demo_runner=demo_runner,
        room_mode=room_mode,
        ai_client=ai_client,
        repository=repository,
        history_days=history_days,
        identity=identity,
        home_client=home_client,
    )
    limiter = JoinLimiter()
    if repository is not None:
        hub.load_history()

    async def _reaper_loop() -> None:
        assert gc_interval
        while True:
            await asyncio.sleep(gc_interval)
            try:
                await asyncio.to_thread(hub.reap)
            except Exception:  # a failed sweep must never stop the next one
                log.exception("housekeeping pass failed")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ws_manager.bind_loop(asyncio.get_running_loop())
        if tokens.ephemeral:
            log.warning("CS_HELPER_SERVER_SECRET is unset; tokens die with this process")
        reaper = asyncio.create_task(_reaper_loop()) if gc_interval else None
        log.info(
            "relay ready (persistence=%s, gc=%ss)",
            repository.root if repository else "off",
            gc_interval or "off",
        )
        try:
            yield
        finally:
            if reaper is not None:
                reaper.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await reaper
            hub.shutdown()
            await ws_manager.shutdown()

    app = FastAPI(title="CS Helper Relay", version="0.1.0", lifespan=lifespan)
    app.state.hub = hub
    app.state.store = store

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _shell_no_cache(request: Request, call_next):
        """页面外壳绝不能被缓存。

        网页端跑在手机上，浏览器（以及旧版 Service Worker）会把 HTML/JS 缓存很久，
        结果就是「改了没生效、只有无痕窗口能看到新数据」。静态外壳一律 no-store，
        数据接口本来就走 /api，不受影响。
        """

        response = await call_next(request)
        path = request.url.path
        if (
            path == "/"
            or path.startswith("/static/")
            or path in {"/sw.js", "/manifest.webmanifest"}
        ):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response

    # -- error envelope -------------------------------------------------
    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError):
        return JSONResponse({"code": exc.code, "message": exc.message}, status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            {"code": exc.status_code * 10, "message": str(exc.detail)},
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(part) for part in first.get("loc", ())[1:]) or "body"
        return JSONResponse(
            {"code": 1005, "message": f"{field}: {first.get('msg', 'invalid')}"},
            status_code=422,
        )

    # -- auth -----------------------------------------------------------
    def require_room(authorization: str | None, room_code: str | None = None):
        token = ""
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        try:
            room, member = hub.authenticate(token)
        except RoomNotFound:
            raise ApiError("房间凭证无效或已过期", code=1001, status=401) from None
        if room_code and room.code != room_code.strip().upper():
            raise ApiError("凭证与房间不匹配", code=1001, status=403)
        return room, member

    # -- room endpoints -------------------------------------------------
    @app.get("/api/v1/config")
    def public_config():
        """Lets the phone page know whether it needs to ask for a room code."""

        return ok(
            {
                "mode": hub.room_mode,
                "roomCode": hub.single_room_code if hub.is_single_room else None,
                "protocolVersion": events.PROTOCOL_VERSION,
                "demoEnabled": demo_runner is not None,
                "aiEnabled": ai_client is not None,
            }
        )

    @app.post("/api/v1/room/create")
    def room_create(payload: RoomCreate):
        room, _member, token, expires_at = hub.create_room(payload.creatorNickname, payload.deviceType)
        return ok(
            {
                "roomCode": room.code,
                "roomId": room.room_id,
                "token": token,
                "expiresAt": expires_at,
                "joinUrl": f"/?room={room.code}",
            }
        )

    @app.post("/api/v1/room/join")
    def room_join(payload: RoomJoin, request: Request):
        client = request.client.host if request.client else "unknown"
        if not limiter.allow(client):
            raise ApiError("尝试过于频繁，请稍后再试", code=1004, status=429)
        if not hub.is_single_room and len(payload.roomCode.strip()) < 4:
            raise ApiError("房间码无效", code=1002, status=400)
        try:
            room, _member, token, expires_at = hub.join_room(
                payload.roomCode, payload.nickname, payload.deviceType
            )
        except RoomNotFound:
            raise ApiError("房间不存在或已过期", code=1002, status=404) from None
        return ok({"roomCode": room.code, "roomId": room.room_id, "token": token, "expiresAt": expires_at})

    @app.get("/api/v1/room/network/info")
    def network_info(request: Request):
        ips = lan_addresses()
        port = request.url.port or 8787
        return ok(
            {
                "ips": ips,
                "port": port,
                "urls": [f"http://{ip}:{port}" for ip in ips],
            }
        )

    @app.get("/api/v1/room/{code}/snapshot")
    def room_snapshot(code: str, authorization: str | None = Header(default=None)):
        room, _member = require_room(authorization, code)
        return ok(hub.room_state(room))

    @app.get("/api/v1/history/sessions")
    def history_sessions(
        limit: int = Query(default=20, ge=1, le=200),
        authorization: str | None = Header(default=None),
    ):
        """Past matches, newest first. Survives restarts; feeds the habits view."""

        require_room(authorization)
        return ok({"sessions": hub.history(limit)})

    # -- artifacts ------------------------------------------------------
    def _artifact_response(
        request: Request,
        if_none_match: str | None,
        body: bytes,
        media_type: str,
    ):
        # 与其它接口保持同一套信封；直接拼接避免解析再序列化。
        wrapped = b'{"code":0,"message":"ok","data":' + body + b"}"
        etag = f'"{hashlib.sha256(wrapped).hexdigest()[:32]}"'
        if if_none_match and if_none_match.strip() == etag:
            return Response(status_code=304, headers={"ETag": etag})
        headers = {
            "ETag": etag,
            "Cache-Control": "private, max-age=3600",
            "Vary": "Accept-Encoding",
        }
        if "gzip" in (request.headers.get("accept-encoding") or "").lower():
            wrapped = gzip.compress(wrapped, compresslevel=6)
            headers["Content-Encoding"] = "gzip"
        return Response(content=wrapped, media_type=media_type, headers=headers)

    @app.get("/api/v1/artifacts/{artifact_id}")
    def get_artifact(
        artifact_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
        if_none_match: str | None = Header(default=None),
    ):
        require_room(authorization)
        artifact = hub.artifacts.get(artifact_id)
        if artifact is None:
            raise ApiError("对象不存在或已过期", code=1007, status=404)
        return _artifact_response(request, if_none_match, artifact.body, artifact.media_type)

    @app.get("/api/v1/artifacts/{artifact_id}/players/{steam_id}")
    def get_artifact_player(
        artifact_id: str,
        steam_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
        if_none_match: str | None = Header(default=None),
    ):
        require_room(authorization)
        part = hub.artifacts.get_part(artifact_id, steam_id)
        if part is None:
            raise ApiError("该玩家的轨迹不存在或已过期", code=1007, status=404)
        return _artifact_response(request, if_none_match, part.body, "application/json")

    # -- match ----------------------------------------------------------
    @app.post("/api/v1/match/report")
    def match_report(
        payload: MatchReport,
        roomCode: str = Query(..., min_length=4, max_length=12),
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ):
        room, _member = require_room(authorization, roomCode)
        if payload.protocolVersion > events.PROTOCOL_VERSION:
            raise ApiError("客户端协议版本高于服务端，请升级服务端", code=1006, status=409)
        session, created = hub.report_match(room, payload.model_dump())
        return ok(
            {
                "sessionId": session.id,
                "matchId": session.match_id,
                "platform": session.platform,
                "created": created,
                "idempotencyKey": idempotency_key,
                "profileState": session.profile_state,
            }
        )

    @app.post("/api/v1/match/post-report")
    def post_match_report(
        payload: PostMatchReport,
        roomCode: str = Query(..., min_length=4, max_length=12),
        authorization: str | None = Header(default=None),
    ):
        room, _member = require_room(authorization, roomCode)
        try:
            hub.report_post_match(room, payload.model_dump())
        except RoomNotFound:
            raise ApiError("房间里还没有对局，无法归档战报", code=1009, status=409) from None
        return ok({"stored": True, "matchCode": payload.matchCode})

    @app.post("/api/v1/room/{code}/analysis-side")
    def set_analysis_side(
        code: str,
        payload: AnalysisSideRequest,
        authorization: str | None = Header(default=None),
    ):
        """Pick our roster so only the opposing five get downloaded."""

        room, _member = require_room(authorization, code)
        try:
            session = hub.set_analysis_side(room, payload.mySide, payload.all)
        except RoomNotFound:
            raise ApiError("房间里还没有对局", code=1009, status=409) from None
        side, source = resolve_side(
            session.report, hub.identity.match(room.code, session.report)
        )
        return ok(
            {
                "mySide": side,
                "mySideSource": source,
                "demoState": session.demo_state,
                "targets": len(demo_targets(session.report, side)),
            }
        )

    @app.post("/api/v1/room/{code}/analysis/rerun")
    def rerun_analysis(
        code: str,
        authorization: str | None = Header(default=None),
    ):
        """Re-run the AI pass without touching the demo job."""

        room, _member = require_room(authorization, code)
        try:
            session = hub.rerun_analysis(room)
        except RoomNotFound:
            raise ApiError("房间里还没有对局", code=1009, status=409) from None
        return ok({"aiState": session.ai_state})

    # -- identity library ----------------------------------------------
    @app.get("/api/v1/identity")
    def identity_summary(
        roomCode: str = Query(..., min_length=1, max_length=12),
        authorization: str | None = Header(default=None),
    ):
        """Which IDs the relay already recognises as ours."""

        room, _member = require_room(authorization, roomCode)
        return ok(hub.identity.summary(room.code))

    @app.post("/api/v1/identity/learn")
    def identity_learn(
        payload: IdentityLearnRequest,
        roomCode: str = Query(..., min_length=1, max_length=12),
        authorization: str | None = Header(default=None),
    ):
        """Remember one roster block; the next report then needs no picker."""

        room, _member = require_room(authorization, roomCode)
        try:
            added = hub.learn_identity(room, payload.side)
        except RoomNotFound:
            raise ApiError("房间里还没有对局", code=1009, status=409) from None
        return ok({"added": added, **hub.identity.summary(room.code)})

    @app.delete("/api/v1/identity")
    def identity_clear(
        roomCode: str = Query(..., min_length=1, max_length=12),
        authorization: str | None = Header(default=None),
    ):
        room, _member = require_room(authorization, roomCode)
        return ok({"removed": hub.identity.clear(room.code)})

    @app.post("/api/v1/dev/client-log")
    def dev_client_log(payload: dict | None = Body(default=None)):
        """开发辅助：客户端把本地日志推上来，落盘成 JSONL。

        没有 devtools 的机器上排查「5E 侦测为什么没触发」全靠它：客户端看到什么、
        丢了什么，都在这里。
        """

        if not settings.DEV_MODE:
            raise ApiError("开发模式未开启", code=1010, status=404)
        lines = (payload or {}).get("lines")
        if not isinstance(lines, list):
            raise ApiError("lines 必须是数组", code=1003, status=422)

        folder = settings.DATA_DIR / "client-log"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{time.strftime('%Y-%m-%d')}.jsonl"
        written = 0
        with target.open("a", encoding="utf-8") as handle:
            for line in lines[:300]:
                if not isinstance(line, dict):
                    continue
                handle.write(json.dumps(line, ensure_ascii=False) + "\n")
                written += 1
        return ok({"written": written, "file": str(target)})

    @app.post("/api/v1/dev/seed-paths")
    def dev_seed_paths(
        roomCode: str = Query(..., min_length=4, max_length=12),
        authorization: str | None = Header(default=None),
    ):
        """开发辅助：给当前对局塞一条合成轨迹，手机/桌面可立刻验证回放。"""

        room, _member = require_room(authorization, roomCode)
        if not settings.DEV_MODE:
            raise ApiError("开发模式未开启", code=1010, status=404)
        try:
            artifact = hub.seed_dev_paths(room)
        except RoomNotFound:
            raise ApiError("房间里还没有对局", code=1009, status=409) from None
        return ok({"artifactId": artifact.id, "synthetic": True})

    @app.get("/api/v1/dev/demos")
    def dev_list_demos():
        """开发辅助：列出 CS_HELPER_LOCAL_DEMO_DIR 里的 .dem。"""

        if not settings.DEV_MODE:
            raise ApiError("开发模式未开启", code=1010, status=404)
        try:
            _root, items = devtools.list_local_demos()
        except FileNotFoundError as exc:
            raise ApiError(str(exc), code=1011, status=404) from None
        return ok({"demos": items})

    @app.post("/api/v1/dev/parse-local")
    def dev_parse_local(
        payload: DevParseRequest,
        roomCode: str = Query(..., min_length=4, max_length=12),
        authorization: str | None = Header(default=None),
    ):
        """开发辅助：用本机 .dem 跑真实解析，跳过 5E 检索与下载。"""

        room, _member = require_room(authorization, roomCode)
        if not settings.DEV_MODE:
            raise ApiError("开发模式未开启", code=1010, status=404)
        try:
            artifact, bundle = hub.parse_dev_demo(room, payload.name)
        except FileNotFoundError:
            raise ApiError(f"找不到 demo：{payload.name}", code=1011, status=404) from None
        except RoomNotFound:
            raise ApiError("房间里还没有对局", code=1009, status=409) from None
        except (RuntimeError, ValueError) as exc:
            raise ApiError(f"解析失败：{exc}", code=2001, status=500) from None
        return ok(
            {
                "artifactId": artifact.id,
                "map": bundle.get("map"),
                "players": len(bundle.get("players") or []),
                "failed": bundle.get("failed") or [],
            }
        )

    # -- websocket ------------------------------------------------------
    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket, token: str = "", lastSeq: int = 0):
        try:
            room, member = hub.authenticate(token)
        except RoomNotFound:
            await websocket.close(code=4401)
            return

        await websocket.accept()
        connection = Connection(websocket, room.code, member.id)

        # Replay first, snapshot last: the snapshot is the authoritative tail
        # and carries the sequence the client should resume from.
        if lastSeq > 0 and store.can_replay(room, lastSeq):
            for event in store.events_since(room, lastSeq):
                connection.enqueue(event)
        connection.enqueue(
            events.envelope(Action.ROOM_STATE_SYNC, hub.room_state(room), room.seq, now=time.time())
        )
        connection.start()
        ws_manager.register(connection)
        hub.on_connect(room, member)

        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:
            log.debug("websocket closed unexpectedly", exc_info=True)
        finally:
            ws_manager.unregister(connection)
            await connection.stop()
            hub.on_disconnect(room.code, member)

    # -- misc -----------------------------------------------------------
    @app.get("/healthz")
    def healthz():
        # `rooms` / `protocolVersion` stay for existing probes; the rest is the
        # P5 ops surface (residency, disk, last sweep).
        return {"status": "ok", "protocolVersion": events.PROTOCOL_VERSION, **hub.metrics()}

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/")
        def index():
            return FileResponse(STATIC_DIR / "mobile.html")

        @app.get("/manifest.webmanifest")
        def manifest():
            return FileResponse(
                STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json"
            )

        @app.get("/sw.js")
        def service_worker():
            # Must be served from the root scope to control "/".
            return FileResponse(STATIC_DIR / "sw.js", media_type="text/javascript")

    _MAP_NAME_RE = re.compile(r"^[a-z0-9_]{1,32}$")
    _MAP_FILES = frozenset({"radar.png", "meta.json"})

    @app.get("/maps/{map_name}/{filename}")
    def map_asset(map_name: str, filename: str):
        if not _MAP_NAME_RE.match(map_name) or filename not in _MAP_FILES:
            raise ApiError("地图资源不存在", code=1008, status=404)
        path = (settings.MAPS_DIR / map_name / filename).resolve()
        base = settings.MAPS_DIR.resolve()
        if base not in path.parents or not path.is_file():
            raise ApiError("地图资源不存在", code=1008, status=404)
        return FileResponse(path)

    return app


app = create_app(
    secret=os.getenv("CS_HELPER_SERVER_SECRET", ""),
    room_ttl=settings.ROOM_TTL,
    persist_dir=settings.DATA_DIR,
    gc_interval=settings.GC_INTERVAL or None,
    history_days=settings.HISTORY_DAYS,
    session_memory_max=settings.SESSION_MEMORY_MAX,
    home_client="auto",
)
