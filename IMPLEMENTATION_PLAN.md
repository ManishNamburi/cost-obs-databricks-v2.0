# Cost Observability V2 — Implementation Plan

_Last updated: 2026-05-28_

---

## Repo layout (after restructure)

```
cost-obs-app-v2/
├── app/
│   ├── backend/           FastAPI (Python package "backend", uvicorn backend.app:app)
│   └── frontend/          React/TypeScript (vite outDir: ../../static)
├── bundle/
│   ├── databricks.yml     Root config + variables
│   ├── resources/         app.yml, lakebase.yml, jobs.yml, permissions.yml, app_resources.yml
│   └── targets/           dev.yml, staging.yml, prod.yml
├── setup/
│   ├── notebooks/         01_validate → 02_lakebase_bootstrap → 03_seed_genie
│   │                      → 04_usage_policy_setup → 05_post_setup_verify
│   ├── python/            shared_setup_lib.py, migrate_delta_to_lakebase.py
│   └── sql/               uc_grants.sql, lakebase_roles.sql, default_privileges.sql
├── migrations/
│   ├── delta/             Delta table schema migrations
│   └── lakebase/          Lakebase/Postgres schema migrations
├── shared/
│   ├── constants/
│   ├── prompts/
│   └── schemas/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── smoke/
└── static/                Pre-built frontend (committed for deploy-from-git)
```

---

## Deployment model (two-phase)

```
Phase 1 — declarative infra (idempotent):
  databricks bundle deploy -t <target>
  Provisions: App, SQL warehouse binding, Lakebase project/branch/endpoint, setup job

Phase 2 — one-time privileged setup (idempotent via setup_state):
  databricks bundle run cost_obs_setup -t <target>
  Runs: validate → bootstrap_lakebase → [migrate_delta || seed_genie || setup_usage_policy] → verify

App Setup Wizard:
  Verify + guided repair only — never provisions Lakebase/Genie/budgets at runtime
```

---

## What is already built (V1 baseline, now in V2)

### Application features (stable)
| Feature | Status | Notes |
|---|---|---|
| $DBU Spend tab | ✅ Complete | Daily timeseries, product/SKU/user/workspace breakdown, interactive compute, ETL |
| SQL tab | ✅ Complete | Query spend by source, warehouse type/size, rightsizing, top users, query profile links |
| AI/ML tab | ✅ Complete | Spend by category, endpoints, ML clusters, Agent Bricks |
| Apps tab | ✅ Complete | Per-app spend, SKU drill-down, connected artifacts |
| Tagging Hub | ✅ Complete | Coverage, spend by tag/key, untagged resources with suggested tags |
| Users tab | ✅ Complete | Ranked users, per-user timeseries, product breakdown, growth trend |
| KPIs & Trends | ✅ Complete | Platform KPIs, drill-downs, anomaly detection |
| Cloud Costs | ✅ Complete | AWS/Azure/GCP estimated + actual, instance family, in-app integration wizards |
| Settings | ✅ Complete | General, Config (rebuild), Permissions, User management, Account pricing toggle |

### Infrastructure
| Component | Status | Notes |
|---|---|---|
| Materialized views (6 tables) | ✅ Complete | Nightly auto-refresh, incremental MERGE INTO, CLUSTER BY |
| Setup wizard | ✅ Complete | DBFS state persistence, setup_done.json, auto-heal on redeploy |
| In-app alerting | ✅ Complete | Spike detection, email + webhook delivery |
| Multi-cloud detection | ✅ Complete | AWS/Azure/GCP from workspace URL |
| SP-only auth model | ✅ Complete | DATABRICKS_CLIENT_ID/SECRET via SDK unified auth |

### V2 skeleton (structure only — not wired to app)
| Component | Status | Notes |
|---|---|---|
| DAB bundle structure | ✅ Skeleton | databricks.yml + resources/ + targets/ defined |
| Setup job (6 phases) | ✅ Skeleton | Notebook tasks defined, shared_setup_lib.py stub |
| Lakebase bootstrap | ✅ Skeleton | Schema, OAuth role, setup_state table in shared_setup_lib.py |
| Delta → Lakebase migration | ✅ Skeleton | migrate_delta_to_lakebase.py stub with setup_state gating |
| Migrations framework | ✅ Scaffold | delta/ and lakebase/ dirs (empty) |
| Shared resources | ✅ Scaffold | constants/, prompts/, schemas/ dirs (empty) |
| tests/ scaffold | ✅ Scaffold | unit/, integration/, smoke/ dirs |

