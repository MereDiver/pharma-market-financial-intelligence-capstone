"""Safe operational writes; this module cannot mutate analytical source tables."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from psycopg2 import sql

try:
    from mcp_server import lakebase
    from mcp_server.validation import (ACTION_STATUSES, INVESTIGATION_STATUSES, PRIORITIES,
                                       validate_allowed, validate_due_date, validate_text, validate_uuid)
except ModuleNotFoundError:  # pragma: no cover
    import lakebase
    from validation import (ACTION_STATUSES, INVESTIGATION_STATUSES, PRIORITIES,
                            validate_allowed, validate_due_date, validate_text, validate_uuid)


def _scope_payload(scope: dict[str, Any] | str | None) -> dict[str, Any]:
    if isinstance(scope, dict):
        return scope
    if isinstance(scope, str):
        return {"description": validate_text(scope, "scope")}
    return {}


def _finding_payloads(findings: list[dict[str, Any]] | str | None) -> list[dict[str, Any]]:
    if isinstance(findings, str):
        return [{"finding_type": "observation", "finding_text": validate_text(findings, "findings"), "evidence": {}}]
    return findings or []


def save_investigation(title: str, question: str, summary: str,
                       scope: dict[str, Any] | str | None,
                       findings: list[dict[str, Any]] | str | None) -> dict[str, Any]:
    # Schema DDL belongs to the ingestion/deployment path. Runtime App roles use
    # least-privilege DML grants and must not need ownership of existing tables.
    investigation_id = str(uuid4())
    title = validate_text(title, "title", 300)
    question = validate_text(question, "question")
    summary = validate_text(summary, "summary")
    schema = sql.Identifier(lakebase.get_schema_name())
    with lakebase.get_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL("INSERT INTO {}.investigations (investigation_id,title,question,summary,scope,status) VALUES (%s,%s,%s,%s,%s::jsonb,'open')").format(schema),
                               (investigation_id, title, question, summary, json.dumps(_scope_payload(scope))))
                for finding in _finding_payloads(findings):
                    cursor.execute(sql.SQL("INSERT INTO {}.investigation_findings (finding_id,investigation_id,finding_type,finding_text,evidence) VALUES (%s,%s,%s,%s,%s::jsonb)").format(schema),
                                   (str(uuid4()), investigation_id, validate_text(finding.get("finding_type", "observation"), "finding_type", 100),
                                    validate_text(finding.get("finding_text"), "finding_text"), json.dumps(finding.get("evidence") or {})))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {"status": "success", "investigation_id": investigation_id}


def add_analyst_note(investigation_id: str, note_text: str, author: str | None = None) -> dict[str, Any]:
    note_id = str(uuid4())
    statement = sql.SQL("INSERT INTO {}.analyst_notes (note_id,investigation_id,note_text,author) VALUES (%s,%s,%s,%s)").format(sql.Identifier(lakebase.get_schema_name()))
    lakebase.run_write(statement, (note_id, validate_uuid(investigation_id), validate_text(note_text, "note_text"), author))
    return {"status": "success", "note_id": note_id}


def create_follow_up_action(investigation_id: str, action_text: str, priority: str,
                            due_date: str | None = None) -> dict[str, Any]:
    action_id = str(uuid4())
    priority = validate_allowed(priority, PRIORITIES, "priority")
    statement = sql.SQL("INSERT INTO {}.follow_up_actions (action_id,investigation_id,action_text,priority,status,due_date) VALUES (%s,%s,%s,%s,'open',%s)").format(sql.Identifier(lakebase.get_schema_name()))
    lakebase.run_write(statement, (action_id, validate_uuid(investigation_id), validate_text(action_text, "action_text"), priority, validate_due_date(due_date)))
    return {"status": "success", "action_id": action_id}


def update_investigation_status(investigation_id: str, status: str) -> dict[str, Any]:
    status = validate_allowed(status, INVESTIGATION_STATUSES, "status")
    statement = sql.SQL("UPDATE {}.investigations SET status=%s,updated_at=now() WHERE investigation_id=%s RETURNING investigation_id").format(sql.Identifier(lakebase.get_schema_name()))
    rows = lakebase.run_query(statement, (status, validate_uuid(investigation_id)))
    return {"status": "success" if rows else "not_found", "investigation_id": investigation_id}


def update_follow_up_action(action_id: str, status: str) -> dict[str, Any]:
    status = validate_allowed(status, ACTION_STATUSES, "status")
    statement = sql.SQL("UPDATE {}.follow_up_actions SET status=%s,updated_at=now() WHERE action_id=%s RETURNING action_id").format(sql.Identifier(lakebase.get_schema_name()))
    rows = lakebase.run_query(statement, (status, validate_uuid(action_id, "action_id")))
    return {"status": "success" if rows else "not_found", "action_id": action_id}
