"""Step2 Nitori 测试的样本守卫。

Nitori 相关测试依赖真实样本目录 `资料/2026.05.26/_nitori_unzip/ニトリ様海上入札/`
（该目录被 git 忽略，由 `ニトリ様海上入札.zip` 解压得到）。在缺样本的机器/CI 上
clone 后跑测试时，自动 skip 这些用例，避免 FileNotFoundError 误判为失败。
customer_a 等不依赖该样本的用例不受影响（按模块名是否含 'nitori' 区分）。
"""
from __future__ import annotations

from pathlib import Path

import pytest


_NITORI_DIR = (
    Path(__file__).resolve().parents[4]
    / "资料"
    / "2026.05.26"
    / "_nitori_unzip"
    / "ニトリ様海上入札"
)


@pytest.fixture(autouse=True)
def _skip_if_no_nitori_fixtures(request):
    module_name = str(getattr(request.module, "__name__", "")).lower()
    if "nitori" in module_name and not _NITORI_DIR.exists():
        pytest.skip(
            "Nitori 真实样本不可用：缺 资料/2026.05.26/_nitori_unzip/ニトリ様海上入札/"
            "（由 ニトリ様海上入札.zip 解压得到）"
        )
