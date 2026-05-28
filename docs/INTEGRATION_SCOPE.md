# Integration Scope: Private Preview Cost Tools

This document outlines how to integrate two Databricks private preview projects into the Cost Observability & Control (COC) dashboard.

---

## 1. DBSQL Cost Granularity (Per-Query Attribution)

**Source:** https://github.com/databrickslabs/sandbox/tree/main/dbsql/cost_per_query/PrPr

### What It Does

Creates a materialized view `dbsql_cost_per_query` that provides **query-level cost attribution** for all DBSQL queries. Key capabilities:

- **Per-statement cost breakdown** with hourly granularity
- **Query source identification** distinguishing:
  - `GENIE SPACE` - AI/BI Genie queries
  - `AI/BI DASHBOARD` - Lakeview dashboards
  - `LEGACY DASHBOARD` - Classic SQL dashboards
  - `SQL QUERY` - Ad-hoc SQL queries
  - `NOTEBOOK` - Notebook SQL cells
  - `JOB` - Workflow jobs
  - `ALERT` - SQL alerts
- **Warehouse utilization tracking** (ON/OFF/UTILIZED/IDLE states)
- **Proportional cost allocation** based on actual work done

### Key Schema

```sql
CREATE MATERIALIZED VIEW dbsql_cost_per_query (
  statement_id STRING,
  query_source_id STRING,
  query_source_type STRING,           -- JOB, GENIE SPACE, AI/BI DASHBOARD, etc.
  client_application STRING,
  executed_by STRING,
  warehouse_id STRING,
  statement_text STRING,
  workspace_id STRING,
  statement_hour_bucket_costs ARRAY<STRUCT<
    hour_bucket: TIMESTAMP,
    hour_attributed_cost: DOUBLE,
    hour_attributed_dbus: DOUBLE
  >>,
  start_time TIMESTAMP,
  end_time TIMESTAMP,
  duration_seconds DOUBLE,
  query_attributed_dollars_estimation DOUBLE,
  query_attributed_dbus_estimation DOUBLE,
  url_helper STRING,                  -- Deep link to source object
  query_profile_url STRING
)
SCHEDULE EVERY 1 HOUR
```

### Integration Benefits for COC

1. **Replace current DBSQL vs Genie estimation** with actual query-level attribution
2. **Add new "Query Cost Explorer" tab** with:
   - Cost by query source type (pie chart)
   - Top queries by cost (table)
   - Cost by user/executed_by (bar chart)
   - Query source breakdown within each type
3. **Enhanced Genie insights** - actual Genie query costs, not estimated
4. **Drill-down capability** - link to query profiles and source objects

### Integration Tasks

| Task | Effort | Priority |
|------|--------|----------|
| Add setup script to create MV in customer catalog | Low | P0 |
| Create `/api/dbsql/query-costs` endpoint to query MV | Medium | P0 |
| Build `QueryCostExplorer.tsx` component | Medium | P0 |
| Add aggregation by query_source_type | Low | P0 |
| Add aggregation by executed_by (user) | Low | P1 |
| Add top-N expensive queries table | Low | P1 |
| Deep-link to Databricks query profile | Low | P2 |
| Add to PDF export | Low | P2 |

### Backend Implementation

```python
# server/routers/dbsql.py

QUERY_COST_BY_SOURCE = """
SELECT
  query_source_type,
  COUNT(*) as query_count,
  SUM(query_attributed_dollars_estimation) as total_spend,
  SUM(query_attributed_dbus_estimation) as total_dbus,
  AVG(query_attributed_dollars_estimation) as avg_cost_per_query
FROM {catalog}.{schema}.dbsql_cost_per_query
WHERE start_time >= :start_date
  AND start_time < :end_date
GROUP BY query_source_type
ORDER BY total_spend DESC
"""

QUERY_COST_BY_USER = """
SELECT
  executed_by,
  query_source_type,
  COUNT(*) as query_count,
  SUM(query_attributed_dollars_estimation) as total_spend
FROM {catalog}.{schema}.dbsql_cost_per_query
WHERE start_time >= :start_date
  AND start_time < :end_date
GROUP BY executed_by, query_source_type
ORDER BY total_spend DESC
LIMIT 50
"""

TOP_EXPENSIVE_QUERIES = """
SELECT
  statement_id,
  query_source_type,
  executed_by,
  warehouse_id,
  SUBSTRING(statement_text, 1, 200) as statement_preview,
  duration_seconds,
  query_attributed_dollars_estimation as cost,
  query_attributed_dbus_estimation as dbus,
  query_profile_url
FROM {catalog}.{schema}.dbsql_cost_per_query
WHERE start_time >= :start_date
  AND start_time < :end_date
ORDER BY query_attributed_dollars_estimation DESC
LIMIT 100
"""
```

