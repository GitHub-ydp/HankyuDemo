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
    """从模型文本解析 JSON 数组；失败抛 JsonExtractError。单对象自动包成单元素数组。

    max_tokens 截断时数组缺右 ]（甚至最后一条对象残缺），整体 json.loads 必失败。
    此时退而求其次：逐个抢救数组里已闭合的顶层对象（见 _salvage_objects），
    把完整的那几条照样返回，避免一张密图被截断就整张归零（漏行 bug 根因）。
    """
    if not raw:
        raise JsonExtractError("空响应")
    text = raw.strip()
    if text.startswith("```"):
        text = _FENCE.sub("", text).strip()
    full = text  # 抢救用未裁剪文本：下面 rfind("]") 裁剪可能切进字符串里的 ]，会毁掉残文
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    for candidate in (text, _TRAILING_COMMA.sub(r"\1", text)):
        try:
            data = json.loads(candidate)
            return data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            continue
    salvaged = _salvage_objects(full)
    if salvaged:
        return salvaged
    raise JsonExtractError(f"无法解析为 JSON 数组: {raw[:200]}")


def _salvage_objects(text: str) -> list[Any]:
    """从（可能被 max_tokens 截断的）JSON 数组文本里抢救出所有已闭合的顶层对象。

    从首个 [ 之后开始扫描，按花括号深度切出每个完整的 {...}（深度回到 0 时闭合），
    逐个 json.loads，丢弃解析失败的（即末尾被截断的残缺对象）。
    扫描时跟踪字符串状态与转义，确保字符串值里的 {}[]" 不被误判为结构边界。
    """
    arr_start = text.find("[")
    if arr_start == -1:
        return []
    objs: list[Any] = []
    depth = 0
    obj_start = -1
    in_str = False
    escaped = False
    for i in range(arr_start + 1, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and obj_start != -1:
                    try:
                        objs.append(json.loads(text[obj_start : i + 1]))
                    except json.JSONDecodeError:
                        pass
                    obj_start = -1
        elif ch == "]" and depth == 0:
            break
    return objs


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
