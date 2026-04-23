"""T-B10 一次性下载 token 存储（进程级内存单例）。

限制：单进程、单 worker。多 worker 场景失效 —— v0.2 换 Redis。
uvicorn --reload 热重载会丢 dict（Demo 场景不热重载，可接受）。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class TokenEntry:
    path: Path
    filename: str
    expires_at: datetime


class TokenStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, TokenEntry] = {}

    def put(self, path: Path, filename: str, ttl: int = 3600) -> str:
        token = uuid4().hex
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        with self._lock:
            self._sweep_expired_locked()
            self._entries[token] = TokenEntry(path, filename, expires_at)
        return token

    def consume(self, token: str) -> TokenEntry | None:
        """一次性：拿到 pop；拿不到或过期返回 None。"""
        with self._lock:
            entry = self._entries.pop(token, None)
        if entry is None:
            return None
        if entry.expires_at < datetime.utcnow():
            try:
                entry.path.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        return entry

    def sweep_expired(self) -> None:
        with self._lock:
            self._sweep_expired_locked()

    def clear(self) -> int:
        """清空所有 token（admin 重置用）。返回清空前的条数。"""
        with self._lock:
            count = len(self._entries)
            for entry in list(self._entries.values()):
                try:
                    entry.path.unlink(missing_ok=True)
                except OSError:
                    pass
            self._entries.clear()
        return count

    def _sweep_expired_locked(self) -> None:
        now = datetime.utcnow()
        dead = [t for t, e in self._entries.items() if e.expires_at < now]
        for t in dead:
            e = self._entries.pop(t)
            try:
                e.path.unlink(missing_ok=True)
            except OSError:
                pass


TOKEN_STORE = TokenStore()
