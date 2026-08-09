from __future__ import annotations

from types import SimpleNamespace

from mcp_server import lakebase


class FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _set_required_environment(monkeypatch) -> None:
    monkeypatch.setenv("ENDPOINT_NAME", "projects/p/branches/b/endpoints/e")
    monkeypatch.setenv("PGDATABASE", "databricks_postgres")
    monkeypatch.setenv("PGPORT", "5432")
    monkeypatch.setenv("PGSSLMODE", "require")
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv("PGUSER", raising=False)


def test_connection_derives_host_and_current_user(monkeypatch) -> None:
    _set_required_environment(monkeypatch)
    requested = {}
    endpoint = SimpleNamespace(
        status=SimpleNamespace(hosts=SimpleNamespace(host="endpoint.database.databricks.com"))
    )

    def get_endpoint(name: str):
        requested["endpoint_name"] = name
        return endpoint

    def generate_database_credential(endpoint: str):
        requested["credential_endpoint"] = endpoint
        return SimpleNamespace(token="temporary-token")

    client = SimpleNamespace(
        postgres=SimpleNamespace(
            get_endpoint=get_endpoint,
            generate_database_credential=generate_database_credential,
        ),
        current_user=SimpleNamespace(me=lambda: SimpleNamespace(user_name="analyst@example.com")),
    )
    monkeypatch.setattr(lakebase, "WorkspaceClient", lambda: client)

    captured = {}
    connection = FakeConnection()

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return connection

    monkeypatch.setattr(lakebase.psycopg2, "connect", fake_connect)

    with lakebase.get_connection() as opened:
        assert opened is connection

    assert requested == {
        "endpoint_name": "projects/p/branches/b/endpoints/e",
        "credential_endpoint": "projects/p/branches/b/endpoints/e",
    }
    assert captured["host"] == "endpoint.database.databricks.com"
    assert captured["user"] == "analyst@example.com"
    assert captured["dbname"] == "databricks_postgres"
    assert captured["port"] == 5432
    assert captured["password"] == "temporary-token"
    assert connection.closed


def test_connection_preserves_injected_app_settings(monkeypatch) -> None:
    _set_required_environment(monkeypatch)
    monkeypatch.setenv("PGHOST", "injected-app-host")
    monkeypatch.setenv("PGUSER", "injected-app-role")

    def unexpected_call(*args, **kwargs):
        raise AssertionError("Injected App metadata should be used")

    client = SimpleNamespace(
        postgres=SimpleNamespace(
            get_endpoint=unexpected_call,
            generate_database_credential=lambda endpoint: SimpleNamespace(token="temporary-token"),
        ),
        current_user=SimpleNamespace(me=unexpected_call),
    )
    monkeypatch.setattr(lakebase, "WorkspaceClient", lambda: client)
    connection = FakeConnection()
    monkeypatch.setattr(lakebase.psycopg2, "connect", lambda **kwargs: connection)

    with lakebase.get_connection() as opened:
        assert opened is connection

    assert connection.closed
