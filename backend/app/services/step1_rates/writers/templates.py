from __future__ import annotations

from pathlib import Path

from app.services import rate_batch_service


def resolve_template_path(batch_id: str) -> Path:
    """从 rate_batch_service 内存 stub 中取出原件模板路径。

    抛：
      KeyError        — batch_id 不存在
      FileNotFoundError — 模板文件已被清理
      ValueError      — draft 无 file_path（异常状态）
    """
    draft = rate_batch_service._draft_batches.get(batch_id)
    if draft is None:
        raise KeyError(f"rate batch {batch_id} not found")
    if not draft.file_path:
        raise ValueError(f"rate batch {batch_id} has no file_path recorded")
    path = Path(draft.file_path)
    if not path.exists():
        raise FileNotFoundError(f"template file missing for batch {batch_id}: {path}")
    return path


def get_draft(batch_id: str):
    """只读 getter，方便 writer 取 legacy_payload / records。"""
    draft = rate_batch_service._draft_batches.get(batch_id)
    if draft is None:
        raise KeyError(f"rate batch {batch_id} not found")
    return draft
