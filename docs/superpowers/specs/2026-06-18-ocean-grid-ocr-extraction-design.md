# 规整表格 OCR 抽取（海运图像）设计

- 日期：2026-06-18
- 状态：设计已确认，待写实现计划
- 关联：`backend/app/services/step1_rates/sheet_builder/{orchestrator,ocean_ai_extractor,air_ai_extractor}.py`
- 背景调查：见记忆 `step1-ocean-image-truncation-and-ocr-poc`（含 POC 实测数据）

## 1. 背景与问题

海运图像运价抽取目前统一走 VLM（本地 ollama gemma4 / 上线 Qwen-VL），`orchestrator.add_file` 里
sea + 图像 → `ocean_ai_extractor.parse_ocean_image`。客户反馈两类"识别不全"：

- **规整网格截图**（订舱网站导出，列：起运港/目的港/舱位/船期/船司/航线/20'GP/40'GP/40'HQ/45'HQ/40'NOR/历史/有效期/操作）——
  VLM 慢（单张 50~150s）、密图会被 `max_tokens` 截断丢整张（"两张半"，另有截断修复单独处理）、并发会超时。
- **密集自由文本报价**——VLM 会幻觉（把目的港编成 prompt 示例 `ICD AHMEDABAD`）、超时（"一直解析直到失败"）。

POC 实测（RapidOCR 本地）对 3 张规整网格图：**价格召回 20/20、船司 13/13 全对，每张 ~1.0~1.4s，$0**，
对照 gemma4 的 50~150s + 幻觉/截断风险。结论：**规整表格走 OCR 碾压 VLM**。

本设计只解决**规整网格表**这一类。自由文本图仍走 VLM（换 Qwen-VL / 分块另立项），不在本范围。

## 2. 目标与非目标

### 目标
- 海运图像里被判定为"规整网格表"的，走本地 RapidOCR 确定性抽取，替掉 VLM。
- 抽取产物与现有 `parse_ocean_image` **完全同构**，下游 `_normalize_sea`、审核台、入库**零改动**。
- 判定不命中 / OCR 抽 0 行 / 引擎异常时，**自动回落现有 VLM 路**，绝不丢图。
- OCR 抽出的可疑单元格 → `needs_review` 飘黄，交审核台人工核（沿用既有兜底）。

### 非目标（YAGNI）
- 不做自由文本图的 OCR（仍 VLM/Qwen-VL，另立项）。
- 不做 OCR 数字"双跑自一致"校验（后续可加）。
- 不支持当前订舱网站之外的表头布局（动态学列 X 使列增减/换序鲁棒，但表头关键词针对该站；新站后续补关键词）。
- 不动 air 路、不动 sea 的 文本/Excel/PDF 路。

## 3. 架构

### 3.1 新模块
新增 `backend/app/services/step1_rates/sheet_builder/ocean_ocr_extractor.py`，与 `ocean_ai_extractor.py` 并列、职责单一。

对外仅暴露一个函数：

```python
def parse_ocean_grid(image_path: str, db: Session | None = None) -> dict[str, Any]:
    """规整网格海运截图 → 行。返回结构与 ocean_ai_extractor.parse_ocean_image 同构：
    {parsed_rows, total_rows, warnings, source_type, file_name}，失败/不命中带 error 键。
    未检测到表头 → 返回 error 标记（让 orchestrator 回落 VLM），不抛异常。"""
```

返回结构同构是硬约束：`parsed_rows` 每条 dict 的键与 `ocean_ai_extractor._build_rows` 一致
（origin / destination / carrier / vessel_voyage / via / is_direct / container_20gp / container_40gp /
container_40hq / container_45 / currency / valid_from / valid_to / transit_days / surcharges /
remark / needs_review / source_file / source_type）。

### 3.2 内部三步

1. **`_detect_grid_header(ocr_blocks) -> dict[str, tuple[float,float]] | None`**
   - 在 OCR 文本块里找表头签名：同一 Y 带（行）内出现 ≥4 个列头关键词
     （`起运港`/`目的港`/`船司`/`20'GP`/`40'GP`/`40'HQ` 等，关键词做容错匹配，允许 OCR 轻微变形）。
   - 命中 → 返回 `{列名: (x_left, x_right)}`，X 区间由相邻表头单元中点切分得到。
   - 未命中 → `None`。

2. **`_rows_from_ocr(ocr_blocks, header_cols) -> list[dict]`**
   - 取表头 Y 之下的文本块，按 Y 聚成数据行（间隔阈值 = 中位文本高度 × 0.8，沿用 POC 验证过的聚行法）。
   - 每行的 token 按 X 中心落到 `header_cols` 学到的列区间；落不进任何价格列区间的 token（如水印）丢弃。
   - 抽取：目的港（目的港列）、船司（船司列）、20'GP/40'GP/40'HQ/45'HQ、有效期（两行日期 → valid_from/valid_to）。

