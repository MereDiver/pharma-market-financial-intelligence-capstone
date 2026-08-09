"""Governed application-owned SQL for Medicaid reimbursement analytics."""

from __future__ import annotations

import re
from typing import Any

try:
    from mcp_server.sql_warehouse import execute_statement, qualified_table
    from mcp_server.validation import (ALLOWED_DIMENSIONS, ALLOWED_METRICS, validate_allowed,
                                       validate_product, validate_quarter, validate_state,
                                       validate_top_n, validate_year)
except ModuleNotFoundError:  # pragma: no cover
    from sql_warehouse import execute_statement, qualified_table
    from validation import (ALLOWED_DIMENSIONS, ALLOWED_METRICS, validate_allowed,
                            validate_product, validate_quarter, validate_state,
                            validate_top_n, validate_year)


def _filters(year_field: str = "year", *, year: int, quarter: int | None = None,
             state: str | None = None, utilization_type: str | None = None) -> tuple[str, dict[str, Any]]:
    clauses = [f"{year_field}=CAST(:year AS INT)"]
    params: dict[str, Any] = {"year": validate_year(year)}
    quarter = validate_quarter(quarter)
    state = validate_state(state)
    if quarter:
        clauses.append("quarter=CAST(:quarter AS INT)"); params["quarter"] = quarter
    if state:
        clauses.append("state=:state"); params["state"] = state
    if utilization_type:
        normalized = utilization_type.strip().upper()
        if normalized not in {"FFSU", "MCOU"}:
            raise ValueError("utilization_type must be FFSU or MCOU")
        clauses.append("utilization_type=:utilization_type"); params["utilization_type"] = normalized
    return " AND ".join(clauses), params


def get_market_overview(year: int, quarter: int | None = None, state: str | None = None,
                        utilization_type: str | None = None) -> dict[str, Any]:
    where, params = _filters(year=year, quarter=quarter, state=state, utilization_type=utilization_type)
    table = qualified_table("quarterly")
    metrics = execute_statement(f"""
      SELECT SUM(total_reimbursement) total_reimbursement,
             SUM(medicaid_reimbursement) medicaid_reimbursement,
             SUM(non_medicaid_reimbursement) non_medicaid_reimbursement,
             SUM(prescriptions) prescriptions, SUM(units_reimbursed) units_reimbursed,
             CASE WHEN SUM(prescriptions)<>0 THEN SUM(total_reimbursement)/SUM(prescriptions) END reimbursement_per_prescription
      FROM {table} WHERE {where}
    """, params)
    top = execute_statement(f"""
      SELECT product_key, MAX(display_product_name) display_product_name,
             SUM(total_reimbursement) total_reimbursement, SUM(prescriptions) prescriptions
      FROM {table} WHERE {where}
      GROUP BY product_key ORDER BY total_reimbursement DESC LIMIT 10
    """, params)
    yoy_where, yoy_params = _filters("current_year", year=year, quarter=quarter, state=state,
                                    utilization_type=utilization_type)
    yoy = execute_statement(f"""
      SELECT SUM(current_total_reimbursement) current_total_reimbursement,
             SUM(prior_total_reimbursement) prior_total_reimbursement,
             SUM(reimbursement_change) reimbursement_change,
             CASE WHEN SUM(prior_total_reimbursement)<>0
               THEN SUM(reimbursement_change)/SUM(prior_total_reimbursement) END reimbursement_change_percent
      FROM {qualified_table('yoy')} WHERE {yoy_where}
    """, yoy_params)
    return {"status": "success", "scope": params, "metrics": metrics[0] if metrics else {},
            "yoy": yoy[0] if yoy else {}, "top_products": top,
            "semantic_note": "Amounts are Medicaid reimbursement/spend metrics, not manufacturer sales."}


