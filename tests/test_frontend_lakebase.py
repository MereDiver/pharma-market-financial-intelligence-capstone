from __future__ import annotations

from contextlib import contextmanager

from frontend import lakebase


def test_notes_returns_joined_investigation_context(monkeypatch):
    expected = [{"note_text": "Reviewed", "investigation_title": "California review"}]
    captured = {}

    def fake_query(statement, params=()):
        captured["statement"] = statement
        captured["params"] = params
        return expected

    monkeypatch.setattr(lakebase, "query", fake_query)

    assert lakebase.notes() == expected
    assert captured["params"] == ()
    rendered = repr(captured["statement"])
    assert "analyst_notes" in rendered
    assert "investigations" in rendered


class FakeCursor:
    def __init__(self):
        self.call = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, statement, params):
        self.call = (statement, params)


class FakeConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        raise AssertionError("Valid note should not roll back")


def test_add_note_validates_and_commits(monkeypatch):
    database = FakeConnection()

    @contextmanager
    def fake_connection():
        yield database

    monkeypatch.setattr(lakebase, "connection", fake_connection)
    investigation_id = "a5a80cb4-01a4-4b6a-a4b3-fe3e01f0384f"

    note_id = lakebase.add_note(investigation_id, "  Reviewed   by controller. ")

    assert note_id
    assert database.committed
    assert database.cursor_instance.call[1][1:] == (
        investigation_id,
        "Reviewed by controller.",
        "Frontend controller",
    )
