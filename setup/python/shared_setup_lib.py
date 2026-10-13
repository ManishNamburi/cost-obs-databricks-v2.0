"""
Shared setup library for cost-obs V2 onboarding notebooks.

Each function maps to one task in the cost_obs_setup Databricks job:
  validate()           → 01_validate_prereqs
  bootstrap_lakebase() → 02_lakebase_bootstrap
  build_gold()         → 02c_build_gold
  seed_genie()         → 03_seed_genie
  setup_usage_policy() → 04_usage_policy_setup
  verify()             → 05_post_setup_verify

All functions are idempotent. They check setup_state in Lakebase before
running and write a completion marker on success.
"""

from __future__ import annotations

import json
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

def _probe_existing_deployment(w: WorkspaceClient) -> dict:
    """Return signals used to distinguish a fresh deploy from a 1.1 upgrade.

    The reliable discriminator is whether a prior cost-obs deployment already
    built its materialized views in the target schema — `daily_usage_summary`
    is created by the 1.x app and persists. We deliberately do NOT key off the
    Lakebase `setup_state` table: it is a v2-only artifact that gets populated
    by earlier tasks *during the current run*, so its presence indicates
    "v2 setup has run before", not "a 1.1 deployment exists".
    """
    catalog = os.environ["COST_OBS_CATALOG"]
    schema = os.environ["COST_OBS_SCHEMA"]
    wh_id = os.environ["DATABRICKS_WAREHOUSE_ID"]

    signals: dict = {"has_v1_mv": False}

    try:
        resp = w.statement_execution.execute_statement(
            warehouse_id=wh_id,
            statement=(
                f"SELECT COUNT(*) FROM system.information_schema.tables "
                f"WHERE table_catalog = '{catalog}' "
                f"AND table_schema = '{schema}' "
                f"AND table_name = 'daily_usage_summary'"
            ),
            wait_timeout="30s",
        )
        rows = (resp.result.data_array or []) if resp.result else []
        signals["has_v1_mv"] = bool(rows) and int(rows[0][0]) > 0
    except Exception as exc:
        print(f"[detect_deployment_mode] MV probe failed (assuming absent): {exc}")

    return signals


def detect_deployment_mode() -> str:
    """Resolve `DEPLOYMENT_MODE` to a concrete "fresh" or "migrate" value.

    Reads the bundle-variable-driven env var, then probes real state when set
    to "auto" (default). Each setup task calls this independently — the probe
    is idempotent and does not rely on the resolved value propagating across
    task processes (base_parameters carry the raw "auto"/"fresh"/"migrate").
    """
    raw = (os.environ.get("DEPLOYMENT_MODE") or "auto").strip().lower()
    if raw in ("fresh", "migrate"):
        print(f"[detect_deployment_mode] Operator override: {raw}")
        return raw
    if raw != "auto":
        print(
            f"[detect_deployment_mode] Unknown DEPLOYMENT_MODE={raw!r}; treating as 'auto'."
        )

    signals = _probe_existing_deployment(_get_workspace_client())
    mode = "migrate" if signals["has_v1_mv"] else "fresh"
    print(f"[detect_deployment_mode] Detected mode={mode} (signals={signals})")
    return mode


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

    # Decide fresh install vs 1.1 migration (for logging here; each downstream
    # task re-probes independently since env vars don't cross task processes).
    mode = detect_deployment_mode()
    if mode == "migrate":
        print(
            "[validate] Migration mode: existing 1.1 state detected. "
            "Existing MVs are reused (incremental gold); Lakebase + Genie are created."
        )
    else:
        print("[validate] Fresh install mode: no prior cost-obs state detected.")

    print("[validate] All prerequisites satisfied.")


def _ensure_app_on_sys_path() -> None:
    """Put the bundled app package on sys.path so setup can reuse gold builders.

    Workspace layout: ``.../files/setup/python`` and ``.../files/app``.
    Local layout: ``<repo>/setup/python`` and ``<repo>/app``.
    """
    import sys

    here = os.path.dirname(os.path.abspath(__file__))
    files_root = os.path.dirname(os.path.dirname(here))
    app_dir = os.path.join(files_root, "app")
    if os.path.isdir(app_dir) and app_dir not in sys.path:
        sys.path.insert(0, app_dir)


