"""百福东方(EES)空运报价解析测试 —— 自适应多档抽取。

业务规则(福山 2026-05-28 定稿)：
  - 不取单一 100KG 档，而是从每个运价块的**表头行**自适应读出所有「数字+KG」列当档位
    (本文件实际为 45/100/300/500/1000)，每条线存稀疏档位 dict `{45:17,100:14,…}`；
  - 一条线**只要任一档是数字**就保留该行（议价/单询的格留空，不算价）；
  - 卡车转运子表里 `4000KGS/250KGS…` 是单元格**值**不是表头 → 不得当成档位。
断言里的具体档位价均来自对真实文件的逐行勘探(见各行注释)，非解析器自证。
"""
from datetime import date
from pathlib import Path

import pytest

from app.services.step1_rates.sheet_builder import air_ees, air_extractor

_REPO = Path(__file__).resolve().parents[3]
_SAMPLE = _REPO / "资料/2026.05.27/air/EES（2026-5-21）报价.xlsx"

# 真实文件出现过的全部档位(KG)；任何 tier_prices 的键都应落在此集合内，
# 落在集合外即说明把卡车子表的 4000KGS/3000KGS 之类单元格值误读成了档位。
_KNOWN_TIERS = {45, 100, 300, 500, 1000}


def _tier_dicts(rows, dest):
    return [r["tier_prices"] for r in rows if r["destination_port_name"] == dest]


@pytest.mark.skipif(not _SAMPLE.exists(), reason="EES 样本缺失，跳过")
def test_parse_yields_multi_tier_rows():
    """每行带稀疏档位 dict(取代单价×7天)：tier_prices 非空、键为 KG 整数、值为正数；
    旧的 price_dayN 字段已被取代，不再出现。"""
    rows = air_ees.parse_ees(str(_SAMPLE))["parsed_rows"]
    assert rows, "应从 EES 航线表抽到行"
    for r in rows:
        assert r["destination_port_name"]
        assert r["multi_flight_pick"] is True
        assert r["source_file"]
        tiers = r["tier_prices"]
        assert isinstance(tiers, dict) and tiers, "每行应有非空档位 dict"
        for kg, price in tiers.items():
            assert isinstance(kg, int) and kg > 0
            assert isinstance(price, (int, float)) and price > 0
        assert "price_day1" not in r, "单价×7天写法应已被档位 dict 取代"


@pytest.mark.skipif(not _SAMPLE.exists(), reason="EES 样本缺失，跳过")
def test_tiers_read_adaptively_from_block_header():
    """档位从运价块表头自适应抽取(45/100/300/500/1000)，不止 100 一档。"""
    rows = air_ees.parse_ees(str(_SAMPLE))["parsed_rows"]

    # 日本线 KIX：CK/MU 基准行 ≧45KG=17 / ≧100KG=14（500、1000 为「/」留空）
    assert {45: 17, 100: 14} in _tier_dicts(rows, "KIX")
    # 同 KIX 托盘1:200 行只在 ≧500KG=13.5 / ≧1000KG=13 有价 → 证明 100 以外的档也抽到
    assert {500: 13.5, 1000: 13} in _tier_dicts(rows, "KIX")

    # 亚太线 BKK：平散货 100/300/500/1000 全 16；平托盘全 17（45KG 列为「/」留空）
    assert {100: 16, 300: 16, 500: 16, 1000: 16} in _tier_dicts(rows, "BKK")
    assert {100: 17, 300: 17, 500: 17, 1000: 17} in _tier_dicts(rows, "BKK")


