import pytest

from mcp_server.validation import (ACTION_STATUSES, ALLOWED_DIMENSIONS, ALLOWED_METRICS,
                                   INVESTIGATION_STATUSES, PRIORITIES, ValidationError,
                                   validate_allowed, validate_product, validate_quarter,
                                   validate_state, validate_top_n, validate_uuid, validate_year)


def test_state_quarter_year_and_top_n():
    assert validate_state("ca") == "CA"
    assert validate_quarter(4) == 4
    assert validate_year(2025) == 2025
    assert validate_top_n(20) == 20
    for operation in (lambda: validate_state("XX"), lambda: validate_quarter(5),
                      lambda: validate_year(1999), lambda: validate_top_n(0)):
        with pytest.raises(ValidationError): operation()


def test_allowlists_product_and_uuid():
    assert validate_allowed("prescriptions", ALLOWED_METRICS, "metric") == "prescriptions"
    assert validate_allowed("state", ALLOWED_DIMENSIONS, "dimension") == "state"
    assert validate_allowed("open", INVESTIGATION_STATUSES, "status") == "open"
    assert validate_allowed("completed", ACTION_STATUSES, "status") == "completed"
    assert validate_allowed("high", PRIORITIES, "priority") == "high"
    with pytest.raises(ValidationError): validate_allowed("profit", ALLOWED_METRICS, "metric")
    with pytest.raises(ValidationError): validate_product("  ")
    with pytest.raises(ValidationError): validate_uuid("not-a-uuid")
    with pytest.raises(ValidationError): validate_allowed("delete", ACTION_STATUSES, "status")
    with pytest.raises(ValidationError): validate_allowed("urgent", PRIORITIES, "priority")