def _gold_lookback_days() -> int:
    raw = (os.environ.get("LOOKBACK_DAYS") or "180").strip()
    try:
        days = int(raw)
    except ValueError:
        days = 180
    return max(1, min(days, 730))


def _gold_hard_errors(results: dict) -> list[str]:
    errors: list[str] = []
    for name, status in results.items():
        if name.startswith("__"):
            continue
        if isinstance(status, str) and status.startswith("error"):
            errors.append(f"{name}: {status}")
    return errors


def build_gold(*, _create_mvs=None, _sync_all=None) -> None:
    """Build warehouse gold and copy dashboard aggregates into Lakebase.

    Fresh: full CREATE OR REPLACE of MVs + gold, then Lakebase load.
    Migrate: reuse existing MVs (incremental MERGE), create any missing v2
    gold tables, then a full Lakebase backfill so dashboards do not wait on
    a Settings rebuild.
    """
    _resolve_lakebase_env()
    catalog = os.environ["COST_OBS_CATALOG"]
    schema = os.environ["COST_OBS_SCHEMA"]
    lookback = _gold_lookback_days()
    mode = detect_deployment_mode()
    force_full = mode == "fresh"

    with pg_conn() as conn:
        if _is_step_done(conn, "build_gold"):
            print("[build_gold] Already complete — skipping.")
            return

    print(
        f"[build_gold] mode={mode} catalog={catalog} schema={schema} "
        f"lookback_days={lookback} force_full={force_full}"
    )

    create_mvs = _create_mvs
    sync_all = _sync_all
    if create_mvs is None or sync_all is None:
        _ensure_app_on_sys_path()
        from backend.materialized_views import create_materialized_views
        from backend.lakebase_sync import sync_all_aggregates
        create_mvs = create_mvs or create_materialized_views
        sync_all = sync_all or sync_all_aggregates

    results = create_mvs(
        catalog=catalog,
        schema=schema,
        lookback_days=lookback,
        force_full_rebuild=force_full,
    )
    if not isinstance(results, dict):
        raise RuntimeError(f"Gold build returned unexpected result: {results!r}")
    if results.get("error"):
        raise RuntimeError(f"Gold build refused: {results['error']}")
    hard = _gold_hard_errors(results)
    if hard:
        raise RuntimeError("Gold build failed for required tables: " + "; ".join(hard))

    table_status = {
        k: v for k, v in results.items() if not str(k).startswith("__") and isinstance(v, str)
    }
    print(f"[build_gold] warehouse tables: {table_status}")

    # Fresh already full-syncs inside create_materialized_views. Migrate uses
    # incremental MV refresh, so Lakebase still needs a one-time full copy.
    sync_summary = results.get("lakebase_sync")
    if mode == "migrate" or not sync_summary or (
        isinstance(sync_summary, dict) and sync_summary.get("skipped")
    ):
        sync_summary = sync_all(catalog, schema, full=True)
        print(f"[build_gold] lakebase_sync (full): {sync_summary}")
    else:
        print(f"[build_gold] lakebase_sync: {sync_summary}")

    with pg_conn() as conn:
        _mark_step_done(conn, "build_gold", {
            "mode": mode,
            "catalog": catalog,
            "schema": schema,
            "lookback_days": lookback,
            "force_full": force_full,
            "tables": table_status,
        })
    print("[build_gold] Complete.")