@pytest.mark.skipif(not _SAMPLE.exists(), reason="EES 样本缺失，跳过")
def test_carrier_forward_filled_across_merged_subrows():
    """航司(航班列)在 EES 是合并单元格：只在每个航司块首行有值，托盘/散货泡比子行的航司格为空。
    解析须把航司前向填充到块内每一行 → 每条 KIX 行都带 carrier，CK/MU 块的泡比子行 carrier 仍是 CK/MU。
    (邓老师 2026-06-04 测试反馈 #1：航司丢在子行，审核台「航司」「比重」未分两列。)
    真实文件「日本线」KIX 块逐行：CK/MU 基准行(≧45=17,≧100=14)；其下托盘1:200(≧500=13.5,≧1000=13)
    /托盘1:300/散货1:200/散货1:300 的航班格均为合并空格。"""
    rows = air_ees.parse_ees(str(_SAMPLE))["parsed_rows"]
    kix = [r for r in rows if r["destination_port_name"] == "KIX"]
    assert kix, "应抽到 KIX 行"

    # 核心修复：CK/MU 航司格只在基准行有值，托盘/散货泡比子行为合并空格——子行航司须回填为 CK/MU。
    sub_services = {"托盘1:200", "托盘1:300", "散货1:200", "散货1:300"}
    sub_rows = [r for r in kix if r.get("service_desc") in sub_services]
    assert len(sub_rows) == 4, f"应有 4 条 CK/MU 泡比子行, 实得 {len(sub_rows)}"
    assert all(r.get("carrier") == "CK/MU" for r in sub_rows), "泡比子行的航司应前向填充为 CK/MU"

    # 基准行(45/100)也归属 CK/MU
    ckmu_tiers = [r["tier_prices"] for r in kix if r.get("carrier") == "CK/MU"]
    assert {45: 17, 100: 14} in ckmu_tiers, "CK/MU 基准行应归属 CK/MU"
    assert {500: 13.5, 1000: 13} in ckmu_tiers, "托盘1:200 子行的航司应被回填为 CK/MU"


@pytest.mark.skipif(not _SAMPLE.exists(), reason="EES 样本缺失，跳过")
def test_carrier_not_polluted_by_flight_schedule_columns():
    """只有「日本线」那种档位列左侧的航班列(放航司码 CK/MU)才取作 carrier。
    亚太/欧洲/美国线把航班时刻/二程航班/路线放在档位列右侧的「航班」或「航班信息」列——
    那是排班信息不是航司，不得灌进 carrier(否则审核台「船司/航司」列变成一串时刻表)。"""
    rows = air_ees.parse_ees(str(_SAMPLE))["parsed_rows"]
    polluted = [
        r["carrier"]
        for r in rows
        if r.get("carrier")
        and ("二程" in r["carrier"] or "--" in r["carrier"] or "信息" in r["carrier"])
    ]
    assert not polluted, f"carrier 混入了航班时刻/二程排班文本: {polluted[:3]}"


@pytest.mark.skipif(not _SAMPLE.exists(), reason="EES 样本缺失，跳过")
def test_negotiation_rows_kept_when_any_tier_numeric():
    """美国线 NH-DFW 包板：议价行(100/500/1000 全「议价」)只有 45KGS=65 是数字 →
    新模型保留该行(只存 {45:65})；有完整价的行各自存全档。"""
    dfw = _tier_dicts(rows := air_ees.parse_ees(str(_SAMPLE))["parsed_rows"], "DFW")
    assert {45: 65, 100: 49, 500: 49, 1000: 49} in dfw, "平散货整档"
    assert {45: 65, 100: 51, 500: 51, 1000: 51} in dfw, "平托盘整档"
    assert {45: 65, 100: 48, 500: 48, 1000: 48} in dfw, "托盘1:300 整档"
    assert {45: 65} in dfw, "议价行应保留：45KGS=65 是数字，其余档留空"
    assert rows  # silence unused


@pytest.mark.skipif(not _SAMPLE.exists(), reason="EES 样本缺失，跳过")
def test_known_europe_and_central_america_dicts():
    rows = air_ees.parse_ees(str(_SAMPLE))["parsed_rows"]
    # 欧洲线 CZ 块(档位 45/100/300/500)
    assert {45: 42, 100: 40, 300: 40, 500: 40} in _tier_dicts(rows, "AMS")
    assert {45: 33, 100: 31, 300: 31, 500: 31} in _tier_dicts(rows, "FRA")
    assert {45: 33, 100: 33, 300: 33, 500: 33} in _tier_dicts(rows, "LHR")
    # 中南美 MEX/包板 平散货(档位 45/100/500/1000)
    assert {45: 75, 100: 53, 500: 53, 1000: 53} in _tier_dicts(rows, "MEX")


