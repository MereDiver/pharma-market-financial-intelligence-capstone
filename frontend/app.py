"""Databricks App frontend for management KPIs, Agent analysis, and saved work."""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from flask import Flask, jsonify, render_template, request

import agent_client
import analytics_client
import lakebase

logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO))
logger = logging.getLogger("pharma-finance-frontend")
app = Flask(__name__)


def safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)): return value.isoformat()
    if isinstance(value, Decimal): return float(value)
    if isinstance(value, dict): return {key: safe(item) for key, item in value.items()}
    if isinstance(value, list): return [safe(item) for item in value]
    return value


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/dashboard")
def dashboard():
    year = int(request.args.get("year", "2025"))
    quarter = int(request.args["quarter"]) if request.args.get("quarter") else None
    state = request.args.get("state") or None
    return jsonify({"status": "success", **safe(analytics_client.dashboard(year, quarter, state))})


@app.post("/api/agent")
def agent():
    payload = request.get_json(silent=True) or {}
    return jsonify({"status": "success", **safe(agent_client.ask_agent(payload.get("message", "")))})


@app.post("/api/agent/approval")
def agent_approval():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload.get("approve"), bool):
        raise ValueError("approve must be true or false.")
    result = agent_client.continue_agent(payload.get("approval_token", ""), payload["approve"])
    return jsonify({"status": "success", **safe(result)})


@app.get("/api/workspace")
def workspace():
    return jsonify({"status": "success", "investigations": safe(lakebase.investigations()),
                    "actions": safe(lakebase.actions()), "notes": safe(lakebase.notes())})


@app.post("/api/actions/<action_id>/complete")
def complete_action(action_id: str):
    changed = lakebase.complete_action(action_id)
    return jsonify({"status": "success" if changed else "not_found"}), (200 if changed else 404)


@app.errorhandler(Exception)
def error_handler(error: Exception):
    logger.exception("Frontend request failed")
    if isinstance(error, ValueError):
        return jsonify({"status": "error", "message": str(error)}), 400
    return jsonify({"status": "error", "message": "The intelligence workspace is temporarily unavailable. Verify attached resources."}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("DATABRICKS_APP_PORT", "8001")))