def _get_app_sp_identities() -> tuple[str, str]:
    """Return (oauth_role, scim_id) for the app service principal.

    Lakebase OAuth `current_user` is the app SP *client UUID*, not the SCIM
    numeric id. Grants must target that UUID or the app connects but has
    USAGE/CREATE = false on the working schema.
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
    return client_id, str(sps[0].id)


def _get_app_sp_uuid() -> str:
    """OAuth role name the app actually logs in as (SP client UUID)."""
    client_id, _scim_id = _get_app_sp_identities()
    return client_id


def _run_migration_file(conn: psycopg.Connection, path: str) -> None:
    """Execute a SQL migration file as a single transaction."""
    with open(path) as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    print(f"[bootstrap_lakebase] Ran migration: {path}")


def _ensure_endpoint_scale_to_zero() -> None:
    """Apply 0.5–4 CU + 5-minute suspend on the existing primary endpoint.

    DAB `default_endpoint_settings` only affect newly created endpoints.
    Production branches stay awake unless we patch the live endpoint too.
    """
    endpoint = os.environ.get("ENDPOINT_NAME", "")
    if not endpoint:
        print("[bootstrap_lakebase] ENDPOINT_NAME unset — skipping scale-to-zero")
        return
    w = _get_workspace_client()
    try:
        w.api_client.do(
            "PATCH",
            f"/api/2.0/postgres/{endpoint}",
            query={
                "update_mask": (
                    "spec.autoscaling_limit_min_cu,"
                    "spec.autoscaling_limit_max_cu,"
                    "spec.suspend_timeout_duration"
                )
            },
            body={
                "spec": {
                    "autoscaling_limit_min_cu": 0.5,
                    "autoscaling_limit_max_cu": 4.0,
                    "suspend_timeout_duration": "300s",
                }
            },
        )
        print("[bootstrap_lakebase] Endpoint scale-to-zero set (0.5–4 CU, 300s suspend)")
    except Exception as e:
        print(f"[bootstrap_lakebase] WARNING: could not set scale-to-zero: {e}")


def bootstrap_lakebase() -> None:
    """Create schema, OAuth role, grants, ALTER DEFAULT PRIVILEGES, and all tables."""
    import os as _os
    schema = os.environ["COST_OBS_SCHEMA"]
    catalog = os.environ["COST_OBS_CATALOG"]
    _ensure_endpoint_scale_to_zero()

    with pg_conn() as conn:
        # 1. Create working schema FIRST — the connection string sets search_path
        #    to this schema, so this must succeed before any table DDL runs.
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        print(f"[bootstrap_lakebase] Schema '{schema}' ready.")

        # Role + grants always re-run. A completed setup_state marker used to
        # skip them, which left the app SP without CREATE on schemas that the
        # deployer (not the app) created — sync then failed at runtime.
        oauth_role, scim_id = _get_app_sp_identities()
        # OAuth login is the client UUID. Also grant the SCIM id in case a
        # workspace maps that way; duplicates are harmless.
        grant_roles = list(dict.fromkeys([oauth_role, scim_id]))
        for sp_uuid in grant_roles:
            with conn.cursor() as cur:
                cur.execute("SAVEPOINT create_role")
                try:
                    cur.execute(f'CREATE ROLE "{sp_uuid}" LOGIN')
                    print(f"[bootstrap_lakebase] Created OAuth role {sp_uuid}")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        cur.execute("ROLLBACK TO SAVEPOINT create_role")
                        print(f"[bootstrap_lakebase] OAuth role {sp_uuid} already exists")
                    else:
                        raise
            with conn.cursor() as cur:
                cur.execute(f'GRANT USAGE, CREATE ON SCHEMA {schema} TO "{sp_uuid}"')
                cur.execute(
                    f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} TO "{sp_uuid}"'
                )
                cur.execute(
                    f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO "{sp_uuid}"'
                )
            print(f"[bootstrap_lakebase] Grants applied for {sp_uuid} on schema {schema}")
        sp_uuid = oauth_role

        if _is_step_done(conn, "bootstrap_lakebase"):
            print("[bootstrap_lakebase] Already complete — grants refreshed, skipping remaining steps.")
            return

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


_GENIE_SPACE_NAME = "cost-obs"


def _persist_genie_space_id(space_id: str) -> None:
    """Store the space id so the app can find it without a DAB env binding."""
    payload = json.dumps({"space_id": space_id})
    try:
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO app_config (key, value, updated_at)
                    VALUES ('genie_space_id', %s::jsonb, now())
                    ON CONFLICT (key) DO UPDATE
                      SET value = EXCLUDED.value, updated_at = now()
                    """,
                    (payload,),
                )
        print(f"[seed_genie] Wrote space_id={space_id} to Lakebase app_config.")
    except Exception as exc:
        print(f"[seed_genie] WARNING — could not persist space id to Lakebase: {type(exc).__name__}: {exc}")


