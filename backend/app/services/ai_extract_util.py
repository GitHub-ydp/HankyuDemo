"""AI 抽取通用工具：把模型返回文本稳健解析成 JSON 数组。

模型常在 JSON 外包 markdown 代码块、前后带说明文字，或因 max_tokens 截断留下尾逗号/
不完整结构。这里集中：去壳 → 抓首个 [..] → 尽力修复尾逗号 → json.loads。air(SP1)/ocean(SP2) 共用。
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


class JsonExtractError(ValueError):
    """文本无法解析为 JSON 数组。"""


def parse_json_array(raw: str | None) -> list[Any]:
    """从模型文本解析 JSON 数组；失败抛 JsonExtractError。单对象自动包成单元素数组。"""
    if not raw:
        raise JsonExtractError("空响应")
    text = raw.strip()
    if text.startswith("```"):
        text = _FENCE.sub("", text).strip()
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    for candidate in (text, _TRAILING_COMMA.sub(r"\1", text)):
        try:
            data = json.loads(candidate)
            return data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            continue
    raise JsonExtractError(f"无法解析为 JSON 数组: {raw[:200]}")


def chat_json_with_retry(call: Callable[[], str], *, retries: int = 1) -> list[Any]:
    """调 call() 取模型文本并解析；仅在「解析失败」时按 retries 重试（provider 异常不在此吞）。"""
    last: Exception | None = None
    for _ in range(retries + 1):
        raw = call()
        try:
            return parse_json_array(raw)
        except JsonExtractError as e:
            last = e
    raise last if last else JsonExtractError("无响应")
