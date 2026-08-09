from __future__ import annotations

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
