"""模板注册表测试：Air/Sea 空白模板的列映射 + 数据起始行配置正确。"""
import pytest

from app.services.step1_rates.sheet_builder.template_registry import (
    TemplateConfig,
    get_template_config,
)


def test_air_config_basic():
    cfg = get_template_config("air")
    assert isinstance(cfg, TemplateConfig)
    assert cfg.template_type == "air"
    assert cfg.template_path.exists(), "air 空白模板文件应存在"
    sheet = cfg.sheets[0]
    assert sheet.sheet_name == "May 25 to May 31"
    assert sheet.header_row == 1
    assert sheet.data_start_row == 2
    # 列语义 → 1-based 列号（A 起运港插入后整体右移一列）
    assert sheet.columns["origin"] == 1
    assert sheet.columns["destination"] == 2
    assert sheet.columns["service"] == 3
    assert sheet.columns["day1"] == 4
    assert sheet.columns["day7"] == 10
    assert sheet.columns["remark"] == 11


def test_sea_config_basic():
    cfg = get_template_config("sea")
    assert cfg.template_type == "sea"
    assert cfg.template_path.exists(), "sea 空白模板文件应存在"
    jp = cfg.sheets[0]
    assert jp.sheet_name == "JP N RATE FCL & LCL"
    assert jp.header_row == 8
    assert jp.data_start_row == 9
    assert jp.columns["destination"] == 1
    assert jp.columns["carrier"] == 2
    assert jp.columns["container"] == 3
    assert jp.columns["freight"] == 4
    assert jp.columns["lss_cic"] == 5
    assert jp.columns["baf"] == 6
    assert jp.columns["rmks"] == 17


def test_unknown_template_type_raises():
    with pytest.raises(ValueError):
        get_template_config("rail")
