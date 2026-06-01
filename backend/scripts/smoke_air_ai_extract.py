"""通网机器上对真实 air 微信图跑 AI 抽取，肉眼验证结果。

前置：backend/.env 已切百炼 Qwen-VL 且网络可达 dashscope。
用法（在 backend 目录）：
    ../.venv/bin/python scripts/smoke_air_ai_extract.py
"""
from app.services.step1_rates.sheet_builder import air_ai_extractor

IMAGES = [
    "../资料/2026.05.27/air/Weixin Image_20260527150724_2133_110.png",
    "../资料/2026.05.27/air/Weixin Image_20260527151753_2134_110.png",
]

for img in IMAGES:
    print("=" * 70)
    print("图片:", img)
    out = air_ai_extractor.parse_air_image(img, db=None)
    print("warnings:", out.get("warnings"))
    print(f"抽取 {len(out['parsed_rows'])} 行（前 20）：")
    for r in out["parsed_rows"][:20]:
        print(
            f"  {r['destination']:>5} | {r.get('carrier') or '-':<14} | "
            f"{r.get('cargo_class') or '-'}/{r.get('packing') or '-'}/{r.get('density') or '-'} | "
            f"{r['tier_prices']} {r['currency']}"
        )
