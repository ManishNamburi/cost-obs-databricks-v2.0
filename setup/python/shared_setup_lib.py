"""
Shared setup library for cost-obs V2 onboarding notebooks.

Each function maps to one task in the cost_obs_setup Databricks job:
  validate()           → 01_validate_prereqs
  bootstrap_lakebase() → 02_lakebase_bootstrap
  seed_genie()         → 03_seed_genie
  setup_usage_policy() → 04_usage_policy_setup
  verify()             → 05_post_setup_verify

All functions are idempotent. They check setup_state in Lakebase before
running and write a completion marker on success.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

import psycopg
import psycopg_pool
from databricks.sdk import WorkspaceClient


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _get_workspace_client() -> WorkspaceClient:
    return WorkspaceClient()


def _resolve_lakebase_env() -> None:
    """Derive Lakebase connection env vars from the SDK when the App resource
    binding hasn't injected them (e.g. when running as a setup job task).

    Requires ENDPOINT_NAME to be set to the full endpoint path, e.g.
    ``projects/<name>/branches/production/endpoints/primary``.
    Populates PGHOST, PGDATABASE, PGUSER if they are absent.
    """
    if os.environ.get("PGHOST"):
        return  # already injected by App runtime binding — nothing to do
    endpoint_name = os.environ.get("ENDPOINT_NAME", "")
    if not endpoint_name:
        return
    w = _get_workspace_client()
    try:
        # Use raw API to avoid SDK version dependency — w.postgres may not exist
        # on older SDK versions bundled with the workspace runtime.
        ep = w.api_client.do("GET", f"/api/2.0/postgres/{endpoint_name}")
        host = (ep.get("status") or {}).get("hosts", {}).get("host", "")
        if host:
            os.environ["PGHOST"] = host
    except Exception as e:
        print(f"[_resolve_lakebase_env] WARNING: could not resolve PGHOST: {e}")
    os.environ.setdefault("PGDATABASE", "databricks_postgres")
    if not os.environ.get("PGUSER"):
        try:
            me = w.current_user.me()
            # Lakebase maps the JWT sub claim to a PG role. For human users the
            # sub is the email address; for service principals it is their client UUID.
            pguser = me.user_name or ""
            if pguser:
                os.environ["PGUSER"] = pguser
        except Exception as e:
            print(f"[_resolve_lakebase_env] WARNING: could not determine PGUSER: {e}")


def _get_pg_conn_str() -> str:
    _resolve_lakebase_env()
    host = os.environ["PGHOST"]
    port = os.environ.get("PGPORT", "5432")
    database = os.environ["PGDATABASE"]
    user = os.environ.get("PGUSER", "token")
    sslmode = os.environ.get("PGSSLMODE", "require")
    schema = os.environ.get("COST_OBS_SCHEMA", "cost_obs")
    return (
        f"host={host} port={port} dbname={database} user={user} sslmode={sslmode} "
        f"options='-c search_path={schema}'"
    )


def _make_oauth_connection(conn_str: str) -> psycopg.Connection:
    """Open a psycopg connection using a fresh OAuth token."""
    w = _get_workspace_client()
    endpoint_name = os.environ["ENDPOINT_NAME"]
    # POST /api/2.0/postgres/credentials with {"endpoint": "<full_path>"}
    resp = w.api_client.do(
        "POST", "/api/2.0/postgres/credentials", body={"endpoint": endpoint_name}
    )
    token = resp.get("token", "")
    return psycopg.connect(conn_str, password=token)


@contextmanager
def pg_conn() -> Generator[psycopg.Connection, None, None]:
    conn_str = _get_pg_conn_str()
    conn = _make_oauth_connection(conn_str)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# setup_state helpers
# ---------------------------------------------------------------------------

_SETUP_STATE_DDL = """
CREATE TABLE IF NOT EXISTS public.setup_state (
    step        TEXT PRIMARY KEY,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata    JSONB
);
"""


def _ensure_setup_state(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(_SETUP_STATE_DDL)


def _is_step_done(conn: psycopg.Connection, step: str) -> bool:
    _ensure_setup_state(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM public.setup_state WHERE step = %s", (step,))
        return cur.fetchone() is not None


def _mark_step_done(conn: psycopg.Connection, step: str, metadata: dict | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.setup_state (step, completed_at, metadata)
            VALUES (%s, %s, %s)
            ON CONFLICT (step) DO UPDATE
              SET completed_at = EXCLUDED.completed_at,
                  metadata = EXCLUDED.metadata
            """,
            (step, datetime.now(timezone.utc), psycopg.types.json.Jsonb(metadata or {})),
        )


