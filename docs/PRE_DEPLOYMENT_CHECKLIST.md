# Pre-Deployment Checklist

Use this checklist before deploying Cost Observability & Control to a customer's Databricks environment.

---

## 1. Information to Collect

### Required

| Item | Description | Example |
|------|-------------|---------|
| **Workspace URL** | The customer's Databricks workspace URL | `https://yourcompany.cloud.databricks.com` |
| **SQL Warehouse ID** | ID of the warehouse to use for queries | `abc123def456` |
| **Unity Catalog name** | Catalog for materialized views | `main` (default) |
| **Schema name** | Schema for materialized views | `cost_obs` (default) |
| **Personal Access Token** | Token for the installing user | Generated in workspace settings |

### Optional

| Item | Description |
|------|-------------|
| **Genie Space ID** | If the customer wants the AI cost assistant |
| **AWS CUR S3 path** | If the customer wants actual AWS infrastructure costs |

---

## 2. Customer Environment Prerequisites

### Hard requirements (blockers if missing)

- [ ] **Databricks Apps is enabled** on the workspace
  - Check: Workspace Settings → Apps
  - If not enabled, contact your Databricks account team

- [ ] **Account-level system tables are enabled**
  - Required tables: `system.billing.usage`, `system.billing.list_prices`, `system.compute.clusters`, `system.compute.node_types`
  - Check: run `SELECT * FROM system.billing.usage LIMIT 1` in a notebook
  - If not enabled, a Databricks account admin must enable them

- [ ] **A SQL warehouse exists** (Serverless or Pro recommended)
  - Serverless gives the best query performance
  - Note the warehouse ID from the warehouse settings page

### Recommended

- [ ] **`system.query.history` is accessible** — enables the SQL Warehousing tab
- [ ] **Unity Catalog is enabled** — required for materialized views (sub-second load times)
- [ ] **Lakebase is enabled** — required for alerts, email digests, and user permissions persistence
  - If not available, the app still works but alerts and permissions won't persist across restarts

---

## 3. Permissions the Installing User Needs

| Permission | Why it's needed |
|------------|-----------------|
| **Workspace Admin** | Create the Databricks App, grant the app's service principal access to system tables and warehouse |
| **Account Admin** (or assistance from one) | Enable system tables if not already on |
| **CREATE SCHEMA + CREATE TABLE** on target catalog | Create materialized views for fast query performance |
| **CAN_USE** on the SQL warehouse | Run queries during setup and materialized view creation |

> **Note:** The app's service principal is granted the necessary permissions automatically by the deploy script after deployment completes.

---

## 4. AWS-Specific (Optional — Actual Cloud Costs)

If the customer wants real AWS infrastructure cost data (beyond DBU spend):

- [ ] AWS Cost and Usage Reports (CUR 2.0) is configured
- [ ] CUR data is exported to an S3 bucket
- [ ] The Databricks workspace has an S3 external location pointing to that bucket
- [ ] Customer knows the S3 path to the CUR data

This can be configured after initial deployment using the in-app Cloud Integration Wizard.

---

## 5. Pre-Deployment Setup Steps

1. Clone the repo: `git clone https://github.com/smathews13/cost-obs-databricks.git`
2. Copy the template: `cp app.yaml.example app.yaml`
3. Fill in `app.yaml` with the values collected above
4. Copy the env template: `cp .env.local.example .env.local` *(if provided)*
5. Fill in `.env.local` with `DATABRICKS_HOST` and `DATABRICKS_TOKEN`
6. Run: `bash dba_deploy.sh`

The deploy script will automatically:
- Build the frontend
- Sync files to the Databricks workspace
- Create the Databricks App
- Set up Lakebase (if enabled)
- Grant the app service principal the necessary permissions
- Run health checks to confirm everything is working

---

## 6. Post-Deployment

- [ ] Open the app URL and confirm the dashboard loads
- [ ] Run the **Setup Wizard** (Settings → Setup) to create materialized views
- [ ] Verify billing data is showing in the DBU Overview tab
- [ ] Add users in Settings → Permissions
