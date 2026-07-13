"""
Curated content for the cost-obs Genie space.

Kept in one file so operators can edit curation without touching the setup
job code. `seed_genie()` in `shared_setup_lib.py` reads these constants and
best-effort applies them to the space via the workspace API. If the API
endpoints for programmatic curation aren't available in the customer's
workspace region, the setup job prints the content to the notebook output
so an operator can paste it into the Genie space UI directly.

Everything here is intentionally scoped to what the customer's SP can actually
query — no internal Databricks tables, no PrPr features, no salesforce_account
grain. See V2.1_SPEC §4.2 for the design rationale.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


# ---------------------------------------------------------------------------
# Data sources — the four-table spine.
# ---------------------------------------------------------------------------

TRUSTED_ASSETS: List[str] = [
    "system.billing.usage",
    "system.billing.list_prices",
    "system.billing.account_prices",
    "system.access.workspaces_latest",
]


# ---------------------------------------------------------------------------
# Instructions — appears at the top of the Genie space configuration.
# Written from the "curate the model's behavior" perspective, not a user guide.
# ---------------------------------------------------------------------------

INSTRUCTIONS: str = """\
You are a cost analyst answering Databricks cost questions over the following four Unity Catalog system tables:

  - system.billing.usage
  - system.billing.list_prices
  - system.billing.account_prices
  - system.access.workspaces_latest

**Time-aware price joins.**
When joining system.billing.usage to system.billing.list_prices, always match on sku_name AND cloud, and require p.price_end_time IS NULL to pick up the currently active price. When negotiated prices matter, prefer system.billing.account_prices — it uses the same join keys plus effective/end dates.

**Time grain.**
Use usage_date for daily grain, DATE_TRUNC('month', usage_date) for monthly. Do not use usage_start_time / usage_end_time except when the question is explicitly about intra-day timing (rare — usually not what people mean by "when did we spend").

**Product breakdowns.**
Do not invent product categories. Use system.billing.usage.billing_origin_product as the primary product signal (values include SQL, JOBS, DLT, SERVING, APPS, MODEL_SERVING, and others). When the user asks about "AI spend", include VECTOR_SEARCH, FOUNDATION_MODEL, FINE_TUNING, AI_BI_GENIE, AI_QUERY, AI_FUNCTIONS, SERVING, MODEL_SERVING — but state the definition in your answer.

**List price vs account price.**
Default to list price (system.billing.list_prices.pricing.default) unless the user explicitly asks for actual/negotiated. Say which one you used in the answer.

**Workspace name resolution.**
system.billing.usage has workspace_id but not workspace_name. Join to system.access.workspaces_latest ON workspace_id to surface names. If that table isn't accessible (grant not applied), fall back to the raw workspace_id and say so.

**Unsupported questions — reject clearly.**
This space cannot answer:
  - query-level warehouse cost (no per-statement attribution in the four tables)
  - cloud VM cost / infrastructure spend outside Databricks DBUs
  - future forecasts or trend projections
  - anomaly explanations that require narrative reasoning (those go through the AI Gateway summary path, not Genie)
If asked, respond with "this Genie space cannot answer that — try the [X] tab in the cost-obs app instead" where [X] is the appropriate tab name (Cloud Costs, SQL, KPIs & Trends, etc.).

**No hallucinated usage_quantity semantics.**
usage_quantity is measured in DBUs. To get dollars, multiply by price. Never treat usage_quantity as a currency amount.

**Filter to real spend.**
Always include `usage_quantity > 0` in the WHERE clause. Rows with zero or negative quantity are metadata artifacts and don't represent real spend.
"""


# ---------------------------------------------------------------------------
# Example SQL queries — used by Genie both for grounding and as examples in
# the space UI. Each has a natural-language "example question" that maps to
# it plus a short "why this SQL" note.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExampleQuery:
    question: str
    sql: str
    note: str


EXAMPLE_QUERIES: List[ExampleQuery] = [
    ExampleQuery(
        question="What did we spend on Databricks this month?",
        sql="""\
SELECT
    SUM(u.usage_quantity * COALESCE(p.pricing.default, 0)) AS total_usd
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
    ON u.sku_name = p.sku_name
   AND u.cloud = p.cloud
   AND p.price_end_time IS NULL
WHERE u.usage_date BETWEEN DATE_TRUNC('month', CURRENT_DATE()) AND CURRENT_DATE()
  AND u.usage_quantity > 0
""",
        note="Baseline total-spend pattern with the time-aware price join.",
    ),
    ExampleQuery(
        question="Which workspaces spent the most this quarter?",
        sql="""\
