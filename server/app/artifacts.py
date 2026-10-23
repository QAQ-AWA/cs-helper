"""Immutable large-object storage for replay data.

Artifacts are content addressed: the id is a hash of the body, so re-parsing the
same player produces the same id and clients can cache forever.

Two tiers. Memory holds a bounded LRU (``max_items`` / ``max_bytes``) because a
phone only ever asks for one player at a time; when ``directory`` is set the
blob is also written through to disk, so a restart does not turn every
``TACTICAL_PATHS_READY`` into a 404. Disk copies outlive the LRU and are only
removed by the retention sweep in :meth:`prune_orphans`.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from .persistence import atomic_write

log = logging.getLogger("cs-helper.artifacts")

_UNSAFE_KEY = re.compile(r"[^A-Za-z0-9_-]+")
BODY_SUFFIX = ".json"


@dataclass(frozen=True)
class Artifact:
    id: str
    body: bytes
    media_type: str
    etag: str
    # Per-player payloads kept beside the index so a phone downloads one player
    # instead of the whole roster.
    parts: dict[str, bytes] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.body) + sum(len(part) for part in self.parts.values())


@dataclass(frozen=True)
class ArtifactPart:
    body: bytes
    etag: str


def _safe_key(key: str) -> str:
    """SteamIDs are digits; anything stranger gets flattened for the filesystem."""

    return _UNSAFE_KEY.sub("_", key).strip("_") or "part"


class ArtifactStore:
    def __init__(
        self,
        max_items: int = 64,
        max_bytes: int = 96 * 1024 * 1024,
        directory: str | Path | None = None,
    ) -> None:
        self.max_items = max_items
        self.max_bytes = max_bytes
        self.directory = Path(directory) if directory else None
        self._items: OrderedDict[str, Artifact] = OrderedDict()
        self._total = 0

    # -- write ---------------------------------------------------------
    def put(
        self,
        body: bytes,
        media_type: str = "application/json",
        parts: dict[str, bytes] | None = None,
    ) -> Artifact:
        if not body:
            raise ValueError("artifact body must not be empty")
        parts = parts or {}
        total = len(body) + sum(len(part) for part in parts.values())
        digest = hashlib.sha256(body).hexdigest()
        artifact_id = digest[:32]
        existing = self._items.get(artifact_id)
        if existing is not None:
            self._items.move_to_end(artifact_id)
            return existing

        if total > self.max_bytes:
            raise ValueError("artifact exceeds the store budget")

        artifact = Artifact(
            id=artifact_id,
            body=body,
            media_type=media_type,
            etag=f'"{digest[:32]}"',
            parts=parts,
        )
        self._write_through(artifact)
        return self._remember(artifact)

    def _write_through(self, artifact: Artifact) -> None:
        if self.directory is None:
            return
        try:
            atomic_write(self.directory / f"{artifact.id}{BODY_SUFFIX}", artifact.body)
            for key, part in artifact.parts.items():
                atomic_write(self.directory / f"{artifact.id}.{_safe_key(key)}{BODY_SUFFIX}", part)
        except OSError as exc:
            # A full disk must not fail the parse job; the in-memory copy still
            # serves this session, only the post-restart replay is lost.
            log.error("could not persist artifact %s: %s", artifact.id, exc)

    def _remember(self, artifact: Artifact) -> Artifact:
        if artifact.id in self._items:
            self._items.move_to_end(artifact.id)
            return artifact
        if artifact.size > self.max_bytes:
            return artifact  # serve it, just never cache it
        while self._items and (
            len(self._items) >= self.max_items or self._total + artifact.size > self.max_bytes
        ):
            _, evicted = self._items.popitem(last=False)
            self._total -= evicted.size
        self._items[artifact.id] = artifact
        self._total += artifact.size
        return artifact

    # -- read ----------------------------------------------------------
    def get(self, artifact_id: str) -> Artifact | None:
        artifact = self._items.get(artifact_id)
        if artifact is not None:
            self._items.move_to_end(artifact_id)
            return artifact
        artifact = self._read_from_disk(artifact_id)
        if artifact is None:
            return None
        return self._remember(artifact)

    def get_part(self, artifact_id: str, key: str) -> ArtifactPart | None:
        artifact = self.get(artifact_id)
        if artifact is None:
            return None
        body = artifact.parts.get(key)
        if body is None:
            return None
        return ArtifactPart(body=body, etag=f'"{hashlib.sha256(body).hexdigest()[:32]}"')

    def has(self, artifact_id: str) -> bool:
        if not artifact_id:
            return False
        if artifact_id in self._items:
            return True
        return self.directory is not None and (self.directory / f"{artifact_id}{BODY_SUFFIX}").is_file()

    def _read_from_disk(self, artifact_id: str) -> Artifact | None:
        if self.directory is None:
            return None
        path = self.directory / f"{artifact_id}{BODY_SUFFIX}"
        try:
            body = path.read_bytes()
        except OSError:
            return None
        if not body:
            return None
        parts: dict[str, bytes] = {}
        prefix = f"{artifact_id}."
        try:
            entries = list(self.directory.glob(f"{artifact_id}.*{BODY_SUFFIX}"))
        except OSError:
            entries = []
        for entry in entries:
            name = entry.name
            if not name.startswith(prefix):
                continue
            key = name[len(prefix) : -len(BODY_SUFFIX)]
            if not key:
                continue
            try:
                parts[key] = entry.read_bytes()
            except OSError:
                continue
        digest = hashlib.sha256(body).hexdigest()
        return Artifact(
            id=artifact_id,
            body=body,
            media_type="application/json",
            etag=f'"{digest[:32]}"',
            parts=parts,
        )

    # -- housekeeping --------------------------------------------------
    def remove(self, artifact_id: str) -> None:
        artifact = self._items.pop(artifact_id, None)
        if artifact is not None:
            self._total -= artifact.size
        if self.directory is None:
            return
        for path in self.directory.glob(f"{artifact_id}.*"):
            try:
                path.unlink()
            except OSError:
                continue
        try:
            (self.directory / f"{artifact_id}{BODY_SUFFIX}").unlink()
        except OSError:
            pass

    def prune_orphans(
        self, keep: set[str], max_age_seconds: float, now: float | None = None
    ) -> int:
        """Delete on-disk blobs no stored match points at and older than the window."""

        if self.directory is None or not self.directory.is_dir():
            return 0
        cutoff = (now if now is not None else time.time()) - max_age_seconds
        removed = 0
        grouped: dict[str, list[Path]] = {}
        for path in self.directory.iterdir():
            if not path.is_file() or path.name.startswith(".tmp-"):
                continue
            artifact_id = path.name.split(".", 1)[0]
            grouped.setdefault(artifact_id, []).append(path)
        for artifact_id, paths in grouped.items():
            if artifact_id in keep:
                continue
            try:
                newest = max(path.stat().st_mtime for path in paths)
            except OSError:
                continue
            if newest >= cutoff:
                continue
            for path in paths:
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    continue
            artifact = self._items.pop(artifact_id, None)
            if artifact is not None:
                self._total -= artifact.size
        if removed:
            log.info("pruned %d orphaned replay blob(s)", removed)
        return removed

    @property
    def total_bytes(self) -> int:
        return self._total

    @property
    def item_count(self) -> int:
        return len(self._items)

    def disk_bytes(self) -> int:
        if self.directory is None or not self.directory.is_dir():
            return 0
        total = 0
        for path in self.directory.iterdir():
            try:
                if path.is_file():
                    total += path.stat().st_size
            except OSError:
                continue
        return total
