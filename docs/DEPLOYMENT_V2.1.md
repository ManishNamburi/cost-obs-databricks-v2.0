# Cost Observability — v2.1 Deployment

Two supported deployment paths, both driven end-to-end by the Databricks
Asset Bundle (DAB) in `bundle/`. Pick the target at deploy time. Authenticate
with a CLI profile (or `DATABRICKS_HOST`) for the customer workspace, and
pass catalog, schema, and warehouse as `--var` values. The bundle cannot
take the workspace URL as a variable — the CLI rejects `${var.*}` in
`workspace.host`.

| Starting state | Target | `deployment_mode` | Catalog / schema / warehouse |
|---|---|---|---|
| No prior cost-obs deployment | `-t fresh` | `fresh` | Customer-supplied (new) |
| Existing 1.x app | `-t upgrade` | `migrate` | Reuse the v1 names; Lakebase and the v2 app are new |

```bash
cd bundle
databricks bundle deploy -t fresh \
  --var="catalog=<catalog>" \
  --var="schema=cost_obs" \
  --var="warehouse_id=<warehouse_id>"
databricks bundle run cost_obs_setup -t fresh
```

```bash
cd bundle
databricks bundle deploy -t upgrade \
  --var="catalog=<v1_catalog>" \
  --var="schema=<v1_schema>" \
  --var="warehouse_id=<v1_warehouse_id>"
databricks bundle run cost_obs_setup -t upgrade
```

The `fresh` and `upgrade` targets pin the motion so a leftover MV cannot
flip a fresh install into an upgrade. Other targets (`dev`, `cmegdemos`,
…) still default `deployment_mode` to `auto`.

---

## Prerequisites

Same for both paths.

| Requirement | Notes |
|---|---|
| Databricks workspace on Premium or above with Apps enabled | Contact your account team if Apps aren't available |
| Unity Catalog enabled | Required for materialized views and system table access |
| System tables `system.billing.usage` + `system.billing.list_prices` accessible | Metastore admin can grant if not already visible |
| A Serverless (or Pro) SQL warehouse | Serverless Medium is the recommended default |
| Workspace admin role on the target workspace | Needed to create the app and grant the app SP access |
| Databricks CLI v0.240 or newer with a configured profile for the target workspace | `databricks --version` |

---

## Bundle variables

For `-t fresh` and `-t upgrade`, pass catalog, schema, and warehouse on
the `bundle deploy` command line. Point the CLI at the customer workspace
with `--profile` (or `DATABRICKS_HOST`). Other targets may pin catalog
names in their YAML.

| Variable | Purpose | Example |
|---|---|---|
| `workspace_host` | Not used by `-t fresh` / `-t upgrade`. Workspace URL comes from the CLI profile. | — |
| `catalog` | UC catalog where MVs live | `acme_catalog` |
| `schema` | UC schema for MVs | `cost_obs` |
| `warehouse_id` | Serverless / Pro warehouse ID | `dd43ee29fedd958d` |
| `lakebase_project_name` | Lakebase Autoscaling project name — new in 2.x | `cost-obs-db` |
| `lakebase_read_mode` | Dashboard serving mode; defaults to Lakebase-first with warehouse-gold fallback | `on` |
| `genie_space_id` | (Optional) existing Genie space ID | `01f0fcc775c…` |
| `ai_gateway_usage_table` | (Optional) admin-managed derived table over `system.ai_gateway.usage` | `acme_catalog.cost_obs.ai_gateway_usage_shared` |
| `databricks_account_id` | Account UUID — required for account-level APIs | `f8d9…` |
| `deployment_mode` | `auto` (default) / `fresh` / `migrate` — pinned by `-t fresh` / `-t upgrade` | `fresh` or `migrate` |

The `lakebase_endpoint_name` variable must use the full path form
`projects/<project>/branches/production/endpoints/primary` so the Apps
runtime can resolve it. Each `bundle/targets/*.yml` already sets this.

---

## Fresh install

```bash
cd bundle
databricks bundle deploy -t fresh \
  --var="catalog=<catalog>" \
  --var="schema=cost_obs" \
  --var="warehouse_id=<warehouse_id>"
databricks bundle run cost_obs_setup -t fresh
```

`bundle deploy` provisions, in the target workspace:

1. The Databricks App (`cost-observability`).
2. The Lakebase project + `production` branch + `primary` endpoint (via
   `postgres_projects` / `postgres_branches` / `postgres_endpoints`).
3. The `sql-warehouse` and `lakebase` resource bindings on the app.
   (The Genie space is **not** an app-resource binding — see the note
   below — but `GENIE_SPACE_ID` is injected as an app env var from the
   `genie_space_id` variable.)
4. The `cost_obs_setup` job (validate → bootstrap_lakebase → migrate_delta +
   build_gold → seed_genie → setup_usage_policy → verify).

`bundle run cost_obs_setup` then runs the setup job. In fresh mode:

- `validate` confirms the warehouse and Lakebase endpoint.
- `bootstrap_lakebase` provisions the OAuth role, grants, ALTER DEFAULT
  PRIVILEGES, and the `setup_state` table.
- `migrate_delta` is a no-op (nothing to migrate).
- `build_gold` creates the catalog/schema if needed, builds every warehouse
  gold table from `system.*`, and copies those aggregates into Lakebase.
