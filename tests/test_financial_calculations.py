import pytest

from pipeline.financial_calculations import absolute_change, decompose_change, percent_change, safe_divide


def test_rates_and_zero_denominators():
    assert safe_divide(100, 4) == 25
    assert safe_divide(100, 5) == 20
    assert safe_divide(100, 0) is None
    assert safe_divide(100, None) is None


def test_yoy_changes_and_zero_prior():
    assert absolute_change(125, 100) == 25
    assert percent_change(125, 100) == pytest.approx(.25)
    assert percent_change(10, 0) is None


@pytest.mark.parametrize("v0,v1,r0,r1", [(100, 120, 10, 11), (120, 90, 11, 9), (100, 80, 10, 12)])
def test_exact_symmetric_decomposition_reconciles(v0, v1, r0, r1):
    result = decompose_change(v0, v1, r0, r1)
    assert result["volume_effect"] + result["reimbursement_per_prescription_effect"] == pytest.approx(result["total_change"])
    assert result["reconciliation_difference"] == pytest.approx(0)


def test_negative_change_and_zero_prior_period():
    result = decompose_change(0, 10, 0, 8)
    assert result["total_change"] == 80
    assert result["volume_effect"] + result["reimbursement_per_prescription_effect"] == pytest.approx(80)
    assert decompose_change(10, 5, 10, 10)["total_change"] < 0

