# Step1 Ocean 测试复核 — Windows py310 执行清单

- **执行人**：张东旭（Windows 本机）
- **发起人**：测试大师（环境阻塞后让 Windows 代跑）
- **目的**：独立复核开发大师对 Ocean 解析器 P0 修复（T-A / T-B / T-C）的交付
- **目标 commit**：`7117cc6` 或更新（`git rev-parse HEAD` 确认）
- **请将下面每一步的完整 stdout/stderr 原样贴回给 Claude**（不要删减，不要截断）

---

## 0. 前置检查

```powershell
# 进入项目目录
cd D:\你的路径\阪急阪神\backend

# 确认 Python 版本 >= 3.10
python --version

# 确认 git HEAD
git rev-parse HEAD
git log --oneline -5

# 确认关键文件在位
dir app\services\step1_rates\adapters\ocean.py
dir tests\services\step1_rates\adapters\test_ocean_pairing.py
dir tests\services\step1_rates\adapters\test_ocean_lcl_freight.py
```

**要求**：Python >= 3.10.0；若低于此版本，停止，向 Claude 报告。

---

## 1. 安装依赖（如未装）

```powershell
pip install -r requirements.txt
# 最小要求：pytest、openpyxl、sqlalchemy、pydantic、fastapi
pip show pytest openpyxl sqlalchemy pydantic fastapi | findstr /C:"Name" /C:"Version"
```

---

## 2. 任务 A — pytest 14 用例裸跑（禁用 shim）

```powershell
cd D:\你的路径\阪急阪神\backend

pytest tests\services\step1_rates\adapters\test_ocean_pairing.py tests\services\step1_rates\adapters\test_ocean_lcl_freight.py -v
```

**验收点**：
- 14 个用例全部 PASS（或明确 FAIL，禁止 error/skipped）
- exit code = 0

把完整输出贴回来。

---

## 3. 任务 B — 真实 Ocean 文件解析 + 5 个验收点

把下面整段脚本存为 `backend\tmp_ocean_verify.py`（或用 `python -c` 粘贴），然后运行：

```python
# tmp_ocean_verify.py
from pathlib import Path
from collections import Counter
from app.services.step1_rates.adapters.ocean import OceanAdapter

# 路径按 Windows 实际调整
XLSX_PATH = Path(r"D:\你的路径\阪急阪神\资料\2026.04.21\RE_ 今後の進め方に関するご提案\【Ocean】 Sea Net Rate_2026_Apr.21 - Apr.30.xlsx")

batch = OceanAdapter().parse(XLSX_PATH)
records = batch.records
warnings = batch.warnings

print("=== 记录总数 ===", len(records))

# sheet 分布
sheet_counter = Counter()
for r in records:
    sheet = (r.extras or {}).get("source_sheet", "<unknown>")
    sheet_counter[(r.record_kind, sheet)] += 1
for k, v in sorted(sheet_counter.items()):
    print("sheet分布:", k, "=", v)

# 验收 1: MBL CC 不在 warnings
mbl_noise = [w for w in warnings if "MBL CC" in w]
print("\n=== 验收1 MBL CC noise count ===", len(mbl_noise))
for w in mbl_noise[:5]:
    print("  ", w)

mbl_records = [r for r in records
               if (r.extras or {}).get("freight_raw", "").strip().upper() == "MBL CC"]
print("=== MBL CC records count ===", len(mbl_records))
for r in mbl_records[:5]:
    print("  status=", (r.extras or {}).get("freight_parse_status"),
          "per_cbm=", r.freight_per_cbm, "per_ton=", r.freight_per_ton,
          "raw=", (r.extras or {}).get("freight_raw"),
          "dest=", r.destination_port_name)

# 验收 2: BUSAN 0/RT
zero_rt_records = [r for r in records
                   if (r.extras or {}).get("freight_raw", "").strip() == "0/RT"]
print("\n=== 0/RT records ===", len(zero_rt_records))
for r in zero_rt_records:
    print("  dest=", r.destination_port_name,
          "per_cbm=", r.freight_per_cbm, "per_ton=", r.freight_per_ton,
          "unit=", (r.extras or {}).get("freight_unit"),
          "raw=", (r.extras or {}).get("freight_raw"))
zero_warnings = [w for w in warnings if "zero freight rate ignored" in w]
print("=== zero freight warnings ===", len(zero_warnings))
for w in zero_warnings:
    print("  ", w)

# 验收 3: BANGKOK / KMTC / 20GP 回归（P0-A）
bkk = [r for r in records
       if (r.destination_port_name or "").upper().startswith("BANGKOK")
       and (r.carrier_name or "").upper() == "KMTC"]
print("\n=== BANGKOK/KMTC records ===", len(bkk))
for r in bkk:
    print("  20gp=", r.container_20gp, "40gp=", r.container_40gp, "40hq=", r.container_40hq,
          "dest=", r.destination_port_name, "carrier=", r.carrier_name)

# 验收 4: JP 首条 destination == 'TOKYO YOKOHAMA'（P0-B）
jp_records = [r for r in records
              if (r.extras or {}).get("source_sheet", "").upper().startswith("JP")]
print("\n=== JP records count ===", len(jp_records))
if jp_records:
    print("  first dest=", repr(jp_records[0].destination_port_name))
    print("  first carrier=", repr(jp_records[0].carrier_name))

# 验收 5: 批次级生效期
print("\n=== batch effective ===")
print("  effective_from=", batch.effective_from)
print("  effective_to=", batch.effective_to)

# 抽样 10 条便于手工对原表
print("\n=== 抽样 10 条 records ===")
sample_idx = [0, 1, 2, 20, 39, 40, 60, 80, 100, len(records)-1]
for idx in sample_idx:
    if 0 <= idx < len(records):
        r = records[idx]
        print(f"#{idx} kind={r.record_kind} sheet={(r.extras or {}).get('source_sheet')} "
              f"origin={r.origin_port_name} dest={r.destination_port_name} carrier={r.carrier_name} "
              f"20gp={r.container_20gp} 40gp={r.container_40gp} 40hq={r.container_40hq} "
              f"per_cbm={r.freight_per_cbm} per_ton={r.freight_per_ton}")

# warnings 全量
print("\n=== warnings 全量 ===", len(warnings))
for w in warnings:
    print("  ", w)
```

