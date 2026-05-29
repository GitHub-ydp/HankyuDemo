"""对真实 Customer A (Air) 投标包验证想定平均重量解析。样本缺失时优雅 skip。

投标包是单一价：货量写在「想定物量」列。验证 parse_assumed_weight 能从真实单元格抽出重量
(日本→ATL=750kg、上海→ATL=150kg 等)，证明 step2 按货量选档的输入端在真实文件上成立。
"""
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.step2_bidding.weight_tier import parse_assumed_weight

# 本测试在 tests/services/step2_bidding/，比 sheet_builder 深一层 → 仓库根是 parents[4]
_REPO = Path(__file__).resolve().parents[4]
_SAMPLE = (
    _REPO / "资料/2026.04.02/Customer A (Air)/Customer A (Air)/2-①.xlsx"
)


@pytest.mark.skipif(not _SAMPLE.exists(), reason="Customer A (Air) 投标包样本缺失，跳过")
def test_parse_assumed_weight_from_real_bid_package():
    import pandas as pd

    df = pd.read_excel(_SAMPLE, sheet_name="見積りシート", header=None)
    # 「想定物量」是 D 列(0-based 索引 3)
    weights = set()
    for cell in df.iloc[:, 3].tolist():
        w = parse_assumed_weight(None if pd.isna(cell) else str(cell))
        if w is not None:
            weights.add(w)

    assert weights, "应从投标包『想定物量』列抽到至少一个想定平均重量"
    # 真实样本里出现过的两条(日本成田→ATL=750、中国上海→ATL=150)
    assert Decimal("750") in weights
    assert Decimal("150") in weights
    assert all(w > 0 for w in weights)
