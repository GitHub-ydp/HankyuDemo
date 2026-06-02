from app.services.step1_rates.port_normalizer import canonicalize


def test_alias_pusan_to_busan():
    assert canonicalize("PUSAN") == "BUSAN"


def test_strip_city_suffix():
    assert canonicalize("KAOHSIUNG CITY") == "KAOHSIUNG"
    assert canonicalize("TAICHUNG CITY") == "TAICHUNG"


def test_strip_port_suffix():
    assert canonicalize("KATTUPALLI PORT") == "KATTUPALLI"


def test_saint_louis_alias_and_fold():
    assert canonicalize("SAINT LOUIS") == "STLOUIS"


def test_port_klang_keeps_leading_port():
    # 末尾词是 KLANG(非尾缀)，首词 PORT 不删；KLANG→KELANG
    assert canonicalize("PORT KLANG") == "PORTKELANG"


def test_chittagong_alias():
    assert canonicalize("CHITTAGONG") == "CHATTOGRAM"


def test_empty():
    assert canonicalize(None) == ""
    assert canonicalize("") == ""
    assert canonicalize("   ") == ""