---

## What remains to build

---

### Feature 1 — Unity Gateway Cost Intelligence

**Goal:** Surface Unity Gateway usage, token spend, and external model cost in the app.

**Constraint:** `system.ai_gateway.usage` is account-admin only. App SP cannot query it directly.

**Required admin setup (documented in README/onboarding):**
```sql
CREATE TABLE IF NOT EXISTS <catalog>.<schema>.ai_gateway_usage_shared AS
SELECT * FROM system.ai_gateway.usage
WHERE workspace_id IN ('...your workspace IDs...');
GRANT SELECT ON TABLE <catalog>.<schema>.ai_gateway_usage_shared TO `<app-sp-client-id>`;
```
Refreshed by an account-admin scheduled job (not managed by the app).

**Backend work:**
- `app/backend/routers/ai_gateway.py` — new router, reads from the admin-owned shared table
- Bundle endpoint pattern: aggregate by endpoint, requester, tags, model type
- Cost derivation: join `system.billing.usage` (billing_origin_product = 'AI_GATEWAY') with `system.billing.list_prices` for 1P cost — no stable `dbu_cost` column in usage table
- External model cost: token-based estimation (per-model pricing table, similar to existing cloud_pricing.py pattern)
- No 1:1 join between ai_gateway.usage (per-request) and billing.usage (aggregate) — correlate at aggregate level only

**Frontend work:**
- New section in AI/ML tab (or standalone tab if data warrants it)
- Views: requests/tokens over time by endpoint, cost by model/provider, requester leaderboard, tag-based chargeback

**Bundle work:**
- Add `AI_GATEWAY_USAGE_TABLE` variable to databricks.yml (already declared, needs wiring)
- Onboarding doc: admin setup steps for the derived table + refresh job

**Effort estimate:** ~3–4 days

---

### Feature 2 — Production Alerting (replace in-app scheduler)

**Goal:** Replace the app-local alert scheduler with durable SQL Alerts + Databricks Jobs.

**Key constraint:** App pod logs are not persisted when compute shuts down — in-process schedulers are not reliable for production alerting.

**Current state:** In-app spike detection writes to Delta + delivers via email/webhook. Works but depends on pod staying alive.

**Target architecture:**
```
SQL Alert (scheduled query) → Notification Destination → Email/Slack/Webhook/Teams/PagerDuty
```

**Backend work:**
- `app/backend/routers/alerts.py` — add endpoints to read/list/create SQL Alert configs
- Alert templates: cost spike, table freshness, missing grants, budget threshold proximity
- Use Databricks SDK `w.alerts` + `w.notification_destinations` APIs
- Bundle `resources/alerts.yml` — define standard alert set as DAB-managed resources

**Frontend work:**
- Alerts settings page: show configured SQL Alerts, destinations, current status
- Map existing alert config UI to SQL Alert creation (not local in-app config)

**Transition:** Keep existing in-app alerting as fallback during transition; mark as deprecated

**Effort estimate:** ~2–3 days

---

### Feature 3 — Budget & Usage Policy Integration

**Goal:** Display account budgets, create/manage serverless usage policies, surface attribution in billing data.

**APIs available (programmatic):**
- Account budgets: `databricks account budgets` CLI / REST API (get/list/create/update/delete)
- Serverless usage policies: `databricks account budget-policy` CLI / REST API
- Usage policy attribution: lands in `system.billing.usage.custom_tags`

**Key nuance:**
- Usage policies are NON-RETROACTIVE — only future workloads get tagged
- Creating budgets requires account admin; creating usage policies requires workspace admin
- Unity Gateway budgets are a separate subtype (per-user thresholds, do not stop usage)

**Backend work:**
- `app/backend/routers/budgets.py` — read-only budget listing + usage policy CRUD (admin-gated)
- Surface `custom_tags` from billing usage for policy-attributed spend
- Budget vs actual spend comparison queries

