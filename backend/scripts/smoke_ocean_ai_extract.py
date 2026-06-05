"""通网机器上对真实海运微信图跑 AI 抽取，肉眼验证结果（含结构化附加费）。

前置：backend/.env 已切百炼 Qwen-VL 且网络可达 dashscope。
用法（在 backend 目录）：
    ../.venv/bin/python scripts/smoke_ocean_ai_extract.py
"""
from app.services.step1_rates.sheet_builder import ocean_ai_extractor

IMAGES = [
    "../资料/2026.05.27/image001.png",   # SHA→ICD Ahmedabad, 含LSS + EIS 150/300 到付 + 转运稍等
    "../资料/2026.05.27/image002.png",   # →NEW YORK, OOCL, USD 3150/40HQ
]

for img in IMAGES:
    print("=" * 70)
    print("图片:", img)
    out = ocean_ai_extractor.parse_ocean_image(img, db=None)
    print("warnings:", out.get("warnings"))
    print(f"抽取 {len(out['parsed_rows'])} 行：")
    for r in out["parsed_rows"]:
        boxes = {k: r.get(k) for k in ("container_20gp", "container_40gp", "container_40hq", "container_45") if r.get(k)}
        scs = " / ".join(
            f"{s['code']}"
            + ("含" if s["included"] else "")
            + (f" {s['amount_20']}/{s['amount_40']}" if (s["amount_20"] or s["amount_40"]) else "")
            + (f" {s['payment']}" if s["payment"] else "")
            + (f" [{s['note']}]" if s["note"] else "")
            for s in r["surcharges"]
        ) or "-"
        print(
            f"  {r['destination']:>16} | {r.get('carrier') or '-':<8} | via {r.get('via') or '-':<12} | "
            f"{boxes} {r['currency']} | 附加费: {scs} | review={r['needs_review']}"
        )