SELECT
    COALESCE(w.workspace_name, CAST(u.workspace_id AS STRING)) AS workspace,
    SUM(u.usage_quantity * COALESCE(p.pricing.default, 0)) AS total_usd
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
    ON u.sku_name = p.sku_name
   AND u.cloud = p.cloud
   AND p.price_end_time IS NULL
LEFT JOIN system.access.workspaces_latest w
    ON u.workspace_id = w.workspace_id
WHERE u.usage_date >= DATE_TRUNC('quarter', CURRENT_DATE())
  AND u.usage_quantity > 0
GROUP BY 1
ORDER BY total_usd DESC
LIMIT 20
""",
        note="Workspace resolution pattern — fall back to raw ID if workspaces_latest is missing.",
    ),
    ExampleQuery(
        question="Which product are we spending the most on?",
        sql="""\
SELECT
    u.billing_origin_product AS product,
    SUM(u.usage_quantity * COALESCE(p.pricing.default, 0)) AS total_usd
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
    ON u.sku_name = p.sku_name
   AND u.cloud = p.cloud
   AND p.price_end_time IS NULL
WHERE u.usage_date >= CURRENT_DATE() - INTERVAL 30 DAYS
  AND u.usage_quantity > 0
GROUP BY 1
ORDER BY total_usd DESC
""",
        note="Product breakdown grouped by billing_origin_product — no invented buckets.",
    ),
    ExampleQuery(
        question="Who are the top 10 users by spend this month?",
        sql="""\
SELECT
    u.identity_metadata.run_as AS user_identity,
    SUM(u.usage_quantity * COALESCE(p.pricing.default, 0)) AS total_usd
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
    ON u.sku_name = p.sku_name
   AND u.cloud = p.cloud
   AND p.price_end_time IS NULL
WHERE u.usage_date >= DATE_TRUNC('month', CURRENT_DATE())
  AND u.usage_quantity > 0
  AND u.identity_metadata.run_as IS NOT NULL
GROUP BY 1
ORDER BY total_usd DESC
LIMIT 10
""",
        note="User attribution via identity_metadata.run_as. Service principal UUIDs come through here; there's no join to SCIM in the four-table spine.",
    ),
    ExampleQuery(
        question="What was the cost of model serving this month?",
        sql="""\
SELECT
    SUM(u.usage_quantity * COALESCE(p.pricing.default, 0)) AS total_usd
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
    ON u.sku_name = p.sku_name
   AND u.cloud = p.cloud
   AND p.price_end_time IS NULL
WHERE u.usage_date >= DATE_TRUNC('month', CURRENT_DATE())
  AND u.usage_quantity > 0
  AND (
        u.billing_origin_product IN ('SERVING', 'MODEL_SERVING')
     OR u.sku_name ILIKE '%SERVING%'
     OR u.sku_name ILIKE '%INFERENCE%'
     OR u.sku_name ILIKE '%PROVISIONED_THROUGHPUT%'
  )
""",
        note="Model-serving inclusion pattern — checks both billing_origin_product and sku_name because the exact stamping varies.",
    ),
    ExampleQuery(
        question="What is the AI product cost trend over the last 90 days?",
        sql="""\
SELECT
    u.usage_date,
    SUM(u.usage_quantity * COALESCE(p.pricing.default, 0)) AS total_usd
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
    ON u.sku_name = p.sku_name
   AND u.cloud = p.cloud
   AND p.price_end_time IS NULL
WHERE u.usage_date >= CURRENT_DATE() - INTERVAL 90 DAYS
  AND u.usage_quantity > 0
  AND (
        u.billing_origin_product IN ('SERVING', 'MODEL_SERVING')
     OR u.sku_name ILIKE '%VECTOR_SEARCH%'
     OR u.sku_name ILIKE '%FOUNDATION_MODEL%'
     OR u.sku_name ILIKE '%FINE_TUNING%'
     OR u.sku_name ILIKE '%AI_BI%'
     OR u.sku_name ILIKE '%AI_QUERY%'
     OR u.sku_name ILIKE '%AI_FUNCTIONS%'
     OR u.sku_name ILIKE '%GENIE%'
  )
GROUP BY u.usage_date
ORDER BY u.usage_date
""",
        note='"AI product" definition documented in INSTRUCTIONS — always state the definition when answering.',
    ),
    ExampleQuery(
        question="How much did we spend on Genie last month?",
        sql="""\