### Setup Script Addition

```python
# Add to server/materialized_views.py

DBSQL_COST_PER_QUERY_MV = """
CREATE OR REPLACE MATERIALIZED VIEW {catalog}.{schema}.dbsql_cost_per_query
-- [Full SQL from the PrPr project]
SCHEDULE EVERY 1 HOUR
"""
```

---

## 2. AWS Cloud Infrastructure Costs (Actual AWS Billing)

**Source:** https://github.com/databricks-solutions/cloud-infra-costs/tree/main/aws

### What It Does

Integrates **actual AWS Cost and Usage Reports (CUR 2.0)** with Databricks, replacing our current estimation-based AWS costs with real billing data.

### Architecture

```
AWS CUR 2.0 (S3) → Bronze Table → Silver Table → Gold Table
                                       ↓
                              Links to Databricks:
                              - cluster_id
                              - warehouse_id
                              - instance_pool_id
                              - job_id
```

### Gold Table Schema

```sql
CREATE TABLE aws_cost_gold (
  cloud_account_id STRING,
  billing_period STRING,
  usage_start_time TIMESTAMP,
  usage_end_time TIMESTAMP,
  usage_date TIMESTAMP,
  charge_type STRING,                -- Storage, Compute, Networking
  unblended_cost DOUBLE,
  net_unblended_cost DOUBLE,
  amortized_cost DOUBLE,
  net_amortized_cost DOUBLE,
  currency_code STRING,
  usage_metadata STRUCT<
    cluster_id: STRING,
    warehouse_id: STRING,
    instance_pool_id: STRING,
    job_id: STRING
  >
)
```

### Silver Table - Detailed Fields

```sql
-- Key fields linking AWS costs to Databricks
cluster_id STRING,          -- From resource tags
cluster_name STRING,
warehouse_id STRING,        -- SQL warehouse
instance_pool_id STRING,
job_id STRING,
cluster_creator STRING,
instance_type STRING,
region STRING,
pricing_term STRING,        -- OnDemand, Spot, Reserved, SavingsPlan
unblended_cost DOUBLE,
net_unblended_cost DOUBLE,
amortized_cost DOUBLE,
net_amortized_cost DOUBLE
```

### Integration Benefits for COC

1. **Replace estimated AWS costs** with actual CUR data
2. **Support multiple cost types**:
   - Unblended (pay-as-you-go rate)
   - Net Unblended (after discounts)
   - Amortized (spreads upfront costs)
   - Net Amortized (amortized after discounts)
3. **Accurate Reserved Instance / Savings Plan attribution**
4. **Better cost breakdown** by charge type (Compute, Storage, Networking)

### Prerequisites for Customers

| Requirement | Customer Action |
|-------------|-----------------|
| AWS CUR 2.0 Export | Enable in AWS Billing console |
| S3 Bucket | Create bucket for CUR data |
| Unity Catalog External Location | Point to CUR S3 bucket |
| Storage Credential | IAM role with S3 read access |

### Integration Tasks

| Task | Effort | Priority |
|------|--------|----------|
| Add setup notebook for medallion pipeline | Medium | P0 |
| Create `/api/aws/actual-costs` endpoint | Medium | P0 |
| Detect if CUR tables exist, graceful fallback | Low | P0 |
| Update `AWSCostsView.tsx` to show actual vs estimated | Medium | P1 |
| Add cost type selector (Unblended/Amortized/etc.) | Low | P1 |
| Add Reserved/Spot/OnDemand breakdown | Medium | P1 |
| Timeseries of actual AWS costs | Medium | P2 |
| Join AWS costs with DBU costs for total TCO | High | P2 |

