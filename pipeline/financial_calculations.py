"""Pure deterministic finance calculations shared with tests and services."""

from __future__ import annotations

from typing import Any


def safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def absolute_change(current: float | None, prior: float | None) -> float | None:
    return None if current is None or prior is None else current - prior


def percent_change(current: float | None, prior: float | None) -> float | None:
    change = absolute_change(current, prior)
    return None if change is None or prior == 0 else change / prior


def decompose_change(prior_volume: float, current_volume: float,
                     prior_rate: float, current_rate: float) -> dict[str, Any]:
    """Exact symmetric two-factor decomposition of V*R movement."""
    volume_effect = (current_volume - prior_volume) * ((prior_rate + current_rate) / 2)
    rate_effect = (current_rate - prior_rate) * ((prior_volume + current_volume) / 2)
    total_change = current_volume * current_rate - prior_volume * prior_rate
    return {
        "volume_effect": volume_effect,
        "reimbursement_per_prescription_effect": rate_effect,
        "total_change": total_change,
        "reconciliation_difference": total_change - volume_effect - rate_effect,
    }

