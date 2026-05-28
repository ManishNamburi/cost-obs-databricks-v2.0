# Genie Space Configuration Guide

## Quick Setup (Recommended)

Import a pre-configured Genie Space with one command:

```bash
uv run python scripts/import_genie_space.py
```

This will automatically:
- Import a production-ready Genie Space configuration from the [Cost-Reporting-Genie](https://github.com/numanali-db/Cost-Reporting-Genie) repository
- Configure all required system billing tables
- Add comprehensive instructions and sample questions
- Update your `.env.local` with the Space ID
- Display the Genie Space URL for verification

### What's Included

The imported Genie Space includes:

**Data Sources:**
- `system.billing.usage` - All usage records with DBU consumption
- `system.billing.list_prices` - Current pricing by SKU and cloud provider
- `system.billing.account_prices` - Account-specific discounted pricing (Private Preview)
- `system.access.workspaces_latest` - Workspace metadata for attribution

**Features:**
- 17 benchmark questions with verified SQL answers
- Comprehensive cost analysis instructions
- Join specifications for multi-table queries
- SQL filters for common cost categories (AI products, workflows, serverless, etc.)
- Column configurations with value dictionaries
- Example question/SQL pairs for AI learning

**Sample Questions:**
- "What are my top 5 most expensive workspaces this month?"
- "Show me daily spending trends for the last 30 days"
- "Which SQL warehouses consume the most DBUs?"
- "What is the cost breakdown by product type?"
- "Show me AI/ML workload costs vs traditional data engineering"

### Next Steps After Import

1. Visit your Genie Space (URL will be displayed after import)
2. Restart the watch server to use the new configuration:
   ```bash
   pkill -f watch.sh
   nohup ./watch.sh > /tmp/databricks-app-watch.log 2>&1 &
   ```
3. Open the app and test the Genie Assistant tab

## Manual Setup Steps (Alternative)

### 1. Create Genie Space

1. Visit your Databricks workspace: https://e2-demo-field-eng.cloud.databricks.com/sql/genie
2. Click **"Create Space"** button
3. Name it: **"Cost Observability & Control (COC)"**
4. Select a SQL Warehouse (e.g., "siddy")

### 2. Add System Tables

Add these system tables to your Genie Space:

- `system.billing.usage`
- `system.billing.list_prices`
- `system.compute.clusters`
- `system.lakeflow.pipelines` (for batch vs streaming analysis)

### 3. Add Instructions

Copy and paste these instructions into your Genie Space:

```
This space provides access to Databricks system tables for cost analysis.

Key Tables:
- system.billing.usage: Usage records with DBU consumption, SKUs, and metadata
- system.billing.list_prices: Current pricing for all SKUs by cloud provider
- system.compute.clusters: Cluster configurations including instance types
- system.lakeflow.pipelines: Pipeline configurations for DLT execution mode

Important Columns:
- usage_date: Date of usage
- sku_name: Product SKU (ALL_PURPOSE_COMPUTE, JOBS_COMPUTE, SERVERLESS_SQL, etc.)
- usage_quantity: DBUs consumed
- workspace_id: Workspace identifier
- billing_origin_product: Product taxonomy (SQL, JOBS, DLT)
- usage_metadata: JSON with cluster_id, warehouse_id, notebook_path, etc.
- identity_metadata: JSON with run_as user information

Common Queries:
- Top expensive workspaces by total spend
- Daily spending trends over time periods
- SQL warehouse DBU consumption analysis
- Cost breakdown by product/SKU type
- Most expensive notebooks and users
- Interactive compute vs jobs compute attribution
- Batch vs streaming costs for DLT pipelines
```

### 4. Add Sample Questions

Add these sample questions to help users:

- "What are my top 5 most expensive workspaces this month?"
- "Show me daily spending trends for the last 30 days"
- "Which SQL warehouses consume the most DBUs?"
- "What percentage of costs come from interactive compute?"
- "Show me the most expensive notebooks by total spend"
- "Show me batch vs streaming costs for DLT pipelines"

### 5. Get Your Space ID and Configure the App

1. In your Genie Space, click the **'...'** menu
2. Copy the **Space ID** (format: `01f0fada534f16b19656a2e3ebd0f46e`)
3. Run this command to update your `.env.local`:

```bash
uv run python scripts/setup_genie_space.py <space-id>
```

4. Restart the watch server:

```bash
pkill -f watch.sh
nohup ./watch.sh > /tmp/databricks-app-watch.log 2>&1 &
```

5. Open the app and click the **"Genie Assistant"** tab

## Verification

After setup, you should be able to:

- ✅ See the Genie chat interface in the dashboard
- ✅ Ask questions about your cost data
- ✅ Get SQL queries and visualizations
- ✅ Access all system billing tables

## Troubleshooting

**Genie tab not showing:**
- Check that `GENIE_SPACE_ID` is set in `.env.local`
- Restart the watch server after updating `.env.local`

**"No tables found" error:**
- Ensure all system tables are added to your Genie Space
- Check warehouse permissions for system table access

**API errors:**
- Verify `DATABRICKS_HOST` and `DATABRICKS_TOKEN` are correct
- Ensure the Space ID is valid and accessible with your token