def _resolve_product(product: str) -> dict[str, Any]:
    product = validate_product(product)
    rows = execute_statement(f"""
      SELECT product_key, MAX(display_product_name) display_product_name,
             SUM(total_reimbursement) total_reimbursement
      FROM {qualified_table('quarterly')}
      WHERE product_key=:exact OR upper(display_product_name) LIKE upper(:pattern)
      GROUP BY product_key ORDER BY CASE WHEN product_key=:exact THEN 0 ELSE 1 END,
               total_reimbursement DESC LIMIT 8
    """, {"exact": product, "pattern": f"%{product}%"})
    if not rows:
        return {"status": "not_found", "candidates": []}
    exact_names = [row for row in rows if str(row.get("display_product_name", "")).strip().casefold() == product.casefold() or row.get("product_key") == product]
    if len(exact_names) == 1:
        return {"status": "resolved", **exact_names[0]}
    if len(rows) == 1:
        return {"status": "resolved", **rows[0]}
    return {"status": "ambiguous", "candidates": rows}


def get_product_performance(product: str, year: int, state: str | None = None,
                            quarter: int | None = None, compare_year: int | None = None) -> dict[str, Any]:
    resolved = _resolve_product(product)
    if resolved["status"] != "resolved":
        return resolved
    where, params = _filters(year=year, quarter=quarter, state=state)
    params["product_key"] = resolved["product_key"]
    current = execute_statement(f"""
      SELECT SUM(total_reimbursement) total_reimbursement, SUM(medicaid_reimbursement) medicaid_reimbursement,
             SUM(prescriptions) prescriptions, SUM(units_reimbursed) units_reimbursed,
             CASE WHEN SUM(prescriptions)<>0 THEN SUM(total_reimbursement)/SUM(prescriptions) END reimbursement_per_prescription
      FROM {qualified_table('quarterly')} WHERE {where} AND product_key=:product_key
    """, params)
    trend_params = {"year": validate_year(year), "product_key": resolved["product_key"]}
    trend_clause = "year=CAST(:year AS INT) AND product_key=:product_key"
    normalized_state = validate_state(state)
    if normalized_state:
        trend_clause += " AND state=:state"; trend_params["state"] = normalized_state
    trend = execute_statement(f"""
      SELECT year,quarter,SUM(total_reimbursement) total_reimbursement,SUM(prescriptions) prescriptions,
             CASE WHEN SUM(prescriptions)<>0 THEN SUM(total_reimbursement)/SUM(prescriptions) END reimbursement_per_prescription
      FROM {qualified_table('quarterly')} WHERE {trend_clause}
      GROUP BY year,quarter ORDER BY year,quarter
    """, trend_params)
    comparison = None
    if compare_year is not None:
        compare_where, compare_params = _filters(year=validate_year(compare_year), quarter=quarter, state=state)
        compare_params["product_key"] = resolved["product_key"]
        rows = execute_statement(f"""
          SELECT SUM(total_reimbursement) total_reimbursement,SUM(prescriptions) prescriptions,
                 SUM(units_reimbursed) units_reimbursed,
                 CASE WHEN SUM(prescriptions)<>0 THEN SUM(total_reimbursement)/SUM(prescriptions) END reimbursement_per_prescription
          FROM {qualified_table('quarterly')} WHERE {compare_where} AND product_key=:product_key
        """, compare_params)
        comparison = rows[0] if rows else {}
    return {"status": "success", "product": resolved, "current": current[0] if current else {},
            "comparison": comparison, "quarterly_trend": trend,
            "semantic_note": "Reimbursement per prescription is a utilization rate/mix metric, not drug price."}


