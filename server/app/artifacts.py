"""Immutable large-object storage for replay data.

Artifacts are content addressed: the id is a hash of the body, so re-parsing the
same player produces the same id and clients can cache forever. The store is
in-process because a single relay serves one team; the interface is what a
disk/S3 backend would need.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import dataclass


@dataclass(frozen=True)
class Artifact:
    id: str
    body: bytes
    media_type: str
    etag: str

    @property
    def size(self) -> int:
        return len(self.body)


class ArtifactStore:
    def __init__(self, max_items: int = 64, max_bytes: int = 96 * 1024 * 1024) -> None:
        self.max_items = max_items
        self.max_bytes = max_bytes
        self._items: OrderedDict[str, Artifact] = OrderedDict()
        self._total = 0

    def put(self, body: bytes, media_type: str = "application/json") -> Artifact:
        if not body:
            raise ValueError("artifact body must not be empty")
        digest = hashlib.sha256(body).hexdigest()
        artifact_id = digest[:32]
        existing = self._items.get(artifact_id)
        if existing is not None:
            self._items.move_to_end(artifact_id)
            return existing

        if len(body) > self.max_bytes:
            raise ValueError("artifact exceeds the store budget")

        while self._items and (
            len(self._items) >= self.max_items or self._total + len(body) > self.max_bytes
        ):
            _, evicted = self._items.popitem(last=False)
            self._total -= evicted.size

        artifact = Artifact(
            id=artifact_id,
            body=body,
            media_type=media_type,
            etag=f'"{digest[:32]}"',
        )
        self._items[artifact_id] = artifact
        self._total += artifact.size
        return artifact

    def get(self, artifact_id: str) -> Artifact | None:
        artifact = self._items.get(artifact_id)
        if artifact is not None:
            self._items.move_to_end(artifact_id)
        return artifact

    @property
    def total_bytes(self) -> int:
        return self._total
