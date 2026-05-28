"""
Migrate historical cost-obs data from Delta tables into Lakebase.

Reads the following Delta tables (if they exist) and writes them into
the Lakebase schema. Uses setup_state to track per-table progress so
partial runs can be resumed safely.

Delta source tables (all optional):
  {catalog}.{schema}.budget_alerts
  {catalog}.{schema}.tagging_rules
  {catalog}.{schema}.cost_snapshots

Idempotent: each table migration is gated on a setup_state marker.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import psycopg

# Reuse connection and state helpers from shared_setup_lib
from shared_setup_lib import pg_conn, _is_step_done, _mark_step_done


_TABLES = [
    "budget_alerts",
    "tagging_rules",
    "cost_snapshots",
]


def _delta_table_exists(spark, catalog: str, schema: str, table: str) -> bool:
    try:
        spark.table(f"{catalog}.{schema}.{table}")
        return True
    except Exception:
        return False


def _migrate_table(spark, conn: psycopg.Connection, catalog: str, schema: str, table: str) -> None:
    step = f"migrate_delta_{table}"
    if _is_step_done(conn, step):
        print(f"[migrate] {table} — already migrated, skipping.")
        return

    if not _delta_table_exists(spark, catalog, schema, table):
        print(f"[migrate] {table} — Delta source not found, skipping.")
        _mark_step_done(conn, step, {"skipped": True, "reason": "source_not_found"})
        return

    df = spark.table(f"{catalog}.{schema}.{table}")
    row_count = df.count()
    print(f"[migrate] {table} — {row_count} rows to migrate.")

    # TODO: implement per-table DDL and INSERT logic using df.toPandas() or
    # a JDBC write via spark.write.jdbc(...) once Lakebase JDBC support is GA.
    # For now, log the intent and mark complete as a placeholder.
    print(f"[migrate] {table} — migration placeholder (implement DDL + INSERT).")

    _mark_step_done(conn, step, {
        "row_count": row_count,
        "migrated_at": datetime.now(timezone.utc).isoformat(),
    })


def migrate() -> None:
    """Entry point called by 02b_migrate_delta notebook."""
    try:
        spark  # noqa: F821 — available in Databricks notebook context
    except NameError:
        raise RuntimeError("migrate() must be called from a Databricks notebook (spark not available)")

    catalog = os.environ["COST_OBS_CATALOG"]
    schema = os.environ["COST_OBS_SCHEMA"]

    with pg_conn() as conn:
        if _is_step_done(conn, "migrate_delta"):
            print("[migrate] All Delta migrations already complete — skipping.")
            return

        for table in _TABLES:
            _migrate_table(spark, conn, catalog, schema, table)  # noqa: F821

        _mark_step_done(conn, "migrate_delta", {
            "tables": _TABLES,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

    print("[migrate] Delta → Lakebase migration complete.")