- `seed_genie` creates the `cost-obs` Genie space when `genie_space_id` is
  empty, grants the app service principal `CAN_RUN`, and stores the id.
- `setup_usage_policy` provisions the serverless usage policy for
  attribution.
- `verify` runs the smoke checks and writes the final `setup_state` row.

### How dashboard tables reach Lakebase

The setup job's `build_gold` task is the first gold build. It uses the same
warehouse builders as Settings → rebuild, then range-replaces the dashboard
aggregates into Lakebase. Later scheduled or manual refreshes keep both copies
current. Lakebase-first serving is on by default, with warehouse gold used if
a Postgres copy is missing or empty.

`migrate_delta` only copies legacy 1.x application-state tables
(`budget_alerts`, `tagging_rules`, `cost_snapshots`). It does not build gold.

> **Why the Genie space isn't a DAB app-resource binding.** `genie_space_id`
> is empty by default (the space is usually created after the first deploy),
> and a binding with an empty `space_id` is emitted verbatim to the Apps API,
> which rejects it — breaking `bundle deploy` for anyone not using Genie.
> Instead, the app reads `GENIE_SPACE_ID` from its env var, and `seed_genie`
> grants the app SP `CAN_RUN` on the space at runtime when an ID is set
> (best-effort; if the Genie permissions API isn't available it logs a
> manual-grant instruction). This mirrors the Lakebase pattern where grants
> Terraform can't issue at plan time live in the setup job.

The materialized views (`daily_usage_summary`, `daily_product_breakdown`,
etc.) build on first app boot when the app connects to the warehouse.

---

## 1.1 → 2.1 migration

Preconditions:

- 1.1 is currently deployed on the target workspace.
- The MV tables in `${catalog}.${schema}` are current.
- You have a change window (the app will restart during redeploy).

Steps:

```bash
cd bundle
databricks bundle deploy -t upgrade \
  --var="catalog=<v1_catalog>" \
  --var="schema=<v1_schema>" \
  --var="warehouse_id=<v1_warehouse_id>"
databricks bundle run cost_obs_setup -t upgrade
```

Pass the live v1 catalog, schema, and warehouse id. Setup then:

- `validate` confirms it can reach that warehouse.
- `bootstrap_lakebase` provisions Lakebase grants. Existing MVs stay.
- `migrate_delta` copies 1.1 app state (permissions, alerts, config,
  workspace_config) from Delta / DBFS into Lakebase.
- `build_gold` incrementally refreshes existing MVs, creates any new v2 gold
  tables, and full-loads Lakebase so dashboards do not wait on Settings.
- `seed_genie` creates the Genie space if none is set.
- `setup_usage_policy` no-ops if the policy already exists.
- `verify` writes the final `setup_state` marker.

**What is preserved** during the migration:

- All materialized views in `${catalog}.${schema}`.
- Nightly MV refresh schedule.
- Any customer-configured alerts and workspace scopes (they move into
  Lakebase, but keep their IDs).

**What changes**:

- App state moves from DBFS to Lakebase. The v2 app reads state only from
  Lakebase, so once the migration completes, the DBFS copy is no longer
  authoritative.
- The AI/ML tab is now a sub-tab under **AI Gateway** (V2.1_SPEC §4.3).
  The saved-tab-visibility setting for `aiml` is silently dropped.
- The dedicated Genie tab appears (V2.1_SPEC §4.4).

---

## Overriding detection

`-t fresh` and `-t upgrade` already pin the motion. On other targets the
setup job auto-detects unless you set `deployment_mode`:

```bash
databricks bundle deploy -t <target> --var="deployment_mode=fresh"
databricks bundle run cost_obs_setup -t <target>
```

| Value | Effect |
|---|---|
| `auto` (default) | Probe for existing MVs and setup_state; use whatever matches. |
| `fresh` | Force fresh mode. `migrate_delta` skips. Use for catalog moves or clean rebuilds. |
| `migrate` | Force migrate mode. Fails loudly if prior state can't be found. |

---

## Rollback

If a v2.1 deploy fails after `bundle deploy` but before or during the
setup job:

- On upgrade, existing v1 materialized views are only incrementally
  refreshed; a failed `build_gold` does not drop them.
- The v1.x app service principal still has its warehouse resource
  binding; you can point DNS / users back at the 1.1 app.
- To fully roll back the DAB changes, redeploy the previous git SHA:
  ```bash
  git checkout <previous-sha>
  databricks bundle deploy -t <target>
  ```

Lakebase project and branch resources are `replace_existing=false` by
default. `bundle destroy` will drop them; a repeat `bundle deploy` on the
old SHA leaves them in place and unused (no ongoing cost when idle).

---

## Post-deploy validation

Both paths finish with `05_post_setup_verify` writing a row to
`setup_state`. In addition:

```bash
databricks apps get <app-name> -o json | jq '.pending_deployment.status.state'
# Expect: "SUCCEEDED"
```

Then open the app and confirm:

- **DBU Spend** tab renders (gold is built during `cost_obs_setup`; a
  first load should not need a Settings rebuild).
- **AI Gateway** tab shows the "Cost" sub-tab as its default view.
- **Genie** tab (new in 2.1) is present.
- Settings → Tab visibility no longer shows an "AI/ML" entry.
