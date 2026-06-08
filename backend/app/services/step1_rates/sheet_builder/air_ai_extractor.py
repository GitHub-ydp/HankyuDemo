"""Air 运价表生成：从图片/文本元料金 AI 抽取「重量档 × 泡比 × 货类/包装」多维行。"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from tempfile import TemporaryDirectory
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services import ai_client
from app.services.ai_extract_util import chat_json_with_retry

SYSTEM_PROMPT = """你是空运（航空货运）运价识别专家。从图片/文本中精确提取**多维**空运运价并输出 JSON 数组。

## 背景
- 起运港通常是上海 PVG（表头常写「PVG始发」），除非另有说明。
- 空运价按多个维度拆分：
  - 目的港（IATA 三字码，如 LAX/ORD/AMS/NRT）
  - 航司代码（如 CK/CA/KE/KZ；多个用 / 连接，原样保留）
  - 货类（普货 / 快件 / 9610-9710 等）
  - 包装种类（托 / 散 / 托散 / 混装）
  - 货型即泡比（如 1:100、1:167、1:1000）
  - 重量档（表头如 45K / 100KG+ / 500KG+ / 1000KG+），每档一个单价

## 输出格式（只输出 JSON 数组，不要其他文字）
[
  {
    "origin": "PVG",
    "destination": "LAX",
    "carrier": "CK/CA/D0/5Y/KE",
    "cargo_class": "普货",
    "packing": "托",
    "density": "1:167",
    "tier_prices": {"45": 60, "100": 60, "500": 60, "1000": 60},
    "currency": "CNY",
    "effective_from": "2026-05-26",
    "effective_to": "2026-05-29",
    "remark": "全程2-4天"
  }
]

