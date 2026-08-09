from __future__ import annotations

import json
from contextlib import contextmanager

from mcp_server import action_service


class FakeCursor:
    def __init__(self) -> None:
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, statement, params) -> None:
        self.calls.append((statement, params))


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        raise AssertionError("The valid write should not roll back")


def test_save_accepts_supervisor_text_without_runtime_ddl(monkeypatch) -> None:
    connection = FakeConnection()

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(action_service.lakebase, "get_connection", fake_connection)
    monkeypatch.setattr(
        action_service.lakebase,
        "ensure_schema",
        lambda: (_ for _ in ()).throw(AssertionError("Runtime writes must not execute DDL")),
    )

    result = action_service.save_investigation(
        "California review",
        "What drove the change?",
        "Prescription volume was the principal driver.",
        "State: California; years: 2024 and 2025",
        "Wegovy 2.4 had the largest increase.",
    )

    assert result["status"] == "success"
    assert connection.committed
    assert len(connection.cursor_instance.calls) == 2
    investigation_params = connection.cursor_instance.calls[0][1]
    finding_params = connection.cursor_instance.calls[1][1]
    assert json.loads(investigation_params[4])["description"].startswith("State: California")
    assert finding_params[2] == "observation"
    assert finding_params[3] == "Wegovy 2.4 had the largest increase."
