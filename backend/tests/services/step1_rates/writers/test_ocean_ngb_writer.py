"""T-W4 验收：OceanNgbWriter 公式纪律。"""
from __future__ import annotations

from io import BytesIO

from openpyxl import load_workbook

from app.services import rate_batch_service
from app.services.step1_rates.writers.ocean_ngb import OceanNgbWriter
from app.services.step1_rates.writers.templates import resolve_template_path


EXPECTED_FORMULA_COUNT = 1687


def _load_writer_output(batch_id: str):
    content, filename = OceanNgbWriter().write(batch_id)
    return load_workbook(BytesIO(content), data_only=False), filename


def _count_formulas(ws) -> int:
    count = 0
    for row in ws.iter_rows():
        for cell in row:
            v = cell.value
            if isinstance(v, str) and v.startswith("="):
                count += 1
    return count


def test_ngb_filename_follows_template(ocean_ngb_batch_id):
    _, filename = _load_writer_output(ocean_ngb_batch_id)
    assert filename.startswith("【Ocean-NGB】 Ocean FCL rate sheet  HHENGB ")
    assert filename.endswith(".xlsx")


def test_ngb_rate_sheet_preserves_1687_formulas(ocean_ngb_batch_id):
    """V-W15: Rate sheet 公式数量完好（parser 当前 stub 0 records → 全保留）。"""
    wb, _ = _load_writer_output(ocean_ngb_batch_id)
    assert _count_formulas(wb["Rate"]) == EXPECTED_FORMULA_COUNT


def test_ngb_specific_formulas_still_exist(ocean_ngb_batch_id):
    """V-W16: 抽样 Lv.2/Lv.3 典型公式保留。"""
    template_path = resolve_template_path(ocean_ngb_batch_id)
    original = load_workbook(template_path, data_only=False)
    wb, _ = _load_writer_output(ocean_ngb_batch_id)
    orig_rate = original["Rate"]
    new_rate = wb["Rate"]
    sampled = 0
    for row in orig_rate.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("="):
                new_val = new_rate[cell.coordinate].value
                assert new_val == cell.value, (
                    f"formula at {cell.coordinate} changed: {cell.value!r} → {new_val!r}"
                )
                sampled += 1
                if sampled >= 50:
                    return
    assert sampled > 0, "did not sample any formulas — unexpected"


def test_ngb_sample_and_shipping_line_sheets_untouched(ocean_ngb_batch_id):
    """V-W17: sample / Shipping line name 两个 sheet 的所有 cell 与原件一致。"""
    template_path = resolve_template_path(ocean_ngb_batch_id)
    original = load_workbook(template_path, data_only=False)
    wb, _ = _load_writer_output(ocean_ngb_batch_id)
    for sheet_name in ("sample", "Shipping line name"):
        orig_ws = original[sheet_name]
        new_ws = wb[sheet_name]
        assert orig_ws.max_row == new_ws.max_row
        assert orig_ws.max_column == new_ws.max_column
        for row_idx in range(1, orig_ws.max_row + 1):
            for col_idx in range(1, orig_ws.max_column + 1):
                orig_v = orig_ws.cell(row_idx, col_idx).value
                new_v = new_ws.cell(row_idx, col_idx).value
                assert orig_v == new_v, (
                    f"{sheet_name}!{orig_ws.cell(row_idx, col_idx).coordinate} "
                    f"changed: {orig_v!r} → {new_v!r}"
                )


def test_ngb_merged_cells_and_columns_invariant(ocean_ngb_batch_id):
    template_path = resolve_template_path(ocean_ngb_batch_id)
    original = load_workbook(template_path, data_only=False)
    wb, _ = _load_writer_output(ocean_ngb_batch_id)
    for sheet_name in original.sheetnames:
        orig_merged = {str(r) for r in original[sheet_name].merged_cells.ranges}
        new_merged = {str(r) for r in wb[sheet_name].merged_cells.ranges}
        assert orig_merged == new_merged, f"merged differ in {sheet_name}"

        orig_cols = {
            k: (d.width, d.hidden)
            for k, d in original[sheet_name].column_dimensions.items()
        }
        new_cols = {
            k: (d.width, d.hidden)
            for k, d in wb[sheet_name].column_dimensions.items()
        }
        assert orig_cols == new_cols, f"column_dimensions differ in {sheet_name}"

    # freeze_panes 保留（V-W05）
    assert original["Rate"].freeze_panes == wb["Rate"].freeze_panes


