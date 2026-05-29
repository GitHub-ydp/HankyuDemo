"""ONE 服务合约 PDF 适配器单元测试。"""
from app.services.step1_rates.adapters.one_contract_pdf import _clean_port_name


def test_clean_port_name_strips_state_suffix():
    assert _clean_port_name("HONOLULU, HI") == "HONOLULU"


def test_clean_port_name_strips_country_and_parens():
    assert _clean_port_name("DALIAN, LIAONING, CHINA(CY)") == "DALIAN"
    assert _clean_port_name("TAIPEI, TAIWAN(CY)") == "TAIPEI"


def test_clean_port_name_plain_passthrough():
    assert _clean_port_name("BUSAN") == "BUSAN"
    assert _clean_port_name("") == ""
    assert _clean_port_name(None) == ""