@pytest.mark.skipif(not _SAMPLE.exists(), reason="EES 样本缺失，跳过")
def test_no_spurious_tier_keys_outside_known_set():
    """全表任何档位键都应落在真实档位集合内：
    防止「+100KG泡货」列或卡车子表 4000KGS/3000KGS 单元格被误读成档位。"""
    rows = air_ees.parse_ees(str(_SAMPLE))["parsed_rows"]
    seen = set().union(*(r["tier_prices"].keys() for r in rows))
    assert seen, "应抽到档位"
    assert seen <= _KNOWN_TIERS, f"出现非法档位键(疑似单元格值/泡货列泄漏): {seen - _KNOWN_TIERS}"


def test_tier_kg_recognizes_real_headers_only():
    """档位识别单元函数：真实表头(带比较符/KG/KGS)认作档位；
    『+100KG泡货』『37分泡比例1:100』『4000KGS』(单元格值)一律不是档位。"""
    f = air_ees._tier_kg
    assert f("≧100KG") == 100
    assert f(">1000KGS") == 1000
    assert f("45K") == 45
    assert f("100KGS") == 100
    assert f("+100KG            泡货") is None, "泡货列不是重量档"
    assert f("37分泡比例1:100") is None
    assert f("港口") is None
    assert f("航班信息") is None


def test_filename_effective_date_parses_common_formats():
    """日期表头取文件名里的报价日；多种分隔符都认，认不出则 None。"""
    f = air_ees._filename_effective_date
    assert f("EES（2026-5-21）报价.xlsx") == date(2026, 5, 21)
    assert f("某联运商 2026/05/09 报价.xlsx") == date(2026, 5, 9)
    assert f("rate 2026.5.1.xlsx") == date(2026, 5, 1)
    assert f("没有日期的文件.xlsx") is None


@pytest.mark.skipif(not _SAMPLE.exists(), reason="EES 样本缺失，跳过")
def test_rows_carry_static_fuel_remark():
    """EES 价多为含油 All-in → 每行带静态含油备注，供下游档位表「备注」列展示。
    (唯凯有独立 MYC/MSC 燃油列、价为净价，故该备注只给 EES。)"""
    rows = air_ees.parse_ees(str(_SAMPLE))["parsed_rows"]
    assert rows
    note = air_ees._EES_FUEL_NOTE
    assert "已包含附加费" in note and "不含杂费" in note, "备注应说明含油/不含杂费"
    assert all(r["remarks"] == note for r in rows), "每行应带含油备注"


@pytest.mark.skipif(not _SAMPLE.exists(), reason="EES 样本缺失，跳过")
def test_rows_carry_filename_effective_date():
    """每行带文件名报价日(2026-5-21)，供下游改写日期表头/sheet 名。"""
    rows = air_ees.parse_ees(str(_SAMPLE))["parsed_rows"]
    assert rows
    assert all(r["effective_week_start"] == date(2026, 5, 21) for r in rows)


@pytest.mark.skipif(not _SAMPLE.exists(), reason="EES 样本缺失，跳过")
def test_coverage_reported_in_warnings():
    res = air_ees.parse_ees(str(_SAMPLE))
    joined = " ".join(res["warnings"])
    assert "日本线" in joined and "欧洲线" in joined, "已覆盖的航线表应在 warnings 报告"


@pytest.mark.skipif(not _SAMPLE.exists(), reason="EES 样本缺失，跳过")
def test_extract_air_rates_routes_ees_instead_of_error():
    """air_extractor 第三路应认出 EES，不再回落到「既不是…也未识别到…」的报错。"""
    parsed = air_extractor.extract_air_rates(str(_SAMPLE), None)
    assert parsed.get("parsed_rows"), "EES 应被第三路解析出行"
    assert "error" not in parsed, "认出 EES 后不应带 error"


def test_clean_dest_returns_all_codes():
    from app.services.step1_rates.sheet_builder.air_ees import _clean_dest
    assert _clean_dest("KIX") == ["KIX"]                       # 单港
    assert _clean_dest("NH-DFW") == ["DFW"]                    # 去航司前缀
    assert _clean_dest("CK/MU-LAX") == ["LAX"]                 # 去多段航司前缀
    assert _clean_dest("美国西部：SEA LAX SFO") == ["SEA", "LAX", "SFO"]  # 区域多港
    assert _clean_dest("MEX,MTY,CUN") == ["MEX", "MTY", "CUN"]  # 逗号多港