def get_variance_drivers(metric: str, current_year: int, comparison_year: int,
                         dimension: str, quarter: int | None = None, state: str | None = None,
                         product: str | None = None, top_n: int = 10) -> dict[str, Any]:
    metric = validate_allowed(metric, ALLOWED_METRICS, "metric")
    dimension = validate_allowed(dimension, ALLOWED_DIMENSIONS, "dimension")
    if metric in {"reimbursement_per_prescription", "yoy_reimbursement_growth"}:
        raise ValueError("Variance contribution supports additive metrics only.")
    metric_column = {"total_reimbursement": "total_reimbursement", "medicaid_reimbursement": "medicaid_reimbursement",
                     "prescriptions": "prescriptions", "units_reimbursed": "units_reimbursed"}[metric]
    dimension_column = {"product": "product_key", "state": "state", "quarter": "quarter", "utilization_type": "utilization_type"}[dimension]
    params: dict[str, Any] = {"current_year": validate_year(current_year), "comparison_year": validate_year(comparison_year), "top_n": validate_top_n(top_n)}
    filters = []
    if validate_quarter(quarter): filters.append("quarter=CAST(:quarter AS INT)"); params["quarter"] = quarter
    if validate_state(state): filters.append("state=:state"); params["state"] = state
    if product:
        resolved = _resolve_product(product)
        if resolved["status"] != "resolved": return resolved
        filters.append("product_key=:product_key"); params["product_key"] = resolved["product_key"]
    extra = (" AND " + " AND ".join(filters)) if filters else ""
    table = qualified_table("quarterly")
    rows = execute_statement(f"""
      WITH c AS (SELECT {dimension_column} driver, SUM({metric_column}) value FROM {table}
                 WHERE year=CAST(:current_year AS INT){extra} GROUP BY {dimension_column}),
           p AS (SELECT {dimension_column} driver, SUM({metric_column}) value FROM {table}
                 WHERE year=CAST(:comparison_year AS INT){extra} GROUP BY {dimension_column}),
           changes AS (SELECT COALESCE(c.driver,p.driver) driver, COALESCE(c.value,0) current_value,
                       COALESCE(p.value,0) comparison_value, COALESCE(c.value,0)-COALESCE(p.value,0) contribution
                       FROM c FULL OUTER JOIN p ON c.driver=p.driver)
      SELECT * FROM changes ORDER BY ABS(contribution) DESC LIMIT CAST(:top_n AS INT)
    """, params)
    return {"status": "success", "metric": metric, "dimension": dimension,
            "positive_contributors": [row for row in rows if float(row["contribution"]) > 0],
            "negative_contributors": [row for row in rows if float(row["contribution"]) < 0]}


def _period(value: str, field: str) -> tuple[int, int]:
    match = re.fullmatch(r"(20\d{2})-Q([1-4])", str(value).upper())
    if not match:
        raise ValueError(f"{field} must use YYYY-Q1 through YYYY-Q4")
    return validate_year(int(match.group(1))), int(match.group(2))


def decompose_reimbursement_change(product: str, current_period: str, comparison_period: str,
                                   state: str | None = None) -> dict[str, Any]:
    resolved = _resolve_product(product)
    if resolved["status"] != "resolved": return resolved
    cy, cq = _period(current_period, "current_period"); py, pq = _period(comparison_period, "comparison_period")
    params: dict[str, Any] = {"product_key": resolved["product_key"], "cy": cy, "cq": cq, "py": py, "pq": pq}
    state_filter = ""
    if validate_state(state): state_filter = " AND state=:state"; params["state"] = state
    rows = execute_statement(f"""
      WITH periods AS (
        SELECT year,quarter,SUM(prescriptions) volume,SUM(total_reimbursement) reimbursement
        FROM {qualified_table('quarterly')} WHERE product_key=:product_key{state_filter}
          AND ((year=CAST(:cy AS INT) AND quarter=CAST(:cq AS INT)) OR (year=CAST(:py AS INT) AND quarter=CAST(:pq AS INT)))
        GROUP BY year,quarter), values AS (
          SELECT MAX(CASE WHEN year=CAST(:cy AS INT) AND quarter=CAST(:cq AS INT) THEN volume END) v1,
                 MAX(CASE WHEN year=CAST(:py AS INT) AND quarter=CAST(:pq AS INT) THEN volume END) v0,
                 MAX(CASE WHEN year=CAST(:cy AS INT) AND quarter=CAST(:cq AS INT) THEN reimbursement END) a1,
                 MAX(CASE WHEN year=CAST(:py AS INT) AND quarter=CAST(:pq AS INT) THEN reimbursement END) a0 FROM periods), rates AS (
          SELECT *, CASE WHEN v1<>0 THEN a1/v1 END r1, CASE WHEN v0<>0 THEN a0/v0 END r0 FROM values)
      SELECT v0 prior_prescriptions,v1 current_prescriptions,a0 prior_reimbursement,a1 current_reimbursement,
             r0 prior_reimbursement_per_prescription,r1 current_reimbursement_per_prescription,
             a1-a0 total_change,(v1-v0)*((r0+r1)/2) volume_effect,
             (r1-r0)*((v0+v1)/2) reimbursement_per_prescription_effect,
             (a1-a0)-((v1-v0)*((r0+r1)/2))-((r1-r0)*((v0+v1)/2)) reconciliation_difference
      FROM rates
    """, params)
    return {"status": "success", "product": resolved, "current_period": current_period,
            "comparison_period": comparison_period, "decomposition": rows[0] if rows else {},
            "method": "exact symmetric two-factor decomposition",
            "limitation": "The rate/mix effect is not a pharmaceutical price effect."}