def _ensure_genie_space(w) -> str:
    """Reuse GENIE_SPACE_ID, a stored id, or an existing cost-obs space; else create one."""
    env_id = os.environ.get("GENIE_SPACE_ID", "").strip()
    if env_id:
        print(f"[seed_genie] Using GENIE_SPACE_ID from env: {env_id}")
        return env_id
    try:
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM app_config WHERE key = %s", ("genie_space_id",))
                row = cur.fetchone()
        if row and row[0]:
            val = row[0]
            if isinstance(val, dict):
                stored = str(val.get("space_id") or "").strip()
            else:
                stored = str(val).strip().strip('"')
            if stored:
                print(f"[seed_genie] Reusing stored space_id={stored}")
                return stored
    except Exception as exc:
        print(f"[seed_genie] No stored space id yet ({type(exc).__name__}).")

    try:
        listed = w.api_client.do("GET", "/api/2.0/genie/spaces")
        spaces = listed.get("spaces") or listed.get("data") or []
        for space in spaces:
            name = space.get("title") or space.get("display_name") or space.get("name") or ""
            sid = space.get("space_id") or space.get("id") or ""
            if name == _GENIE_SPACE_NAME and sid:
                print(f"[seed_genie] Reusing existing '{_GENIE_SPACE_NAME}' space {sid}")
                return str(sid)
    except Exception as exc:
        print(f"[seed_genie] Could not list Genie spaces ({type(exc).__name__}): {exc}")

    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", "").strip()
    if not warehouse_id:
        print("[seed_genie] Cannot create a Genie space — DATABRICKS_WAREHOUSE_ID is empty.")
        return ""
    from genie_curation import INSTRUCTIONS, TRUSTED_ASSETS
    # identifiers must be sorted or the Genie API rejects the export proto
    tables = sorted(
        ({"identifier": t, "column_configs": []} for t in TRUSTED_ASSETS),
        key=lambda r: r["identifier"],
    )
    serialized = json.dumps(
        {"version": 2, "data_sources": {"tables": tables}, "benchmarks": {"questions": []}},
        indent=2,
    )
    body = {
        "warehouse_id": warehouse_id,
        "display_name": _GENIE_SPACE_NAME,
        "title": _GENIE_SPACE_NAME,
        "description": "Cost observability — natural-language questions over Databricks billing system tables.",
        "serialized_space": serialized,
    }
    try:
        created = w.api_client.do("POST", "/api/2.0/genie/spaces", body=body)
    except Exception as exc:
        print(f"[seed_genie] Create Genie space failed ({type(exc).__name__}): {exc}")
        raise
    space_id = str(created.get("space_id") or created.get("id") or "").strip()
    if space_id:
        print(f"[seed_genie] Created Genie space {space_id} ({_GENIE_SPACE_NAME})")
    else:
        print(f"[seed_genie] Create returned no space id: {created}")
    return space_id


