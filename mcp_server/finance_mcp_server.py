"""FastMCP entrypoint for governed Pharma Market & Financial Intelligence tools."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from fastmcp import FastMCP

try:  # Package import in tests/jobs; sibling import when mcp_server/ is the App root.
    from mcp_server import action_service, analytics_service, context_service
    from mcp_server.validation import ValidationError
except ModuleNotFoundError:  # pragma: no cover - exercised by Databricks App startup
    import action_service, analytics_service, context_service
    from validation import ValidationError

logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO))
logger = logging.getLogger("pharma-finance-mcp")
mcp = FastMCP("pharma-market-financial-intelligence")


def _safe(operation: Callable[..., dict], *args: Any, **kwargs: Any) -> dict:
    try:
        return operation(*args, **kwargs)
    except (ValidationError, ValueError) as exc:
        return {"status": "error", "error": "invalid_argument", "message": str(exc)}
    except Exception:
        logger.exception("Governed MCP tool failed")
        return {"status": "error", "error": "service_unavailable", "message": "The governed intelligence service is temporarily unavailable."}


@mcp.tool()
def get_market_overview(year: int, quarter: int | None = None, state: str | None = None,
                        utilization_type: str | None = None) -> dict:
    """Return a broad Medicaid reimbursement and utilization overview.

    Use for portfolio-level KPI questions before drilling into products. Arguments
    are year, optional quarter/state, and optional FFSU/MCOU utilization type.
    Returns reimbursement, prescriptions, units, rate, YoY totals, and top products.
    Values exclude unavailable suppressed quantitative records and are not manufacturer sales.
    """
    return _safe(analytics_service.get_market_overview, year, quarter, state, utilization_type)


@mcp.tool()
def get_product_performance(product: str, year: int, state: str | None = None,
                            quarter: int | None = None, compare_year: int | None = None) -> dict:
    """Retrieve metrics and quarterly trends for one resolved product.

    Use for a named-product performance question, not broad driver ranking. Supply
    product name/key, year, optional state/quarter, and optional comparison year.
    Returns current/comparison metrics and trend. Ambiguous names return candidates;
    reimbursement per prescription is rate/mix, not list price or net price.
    """
    return _safe(analytics_service.get_product_performance, product, year, state, quarter, compare_year)


@mcp.tool()
def get_variance_drivers(metric: str, current_year: int, comparison_year: int, dimension: str,
                         quarter: int | None = None, state: str | None = None,
                         product: str | None = None, top_n: int = 10) -> dict:
    """Rank positive and negative contributors to an additive metric change.

    Use when asked which products, states, quarters, or utilization types drove a
    year-over-year change. Metric/dimension are allow-listed; optional filters and
    top_n narrow scope. Returns current, comparison, and contribution amounts.
    It describes contribution, not unsupported causality, and rejects non-additive rates.
    """
    return _safe(analytics_service.get_variance_drivers, metric, current_year, comparison_year,
                 dimension, quarter, state, product, top_n)


@mcp.tool()
def decompose_reimbursement_change(product: str, current_period: str, comparison_period: str,
                                   state: str | None = None) -> dict:
    """Exactly decompose reimbursement movement into volume and rate/mix effects.

    Use only when the user asks whether reimbursement change reflects prescriptions
    or reimbursement per prescription. Periods use YYYY-Qn; state is optional.
    Returns supporting values, both symmetric effects, and reconciliation difference.
    The second component is never presented as pharmaceutical price.
    """
    return _safe(analytics_service.decompose_reimbursement_change, product, current_period, comparison_period, state)


@mcp.tool()
def detect_reimbursement_outliers(year: int, quarter: int, metric: str = "reimbursement_per_prescription",
                                  dimension: str = "product", state: str | None = None,
                                  top_n: int = 10) -> dict:
    """Flag transparent 1.5-IQR reimbursement/utilization outliers.

    Use for unusual-value or anomaly questions, not contribution analysis. Supply
    period, allow-listed metric/dimension, optional state and result limit. Returns
    observations, quartiles, fences, and flag reason. This is a statistical rule,
    not machine learning and not proof of error or misconduct.
    """
    return _safe(analytics_service.detect_reimbursement_outliers, year, quarter, metric, dimension, state, top_n)


@mcp.tool()
def get_drug_profile(product: str) -> dict:
    """Return stored structured openFDA identity and product metadata.

    Use for manufacturer, generic/brand, route, dosage-form, substance, or FDA
    identifier context after analytics identifies a product. Returns provenance and
    match strength; unmatched/ambiguous products are explicit. It is not medical advice.
    """
    return _safe(context_service.get_drug_profile, product)


@mcp.tool()
def search_drug_context(query: str, product: str | None = None, top_k: int = 5) -> dict:
    """Semantically retrieve real openFDA Drug Label chunks from pgvector.

    Use when FDA label purpose/indication/context helps interpret an analytical
    discussion. Supply a natural-language query, optional product, and top_k up to
    ten. Returns source-linked chunks and cosine similarity. Label text is context
    only; never turn it into diagnosis or treatment guidance.
    """
    return _safe(context_service.search_drug_context, query, product, top_k)


@mcp.tool()
def save_investigation(title: str, question: str, summary: str,
                       scope: dict | None = None, findings: list[dict] | None = None) -> dict:
    """Persist a completed analytical investigation and evidence to Lakebase.

    Use only after analysis and only when the user explicitly asks to save, store,
    or document it. Supply title/question/summary plus optional structured scope and
    findings. Returns the created investigation UUID. It cannot alter CMS, FDA, or Gold data.
    """
    return _safe(action_service.save_investigation, title, question, summary, scope, findings)


@mcp.tool()
def add_analyst_note(investigation_id: str, note_text: str) -> dict:
    """Append a human-readable note to an existing investigation.

    Use only on an explicit note/document request. Requires an investigation UUID
    and note text; returns the note UUID. It writes operational state only and does
    not change analytical facts.
    """
    return _safe(action_service.add_analyst_note, investigation_id, note_text)


@mcp.tool()
def create_follow_up_action(investigation_id: str, action_text: str, priority: str,
                            due_date: str | None = None) -> dict:
    """Create a real operational follow-up linked to a saved investigation.

    Use only when the user explicitly requests a follow-up. Requires investigation
    UUID, action text, low/medium/high priority, and optional YYYY-MM-DD due date.
    Returns action UUID; it never writes source or analytical metrics.
    """
    return _safe(action_service.create_follow_up_action, investigation_id, action_text, priority, due_date)


@mcp.tool()
def update_investigation_status(investigation_id: str, status: str) -> dict:
    """Update only an investigation workflow status.

    Use on an explicit request to mark an investigation open, completed, or archived.
    Returns success/not-found and the UUID. It cannot modify findings or source data.
    """
    return _safe(action_service.update_investigation_status, investigation_id, status)


@mcp.tool()
def update_follow_up_action(action_id: str, status: str) -> dict:
    """Update only a follow-up workflow status.

    Use on an explicit request to mark a follow-up open, completed, or cancelled.
    Returns success/not-found and the UUID; all reimbursement facts remain immutable.
    """
    return _safe(action_service.update_follow_up_action, action_id, status)


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=int(os.getenv("DATABRICKS_APP_PORT", "8000")))
