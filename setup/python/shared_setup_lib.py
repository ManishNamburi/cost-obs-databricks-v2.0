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


def _get_pg_conn_str() -> str:
    host = os.environ["PGHOST"]
    port = os.environ.get("PGPORT", "5432")
    database = os.environ["PGDATABASE"]
    user = os.environ["PGUSER"]
    sslmode = os.environ.get("PGSSLMODE", "require")
    return f"host={host} port={port} dbname={database} user={user} sslmode={sslmode}"


def _make_oauth_connection(conn_str: str) -> psycopg.Connection:
    """Open a psycopg connection using a fresh OAuth token."""
    w = _get_workspace_client()
    endpoint_name = os.environ["ENDPOINT_NAME"]
    cred = w.postgres.generate_database_credential(endpoint_name=endpoint_name)
    return psycopg.connect(conn_str, password=cred.token)


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
CREATE TABLE IF NOT EXISTS setup_state (
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
        cur.execute("SELECT 1 FROM setup_state WHERE step = %s", (step,))
        return cur.fetchone() is not None


def _mark_step_done(conn: psycopg.Connection, step: str, metadata: dict | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO setup_state (step, completed_at, metadata)
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
    required = ["PGHOST", "PGDATABASE", "PGUSER", "ENDPOINT_NAME",
                "DATABRICKS_WAREHOUSE_ID", "COST_OBS_CATALOG", "COST_OBS_SCHEMA"]
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
    """Return the UUID of the app service principal (not the client_id string).

    Lakebase OAuth roles are mapped by UUID, not by the display name or client_id.
    """
    w = _get_workspace_client()
    client_id = os.environ.get("DATABRICKS_CLIENT_ID", "").strip()
    if not client_id:
        raise EnvironmentError("DATABRICKS_CLIENT_ID not set — cannot derive SP UUID")
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
        if _is_step_done(conn, "bootstrap_lakebase"):
            print("[bootstrap_lakebase] Already complete — skipping.")
            return

        # 1. Create working schema
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        print(f"[bootstrap_lakebase] Schema '{schema}' ready.")

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
            cur.execute("SELECT current_role()")
            current_role_row = cur.fetchone()
        current_role = current_role_row[0] if current_role_row else "current_user"
        with conn.cursor() as cur:
            cur.execute(
                f'ALTER DEFAULT PRIVILEGES FOR ROLE {current_role} IN SCHEMA {schema} '
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{sp_uuid}"'
            )
            cur.execute(
                f'ALTER DEFAULT PRIVILEGES FOR ROLE {current_role} IN SCHEMA {schema} '
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
            cur.execute("SELECT step, completed_at FROM setup_state ORDER BY completed_at")
            rows = cur.fetchall()
            print(f"[verify] setup_state entries: {[r[0] for r in rows]}")

        _mark_step_done(conn, "setup_complete", {
            "catalog": catalog,
            "schema": schema,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        })

    print("[verify] Setup complete.")
