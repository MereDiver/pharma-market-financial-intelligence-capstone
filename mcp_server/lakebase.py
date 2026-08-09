"""OAuth-authenticated Lakebase access and idempotent schema setup."""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

import psycopg2
from databricks.sdk import WorkspaceClient
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class LakebaseConfigurationError(RuntimeError):
    pass


def get_schema_name() -> str:
    value = os.getenv("APP_SCHEMA", "pharma_intelligence").strip()
    if not _IDENTIFIER.fullmatch(value):
        raise LakebaseConfigurationError("APP_SCHEMA must be a valid PostgreSQL identifier.")
    return value


@contextmanager
def get_connection() -> Iterator[Any]:
    client = WorkspaceClient()
    settings = {
        "host": os.getenv("PGHOST"), "dbname": os.getenv("PGDATABASE"),
        "port": os.getenv("PGPORT"), "sslmode": os.getenv("PGSSLMODE"),
        "user": os.getenv("PGUSER"), "endpoint": os.getenv("ENDPOINT_NAME"),
    }
    missing = [key.upper() for key, value in settings.items() if not value]
    if missing:
        raise LakebaseConfigurationError("Missing Lakebase settings: " + ", ".join(sorted(missing)))
    endpoint = settings.pop("endpoint")
    try:
        settings["port"] = int(settings["port"])
    except (TypeError, ValueError) as exc:
        raise LakebaseConfigurationError("PGPORT must be an integer.") from exc
    credential = client.postgres.generate_database_credential(endpoint=endpoint)
    temporary_credential = getattr(credential, "token", None)
    if not temporary_credential:
        raise LakebaseConfigurationError("Databricks did not return a temporary database credential.")
    connection = psycopg2.connect(**settings, password=temporary_credential,
                                  cursor_factory=RealDictCursor, connect_timeout=15)
    try:
        yield connection
    finally:
        connection.close()


def run_query(statement: Any, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(statement, params)
            return [dict(row) for row in cursor.fetchall()]


def run_write(statement: Any, params: Sequence[Any] | None = None) -> int:
    with get_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(statement, params)
                affected = cursor.rowcount
            connection.commit()
            return affected
        except Exception:
            connection.rollback()
            raise


def ensure_schema() -> None:
    """Create only the dedicated schema/tables in the already-existing Lakebase project."""
    schema = get_schema_name()
    local_template = Path(__file__).with_name("lakebase_schema.sql")
    repository_template = Path(__file__).resolve().parents[1] / "sql" / "lakebase_schema.sql"
    template = (local_template if local_template.exists() else repository_template).read_text(encoding="utf-8")
    if schema != "pharma_intelligence":
        template = template.replace("pharma_intelligence", schema)
    with get_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector') AS present")
                row = cursor.fetchone()
                if not row or not row["present"]:
                    raise LakebaseConfigurationError("pgvector must be enabled in the existing Lakebase database.")
                cursor.execute(template)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