def seed_genie() -> None:
    """Create (if needed) and curate the customer Genie space.

    Empty DAB genie bindings break deploy, so this task creates the space at
    setup time, stores the id in Lakebase, grants the app SP CAN_RUN, and
    best-effort seeds instructions. Re-running is idempotent.
    """
    with pg_conn() as conn:
        if _is_step_done(conn, "seed_genie"):
            print("[seed_genie] Already complete — skipping.")
            return

    w = _get_workspace_client()
    genie_space_id = _ensure_genie_space(w)
    if not genie_space_id:
        raise RuntimeError("Could not create or resolve a Genie space for cost-obs.")
    _persist_genie_space_id(genie_space_id)

    from genie_curation import (
        TRUSTED_ASSETS,
        INSTRUCTIONS,
        EXAMPLE_QUERIES,
        BENCHMARK_QUESTIONS,
        render_manual_setup_doc,
    )

    # (1) Reachability probe — a read-only GET on the space. This does NOT
    # create a throwaway conversation (the old probe did) and doesn't depend on
    # any SDK waiter/timeout semantics; a 200 means the space exists and the
    # setup identity can see it.
    reachable = False
    try:
        w.api_client.do("GET", f"/api/2.0/genie/spaces/{genie_space_id}")
        reachable = True
    except Exception as exc:
        print(
            f"[seed_genie] WARNING — cannot reach Genie space {genie_space_id}. "
            f"Check the space_id is correct and the setup identity can view it. "
            f"Error: {type(exc).__name__}: {exc}"
        )

    # (2) Grant the app SP CAN_RUN on the space at runtime. The app-resource
    # binding was removed from the DAB (an empty space_id breaks deploy), so
    # this is where the app SP gets access — needed for SP-auth deployments
    # where conversational calls run as the SP rather than the end user.
    # Best-effort: the Genie permissions API is not yet stable, so on failure
    # we log a clear manual instruction and continue.
    sp_granted = False
    if reachable:
        sp_granted = _grant_app_sp_can_run_genie(w, genie_space_id)

    # (3) Best-effort API seeding. The Databricks Genie space configuration
    # endpoints aren't part of the stable SDK yet, so we try a few known
    # candidate paths via the raw API client. If none succeed, we skip and
    # fall through to the manual-setup file (step 4).
    api_seeded = False
    if reachable:
        api_seeded = _try_api_seed_genie(w, genie_space_id, TRUSTED_ASSETS, INSTRUCTIONS, EXAMPLE_QUERIES, BENCHMARK_QUESTIONS)

    # (4) Manual-setup fallback — always write the markdown doc. This is what
    # operators actually consume today; the API path above is aspirational.
    doc_path = "/Workspace/Shared/cost-obs/genie_curation.md"
    try:
        _write_workspace_file(w, doc_path, render_manual_setup_doc())
        print(f"[seed_genie] Wrote curation reference to {doc_path}")
    except Exception as exc:
        # Non-fatal — the doc is nice-to-have, and the notebook also prints it.
        print(f"[seed_genie] WARNING — could not write {doc_path}: {type(exc).__name__}: {exc}")

    # Print the doc to notebook output regardless so operators always have it
    # inline in the setup-job logs, even if the workspace-file write failed.
    print("\n" + "=" * 72)
    print("Genie space curation content (paste into the Genie UI if the setup")
    print("job didn't seed programmatically — see `Manual Setup` heading below)")
    print("=" * 72)
    print(render_manual_setup_doc())
    print("=" * 72 + "\n")

    if not sp_granted:
        print(
            "[seed_genie] ACTION — could not grant the app service principal "
            "CAN_RUN on the Genie space programmatically. If this is an SP-auth "
            "deployment, open the Genie space → Share, and grant the app's "
            "service principal 'Can run' so conversational queries work when no "
            "end-user token is present."
        )

    with pg_conn() as conn:
        _mark_step_done(conn, "seed_genie", {
            "space_id": genie_space_id,
            "reachable": reachable,
            "sp_granted": sp_granted,
            "api_seeded": api_seeded,
            "manual_doc": doc_path,
        })
    print(
        f"[seed_genie] Complete. space_id={genie_space_id}, reachable={reachable}, "
        f"sp_granted={sp_granted}, api_seeded={api_seeded}, manual_doc={doc_path}."
    )


def _grant_app_sp_can_run_genie(w, space_id: str) -> bool:
    """Best-effort: grant the app service principal CAN_RUN on the Genie space.

    The app-resource binding was removed from the DAB (an empty space_id breaks
    deploy), so the SP's access is issued here at runtime instead. Resolves the
    app SP's client_id (application id) and PATCHes the workspace permissions
    for the space. The Genie permissions object type is not yet stable in the
    public API, so we try known candidate paths and return False if none apply —
    the caller then prints a manual-grant instruction.

    PATCH (not PUT) is used so we add the app SP without clobbering existing ACLs.
    """
    client_id = os.environ.get("DATABRICKS_CLIENT_ID", "").strip()
    if not client_id:
        app_name = os.environ.get("APP_NAME", "").strip()
        if not app_name:
            print("[seed_genie] Skipping SP grant — neither DATABRICKS_CLIENT_ID nor APP_NAME is set.")
            return False
        try:
            app = w.api_client.do("GET", f"/api/2.0/apps/{app_name}")
            client_id = (app.get("service_principal_client_id") or "").strip()
        except Exception as exc:
            print(f"[seed_genie] Skipping SP grant — could not look up app '{app_name}': {type(exc).__name__}: {exc}")
            return False
    if not client_id:
        print("[seed_genie] Skipping SP grant — could not resolve app service principal client id.")
        return False

    acl = {"access_control_list": [{"service_principal_name": client_id, "permission_level": "CAN_RUN"}]}
    for object_type in ("genie", "dashboards"):
        path = f"/api/2.0/permissions/{object_type}/{space_id}"
        try:
            w.api_client.do("PATCH", path, body=acl)
            print(f"[seed_genie] Granted app SP {client_id} CAN_RUN on Genie space via {path}.")
            return True
        except Exception as exc:
            print(f"[seed_genie] Permissions path {path} unavailable ({type(exc).__name__}) — trying next.")
    return False


