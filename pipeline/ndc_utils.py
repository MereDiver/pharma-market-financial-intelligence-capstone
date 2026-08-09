"""Deterministic Medicaid NDC11 reconciliation with historical FDA forms."""

from __future__ import annotations

import re


def normalize_ndc11(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) > 11 or not digits:
        raise ValueError("NDC must contain at most 11 digits.")
    return digits.zfill(11)


def fda_package_ndc_candidates(value: str) -> list[str]:
    """Return structurally valid native 4-4-2, 5-3-2, and 5-4-1 candidates."""
    ndc = normalize_ndc11(value)
    labeler, product, package = ndc[:5], ndc[5:9], ndc[9:]
    candidates: list[str] = []
    if labeler.startswith("0"):
        candidates.append(f"{labeler[1:]}-{product}-{package}")
    if product.startswith("0"):
        candidates.append(f"{labeler}-{product[1:]}-{package}")
    if package.startswith("0"):
        candidates.append(f"{labeler}-{product}-{package[1:]}")
    # Preserve order while avoiding ambiguous duplicate renderings.
    return list(dict.fromkeys(candidates))


def product_key_from_ndc11(value: str) -> str:
    ndc = normalize_ndc11(value)
    return ndc[:5] + ndc[5:9]