**Frontend work:**
- Budget panel in Settings or new "Governance" tab
- Usage policy manager: list, create, assign to workspace/app/job/pipeline
- `custom_tags` filter in DBU Spend and other tabs

**Effort estimate:** ~2–3 days

---

### Feature 4 — Lakebase State Store

**Goal:** Replace DBFS JSON + Delta app-state tables with Lakebase (PostgreSQL Autoscaling) for durable, transactional app state.

**Connection pattern (locked in):**
```python
from psycopg_pool import ConnectionPool
import psycopg
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

class OAuthConnection(psycopg.Connection):
    @classmethod
    def connect(cls, conninfo="", **kwargs):
        cred = w.postgres.generate_database_credential(
            endpoint=os.environ["ENDPOINT_NAME"]
        )
        kwargs["password"] = cred.token
        return super().connect(conninfo, **kwargs)

pool = ConnectionPool(
    conninfo=f"dbname={os.environ['PGDATABASE']} user={os.environ['PGUSER']} "
             f"host={os.environ['PGHOST']} port={os.environ.get('PGPORT','5432')} "
             f"sslmode={os.environ.get('PGSSLMODE','require')}",
    connection_class=OAuthConnection,
    min_size=1, max_size=10, open=True,
)
```
_Note: PgBouncer is not compatible with OAuth roles. Connect directly to the Lakebase endpoint._

**Schema (in `setup/python/shared_setup_lib.py` bootstrap):**
```sql
CREATE TABLE IF NOT EXISTS cost_obs.setup_state (
    step_name TEXT PRIMARY KEY,
    completed_at TIMESTAMPTZ,
    version TEXT,
    metadata JSONB
);
CREATE TABLE IF NOT EXISTS cost_obs.alerts (
    id SERIAL PRIMARY KEY,
    name TEXT, type TEXT, threshold FLOAT,
    channels JSONB, enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS cost_obs.user_permissions (
    email TEXT PRIMARY KEY,
    role TEXT NOT NULL,  -- 'admin' | 'viewer'
    granted_by TEXT,
    granted_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS cost_obs.workspace_config (
    key TEXT PRIMARY KEY,
    value JSONB,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER DEFAULT PRIVILEGES IN SCHEMA cost_obs
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cost_obs_app;
```

**Backend work:**
- `app/backend/lakebase.py` — OAuthConnection pool, `get_pg_connection()` context manager
- Migrate alert persistence from Delta → Lakebase
- Migrate user_permissions from Delta → Lakebase
- Migrate workspace_config (currently DBFS JSON) → Lakebase
- Keep V1 DBFS fallback during migration window

**Setup job work:**
- Complete `02_lakebase_bootstrap.py` — schema + role + grants + setup_state
- Complete `default_privileges.sql`

**Effort estimate:** ~4–5 days

---

### Feature 5 — Genie Conversation Interface

**Goal:** Re-enable Genie as a natural-language query interface over curated cost tables. Removed from V1; returns in V2 with correct auth model.

**Auth model (locked in):**
- Use user OAuth passthrough (`x-forwarded-access-token` header) when per-user RLS matters
- App SP token acceptable only for shared admin-owned spaces

**Architecture:**
```
User question → Genie Conversation API (user token) → generated SQL
→ structured results → app renders charts
```

**Prerequisites:**
- Genie space seeded with curated cost tables + 5+ example queries (via setup job)
- Space configured with daily_usage_summary, daily_product_breakdown, etc.

**Backend work:**
- `app/backend/routers/genie.py` — Genie Conversation API proxy, user token passthrough
- Space management: get status, conversation history, follow-up questions
- Result rendering: structured query results → chart-compatible format

**Frontend work:**
- `GenieChatView.tsx` — already exists in V2 (synced back from pre-deletion), wire to new backend
- Embed in its own tab or as a floating panel

**Setup job work:**
- Complete `03_seed_genie.py` — create space, add tables, set example queries, configure instructions

**Bundle work:**
- `resources/` — add Genie space as app resource (already in `app_resources.yml` stub)
- `GENIE_SPACE_ID` variable already in databricks.yml