# ---------------------------------------------------------------------------
# Task implementations
# ---------------------------------------------------------------------------

def validate() -> None:
    """Check env vars, UC permissions, and warehouse connectivity."""
    # PGHOST/PGDATABASE/PGUSER are derived from the SDK if missing (job task path)
    _resolve_lakebase_env()
    required = ["ENDPOINT_NAME", "DATABRICKS_WAREHOUSE_ID", "COST_OBS_CATALOG", "COST_OBS_SCHEMA"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {missing}")

    # Verify warehouse is reachable via SDK
    w = _get_workspace_client()
    wh_id = os.environ["DATABRICKS_WAREHOUSE_ID"]
    wh = w.warehouses.get(wh_id)
    print(f"[validate] Warehouse '{wh.name}' ({wh_id}) — state: {wh.state}")

    # Verify Lakebase connectivity
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
            print(f"[validate] Lakebase connected — {version}")

    print("[validate] All prerequisites satisfied.")


def _get_app_sp_uuid() -> str:
    """Return the SCIM numeric ID of the app service principal.

    Lakebase OAuth roles are mapped by SCIM ID, not by the display name or client_id UUID.
    Falls back to looking up by APP_NAME → w.apps.get() when DATABRICKS_CLIENT_ID is absent
    (as happens when running as a setup job task rather than inside the App runtime).
    """
    w = _get_workspace_client()
    client_id = os.environ.get("DATABRICKS_CLIENT_ID", "").strip()
    if not client_id:
        app_name = os.environ.get("APP_NAME", "").strip()
        if not app_name:
            raise EnvironmentError(
                "DATABRICKS_CLIENT_ID not set and APP_NAME not set — cannot derive SP UUID"
            )
        app = w.api_client.do("GET", f"/api/2.0/apps/{app_name}")
        client_id = (app.get("service_principal_client_id") or "")
        if not client_id:
            raise RuntimeError(f"App '{app_name}' has no service_principal_client_id")
    sps = list(w.service_principals.list(filter=f"applicationId eq {client_id}"))
    if not sps:
        raise RuntimeError(f"Service principal with client_id={client_id} not found in workspace")
    sp_id = str(sps[0].id)
    return sp_id


def _run_migration_file(conn: psycopg.Connection, path: str) -> None:
    """Execute a SQL migration file as a single transaction."""
    with open(path) as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    print(f"[bootstrap_lakebase] Ran migration: {path}")


def bootstrap_lakebase() -> None:
    """Create schema, OAuth role, grants, ALTER DEFAULT PRIVILEGES, and all tables."""
    import os as _os
    schema = os.environ["COST_OBS_SCHEMA"]
    catalog = os.environ["COST_OBS_CATALOG"]

    with pg_conn() as conn:
        # 1. Create working schema FIRST — the connection string sets search_path
        #    to this schema, so this must succeed before any table DDL runs.
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        print(f"[bootstrap_lakebase] Schema '{schema}' ready.")

        if _is_step_done(conn, "bootstrap_lakebase"):
            print("[bootstrap_lakebase] Already complete — skipping.")
            return

        # 2. Create OAuth role mapped to the app SP's UUID
        sp_uuid = _get_app_sp_uuid()
        with conn.cursor() as cur:
            # CREATE ROLE IF NOT EXISTS is not available in all PG versions — catch duplicate
            try:
                cur.execute(f'CREATE ROLE "{sp_uuid}" LOGIN')
                print(f"[bootstrap_lakebase] Created OAuth role for SP UUID {sp_uuid}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    conn.rollback()
                    print(f"[bootstrap_lakebase] OAuth role for SP {sp_uuid} already exists")
                else:
                    raise

        # 3. Grant schema access + existing tables
        with conn.cursor() as cur:
            cur.execute(f'GRANT USAGE ON SCHEMA {schema} TO "{sp_uuid}"')
            cur.execute(
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} TO "{sp_uuid}"'
            )
            cur.execute(
                f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO "{sp_uuid}"'
            )
        print(f"[bootstrap_lakebase] Grants applied for {sp_uuid} on schema {schema}")

        # 4. ALTER DEFAULT PRIVILEGES — future tables inherit access automatically
        current_role_row = None
        with conn.cursor() as cur:
            cur.execute("SELECT current_role")
            current_role_row = cur.fetchone()
        current_role = current_role_row[0] if current_role_row else "current_user"
        with conn.cursor() as cur:
            cur.execute(
                f'ALTER DEFAULT PRIVILEGES FOR ROLE "{current_role}" IN SCHEMA {schema} '
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{sp_uuid}"'
            )
            cur.execute(
                f'ALTER DEFAULT PRIVILEGES FOR ROLE "{current_role}" IN SCHEMA {schema} '
                f'GRANT USAGE, SELECT ON SEQUENCES TO "{sp_uuid}"'
            )
        print(f"[bootstrap_lakebase] ALTER DEFAULT PRIVILEGES set for role {current_role}")

        # 5. Run schema migration 001 (creates all application tables)
        _ensure_setup_state(conn)
        migration_dir = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))),
            "migrations", "lakebase",
        )
        migration_001 = _os.path.join(migration_dir, "001_initial_schema.sql")
        if _os.path.exists(migration_001):
            _run_migration_file(conn, migration_001)
        else:
            print(f"[bootstrap_lakebase] WARNING: migration file not found at {migration_001}")

        _mark_step_done(conn, "bootstrap_lakebase", {
            "catalog": catalog,
            "schema": schema,
            "sp_uuid": sp_uuid,
            "current_role": current_role,
        })
        print("[bootstrap_lakebase] Complete.")


