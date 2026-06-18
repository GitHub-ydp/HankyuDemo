import pytest
from app.services.ai_extract_util import parse_json_array, chat_json_with_retry, JsonExtractError


def test_parse_plain_array():
    assert parse_json_array('[{"a": 1}]') == [{"a": 1}]

def test_parse_strips_markdown_fence():
    assert parse_json_array("```json\n[{\"a\": 1}]\n```") == [{"a": 1}]

def test_parse_extracts_array_from_prose():
    assert parse_json_array("结果如下：\n[{\"a\": 1}]\n以上。") == [{"a": 1}]

def test_parse_repairs_trailing_comma():
    assert parse_json_array('[{"a": 1},]') == [{"a": 1}]

def test_parse_wraps_single_object():
    assert parse_json_array('{"a": 1}') == [{"a": 1}]

def test_parse_garbage_raises():
    with pytest.raises(JsonExtractError):
        parse_json_array("完全不是 JSON")

def test_retry_succeeds_on_second_attempt():
    calls = iter(["截断的坏响应{", '[{"a": 1}]'])
    assert chat_json_with_retry(lambda: next(calls), retries=1) == [{"a": 1}]

def test_retry_exhausted_raises():
    with pytest.raises(JsonExtractError):
        chat_json_with_retry(lambda: "坏", retries=1)


# --- 截断抢救：max_tokens 截断时不再整张归零，已闭合对象照样抽出 ---

def test_parse_salvages_complete_objects_from_truncated_array():
    # 模拟 max_tokens 截断在第 3 条对象中途（无右花括号、无右方括号）
    truncated = (
        '[\n'
        '  {"destination": "PIRAEUS", "container_20gp": 4000},\n'
        '  {"destination": "HO CHI MINH", "container_20gp": 275},\n'
        '  {"destination": "LAEM CHABANG", "container_20gp": 475,\n'
        '   "currency": "USD",\n'
        '   "valid_from'
    )
    rows = parse_json_array(truncated)
    assert [r["destination"] for r in rows] == ["PIRAEUS", "HO CHI MINH"]


def test_salvage_ignores_braces_and_brackets_inside_strings():
    # 字符串值里含 } 和 ] 不能被当成对象/数组边界，截断后仍要正确抽出完整对象
    truncated = (
        '[\n'
        '  {"destination": "NINGBO", "remark": "含LSS [到付] 备注}"},\n'
        '  {"destination": "BUSAN'
    )
    rows = parse_json_array(truncated)
    assert len(rows) == 1
    assert rows[0]["remark"] == "含LSS [到付] 备注}"


def test_complete_array_still_parses_without_salvage():
    # 正常完整数组不受抢救逻辑影响
    assert parse_json_array('[{"a": 1}, {"b": 2}]') == [{"a": 1}, {"b": 2}]
