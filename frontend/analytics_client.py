"""Read-only KPI queries through the attached SQL Warehouse."""

from __future__ import annotations

import os
import time
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import Disposition, Format, StatementParameterListItem, StatementState

VALID_STATES = {"CA", "TX", "NY", "FL", "IL"}


def _table(name: str) -> str:
    allowed = {"quarterly": "gold_drug_performance_quarterly", "yoy": "gold_drug_performance_yoy"}
    catalog, schema = os.getenv("CATALOG", "main"), os.getenv("SCHEMA", "pharma_market_intelligence")
    if name not in allowed or not catalog.replace("_", "a").isalnum() or not schema.replace("_", "a").isalnum():
        raise ValueError("Invalid governed table configuration.")
    return f"`{catalog}`.`{schema}`.`{allowed[name]}`"


def _execute(statement: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    warehouse = os.getenv("WAREHOUSE_ID")
    if not warehouse:
        raise RuntimeError("WAREHOUSE_ID is not configured.")
    client = WorkspaceClient()
    response = client.statement_execution.execute_statement(
        warehouse_id=warehouse, statement=statement,
        parameters=[StatementParameterListItem(name=k, value=str(v)) for k, v in params.items()],
        disposition=Disposition.INLINE, format=Format.JSON_ARRAY, wait_timeout="10s",
    )
    deadline = time.monotonic() + 45
    while response.status and response.status.state in {StatementState.PENDING, StatementState.RUNNING}:
        if time.monotonic() > deadline:
            raise RuntimeError("Dashboard SQL query timed out.")
        time.sleep(0.5)
        response = client.statement_execution.get_statement(response.statement_id)
    if not response.status or response.status.state != StatementState.SUCCEEDED:
        raise RuntimeError("Dashboard SQL query failed.")
    columns = [column.name for column in response.manifest.schema.columns]
    return [dict(zip(columns, row)) for row in (response.result.data_array or [])]


def dashboard(year: int, quarter: int | None, state: str | None) -> dict[str, Any]:
    if year not in {2024, 2025} or quarter not in {None, 1, 2, 3, 4}:
        raise ValueError("Unsupported dashboard period.")
    if state and state not in VALID_STATES:
        raise ValueError("State is outside the deployed pipeline scope.")
    clauses, params = ["year=CAST(:year AS INT)"], {"year": year}
    yoy_clauses, yoy_params = ["current_year=CAST(:year AS INT)"], {"year": year}
    if quarter:
        clauses.append("quarter=CAST(:quarter AS INT)"); yoy_clauses.append("quarter=CAST(:quarter AS INT)")
        params["quarter"] = quarter; yoy_params["quarter"] = quarter
    if state:
        clauses.append("state=:state"); yoy_clauses.append("state=:state")
        params["state"] = state; yoy_params["state"] = state
    where, yoy_where = " AND ".join(clauses), " AND ".join(yoy_clauses)
    kpis = _execute(f"""
      SELECT SUM(total_reimbursement) total_reimbursement,SUM(prescriptions) prescriptions,
             SUM(units_reimbursed) units_reimbursed,
             CASE WHEN SUM(prescriptions)<>0 THEN SUM(total_reimbursement)/SUM(prescriptions) END reimbursement_per_prescription
      FROM {_table('quarterly')} WHERE {where}
    """, params)
    movers = _execute(f"""
      SELECT product_key,MAX(display_product_name) display_product_name,SUM(reimbursement_change) contribution
      FROM {_table('yoy')} WHERE {yoy_where} GROUP BY product_key ORDER BY ABS(contribution) DESC LIMIT 12
    """, yoy_params) if year == 2025 else []
    yoy = _execute(f"""
      SELECT SUM(reimbursement_change) reimbursement_change,
             CASE WHEN SUM(prior_total_reimbursement)<>0 THEN SUM(reimbursement_change)/SUM(prior_total_reimbursement) END reimbursement_change_percent
      FROM {_table('yoy')} WHERE {yoy_where}
    """, yoy_params) if year == 2025 else []
    return {"kpis": kpis[0] if kpis else {}, "yoy": yoy[0] if yoy else {},
            "positive_movers": [row for row in movers if float(row["contribution"]) >= 0][:6],
            "negative_movers": [row for row in movers if float(row["contribution"]) < 0][:6]}

