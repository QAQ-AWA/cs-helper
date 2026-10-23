"""Immutable large-object storage for replay data.

Artifacts are content addressed: the id is a hash of the body, so re-parsing the
same player produces the same id and clients can cache forever. The store is
in-process because a single relay serves one team; the interface is what a
disk/S3 backend would need.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import dataclass, field


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


class ArtifactStore:
    def __init__(self, max_items: int = 64, max_bytes: int = 96 * 1024 * 1024) -> None:
        self.max_items = max_items
        self.max_bytes = max_bytes
        self._items: OrderedDict[str, Artifact] = OrderedDict()
        self._total = 0

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

        while self._items and (
            len(self._items) >= self.max_items or self._total + total > self.max_bytes
        ):
            _, evicted = self._items.popitem(last=False)
            self._total -= evicted.size

        artifact = Artifact(
            id=artifact_id,
            body=body,
            media_type=media_type,
            etag=f'"{digest[:32]}"',
            parts=parts,
        )
        self._items[artifact_id] = artifact
        self._total += artifact.size
        return artifact

    def get(self, artifact_id: str) -> Artifact | None:
        artifact = self._items.get(artifact_id)
        if artifact is not None:
            self._items.move_to_end(artifact_id)
        return artifact

    def get_part(self, artifact_id: str, key: str) -> ArtifactPart | None:
        artifact = self.get(artifact_id)
        if artifact is None:
            return None
        body = artifact.parts.get(key)
        if body is None:
            return None
        return ArtifactPart(body=body, etag=f'"{hashlib.sha256(body).hexdigest()[:32]}"')

    @property
    def total_bytes(self) -> int:
        return self._total
