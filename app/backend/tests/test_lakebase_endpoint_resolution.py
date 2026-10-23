from types import SimpleNamespace

import pytest

from backend import db


def _ep(name, host):
    return SimpleNamespace(
        name=name,
        status=SimpleNamespace(hosts=SimpleNamespace(
            host=host, read_write_pooled_host=None, read_only_host=None, read_only_pooled_host=None,
        )),
    )


@pytest.fixture
def fake_postgres(monkeypatch):
    postgres = SimpleNamespace(
        list_projects=lambda: [SimpleNamespace(name="projects/cost-obs-db")],
        list_branches=lambda parent: [SimpleNamespace(name=f"{parent}/branches/production")],
        list_endpoints=lambda parent: [
            _ep(f"{parent}/endpoints/replica", "other.host"),
            _ep(f"{parent}/endpoints/primary", "ep-primary.host"),
        ],
    )
    monkeypatch.setattr(db, "get_workspace_client", lambda: SimpleNamespace(postgres=postgres))
    monkeypatch.setattr(db, "_endpoint_resolution_done", False)
    monkeypatch.setattr(db, "_endpoint_unresolved", False)
    monkeypatch.delenv("ENDPOINT_NAME", raising=False)
    return postgres


def test_resolves_endpoint_from_pghost(fake_postgres, monkeypatch):
    monkeypatch.setenv("PGHOST", "ep-primary.host")
    assert db._ensure_lakebase_endpoint() is True
    assert db.os.environ["ENDPOINT_NAME"] == "projects/cost-obs-db/branches/production/endpoints/primary"


def test_disables_lakebase_when_no_endpoint_matches(fake_postgres, monkeypatch):
    monkeypatch.setenv("PGHOST", "unknown.host")
    monkeypatch.setenv("PGUSER", "sp")
    assert db._ensure_lakebase_endpoint() is False
    assert db._lakebase_conninfo() == ""
    calls = []
    fake_postgres.list_projects = lambda: calls.append(1) or []
    assert db._ensure_lakebase_endpoint() is False
    assert calls == []


def test_lookup_error_disables_instead_of_hanging(monkeypatch):
    def boom():
        raise RuntimeError("403")
    monkeypatch.setattr(db, "get_workspace_client", lambda: SimpleNamespace(postgres=SimpleNamespace(list_projects=boom)))
    monkeypatch.setattr(db, "_endpoint_resolution_done", False)
    monkeypatch.setattr(db, "_endpoint_unresolved", False)
    monkeypatch.delenv("ENDPOINT_NAME", raising=False)
    monkeypatch.setenv("PGHOST", "ep-primary.host")
    assert db._ensure_lakebase_endpoint() is False


def test_explicit_endpoint_skips_lookup(monkeypatch):
    monkeypatch.setattr(db, "get_workspace_client", lambda: pytest.fail("should not list projects"))
    monkeypatch.setenv("ENDPOINT_NAME", "projects/p/branches/b/endpoints/e")
    monkeypatch.setenv("PGHOST", "ep-primary.host")
    assert db._ensure_lakebase_endpoint() is True