3. **`_build_rows(...) -> (rows, warnings)`**
   - 归一为行 dict，复用 ocean 字段约定与现成 helper（`_to_price` 等）。
   - origin 默认按表（NINGBO，可从起运港列读到则用读到的）、currency=USD、`surcharges=[]`（网格无自由附加费）。
   - `needs_review`：该行任一关键单元格可疑（价缺失/压不出数字/与水印撞车标记）→ True；与现有 ocean
     `needs_review`（无船司/无有效期）口径并集。

### 3.3 引擎封装
- RapidOCR **进程内单例懒加载**（模块级 `_engine`，首次调用初始化），避免每张图重载模型。
- 喂 OCR 的是**原图全分辨率**（不走 VLM 那条 1280px 压缩；OCR 受益于高分辨率，POC 已验证）。

## 4. 路由改动（`orchestrator.add_file`，仅 sea+图像分支）

现状：
```python
elif ext in _IMAGE_EXTS:
    if session.template_type == "air":
        parsed = air_ai_extractor.parse_air_image(file_path, db)
    else:
        parsed = ocean_ai_extractor.parse_ocean_image(file_path, db)
```

改为（air 分支不变）：
```python
elif ext in _IMAGE_EXTS:
    if session.template_type == "air":
        parsed = air_ai_extractor.parse_air_image(file_path, db)
        source_type = "air_image"
    else:
        parsed = ocean_ocr_extractor.parse_ocean_grid(file_path, db)   # 先试 OCR
        if not (parsed.get("parsed_rows")):                            # 没表头/0行/异常
            parsed = ocean_ai_extractor.parse_ocean_image(file_path, db)  # 回落 VLM
        source_type = "ocean_image"
```

- 判定命中且抽出 ≥1 行 → 用 OCR 结果。
- 未命中表头 / 抽 0 行 / 引擎异常 → 回落 VLM。
- `source_type` 仍记 `ocean_image`（前端/入库无需区分来源；如需区分可后续在产物里加 `extractor: ocr|vlm` 标记，本期不做）。

数据流不变：upload → add_file →（OCR 命中用之 / 否则回落 VLM）→ `_normalize_sea`（不动）→ session.rows →
审核台（needs_review 飘黄）→ 下载 / 入库。

## 5. 噪点与错误处理

- **金额归一**：去 `$ ¥ ，`、修掉 OCR 把 `$` 误读成的前导 `S`（如 `S1000`→`1000`）；`_to_price` 已有 `>0` 校验兜底。
- **水印**：靠"token 不落在任何价格列 X 区间内"被丢弃（POC 见水印 `戴恋璐4432` 碎片，按列定位即可滤）。
- **引擎缺失/异常**：`parse_ocean_grid` 捕获后返回 `error` 标记（不抛），由路由回落 VLM；与现有
  "识别失败不抛、交审核台"风格一致。

## 6. 依赖

`backend/requirements.txt` 增加 `rapidocr_onnxruntime`（纯 ONNX runtime，无 PaddlePaddle/torch，
Apache-2.0，模型随包、离线可跑）。POC 阶段已 `pip install` 验证可用（v1.4.4，附带 opencv-python / shapely / pyclipper）。

## 7. 测试（TDD）

- **`_detect_grid_header`**：命中（合成网格表头）/ 不命中（自由文本块）→ None。
- **行重建 + 列绑定**：合成网格图 → destination/carrier/三箱型价 == 预期；真实 3 张图做"存在才跑"集成测试。
- **路由**：网格图 → 走 OCR（mock VLM，断言未被调用）；自由文本/无表头图 → 回落 VLM（断言 VLM 被调用）。
- **噪点**：合成行含 `S1000` / 水印数字 token → 价格正确、水印被丢。
- **兜底**：`parse_ocean_grid` 返回 0 行 → 路由回落 VLM。
- **测试样本放置**：真实客户截图（带水印 + 真运价）**不入 git**。用**小的合成网格图**做确定性单测；
  真实 3 张图放本地固定目录做集成测试，文件缺失则 `pytest.skip`（与 air 真实样本 `parents[4]` 一个套路）。

## 8. 影响面与回归

- 仅新增 1 文件 + 改 `orchestrator.add_file` 图像 sea 分支 + 加 1 依赖。
- air 路、sea 文本/Excel/PDF 路、`_normalize_sea`、审核台、入库、前端 **零改动**。
- 自由文本图行为不变（回落 VLM）。
- 风险：表头关键词写得太严会漏判（→ 回落 VLM，不丢图，只是慢）；写得太松会误判自由文本图为网格
  （→ 抽 0 行 → 回落 VLM）。两个方向的误判都被"回落 VLM"兜住，最坏退化到现状，不会更差。

## 9. 后续（不在本期）
- 自由文本图：换 Qwen-VL / 分块并行 / 引导用户贴文字，另立项。
- OCR 数字双跑自一致校验（飘黄）。
- 多网站表头布局扩展。
- 产物来源标记 `extractor: ocr|vlm`（便于观测/对数）。
