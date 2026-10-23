"""Minimal read-only Source 2 VPK access (v1/v2).

Only what we need to pull `resource/overviews/*.txt` out of the local game
install, so radar transforms work without the awpy CDN. The format is a
string tree (extension -> directory -> filename -> entry) followed by the
file data, either inline in the `_dir.vpk` or in numbered volumes.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

MAGIC = 0x55AA1234
DIR_ARCHIVE = 0x7FFF


@dataclass(frozen=True)
class Entry:
    path: str
    archive_index: int
    offset: int
    length: int
    preload: bytes = b""


def _cstr(buf: bytes, pos: int) -> tuple[str, int]:
    end = buf.index(b"\x00", pos)
    return buf[pos:end].decode("utf-8", "replace"), end + 1


class Vpk:
    def __init__(self, dir_path: str | Path) -> None:
        self.dir_path = Path(dir_path)
        self._data = self.dir_path.read_bytes()
        self.version, self._data_start, entries = self._parse()
        self._entries = {entry.path: entry for entry in entries}

    @property
    def names(self) -> list[str]:
        return list(self._entries)

    def has(self, name: str) -> bool:
        return name in self._entries

    def read(self, name: str) -> bytes:
        entry = self._entries[name]
        return entry.preload + self._read_volume(entry)

    def read_text(self, name: str) -> str:
        return self.read(name).decode("utf-8", "replace")

    # -- internals -----------------------------------------------------
    def _read_volume(self, entry: Entry) -> bytes:
        if not entry.length:
            return b""
        if entry.archive_index == DIR_ARCHIVE:
            start = self._data_start + entry.offset
            return self._data[start : start + entry.length]
        prefix = self.dir_path.name.replace("_dir.vpk", "")
        volume = self.dir_path.with_name(f"{prefix}_{entry.archive_index:03d}.vpk")
        with open(volume, "rb") as handle:
            handle.seek(entry.offset)
            return handle.read(entry.length)

    def _parse(self) -> tuple[int, int, list[Entry]]:
        data = self._data
        if len(data) < 12:
            raise ValueError("truncated VPK")
        signature, version = struct.unpack_from("<II", data, 0)
        if signature != MAGIC:
            raise ValueError("not a VPK archive")
        if version == 1:
            header, tree_size = 12, struct.unpack_from("<I", data, 8)[0]
        elif version == 2:
            header, tree_size = 28, struct.unpack_from("<I", data, 8)[0]
        else:
            raise ValueError(f"unsupported VPK version {version}")

        tree = data[header : header + tree_size]
        if len(tree) != tree_size:
            raise ValueError("truncated VPK tree")

        pos = 0
        entries: list[Entry] = []
        while True:
            extension, pos = _cstr(tree, pos)
            if not extension:
                break
            while True:
                directory, pos = _cstr(tree, pos)
                if not directory:
                    break
                while True:
                    name, pos = _cstr(tree, pos)
                    if not name:
                        break
                    crc, preload_size, archive, offset, length = struct.unpack_from("<IHHII", tree, pos)
                    pos += 16
                    terminator = struct.unpack_from("<H", tree, pos)[0]
                    pos += 2
                    if terminator != 0xFFFF:
                        raise ValueError("corrupt VPK directory entry")
                    preload = tree[pos : pos + preload_size]
                    pos += preload_size
                    parts = [part for part in (directory, name) if part and part != " "]
                    path = "/".join(parts)
                    if extension != " ":
                        path = f"{path}.{extension}" if path else extension
                    entries.append(Entry(path, archive, offset, length, preload))
        return version, header + tree_size, entries