**Effort estimate:** ~2–3 days (after Lakebase setup complete)

---

### Feature 6 — DAB Deployment Model (complete wiring)

**Goal:** Make `databricks bundle deploy -t prod` + `databricks bundle run cost_obs_setup` the complete, production-safe onboarding story.

**Current gaps in bundle:**

| Resource | Status | Gap |
|---|---|---|
| `resources/app.yml` | ✅ Source path + command correct | Needs Genie space wiring |
| `resources/app_resources.yml` | ✅ warehouse + lakebase bindings | Test against real endpoint names |
| `resources/lakebase.yml` | ✅ project/branch/endpoint defined | Validate CU_4 + auto-region |
| `resources/jobs.yml` | ⚠️ Notebook paths defined | `migrate_delta` task has wrong notebook path (copy of bootstrap), task missing for usage_policy |
| `resources/permissions.yml` | ✅ Placeholder | Populate viewer/admin group names |
| `bundle/variables.yml` | ❌ Missing | Variables should move from databricks.yml to dedicated variables.yml |
| `targets/prod.yml` | ⚠️ Template | Needs real workspace host + warehouse ID |

**Setup job work:**
- Fix `resources/jobs.yml` — correct notebook paths for all 6 tasks
- Add `usage_policy` task (currently missing from job graph)
- Add `migrate_delta` as separate task from `bootstrap_lakebase`
- Wire `ENDPOINT_NAME` env var injection for Lakebase auth in notebooks

**App wizard update:**
- Change wizard from "provision + verify" to "verify + guided repair"
- Wizard checks: bundle ran? setup job ran? tables exist? Lakebase reachable? Genie seeded?
- If any check fails: show the exact CLI command to fix it, not a "fix it for you" button

**Effort estimate:** ~2 days (runs alongside other features)

---

## Confirmed technical decisions

| Decision | Choice | Reason |
|---|---|---|
| Unity Gateway data path | Admin-owned derived table | `system.ai_gateway.usage` is account-admin only |
| Unity Gateway cost model | `billing.usage` JOIN `list_prices` for 1P; token estimation for external | No stable cost column in usage table |
| Lakebase auth | `psycopg_pool` + custom `OAuthConnection` class | PgBouncer incompatible with OAuth roles |
| Lakebase type | Autoscaling (`postgres_projects`) | Provisioned deprecated post-2026-03-12 |
| Token rotation | Per new physical connection via `generate_database_credential()` | Tokens expire ~60 min |
| Genie auth | User OAuth passthrough for per-user RLS | App SP only for shared-access spaces |
| Alerting substrate | SQL Alerts + Databricks Jobs | App pod logs not persisted on shutdown |
| Notification channels | Email, Slack, Webhook, MS Teams, PagerDuty | Supported notification destinations |
| Budget API | `account budgets` + `account budget-policy` CLI/API | Programmatic; budget creation requires account admin |
| Usage policy retroactivity | Non-retroactive | Only future workloads get tagged |
| Multi-workspace | One app instance per workspace, bundle promotes across envs | No multi-workspace single-app model |
| App state storage | Lakebase replaces DBFS JSON + Delta state tables | Transactional, shared across workers |
| Pod design | Cold-start tolerant, stateless, externalize all state | Compute shuts down on idle |

---

## Recommended build order

```
Sprint 1 (foundation):
  Feature 6 (bundle wiring) — fix jobs.yml, add variables.yml, test bundle deploy
  Feature 4 (Lakebase) — OAuth pool, schema bootstrap, migrate alerts + permissions

Sprint 2 (new data):
  Feature 1 (Unity Gateway) — backend router, billing join, frontend section in AI/ML
  Feature 3 (Budgets/Policies) — budget read, usage policy CRUD, custom_tags surfacing

Sprint 3 (UX + deployment):
  Feature 2 (Production Alerting) — SQL Alerts wiring, notification destinations
  Feature 5 (Genie) — conversation API, frontend chat view, space seeding
  Final wizard refactor: verify-only, no provisioning from app runtime
```

Total estimated effort: ~15–20 days of focused engineering work.
