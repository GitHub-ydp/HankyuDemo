"""港口名规范化：把料表/合约里的写法折叠成『更可能命中字典』的规范名。

只产出规范名，匹配仍交给 _resolve_port 复用。别名/尾缀为代码常量(YAGNI，不上 DB)。
"""
from __future__ import annotations

import re

# 别名：合约/料表写法(词级, 全大写) → 字典规范名
PORT_ALIASES = {
    "PUSAN": "BUSAN",            # 罗马音变体
    "CHITTAGONG": "CHATTOGRAM",  # 旧名/新名
    "KLANG": "KELANG",           # PORT KLANG → PORT KELANG
    "SAINT": "ST",               # SAINT LOUIS → ST LOUIS →(折叠去点)STLOUIS
}
_SUFFIX_WORDS = {"CITY", "PORT"}  # 末尾独立词尾缀，去掉(KAOHSIUNG CITY / KATTUPALLI PORT)


def canonicalize(name: str | None) -> str:
    """大写 → 拆词(非字母数字分隔) → 去末尾 CITY/PORT 词 → 词级套别名 → 拼成 alnum 串。

    例：'PUSAN'→'BUSAN'、'KAOHSIUNG CITY'→'KAOHSIUNG'、'SAINT LOUIS'→'STLOUIS'、
    'PORT KLANG'→'PORTKELANG'、'KATTUPALLI PORT'→'KATTUPALLI'。无内容→''。
    """
    if not name:
        return ""
    words = re.findall(r"[A-Za-z0-9]+", str(name).upper())
    if not words:
        return ""
    if len(words) > 1 and words[-1] in _SUFFIX_WORDS:
        words = words[:-1]
    words = [PORT_ALIASES.get(w, w) for w in words]
    return "".join(words)