def detect_reimbursement_outliers(year: int, quarter: int, metric: str = "reimbursement_per_prescription",
                                  dimension: str = "product", state: str | None = None,
                                  top_n: int = 10) -> dict[str, Any]:
    metric = validate_allowed(metric, ALLOWED_METRICS, "metric")
    dimension = validate_allowed(dimension, ALLOWED_DIMENSIONS, "dimension")
    if metric == "yoy_reimbursement_growth":
        metric_expr = "SUM(reimbursement_change)/NULLIF(SUM(prior_total_reimbursement),0)"
        table = qualified_table("yoy"); year_field = "current_year"
    else:
        base = {"total_reimbursement": "SUM(total_reimbursement)", "medicaid_reimbursement": "SUM(medicaid_reimbursement)",
                "prescriptions": "SUM(prescriptions)", "units_reimbursed": "SUM(units_reimbursed)",
                "reimbursement_per_prescription": "SUM(total_reimbursement)/NULLIF(SUM(prescriptions),0)"}
        metric_expr = base[metric]; table = qualified_table("quarterly"); year_field = "year"
    dim = {"product": "product_key", "state": "state", "quarter": "quarter", "utilization_type": "utilization_type"}[dimension]
    params: dict[str, Any] = {"year": validate_year(year), "quarter": validate_quarter(quarter), "top_n": validate_top_n(top_n)}
    state_filter = ""
    if validate_state(state): state_filter = " AND state=:state"; params["state"] = state
    rows = execute_statement(f"""
      WITH observations AS (SELECT {dim} item,{metric_expr} observed FROM {table}
        WHERE {year_field}=CAST(:year AS INT) AND quarter=CAST(:quarter AS INT){state_filter} GROUP BY {dim}),
      bounds AS (SELECT percentile_approx(observed,0.25) q1,percentile_approx(observed,0.75) q3 FROM observations)
      SELECT item,observed,q1,q3,q1-1.5*(q3-q1) lower_threshold,q3+1.5*(q3-q1) upper_threshold,
             CASE WHEN observed<q1-1.5*(q3-q1) THEN 'below lower IQR fence' ELSE 'above upper IQR fence' END reason
      FROM observations CROSS JOIN bounds WHERE observed<q1-1.5*(q3-q1) OR observed>q3+1.5*(q3-q1)
      ORDER BY ABS(observed-(q1+q3)/2) DESC LIMIT CAST(:top_n AS INT)
    """, params)
    return {"status": "success", "method": "1.5 x IQR transparent statistical rule", "metric": metric,
            "dimension": dimension, "period": f"{year}-Q{quarter}", "outliers": rows}
