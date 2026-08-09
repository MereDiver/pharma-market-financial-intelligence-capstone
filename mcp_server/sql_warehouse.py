"""Databricks Statement Execution helper; no user-authored SQL is accepted."""

from __future__ import annotations

import os
import time
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import Disposition, Format, StatementParameterListItem, StatementState


class SQLWarehouseError(RuntimeError):
    pass


def execute_statement(sql_text: str, parameters: dict[str, Any] | None = None,
                      wait_timeout_seconds: int = 45) -> list[dict[str, Any]]:
    """Execute application-owned SQL with named values on the attached warehouse."""
    warehouse_id = os.getenv("WAREHOUSE_ID")
    if not warehouse_id:
        raise SQLWarehouseError("WAREHOUSE_ID is not configured from the sql-warehouse App resource.")
    client = WorkspaceClient()
    bound = [StatementParameterListItem(name=name, value=str(value)) for name, value in (parameters or {}).items() if value is not None]
    response = client.statement_execution.execute_statement(
        warehouse_id=warehouse_id, statement=sql_text, parameters=bound,
        disposition=Disposition.INLINE, format=Format.JSON_ARRAY, wait_timeout="10s",
    )
    deadline = time.monotonic() + wait_timeout_seconds
    while response.status and response.status.state in {StatementState.PENDING, StatementState.RUNNING}:
        if time.monotonic() >= deadline:
            if response.statement_id:
                client.statement_execution.cancel_execution(response.statement_id)
            raise SQLWarehouseError("SQL Warehouse query timed out.")
        time.sleep(0.5)
        response = client.statement_execution.get_statement(response.statement_id)
    if not response.status or response.status.state != StatementState.SUCCEEDED:
        message = getattr(getattr(response, "status", None), "error", None)
        raise SQLWarehouseError(f"SQL Warehouse query failed: {message or 'unknown error'}")
    columns = [column.name for column in (response.manifest.schema.columns if response.manifest and response.manifest.schema else [])]
    data = response.result.data_array if response.result and response.result.data_array else []
    return [dict(zip(columns, row)) for row in data]


def qualified_table(table_name: str) -> str:
    allowed = {
        "quarterly": "gold_drug_performance_quarterly", "yoy": "gold_drug_performance_yoy",
        "state": "gold_state_performance", "portfolio": "gold_portfolio_summary",
    }
    if table_name not in allowed:
        raise ValueError("Unknown governed table alias.")
    catalog = os.getenv("CATALOG", "main")
    schema = os.getenv("SCHEMA", "pharma_market_intelligence")
    if not re_identifier(catalog) or not re_identifier(schema):
        raise SQLWarehouseError("CATALOG and SCHEMA must be valid identifiers.")
    return f"`{catalog}`.`{schema}`.`{allowed[table_name]}`"


def re_identifier(value: str) -> bool:
    return bool(value and value.replace("_", "a").isalnum() and not value[0].isdigit())

