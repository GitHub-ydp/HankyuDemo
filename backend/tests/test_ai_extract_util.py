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