### Backend Implementation

```python
# server/routers/aws_actual.py

AWS_ACTUAL_COSTS_SUMMARY = """
SELECT
  SUM(unblended_cost) as total_unblended,
  SUM(net_unblended_cost) as total_net_unblended,
  SUM(amortized_cost) as total_amortized,
  SUM(net_amortized_cost) as total_net_amortized,
  COUNT(DISTINCT usage_metadata.cluster_id) as cluster_count
FROM {catalog}.{schema}.aws_cost_gold
WHERE usage_date >= :start_date
  AND usage_date < :end_date
"""

AWS_COSTS_BY_CLUSTER = """
SELECT
  usage_metadata.cluster_id as cluster_id,
  charge_type,
  SUM(net_unblended_cost) as total_cost,
  COUNT(DISTINCT usage_date) as days_active
FROM {catalog}.{schema}.aws_cost_gold
WHERE usage_date >= :start_date
  AND usage_date < :end_date
  AND usage_metadata.cluster_id IS NOT NULL
GROUP BY usage_metadata.cluster_id, charge_type
ORDER BY total_cost DESC
"""

AWS_COSTS_TIMESERIES = """
SELECT
  DATE(usage_date) as date,
  charge_type,
  SUM(net_unblended_cost) as daily_cost
FROM {catalog}.{schema}.aws_cost_gold
WHERE usage_date >= :start_date
  AND usage_date < :end_date
GROUP BY DATE(usage_date), charge_type
ORDER BY date
"""
```

### Hybrid Mode (Estimated + Actual)

Since not all customers will have CUR set up, implement graceful degradation:

```python
@router.get("/costs")
async def get_aws_costs(start_date: str, end_date: str):
    # Check if actual CUR tables exist
    cur_available = await check_cur_tables_exist()

    if cur_available:
        # Use actual CUR data
        return await get_actual_aws_costs(start_date, end_date)
    else:
        # Fall back to estimation (current implementation)
        return await get_estimated_aws_costs(start_date, end_date)
```

---

