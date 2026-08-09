"""Allow-list validation for every public analytical and write-tool argument."""

from __future__ import annotations

import re
from datetime import date
from uuid import UUID

VALID_STATES = frozenset({"AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC"})
ALLOWED_METRICS = frozenset({"total_reimbursement", "medicaid_reimbursement", "prescriptions", "units_reimbursed", "reimbursement_per_prescription", "yoy_reimbursement_growth"})
ALLOWED_DIMENSIONS = frozenset({"product", "state", "quarter", "utilization_type"})
INVESTIGATION_STATUSES = frozenset({"open", "completed", "archived"})
ACTION_STATUSES = frozenset({"open", "completed", "cancelled"})
PRIORITIES = frozenset({"low", "medium", "high"})


class ValidationError(ValueError):
    pass


def validate_year(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 2000 <= value <= 2100:
        raise ValidationError("year must be an integer from 2000 through 2100")
    return value


def validate_quarter(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value not in {1, 2, 3, 4}:
        raise ValidationError("quarter must be 1 through 4")
    return value


def validate_state(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    normalized = str(value).strip().upper()
    if normalized not in VALID_STATES:
        raise ValidationError("state must be a valid two-letter US state code")
    return normalized


def validate_top_n(value: int, maximum: int = 50) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValidationError(f"top_n must be between 1 and {maximum}")
    return value


def validate_allowed(value: str, allowed: frozenset[str], field: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in allowed:
        raise ValidationError(f"{field} must be one of: {', '.join(sorted(allowed))}")
    return normalized


def validate_product(value: str) -> str:
    normalized = " ".join(str(value or "").split())
    if not normalized or len(normalized) > 120 or not re.search(r"[A-Za-z0-9]", normalized):
        raise ValidationError("product must be a non-empty name or product key")
    return normalized


def validate_uuid(value: str, field: str = "investigation_id") -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError(f"{field} must be a valid UUID") from exc


def validate_due_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError) as exc:
        raise ValidationError("due_date must use YYYY-MM-DD") from exc


def validate_text(value: str, field: str, maximum: int = 10000) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum:
        raise ValidationError(f"{field} must be non-empty and no longer than {maximum} characters")
    return normalized

