from app.services.step1_rates.entities import Step1FileType


def test_air_tier_file_type_exists():
    assert Step1FileType("air_tier") is Step1FileType.air_tier
    assert Step1FileType.air_tier.value == "air_tier"
