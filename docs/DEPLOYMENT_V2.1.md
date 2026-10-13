# Cost Observability — v2.1 Deployment

Two supported deployment paths, both driven end-to-end by the Databricks
Asset Bundle (DAB) in `bundle/`. Pick the one that matches your starting
state.

| Starting state | Path | Command |
|---|---|---|
| No prior cost-obs deployment in the target workspace | **Fresh install** | `bundle deploy` + `bundle run cost_obs_setup` |
| Existing 1.x deployment (MVs already in place, app running) | **1.1 → 2.1 in-place upgrade** | same as above; setup job auto-detects |

The setup job's `01_validate_prereqs` task decides which path is in effect at
runtime and prints the resolved mode. You can override the auto-detection
with the `deployment_mode` bundle variable — see [Overriding
detection](#overriding-detection).

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

Set the variables that don't have a good default before you deploy — either
in a `targets/<your-target>.yml`, or on the `bundle deploy` command line.

| Variable | Purpose | Example |
|---|---|---|
| `workspace_host` | Databricks workspace URL | `https://acme.cloud.databricks.com` |
| `catalog` | UC catalog where MVs live | `acme_catalog` |
| `schema` | UC schema for MVs | `cost_obs` |
| `warehouse_id` | Serverless / Pro warehouse ID | `dd43ee29fedd958d` |
| `lakebase_project_name` | Lakebase Autoscaling project name — new in 2.x | `cost-obs-db` |
| `lakebase_read_mode` | Dashboard serving mode; defaults to Lakebase-first with warehouse-gold fallback | `on` |
| `genie_space_id` | (Optional) existing Genie space ID | `01f0fcc775c…` |
| `ai_gateway_usage_table` | (Optional) admin-managed derived table over `system.ai_gateway.usage` | `acme_catalog.cost_obs.ai_gateway_usage_shared` |
| `databricks_account_id` | Account UUID — required for account-level APIs | `f8d9…` |
| `deployment_mode` | `auto` (default) / `fresh` / `migrate` — see [below](#overriding-detection) | `auto` |

The `lakebase_endpoint_name` variable must use the full path form
`projects/<project>/branches/production/endpoints/primary` so the Apps
runtime can resolve it. Each `bundle/targets/*.yml` already sets this.

---

## Fresh install

```bash
cd bundle
databricks bundle deploy -t <target>
databricks bundle run cost_obs_setup -t <target>
```

`bundle deploy` provisions, in the target workspace:

1. The Databricks App (`cost-observability`).
2. The Lakebase project + `production` branch + `primary` endpoint (via
   `postgres_projects` / `postgres_branches` / `postgres_endpoints`).
3. The `sql-warehouse` and `lakebase` resource bindings on the app.
   (The Genie space is **not** an app-resource binding — see the note
   below — but `GENIE_SPACE_ID` is injected as an app env var from the
   `genie_space_id` variable.)
4. The `cost_obs_setup` job (six tasks: validate → bootstrap_lakebase →
   migrate_delta → seed_genie → setup_usage_policy → verify).

`bundle run cost_obs_setup` then runs the setup job. In fresh mode:

- `validate` detects no prior state (mode resolves to `fresh`).
- `bootstrap_lakebase` provisions the OAuth role, grants, ALTER DEFAULT
  PRIVILEGES, and the `setup_state` table.
- `migrate_delta` is a no-op (nothing to migrate).
- `seed_genie` grants the app service principal `CAN_RUN` on the Genie
  space and writes curation to it (skipped entirely if `genie_space_id`
  is empty).
- `setup_usage_policy` provisions the serverless usage policy for
  attribution.
- `verify` runs the smoke checks and writes the final `setup_state` row.

### How dashboard tables reach Lakebase

The one-time setup job initializes the Lakebase project, OAuth role, grants,
schema, and setup markers. Its `migrate_delta` task is only for legacy 1.x
application-state tables (`budget_alerts`, `tagging_rules`, and
`cost_snapshots`); it does not copy the dashboard's `daily_*` gold tables.

Dashboard gold is built by the app's normal materialized-view refresh in the
SQL warehouse. At the end of the same serialized refresh, the app range-replaces
those aggregates into Lakebase. New deployments therefore need one successful
table build/refresh after setup; subsequent scheduled or manual refreshes keep
Lakebase current automatically. Lakebase-first serving is enabled by default,
with warehouse gold used if a Postgres copy is missing or empty.

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
databricks bundle deploy -t <target>
databricks bundle run cost_obs_setup -t <target>
```

Same commands as fresh, but the setup job takes a different code path:

- `validate` finds `daily_usage_summary` in the target schema and resolves
  the mode to `migrate`.
- `bootstrap_lakebase` provisions the OAuth role and grants against the
  newly-created Lakebase branch — the existing MVs are untouched.
- `migrate_delta` copies the 1.1 app state (permissions, alerts, config,
  workspace_config) from Delta / DBFS into Lakebase. Idempotent: safe to
  re-run.
- `seed_genie` grants the app SP `CAN_RUN` and seeds curation on the space
  in `genie_space_id`.
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

The setup job auto-detects fresh vs. migrate. To pin it, set the
`deployment_mode` bundle variable:

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

- The materialized views are untouched (setup job never rebuilds them).
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

- **DBU Spend** tab renders (fresh install: MVs may still be building on
  first load; retry in a few minutes).
- **AI Gateway** tab shows the "Cost" sub-tab as its default view.
- **Genie** tab (new in 2.1) is present.
- Settings → Tab visibility no longer shows an "AI/ML" entry.
