"""CS Helper relay server (P1).

Scope: rooms, match upload, profile broadcast, WebSocket fan-out.
Demo parsing and AI orchestration plug into ``RoomHub.report_match`` later.
"""

from __future__ import annotations

import asyncio
import gzip
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import events, settings
from .artifacts import ArtifactStore
from .engine_runner import DemoRunner, SubprocessDemoRunner
from .events import Action
from .hub import RoomHub, RoomNotFound
from .models import MatchReport, RoomCreate, RoomJoin
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
) -> FastAPI:
    store = store or Store(**({"room_ttl": room_ttl} if room_ttl else {}))
    tokens = TokenService(secret)
    ws_manager = ConnectionManager()
    artifact_store = artifacts or ArtifactStore()
    if demo_runner == "auto":
        demo_runner = (
            SubprocessDemoRunner()
            if os.getenv("CS_HELPER_DEMO", "1").strip() not in {"0", "false", "no"}
            else None
        )
    hub = RoomHub(store, tokens, ws_manager, artifact_store, demo_runner, room_mode)  # type: ignore[arg-type]
    limiter = JoinLimiter()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ws_manager.bind_loop(asyncio.get_running_loop())
        if tokens.ephemeral:
            log.warning("CS_HELPER_SERVER_SECRET is unset; tokens die with this process")
        log.info("relay ready")
        try:
            yield
        finally:
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

    # -- artifacts ------------------------------------------------------
    def _artifact_response(request: Request, if_none_match: str | None, body: bytes, etag: str, media_type: str):
        if if_none_match and if_none_match.strip() == etag:
            return Response(status_code=304, headers={"ETag": etag})
        headers = {
            "ETag": etag,
            "Cache-Control": "private, max-age=3600",
            "Vary": "Accept-Encoding",
        }
        if "gzip" in (request.headers.get("accept-encoding") or "").lower():
            body = gzip.compress(body, compresslevel=6)
            headers["Content-Encoding"] = "gzip"
        return Response(content=body, media_type=media_type, headers=headers)

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
        return _artifact_response(request, if_none_match, artifact.body, artifact.etag, artifact.media_type)

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
        return _artifact_response(request, if_none_match, part.body, part.etag, "application/json")

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
        return {"status": "ok", "rooms": len(store._rooms), "protocolVersion": events.PROTOCOL_VERSION}

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


app = create_app(secret=os.getenv("CS_HELPER_SERVER_SECRET", ""))