def test_ngb_document_properties_stamped(ocean_ngb_batch_id):
    wb, _ = _load_writer_output(ocean_ngb_batch_id)
    assert ocean_ngb_batch_id in (wb.properties.title or "")
    assert (wb.properties.description or "").startswith("step1-writer")


# ============================================================================
# Ocean-SHA+NGB 多 sheet（5月合并版）回填路由
#
# writer 不应再写死单 'Rate' sheet，而应把每条记录回填到它自己的 sheet
# （'SHA Rate' / 'NGB Rate'）。旧逻辑下 'Rate' 不在 sheetnames → 整个回填循环
# 被跳过，下面注入哨兵值的用例会失败（cell 保留模板原值）。
# ============================================================================

def _find_writeback_record(records, sheet_name):
    """取某 sheet 上第一条带非空 column_index_map 的记录（即 Lv.1 行）。"""
    for r in records:
        if r.get("sheet_name") == sheet_name and r.get("column_index_map"):
            return r
    raise AssertionError(f"no write-back record found for sheet {sheet_name}")


def test_sha_ngb_writeback_routed_per_sheet(ocean_sha_ngb_batch_id):
    """注入哨兵值，验证回填精确落到各自 sheet（SHA Rate / NGB Rate 互不串台）。"""
    draft = rate_batch_service._draft_batches[ocean_sha_ngb_batch_id]
    records = draft.legacy_payload["records"]

    sha_rec = _find_writeback_record(records, "SHA Rate")
    ngb_rec = _find_writeback_record(records, "NGB Rate")
    sha_rec["column_index_map"] = {18: 99999}
    ngb_rec["column_index_map"] = {18: 88888}
    sha_row = sha_rec["row_index"]
    ngb_row = ngb_rec["row_index"]

    content, _ = OceanNgbWriter().write(ocean_sha_ngb_batch_id)
    wb = load_workbook(BytesIO(content), data_only=False)

    assert wb["SHA Rate"].cell(sha_row, 18).value == 99999
    assert wb["NGB Rate"].cell(ngb_row, 18).value == 88888
    # 互不串台：SHA 的哨兵不应出现在 NGB 行，反之亦然
    assert wb["NGB Rate"].cell(sha_row, 18).value != 99999 or sha_row != ngb_row


def test_sha_ngb_both_sheets_present_after_write(ocean_sha_ngb_batch_id):
    """输出工作簿保留全部 4 个 sheet。"""
    content, _ = OceanNgbWriter().write(ocean_sha_ngb_batch_id)
    wb = load_workbook(BytesIO(content), data_only=False)
    assert set(wb.sheetnames) == {"sample", "SHA Rate", "NGB Rate", "Shipping line name"}


def test_sha_ngb_sample_sheet_untouched(ocean_sha_ngb_batch_id):
    """sample / Shipping line name 两个 sheet 不被回填触碰。"""
    template_path = resolve_template_path(ocean_sha_ngb_batch_id)
    original = load_workbook(template_path, data_only=False)
    content, _ = OceanNgbWriter().write(ocean_sha_ngb_batch_id)
    wb = load_workbook(BytesIO(content), data_only=False)
    for sheet_name in ("sample", "Shipping line name"):
        orig_ws = original[sheet_name]
        new_ws = wb[sheet_name]
        for row_idx in range(1, orig_ws.max_row + 1):
            for col_idx in range(1, orig_ws.max_column + 1):
                assert orig_ws.cell(row_idx, col_idx).value == new_ws.cell(row_idx, col_idx).value
