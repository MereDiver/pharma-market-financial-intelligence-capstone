"""Read/operational-update access using fresh Lakebase OAuth credentials."""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg2
from databricks.sdk import WorkspaceClient
from psycopg2 import sql
from psycopg2.extras import RealDictCursor


def schema_name() -> str:
    value = os.getenv("APP_SCHEMA", "pharma_intelligence")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise RuntimeError("Invalid APP_SCHEMA.")
    return value


@contextmanager
def connection() -> Iterator[Any]:
    client = WorkspaceClient()
    values = {"host": os.getenv("PGHOST"), "dbname": os.getenv("PGDATABASE"),
              "port": os.getenv("PGPORT"), "sslmode": os.getenv("PGSSLMODE"),
              "user": os.getenv("PGUSER"), "endpoint": os.getenv("ENDPOINT_NAME")}
    if any(not value for value in values.values()):
        raise RuntimeError("Lakebase App resource configuration is incomplete.")
    endpoint = values.pop("endpoint")
    values["port"] = int(values["port"])
    credential = client.postgres.generate_database_credential(endpoint=endpoint)
    temporary_credential = getattr(credential, "token", None)
    if not temporary_credential:
        raise RuntimeError("No temporary Lakebase credential was returned.")
    db = psycopg2.connect(**values, password=temporary_credential,
                          cursor_factory=RealDictCursor, connect_timeout=15)
    try:
        yield db
    finally:
        db.close()


def query(statement: Any, params: tuple = ()) -> list[dict[str, Any]]:
    with connection() as db:
        with db.cursor() as cursor:
            cursor.execute(statement, params)
            return [dict(row) for row in cursor.fetchall()]


def investigations() -> list[dict[str, Any]]:
    return query(sql.SQL("SELECT investigation_id,title,question,summary,status,created_at FROM {}.investigations ORDER BY created_at DESC LIMIT 50").format(sql.Identifier(schema_name())))


def actions() -> list[dict[str, Any]]:
    return query(sql.SQL("SELECT action_id,investigation_id,action_text,priority,status,due_date,created_at FROM {}.follow_up_actions ORDER BY created_at DESC LIMIT 50").format(sql.Identifier(schema_name())))


def notes() -> list[dict[str, Any]]:
    schema = sql.Identifier(schema_name())
    statement = sql.SQL(
        "SELECT n.note_id,n.investigation_id,n.note_text,n.author,n.created_at,"
        "i.title AS investigation_title FROM {}.analyst_notes n "
        "JOIN {}.investigations i ON i.investigation_id=n.investigation_id "
        "ORDER BY n.created_at DESC LIMIT 50"
    ).format(schema, schema)
    return query(statement)


def complete_action(action_id: str) -> bool:
    from uuid import UUID
    normalized = str(UUID(action_id))
    with connection() as db:
        try:
            with db.cursor() as cursor:
                cursor.execute(sql.SQL("UPDATE {}.follow_up_actions SET status='completed',updated_at=now() WHERE action_id=%s AND status='open'").format(sql.Identifier(schema_name())), (normalized,))
                changed = cursor.rowcount > 0
            db.commit()
            return changed
        except Exception:
            db.rollback(); raise
