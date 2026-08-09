"""Suggest evidence-backed demo cases from materialized Gold data."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_server.analytics_service import detect_reimbursement_outliers, get_variance_drivers


if __name__ == "__main__":
    year = int(os.getenv("DEMO_YEAR", "2025"))
    print("Largest product movers:", get_variance_drivers("total_reimbursement", year, year - 1, "product", top_n=5))
    print("Interesting Q4 outliers:", detect_reimbursement_outliers(year, 4, top_n=5))

