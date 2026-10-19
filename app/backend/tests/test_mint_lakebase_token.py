from types import SimpleNamespace

from backend.db import mint_lakebase_token


class _Cred:
    def __init__(self, token):
        self.token = token


def test_mint_uses_sdk_postgres_when_present(monkeypatch):
    seen = {}

    class _Postgres:
        def generate_database_credential(self, endpoint):
            seen["endpoint"] = endpoint
            return _Cred("sdk-token")

    monkeypatch.setattr(
        "backend.db.get_workspace_client",
        lambda: SimpleNamespace(postgres=_Postgres()),
    )
    assert mint_lakebase_token("projects/cost-obs-db/branches/production/endpoints/primary") == "sdk-token"
    assert seen["endpoint"].endswith("primary")


def test_mint_falls_back_to_raw_credentials_api(monkeypatch):
    class _Client:
        postgres = None

        class api_client:
            @staticmethod
            def do(method, path, body=None):
                assert method == "POST"
                assert path == "/api/2.0/postgres/credentials"
                return {"token": "raw-token"}

    monkeypatch.setattr("backend.db.get_workspace_client", lambda: _Client())
    assert mint_lakebase_token("projects/x/branches/production/endpoints/primary") == "raw-token"