## 规则
1. 每个「目的港 × 航司 × 货类 × 包装 × 泡比」组合输出一行；价随泡比变就分多行，不要合并。
2. tier_prices 的键是重量档数字（去掉 K/KG/+ 单位），值是该档单价；某档为「/」「议价」「单询」或空 → 不写该档。
3. 一行只要任一重量档有数字就保留；全空则不输出该行。
4. 起运港默认 PVG；币种默认人民币 CNY（日本段如 NRT 为 JPY）。
5. 含油/全程时效/操作代码等说明写进 remark。
6. 数字必须精确，不要猜测。"""


def parse_air_image(image_path: str, db: Session | None = None, extra_context: str = "") -> dict[str, Any]:
    """air 图片 → 多维行。db 预留（air 用 IATA 码不解析 Port）。"""
    source_file = os.path.basename(image_path)
    with TemporaryDirectory(prefix="hankyu_air_img_") as tmpdir:
        segments = _split_air_table_image(image_path, tmpdir)
        if len(segments) > 1:
            return _parse_air_image_segments(segments, source_file, extra_context)

        try:
            rates_json = _extract_air_json(image_path, _build_user_text(extra_context), retries=1)
        except Exception as e:  # noqa: BLE001 — 识别失败不抛，交审核台
            return _empty(source_file, "air_image", f"AI 图片识别失败: {e}")
        return _result(rates_json, source_file, "air_image")


def parse_air_text(text: str, db: Session | None = None) -> dict[str, Any]:
    """air 文本/邮件正文 → 多维行。"""
    source_file = "air_text_input"
    user_msg = f"请从以下空运报价文本中提取所有航线的多维运价，只输出 JSON 数组：\n\n{text}"
    try:
        rates_json = chat_json_with_retry(
            lambda: ai_client.chat(
                SYSTEM_PROMPT, user_msg,
                temperature=0.0, max_tokens=settings.ai_max_tokens_extract_json,
            ),
            retries=1,
        )
    except Exception as e:  # noqa: BLE001
        return _empty(source_file, "air_text", f"AI 文本识别失败: {e}")
    return _result(rates_json, source_file, "air_text")


def _build_user_text(extra_context: str = "", segment_label: str | None = None) -> str:
    scope = "这张空运报价图片"
    if segment_label:
        scope = f"这张空运报价图片的{segment_label}局部区块"
    user_text = (
        f"请只从{scope}中提取可见航线的多维运价（重量档×泡比×货类/包装）。"
        "如果顶部有原表日期，所有行沿用该日期。只输出 JSON 数组，不要解释，不要思考过程，不要输出 <think>。 /no_think"
    )
    if extra_context:
        user_text += f"\n\n补充背景：{extra_context}"
    return user_text


def _extract_air_json(image_path: str, user_text: str, *, retries: int) -> list[Any]:
    return chat_json_with_retry(
        lambda: ai_client.chat_with_image(
            SYSTEM_PROMPT, user_text, image_path,
            temperature=0.0, max_tokens=settings.ai_max_tokens_extract_json,
        ),
        retries=retries,
    )


def _parse_air_image_segments(
    segments: list[tuple[str, str]], source_file: str, extra_context: str
) -> dict[str, Any]:
    items_by_index: dict[int, list[Any]] = {}
    warnings: list[str] = []
    max_workers = min(5, len(segments))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _extract_air_json,
                segment_path,
                _build_user_text(extra_context, label),
                retries=0,
            ): (idx, label)
            for idx, (label, segment_path) in enumerate(segments)
        }
        for future in as_completed(futures):
            idx, label = futures[future]
            try:
                items_by_index[idx] = future.result()
            except Exception as e:  # noqa: BLE001
                warnings.append(f"{label}区块识别失败: {e}")

    merged: list[Any] = []
    for idx in sorted(items_by_index):
        merged.extend(items_by_index[idx])

    rows, row_warnings = _build_rows(merged, source_file, "air_image")
    warnings.extend(row_warnings)
    if not rows:
        msg = "；".join(warnings[:3]) if warnings else "没有识别出有效运价行"
        return _empty(source_file, "air_image", f"AI 图片分块识别失败: {msg}")
    return {
        "parsed_rows": rows,
        "total_rows": len(rows),
        "warnings": warnings,
        "source_type": "air_image",
        "file_name": source_file,
    }


def _split_air_table_image(image_path: str, tmpdir: str) -> list[tuple[str, str]]:
    try:
        from PIL import Image
    except Exception:
        return []

    try:
        with Image.open(image_path) as im:
            im.load()
            im = im.convert("RGB")
            w, h = im.size
            if h < 700 or w < 600:
                return []
            starts = _detect_yellow_header_starts(im)
            if len(starts) < 2:
                return []

            bounds = [0] + starts[1:] + [h]
            segments: list[tuple[str, str]] = []
            for idx in range(len(bounds) - 1):
                top, bottom = bounds[idx], bounds[idx + 1]
                if bottom - top < 35:
                    continue
                segment = im.crop((0, top, w, bottom))
                out_path = os.path.join(tmpdir, f"air_segment_{idx + 1}.png")
                segment.save(out_path, optimize=True)
                segments.append((f"第{idx + 1}段", out_path))
            return segments if len(segments) > 1 else []
    except Exception:
        return []


def _detect_yellow_header_starts(im: Any) -> list[int]:
    w, h = im.size
    step = max(1, w // 260)
    threshold = 0.30
    yellow_rows: list[int] = []
    for y in range(h):
        hits = 0
        total = 0
        for x in range(0, w, step):
            r, g, b = im.getpixel((x, y))
            total += 1
            if r >= 210 and 130 <= g <= 220 and b <= 90 and r - g >= 20:
                hits += 1
        if total and hits / total >= threshold:
            yellow_rows.append(y)

    groups: list[tuple[int, int]] = []
    for y in yellow_rows:
        if not groups or y - groups[-1][1] > 3:
            groups.append((y, y))
        else:
            groups[-1] = (groups[-1][0], y)

    starts: list[int] = []
    min_gap = 35
    min_tail = 35
    for start, end in groups:
        if end - start < 5 or h - start < min_tail:
            continue
        if not starts or start - starts[-1] >= min_gap:
            starts.append(start)
    return starts[:8]


def _result(rates_json: Any, source_file: str, source_type: str) -> dict[str, Any]:
    if not isinstance(rates_json, list):
        rates_json = [rates_json]
    rows, warnings = _build_rows(rates_json, source_file, source_type)
    return {
        "parsed_rows": rows,
        "total_rows": len(rows),
        "warnings": warnings,
        "source_type": source_type,
        "file_name": source_file,
    }


def _empty(source_file: str, source_type: str, msg: str) -> dict[str, Any]:
    return {
        "parsed_rows": [], "total_rows": 0, "error": msg,
        "source_type": source_type, "file_name": source_file,
    }


def _build_rows(items: list[Any], source_file: str, source_type: str) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        tiers = _norm_tier_prices(item.get("tier_prices") or {})
        dest = str(item.get("destination") or "").strip()
        if not dest:
            warnings.append(f"第{idx + 1}条无目的港，跳过")
            continue
        if not tiers:
            warnings.append(f"第{idx + 1}条({dest})无有效档位价，跳过")
            continue
        origin = str(item.get("origin") or "PVG").strip() or "PVG"
        currency = str(item.get("currency") or _default_currency(origin)).strip()
        rows.append({
            "origin": origin,
            "destination": dest,
            "carrier": item.get("carrier"),
            "cargo_class": item.get("cargo_class"),
            "packing": item.get("packing"),
            "density": item.get("density"),
            "tier_prices": tiers,
            "currency": currency,
            "effective_week_start": item.get("effective_from"),
            "effective_to": item.get("effective_to"),
            "remark": item.get("remark"),
            "multi_flight_pick": True,
            "source_file": source_file,
            "source_type": source_type,
        })
    return rows, warnings


def _norm_tier_prices(tp: dict[Any, Any]) -> dict[int, float]:
    out: dict[int, float] = {}
    for kg, price in (tp or {}).items():
        try:
            k, v = int(kg), float(price)
        except (TypeError, ValueError):
            continue
        if v > 0:
            out[k] = v
    return out


def _default_currency(origin: str) -> str:
    return "JPY" if (origin or "").upper() in {"NRT", "HND", "KIX", "TYO"} else "CNY"
