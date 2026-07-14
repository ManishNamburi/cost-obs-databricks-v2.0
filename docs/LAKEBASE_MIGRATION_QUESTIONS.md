# Lakebase Migration — Questions for Lakebase / Apps Experts

## Context (for the expert)

**cost-obs** is a Databricks App (FastAPI + React) that shows compute/cost analytics.

- **Current data architecture:** the app reads **everything at runtime from Unity Catalog Delta tables via a SQL warehouse** (`databricks-sql-connector`). Cost analytics come from ~9 pre-aggregated Delta tables (`daily_usage_summary`, `daily_product_breakdown`, `daily_query_stats`, etc.) that the app builds/refreshes from `system.billing.usage` (+ `list_prices`, `access.workspaces_latest`, `query.history`, `lakeflow.pipelines`). App state (settings, permissions, alerts, tagging rules, response cache) is also in UC Delta tables. There are ~300 warehouse query sites.
- **Lakebase today:** a Lakebase (Postgres, Autoscaling) project is provisioned via DAB and has an app-state schema, but the **running app does not read/write it** — only the one-time setup job writes `setup_state` markers. The OAuth `psycopg_pool` in the app is effectively unused.
- **Goal (v2.1):** serve the app's runtime reads from **Lakebase** instead of UC Delta tables — both the pre-aggregated cost tables and app state.
- **Hard constraint we already hit:** Postgres/Lakebase cannot query UC system tables, and continuously duplicating `system.billing.usage` (huge, ever-growing) into Postgres seems impractical. So we expect a **hybrid**: aggregates computed on the warehouse from system tables, then served from Lakebase; live/raw system-table features stay on the warehouse.

The questions below are what we need answered to write the migration design doc.

---

## I. Overall architecture validation (most important)

1. For a Databricks App serving **analytics dashboards**, is the intended pattern: **compute aggregates in Delta (warehouse) → replicate to Lakebase via synced tables → app reads Lakebase**? Or is there a better-supported serving pattern we're missing?
2. Is Lakebase the right tool to **serve** read-heavy analytical aggregates to a dashboard, or is it positioned primarily for **transactional/OLTP + app state**, with analytical serving better left on the warehouse? Where's the line?
3. Given the hard constraint (Postgres can't read UC system tables), do you agree the realistic end state is a **hybrid** (aggregates + app state on Lakebase; aggregate-build + live-system-table features on the warehouse)? Any way to avoid the hybrid?

## II. Getting data into Lakebase (sync mechanism)

4. Are **Lakebase synced tables** (UC Delta → Postgres) the right mechanism for the `daily_*` aggregate tables? Recommended mode — **SNAPSHOT vs TRIGGERED vs CONTINUOUS** — for tables that refresh roughly daily?
5. Do synced tables support **incremental** updates (e.g., only new `usage_date` partitions), or is each refresh a full snapshot? Our largest table is ~370k rows / 180 days today and grows; we currently do incremental `MERGE`.
6. Can synced tables be **declared and managed in a DAB** (a `postgres_synced_tables` resource)? Known Terraform-provider issues? (We've already hit a `CAN_USE` grant panic and had to stop declaring the default branch/endpoint because project creation auto-provisions them.)
7. If synced tables are **not** appropriate, is a scheduled job doing a **direct bulk load** into Postgres (e.g., `COPY`/`psycopg`) supported/acceptable, or an anti-pattern? What do you recommend instead?

## III. Serving layer (app → Lakebase reads)

8. Connection model: the app uses **OAuth** (`generate_database_credential`, ~1h tokens) with `psycopg_pool`, connecting **directly** (we understand PgBouncer is incompatible with OAuth roles). Is this still the recommended pattern for a **multi-user, read-heavy** app? Recommended **pool sizing** and token-refresh handling?
9. **Indexing/partitioning** guidance for the `daily_*` serving tables in Lakebase (queries filter by `usage_date` range + `workspace_id`, group/aggregate, some window functions). What indexes/clustering give warehouse-comparable latency?
10. Realistic **read latency** on Lakebase for group-by/window aggregations over hundreds of thousands to a few million rows, vs a serverless SQL warehouse? Any query patterns to avoid?

## IV. Hybrid boundary + reference/dimension data

11. Small **dimension** tables we join to aggregates — `list_prices`, `access.workspaces_latest` — are in UC. Should we replicate these into Lakebase (small synced tables) so joins happen entirely in Postgres, or is there a federation option?
12. Is there any **federation** — Lakebase querying UC, or the warehouse querying Lakebase (foreign catalog / lakehouse federation) — that would let us avoid duplicating dimensions, or is denormalization into Lakebase the expected approach?
13. For features that genuinely need **live/raw** system data (`system.query.history`, per-query cost, `lakeflow.pipelines`), is keeping those on the warehouse the accepted pattern, or is there a Lakebase-native path?

## V. Refresh, freshness, consistency

14. End-to-end **freshness**: realistic latency from new `system.billing.usage` rows → Delta aggregate → Lakebase synced table? (Drives the "data is N hours behind" UX.)
15. How do synced tables handle **schema evolution** and **full rebuilds** (we sometimes `CREATE OR REPLACE` aggregates)? Does a source rebuild force a full re-sync?
16. Any **transactional/consistency** concerns serving a dashboard mid-sync (partial data, read-during-write)?

## VI. Cost (meta-important — this is a cost-observability app)

17. Cost model for this workload: Lakebase **CU-hours** for continuous sync + serving vs the current serverless-warehouse query cost. For a tool whose whole point is reducing spend, we can't have the app itself be expensive.
18. Can the serving endpoint **autoscale to zero / suspend** when idle, and still wake fast enough for interactive dashboard loads? Recommended autoscaling min/max CU + suspend timeout for spiky interactive traffic?
19. Is **CONTINUOUS** sync cost-justified for daily-refreshed data, or is **TRIGGERED/SNAPSHOT** on a schedule far cheaper with acceptable freshness?

## VII. DAB, provisioning, migration, security

20. Best-practice DAB layout for **project + branch + endpoint + synced tables + roles/grants**, given the provider quirks we hit (default branch/endpoint auto-created; grants must run at setup-job runtime, not plan time)?
21. For existing **1.x → 2.1 customer upgrades**: recommended way to **backfill** historical aggregates into Lakebase (one-time large sync) and then switch to incremental?
22. **Access control**: the app filters by `workspace_id` in SQL today. Any **RLS / row-level** or per-principal patterns in Lakebase we should use for multi-workspace scoping, or keep filtering in the app layer?
23. **Capacity/limits**: any Lakebase limits (table count, table size, connections, sync throughput) we should design around for ~9 aggregate tables + ~8 app-state tables + growth?

---

### Priority if the expert has limited time
Answer **I (1–3)**, **II (4–6)**, and **VI (17–19)** first — those determine whether the whole approach is viable and affordable. The rest refines the design.