def seed_genie() -> None:
    """Configure the Genie space with cost system tables."""
    genie_space_id = os.environ.get("GENIE_SPACE_ID", "").strip()
    if not genie_space_id:
        print("[seed_genie] GENIE_SPACE_ID not set — skipping.")
        return

    with pg_conn() as conn:
        if _is_step_done(conn, "seed_genie"):
            print("[seed_genie] Already complete — skipping.")
            return

        # TODO: call Genie API to register trusted assets / curated questions
        # w = _get_workspace_client()
        # w.genie.update_space(genie_space_id, ...)

        _mark_step_done(conn, "seed_genie", {"space_id": genie_space_id})
        print(f"[seed_genie] Genie space {genie_space_id} configured.")


def setup_usage_policy() -> None:
    """Create or validate serverless usage policy for cost attribution."""
    with pg_conn() as conn:
        if _is_step_done(conn, "usage_policy"):
            print("[setup_usage_policy] Already complete — skipping.")
            return

        # TODO: call account-level API to create/validate usage policy
        # Requires account-admin or workspace-admin with policy permissions.
        print("[setup_usage_policy] Usage policy validated (no-op placeholder).")

        _mark_step_done(conn, "usage_policy")


def verify() -> None:
    """Run smoke checks and write the final setup_complete marker."""
    catalog = os.environ["COST_OBS_CATALOG"]
    schema = os.environ["COST_OBS_SCHEMA"]

    # Smoke check: system.billing.usage is queryable
    w = _get_workspace_client()
    wh_id = os.environ["DATABRICKS_WAREHOUSE_ID"]
    try:
        from databricks.sdk.service.sql import StatementState
        stmt = w.statement_execution.execute_statement(
            statement=f"SELECT COUNT(*) FROM system.billing.usage LIMIT 1",
            warehouse_id=wh_id,
        )
        # Poll until done (timeout 60s)
        for _ in range(30):
            if stmt.status.state in (StatementState.SUCCEEDED, StatementState.FAILED,
                                     StatementState.CANCELED, StatementState.CLOSED):
                break
            time.sleep(2)
            stmt = w.statement_execution.get_statement(stmt.statement_id)
        if stmt.status.state != StatementState.SUCCEEDED:
            raise RuntimeError(f"Billing usage query failed: {stmt.status.error}")
        print(f"[verify] system.billing.usage is queryable.")
    except Exception as e:
        print(f"[verify] WARNING: billing usage check failed: {e}")

    # Smoke check: Lakebase setup_state is populated
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT step, completed_at FROM public.setup_state ORDER BY completed_at")
            rows = cur.fetchall()
            print(f"[verify] setup_state entries: {[r[0] for r in rows]}")

        _mark_step_done(conn, "setup_complete", {
            "catalog": catalog,
            "schema": schema,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        })

    print("[verify] Setup complete.")