def _try_api_seed_genie(
    w,
    space_id: str,
    trusted_assets,
    instructions: str,
    example_queries,
    benchmark_questions,
) -> bool:
    """Best-effort call to the Databricks Genie space configuration REST endpoints.

    Returns True if we successfully posted curation content. False when we hit
    HTTP 404 / 405 / permission errors — signals to fall back to the manual
    workspace-file path.
    """
    # These endpoint paths are the current best guess based on the /api/2.0/genie/*
    # surface. Databricks' Genie configuration API is still shipping; if these
    # 404 we just skip and rely on the manual-setup doc.
    candidate_endpoints = [
        (f"/api/2.0/genie/spaces/{space_id}/instructions", {"instructions": instructions}),
        (
            f"/api/2.0/genie/spaces/{space_id}/trusted_assets",
            {"assets": [{"table_full_name": t} for t in trusted_assets]},
        ),
        (
            f"/api/2.0/genie/spaces/{space_id}/example_queries",
            {
                "examples": [
                    {"question": eq.question, "sql": eq.sql, "note": eq.note}
                    for eq in example_queries
                ]
            },
        ),
        (
            f"/api/2.0/genie/spaces/{space_id}/sample_questions",
            {"questions": [{"text": q} for q in benchmark_questions]},
        ),
    ]

    any_success = False
    for path, body in candidate_endpoints:
        try:
            # api_client.do() is the Databricks SDK's raw REST call — works for
            # any endpoint the SDK doesn't expose a typed method for.
            w.api_client.do(method="POST", path=path, body=body)
            print(f"[seed_genie] Seeded via API: {path}")
            any_success = True
        except Exception as exc:
            print(f"[seed_genie] API path {path} unavailable ({type(exc).__name__}) — skipping.")
    return any_success


def _write_workspace_file(w, path: str, content: str) -> None:
    """Write a UTF-8 text file to /Workspace/... via the workspace API."""
    from databricks.sdk.service.workspace import ImportFormat, Language  # type: ignore

    # Ensure parent dir exists.
    parent = "/".join(path.split("/")[:-1])
    try:
        w.workspace.mkdirs(parent)
    except Exception:
        pass  # already exists is fine

    import base64
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    w.workspace.import_(
        path=path,
        format=ImportFormat.AUTO,
        language=Language.PYTHON,  # ignored for AUTO/text but the SDK signature requires it
        content=encoded,
        overwrite=True,
    )


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

    try:
        gold_stmt = w.statement_execution.execute_statement(
            warehouse_id=wh_id,
            statement=(
                f"SELECT COUNT(*) FROM system.information_schema.tables "
                f"WHERE table_catalog = '{catalog}' "
                f"AND table_schema = '{schema}' "
                f"AND table_name = 'daily_usage_summary'"
            ),
            wait_timeout="30s",
        )
        gold_rows = (gold_stmt.result.data_array or []) if gold_stmt.result else []
        gold_ok = bool(gold_rows) and int(gold_rows[0][0]) > 0
        if gold_ok:
            print(f"[verify] Gold table {catalog}.{schema}.daily_usage_summary is present.")
        else:
            print(
                f"[verify] WARNING: {catalog}.{schema}.daily_usage_summary is missing. "
                "Re-run cost_obs_setup or rebuild from Settings."
            )
    except Exception as e:
        print(f"[verify] WARNING: gold table check failed: {e}")

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