## 3. Combined Integration Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Cost Observability & Control                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │
│  │ DBU Costs   │  │ Query Costs │  │ AWS Costs   │  │ Total TCO  │  │
│  │ (existing)  │  │ (NEW)       │  │ (enhanced)  │  │ (NEW)      │  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────┬──────┘  │
│         │                │                │                │         │
│         ▼                ▼                ▼                ▼         │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                      API Layer                               │    │
│  │  /api/billing/*  /api/dbsql/*  /api/aws/*  /api/tco/*       │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              │                                       │
└──────────────────────────────┼───────────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        ▼                      ▼                      ▼
┌───────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ System Tables │    │ DBSQL Cost MV   │    │ AWS CUR Tables  │
│               │    │ (PrPr project)  │    │ (cloud-infra)   │
├───────────────┤    ├─────────────────┤    ├─────────────────┤
│ billing.usage │    │ dbsql_cost_     │    │ aws_cost_bronze │
│ query.history │    │ per_query       │    │ aws_cost_silver │
│ compute.*     │    │                 │    │ aws_cost_gold   │
└───────────────┘    └─────────────────┘    └─────────────────┘
```

---

## 4. Implementation Phases

### Phase 1: DBSQL Query Cost Attribution (1-2 weeks)

1. **Add MV creation to setup flow**
   - Include SQL in `server/materialized_views.py`
   - Add to auto-setup on first load

2. **Create new API router** (`server/routers/dbsql.py`)
   - `/api/dbsql/query-costs/by-source` - Costs by source type
   - `/api/dbsql/query-costs/by-user` - Costs by user
   - `/api/dbsql/query-costs/top-queries` - Most expensive queries
   - `/api/dbsql/query-costs/genie` - Genie-specific breakdown

3. **Build frontend components**
   - `QueryCostExplorer.tsx` - New tab component
   - Pie chart: Cost by query source type
   - Bar chart: Top users by query cost
   - Table: Expensive queries with links

4. **Update existing views**
   - Replace DBSQL/Genie estimation in GranularView with actual data

### Phase 2: AWS Actual Costs Integration (2-3 weeks)

1. **Add setup workflow**
   - Guide user through CUR setup
   - Create bronze/silver/gold tables
   - Check for existing CUR data

2. **Create new API router** (`server/routers/aws_actual.py`)
   - `/api/aws/actual/summary` - Total costs with multiple cost types
   - `/api/aws/actual/by-cluster` - Costs per cluster
   - `/api/aws/actual/by-charge-type` - Compute/Storage/Network split
   - `/api/aws/actual/timeseries` - Daily costs over time

3. **Update AWS costs view**
   - Toggle between Estimated and Actual modes
   - Cost type selector (Unblended, Amortized, etc.)
   - Reserved/Spot/OnDemand breakdown

4. **Add Total Cost of Ownership view**
   - Combine DBU + AWS costs
   - Show true infrastructure cost per workload

### Phase 3: Enhanced Features (1-2 weeks)

1. **PDF Export updates** - Add query costs and actual AWS sections
2. **Genie Space integration** - Enhanced Genie cost visibility
3. **Alerting** - Cost anomaly detection on query-level data
4. **Deep linking** - Click to see query profile in Databricks

---

## 5. New TypeScript Types

```typescript
// types/billing.ts additions

// DBSQL Query Costs
export interface QueryCostBySource {
  query_source_type: string;
  query_count: number;
  total_spend: number;
  total_dbus: number;
  avg_cost_per_query: number;
}

export interface QueryCostByUser {
  executed_by: string;
  query_source_type: string;
  query_count: number;
  total_spend: number;
}

export interface ExpensiveQuery {
  statement_id: string;
  query_source_type: string;
  executed_by: string;
  warehouse_id: string;
  statement_preview: string;
  duration_seconds: number;
  cost: number;
  dbus: number;
  query_profile_url: string;
}

// AWS Actual Costs
export interface AWSActualCostsSummary {
  total_unblended: number;
  total_net_unblended: number;
  total_amortized: number;
  total_net_amortized: number;
  cluster_count: number;
  data_source: 'actual' | 'estimated';
}

export interface AWSCostByCluster {
  cluster_id: string;
  charge_type: string;
  total_cost: number;
  days_active: number;
}

export interface AWSCostTimeseries {
  date: string;
  charge_type: string;
  daily_cost: number;
}
```

---

## 6. Customer Setup Requirements

### For DBSQL Query Costs
- **Automatic** - MV created in customer's catalog/schema during setup
- **Permissions**: CREATE MATERIALIZED VIEW on target schema
- **No additional infrastructure required**

### For AWS Actual Costs
| Step | Customer Action | COC Support |
|------|----------------|-------------|
| 1 | Enable CUR 2.0 in AWS Billing | Documentation link |
| 2 | Create S3 bucket for exports | Documentation link |
| 3 | Create UC External Location | Setup wizard |
| 4 | Create Storage Credential | Setup wizard |
| 5 | Run setup workflow | One-click in COC |

---

## 7. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| MV creation fails (permissions) | Medium | Graceful fallback to estimation |
| CUR data not available | Low | Hybrid mode with estimation fallback |
| Large query history tables | Medium | Add date filters, use MV aggregations |
| MV refresh delays | Low | Show "last updated" timestamp |
| AWS CUR schema changes | Low | Version detection, adapter pattern |

---

## 8. Success Metrics

1. **DBSQL Query Costs**
   - Accuracy: Compare MV totals vs system.billing.usage
   - Genie attribution: % of SQL spend correctly attributed to Genie

2. **AWS Actual Costs**
   - Coverage: % of clusters with matched AWS costs
   - Accuracy: Delta between CUR totals and estimation

3. **User Adoption**
   - % of deployments with MV created
   - % of deployments with CUR integration
