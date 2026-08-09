import pytest

from pipeline.ndc_utils import fda_package_ndc_candidates, normalize_ndc11, product_key_from_ndc11


def test_valid_standardized_ndc_and_product_key():
    assert normalize_ndc11("00002143380") == "00002143380"
    assert product_key_from_ndc11("00002143380") == "000021433"


def test_candidate_442_conversion():
    assert "1234-0567-08" in fda_package_ndc_candidates("01234056708")


def test_candidate_532_conversion():
    assert "01234-567-08" in fda_package_ndc_candidates("01234056708")


def test_candidate_541_conversion():
    assert "01234-0567-8" in fda_package_ndc_candidates("01234056708")


def test_invalid_ndc():
    with pytest.raises(ValueError):
        normalize_ndc11("123456789012")
    with pytest.raises(ValueError):
        normalize_ndc11("not-an-ndc")


def test_preserves_leading_zeros_and_does_not_create_invalid_forms():
    assert normalize_ndc11("2143380") == "00002143380"
    assert fda_package_ndc_candidates("12345123456") == []

