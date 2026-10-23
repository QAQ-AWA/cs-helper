"""WebSocket fan-out.

Each connection owns a bounded queue and a sender task, so a slow phone can
never block a producer. Publishing is safe from any thread (job workers), which
is what makes the demo parser's progress callbacks usable later.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from fastapi import WebSocket

log = logging.getLogger("cs-helper.ws")

QUEUE_LIMIT = 256


class Connection:
    def __init__(self, websocket: WebSocket, room_code: str, member_id: str) -> None:
        self.websocket = websocket
        self.room_code = room_code
        self.member_id = member_id
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_LIMIT)
        self._sender: asyncio.Task | None = None
        self._dropped = 0

    def enqueue(self, event: dict[str, Any]) -> None:
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            # Drop the oldest event rather than stalling every other client.
            with contextlib.suppress(asyncio.QueueEmpty):
                self.queue.get_nowait()
            self._dropped += 1
            with contextlib.suppress(asyncio.QueueFull):
                self.queue.put_nowait(event)
            if self._dropped % 50 == 1:
                log.warning("client %s is slow; dropped %d events", self.member_id, self._dropped)

    def start(self) -> None:
        self._sender = asyncio.create_task(self._drain(), name=f"ws-send-{self.member_id}")

    async def _drain(self) -> None:
        try:
            while True:
                event = await self.queue.get()
                await self.websocket.send_json(event)
        except asyncio.CancelledError:
            raise
        except Exception:  # client vanished mid-send
            return

    async def stop(self) -> None:
        if self._sender is not None:
            self._sender.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._sender
            self._sender = None


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[str, set[Connection]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, room_code: str, event: dict[str, Any]) -> None:
        """Thread-safe publish. Preserves order because the caller holds the
        store lock while assigning ``seq`` and calling this method."""
        loop = self._loop
        if loop is None:
            self._publish_nowait(room_code, event)
            return
        try:
            loop.call_soon_threadsafe(self._publish_nowait, room_code, event)
        except RuntimeError:  # loop already closed during shutdown
            pass

    def _publish_nowait(self, room_code: str, event: dict[str, Any]) -> None:
        for connection in list(self._rooms.get(room_code, ())):
            connection.enqueue(event)

    def register(self, connection: Connection) -> None:
        self._rooms.setdefault(connection.room_code, set()).add(connection)

    def unregister(self, connection: Connection) -> None:
        peers = self._rooms.get(connection.room_code)
        if not peers:
            return
        peers.discard(connection)
        if not peers:
            self._rooms.pop(connection.room_code, None)

    def has_member_connection(self, room_code: str, member_id: str) -> bool:
        return any(
            connection.member_id == member_id
            for connection in self._rooms.get(room_code, ())
        )

    def connection_count(self, room_code: str) -> int:
        return len(self._rooms.get(room_code, ()))

    async def shutdown(self) -> None:
        for peers in list(self._rooms.values()):
            for connection in list(peers):
                await connection.stop()
        self._rooms.clear()
