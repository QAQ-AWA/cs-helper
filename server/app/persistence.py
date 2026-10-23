"""Durable match history.

One JSON file per match under ``<data>/sessions``; replay blobs live beside it
under ``<data>/artifacts``. Writes are atomic (temp file + ``os.replace``) so a
crash mid-write cannot leave a half-parsed file behind, and an unreadable file
is skipped with a warning instead of taking the process down on boot.

Deliberately a directory of files rather than a database: at LAN scale (one
team, a handful of matches a day) scanning a few hundred small files on boot is
instant, and ``rm -rf .cache/data`` is a complete reset. If the history ever
outgrows that, ``SessionRepository`` is the only surface to swap.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from threading import RLock
from typing import Any

log = logging.getLogger("cs-helper.persistence")

SCHEMA_VERSION = 1
_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def atomic_write(path: Path, payload: bytes) -> None:
    """Write beside the target, then rename: readers never see a partial file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


class SessionRepository:
    """Match history on disk. Thread-safe: job workers persist concurrently."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.sessions_dir = self.root / "sessions"
        self.artifacts_dir = self.root / "artifacts"
        self._lock = RLock()

    # -- paths ---------------------------------------------------------
    @staticmethod
    def file_stem(key: str) -> str:
        """Readable prefix + hash suffix: two odd match ids never collide."""

        safe = _UNSAFE.sub("_", key).strip("._")[:64] or "match"
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
        return f"{safe}-{digest}"

    def path_for(self, key: str) -> Path:
        return self.sessions_dir / f"{self.file_stem(key)}.json"

    # -- write ---------------------------------------------------------
    def save(self, record: dict[str, Any]) -> Path:
        key = f"{record['platform']}:{record['matchId']}"
        path = self.path_for(key)
        payload = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with self._lock:
            atomic_write(path, payload)
        return path

    def delete(self, key: str) -> bool:
        path = self.path_for(key)
        with self._lock:
            try:
                path.unlink()
                return True
            except FileNotFoundError:
                return False

    # -- read ----------------------------------------------------------
    def _read(self, path: Path) -> dict[str, Any] | None:
        try:
            raw = path.read_text(encoding="utf-8")
            record = json.loads(raw)
        except (OSError, ValueError) as exc:
            log.warning("skipping unreadable history file %s: %s", path.name, exc)
            return None
        if not isinstance(record, dict):
            return None
        if record.get("schemaVersion") != SCHEMA_VERSION:
            log.warning("skipping history file with unknown schema: %s", path.name)
            return None
        return record

    def load_all(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Newest first. Corrupt files are skipped, never fatal."""

        if not self.sessions_dir.is_dir():
            return []
        records: list[dict[str, Any]] = []
        with self._lock:
            paths = list(self.sessions_dir.glob("*.json"))
        for path in paths:
            record = self._read(path)
            if record is not None:
                records.append(record)
        records.sort(key=lambda item: float(item.get("updatedAt") or 0), reverse=True)
        return records[:limit] if limit else records

    def count(self) -> int:
        if not self.sessions_dir.is_dir():
            return 0
        return sum(1 for _ in self.sessions_dir.glob("*.json"))

    def referenced_artifacts(self) -> set[str]:
        """Artifact ids still reachable from a stored match."""

        found: set[str] = set()
        for record in self.load_all():
            artifact_id = record.get("artifactId")
            if artifact_id:
                found.add(str(artifact_id))
        return found

    # -- retention -----------------------------------------------------
    def prune(self, max_age_seconds: float, now: float | None = None) -> list[str]:
        """Drop history older than the retention window; returns dropped keys."""

        if not self.sessions_dir.is_dir():
            return []
        cutoff = (now if now is not None else time.time()) - max_age_seconds
        dropped: list[str] = []
        with self._lock:
            paths = list(self.sessions_dir.glob("*.json"))
        for path in paths:
            try:
                modified = path.stat().st_mtime
            except OSError:
                continue
            if modified >= cutoff:
                continue
            record = self._read(path)
            try:
                path.unlink()
            except OSError:
                continue
            if record:
                dropped.append(f"{record.get('platform')}:{record.get('matchId')}")
            else:
                dropped.append(path.stem)
        if dropped:
            log.info("pruned %d expired match(es) from history", len(dropped))
        return dropped

    def disk_bytes(self) -> int:
        total = 0
        for directory in (self.sessions_dir, self.artifacts_dir):
            if not directory.is_dir():
                continue
            for path in directory.iterdir():
                try:
                    if path.is_file():
                        total += path.stat().st_size
                except OSError:
                    continue
        return total