SELECT
    SUM(u.usage_quantity * COALESCE(p.pricing.default, 0)) AS total_usd,
    SUM(CASE WHEN u.usage_type = 'BILLABLE' THEN u.usage_quantity * COALESCE(p.pricing.default, 0) ELSE 0 END) AS charged_usd,
    SUM(CASE WHEN u.usage_type IN ('NON_BILLABLE', 'RELATED') THEN u.usage_quantity * COALESCE(p.pricing.default, 0) ELSE 0 END) AS free_tier_usd
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
    ON u.sku_name = p.sku_name
   AND u.cloud = p.cloud
   AND p.price_end_time IS NULL
WHERE u.usage_date BETWEEN DATE_TRUNC('month', CURRENT_DATE() - INTERVAL 1 MONTH)
                       AND (DATE_TRUNC('month', CURRENT_DATE()) - INTERVAL 1 DAY)
  AND u.usage_quantity > 0
  AND (u.sku_name ILIKE '%GENIE%' OR u.sku_name ILIKE '%AI_BI_GENIE%')
""",
        note="Genie total split into charged vs free-tier by usage_type. Same convention the Genie tab uses (V2.1_SPEC §5.2).",
    ),
]


# ---------------------------------------------------------------------------
# Benchmark questions — a curated set of natural-language questions that the
# space should answer correctly with the instructions + example SQL above.
# These get uploaded as "sample questions" in the Genie UI and act as a smoke
# test for the space's quality after seeding.
# ---------------------------------------------------------------------------

BENCHMARK_QUESTIONS: List[str] = [
    "What did we spend last month?",
    "Which workspaces drove last quarter's increase?",
    "What is the cost trend for AI products over the last 90 days?",
    "Show the top 10 users by spend this month.",
    "How much did we spend on Genie last month, broken down by charged vs free-tier?",
    "What's the cost of model serving this month?",
    "Which product are we spending most on right now?",
    "Show me monthly Databricks spend for the last 6 months.",
]


# ---------------------------------------------------------------------------
# Unsupported question templates — Genie is instructed to reject these,
# but we also list them so the operator can add them as negative examples
# in the UI (Databricks Genie's rejection guidance improves with negative
# examples).
# ---------------------------------------------------------------------------

UNSUPPORTED_QUESTIONS: List[str] = [
    "What's the cost per query for our warehouses?",
    "Explain why last week's DBU spike happened.",
    "How much will we spend next month?",
    "Which EC2 instances cost the most?",
    "What's the ROI of our cost-obs deployment?",
]


def render_manual_setup_doc() -> str:
    """Render the full curation content as a single markdown-style string.

    Used by seed_genie() when the workspace's API endpoints for programmatic
    Genie space curation aren't available — the operator gets a printout to
    copy into the Genie space UI manually.
    """
    lines: List[str] = []
    lines.append("# Genie Space Curation — Manual Setup")
    lines.append("")
    lines.append(
        "The workspace didn't expose programmatic Genie space curation "
        "endpoints, so the seeding was best-effort. Copy the content below "
        "into the Genie space's configuration UI to finish the setup."
    )
    lines.append("")
    lines.append("## 1. Trusted Assets")
    lines.append("")
    lines.append("Add each of these tables to the Genie space's trusted asset list:")
    lines.append("")
    for t in TRUSTED_ASSETS:
        lines.append(f"- `{t}`")
    lines.append("")
    lines.append("## 2. Instructions")
    lines.append("")
    lines.append("Paste this into the Genie space's Instructions field:")
    lines.append("")
    lines.append("```")
    lines.append(INSTRUCTIONS.rstrip())
    lines.append("```")
    lines.append("")
    lines.append("## 3. Example SQL Queries")
    lines.append("")
    lines.append(
        "Add each as a curated example. The question is what the user asks; "
        "the SQL is what Genie should produce. The note is context for the "
        "operator only, not for Genie."
    )
    for eq in EXAMPLE_QUERIES:
        lines.append("")
        lines.append(f"### {eq.question}")
        lines.append("")
        lines.append(f"*Why this SQL:* {eq.note}")
        lines.append("")
        lines.append("```sql")
        lines.append(eq.sql.rstrip())
        lines.append("```")
    lines.append("")
    lines.append("## 4. Benchmark Questions")
    lines.append("")
    lines.append("Add these as sample questions in the Genie UI:")
    lines.append("")
    for q in BENCHMARK_QUESTIONS:
        lines.append(f"- {q}")
    lines.append("")
    lines.append("## 5. Unsupported Questions (negative examples)")
    lines.append("")
    lines.append(
        "Add these as sample questions marked \"unsupported\" so Genie learns "
        "to reject the pattern instead of hallucinating an answer:"
    )
    lines.append("")
    for q in UNSUPPORTED_QUESTIONS:
        lines.append(f"- {q}")
    lines.append("")
    return "\n".join(lines)