运行：
```powershell
cd D:\你的路径\阪急阪神\backend
python tmp_ocean_verify.py
```

**把完整输出贴回**（特别是"记录总数"、"sheet分布"、5 个验收点的结果、抽样 10 条、warnings 全量）。

---

## 4. 任务 C — 抽样对原表（人工核对）

任务 B 抽样的 10 条里，**任选 3 条**（建议 1 条 JP FCL、1 条 Other Ports FCL、1 条 LCL），打开原 Excel：
`资料\2026.04.21\RE_ 今後の進め方に関するご提案\【Ocean】 Sea Net Rate_2026_Apr.21 - Apr.30.xlsx`

对照以下字段逐一核对：

| 字段 | 原 Excel 值 | 解析结果 | 是否一致 |
|---|---|---|---|
| origin_port_name | | | |
| destination_port_name | | | |
| carrier_name | | | |
| container_20gp | | | |
| container_40hq | | | |
| freight_per_cbm (LCL) | | | |
| freight_per_ton (LCL) | | | |

**任何一项不一致**：标红，记下来，连同原 Excel 单元格坐标（sheet + 行号）贴回给 Claude。

---

## 5. 124 → 112 记录数差异调查

开发大师本次跑出 **112 条**，而 4/24 审计报告是 **124 条**（分布 JP=39 / Other=57 / LCL=28）。

请在任务 B 的输出里确认 sheet 分布，对照下表：

| sheet | 4/24 审计 | 本次 | 差值 | 推断 |
|---|---|---|---|---|
| JP N RATE FCL & LCL | 39 | ? | ? | |
| FCL N RATE OF OTHER PORTS | 57 | ? | ? | P0-A 修复把 14 条 orphan 合并回正常配对，应下降 |
| LCL N RATE | 28 | ? | ? | |
| 合计 | 124 | 112 | -12 | |

**如果 Other Ports 差值 ≠ -12**：说明 JP 或 LCL 也有变化，需要单独查。直接把 sheet 分布输出贴回来，Claude 帮你分析。

---

## 6. 回贴格式（直接复制这个模板）

```
## 测试复核原始输出 — 2026-04-21

### 0. 前置检查
- Python 版本：
- git HEAD：
- 依赖：

### 2. 任务 A — pytest 14 用例
<完整 pytest 输出>

### 3. 任务 B — 真实文件
<完整 python tmp_ocean_verify.py 输出>

### 4. 任务 C — 手工对 3 条
| # | sheet | 字段 | 原值 | 解析值 | 一致? |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |

### 备注
<任何异常、报错、环境问题>
```

---

## 附：执行顺序建议

1. 步骤 0 → 1（环境检查 + 装依赖，5 分钟）
2. 步骤 2（pytest 裸跑，1 分钟）→ 结果贴回，Claude 先判 A 是否 PASS
3. 步骤 3（真实文件验证，3 分钟）→ 结果贴回
4. 步骤 4（手工对 3 条，10 分钟）→ 结果贴回
5. 步骤 5（记录数差异，Claude 分析即可，你只需保证步骤 3 的 sheet 分布贴全了）

---

**执行完毕后 Claude 会根据你贴回的原始输出，写测试大师的正式复核报告，落盘到 `docs/Step1_Ocean解析器_测试复核报告_20260421.md`。**
