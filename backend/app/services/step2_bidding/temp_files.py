"""T-B10 临时文件目录管理。

职责：为每个 bid_id 分配独立子目录；lazy sweep 清理 mtime 过期的旧子目录。
不引入 APScheduler / 后台线程（见架构任务单 §4 备注）。
"""
from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path


ROOT = Path(tempfile.gettempdir()) / "hankyu_bidding"


def alloc_bid_dir(bid_id: str) -> Path:
    d = ROOT / bid_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def cleanup_expired(ttl: int = 3600) -> None:
    """删除 mtime 早于 now-ttl 秒的子目录。"""
    if not ROOT.exists():
        return
    cutoff = time.time() - ttl
    for sub in ROOT.iterdir():
        try:
            if sub.is_dir() and sub.stat().st_mtime < cutoff:
                shutil.rmtree(sub, ignore_errors=True)
        except OSError:
            continue
