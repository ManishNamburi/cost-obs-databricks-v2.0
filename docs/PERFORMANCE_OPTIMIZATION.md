# Cost Observability Dashboard - Performance Optimization Analysis

## Current Performance Bottlenecks

### 1. Query Execution Analysis
**Current State:**
- **12 separate SQL queries** executed on page load (DBU Costs tab)
- Each query scans `system.billing.usage` table (millions of rows)
- Complex JOINs with `system.billing.list_prices` and `system.query.history`
- Sequential execution in Python backend
- 10-minute server-side cache helps, but first load is slow

**Queries Executed:**
1. Account Info
2. Billing Summary
3. By Product
4. By Workspace
5. Timeseries
6. SQL Breakdown (Genie vs DBSQL)
7. ETL Breakdown
8. Pipeline Objects
9. Interactive Breakdown
10. AWS Cost Estimate (clusters)
11. AWS Cost by Instance Type
12. AWS Cost Timeseries

### 2. SQL Warehouse Configuration
**Current Warehouse:** `dde448100db8752a`
- Size: Unknown (need to check)
- Type: Classic or Serverless?
- Auto-scaling settings?

---

## Optimization Strategy

### Phase 1: SQL Warehouse Optimization (IMMEDIATE - No Code Changes)

#### 1.1 Upgrade Warehouse Size
**Action:** Increase warehouse to **Large** or **X-Large**
- Small → Medium: 2x compute (2x faster)
- Medium → Large: 4x compute (4x faster)
- Large → X-Large: 8x compute (8x faster)

**Cost Impact:** Higher per-query cost, but queries run 2-8x faster
**Latency Impact:** Can reduce query time from 30s → 5-10s per query

**How to implement:**
```bash
# Option 1: Via Databricks UI
1. Go to SQL > Warehouses
2. Find warehouse ID: dde448100db8752a
3. Click "Edit"
4. Change "Cluster size" to "Large" or "X-Large"
5. Enable "Serverless" if available (instant start, better scaling)

# Option 2: Via API
databricks sql-warehouses update dde448100db8752a \
  --size "LARGE" \
  --enable-serverless-compute
```

#### 1.2 Enable Photon Acceleration
**Action:** Enable Photon on the warehouse
- 2-5x faster query execution for system tables
- No accuracy tradeoff
- Minimal additional cost

#### 1.3 Serverless SQL Warehouse
**Best Option:** Migrate to **Serverless SQL Warehouse**
- Instant cold start (no spin-up delay)
- Automatic scaling based on load
- Better multi-query concurrency
- Typically 2-3x faster than classic warehouses

---

### Phase 2: Query Optimization (MEDIUM PRIORITY - Code Changes)

#### 2.1 Create Materialized Base Table
**Problem:** Every query re-scans `system.billing.usage` + `list_prices`

**Solution:** Create a single materialized view with pre-joined data
```sql
CREATE OR REPLACE TABLE main.cost_observability.billing_enriched_mv
TBLPROPERTIES ('delta.autoOptimize.optimizeWrite' = 'true')
AS
SELECT
  u.usage_date,
  u.workspace_id,
  u.account_id,
  u.cloud,
  u.sku_name,
  u.billing_origin_product,
  u.usage_quantity,
  u.usage_metadata,
  COALESCE(p.pricing.default, 0) as price_per_dbu,
  u.usage_quantity * COALESCE(p.pricing.default, 0) as spend
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
  ON u.sku_name = p.sku_name
  AND u.cloud = p.cloud
  AND p.price_end_time IS NULL
WHERE u.usage_date >= CURRENT_DATE - 90
  AND u.usage_quantity > 0;

-- Refresh daily via scheduled job
CREATE OR REPLACE SCHEDULE cost_observability_refresh
CRON '0 2 * * *'  -- Run at 2 AM daily
AS
  REFRESH TABLE main.cost_observability.billing_enriched_mv;
```

**Benefits:**
- All queries read from 1 pre-joined table instead of 2 system tables
- Delta table with Z-ordering for faster filters
- **Expected speedup: 3-5x for most queries**

#### 2.2 Optimize Individual Queries

**A. Add Date Filters Earlier**
Current queries scan full date range first, then filter.
```sql
-- ❌ SLOW: Scans all data then filters
WHERE u.usage_date BETWEEN :start_date AND :end_date

-- ✅ FAST: Delta/Photon can skip partitions
WHERE u.usage_date >= :start_date
  AND u.usage_date <= :end_date
  AND u.usage_quantity > 0  -- Filter nulls early
```

**B. Reduce Query Complexity**
Some queries have redundant CTEs and can be simplified.

Example: `BILLING_BY_PRODUCT` has 4 CTEs - can be reduced to 2.

**C. Add Indexes/Z-Ordering**
```sql
OPTIMIZE main.cost_observability.billing_enriched_mv
ZORDER BY (usage_date, workspace_id, billing_origin_product);
```

---

### Phase 3: Backend Optimization (HIGH IMPACT - Code Changes)

#### 3.1 Parallel Query Execution
**Current:** Queries run sequentially in Python
**Proposed:** Execute queries in parallel using `asyncio`

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

async def execute_queries_parallel(queries: list[tuple[str, dict]]):
    """Execute multiple queries in parallel."""
    with ThreadPoolExecutor(max_workers=6) as executor:
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(executor, execute_query, query, params)
            for query, params in queries
        ]
        results = await asyncio.gather(*tasks)
    return results
```

**Expected Impact:**
- Current: 12 queries × 5s each = **60 seconds total**
- With parallel: max(query_times) = **5-10 seconds total**
- **6-12x speedup** for full page load

#### 3.2 Incremental Loading (Frontend)
**Current:** Frontend waits for all queries before rendering
**Proposed:** Render components as data arrives

**Changes needed:**
1. Return queries incrementally via streaming response
2. Update frontend to show loading states per component
3. Critical queries first (summary), heavy queries last (AWS costs)

#### 3.3 Smarter Caching Strategy
**Current:** 10-minute cache for all queries
**Proposed:** Variable TTL based on data freshness

```python
# Historical data (>7 days old) - cache 1 hour
# Recent data (<7 days old) - cache 10 minutes
# Today's data - cache 2 minutes

def get_cache_ttl(start_date: str, end_date: str) -> int:
    """Calculate appropriate cache TTL based on date range."""
    from datetime import datetime, timedelta

    end = datetime.fromisoformat(end_date)
    days_old = (datetime.now() - end).days

    if days_old > 7:
        return 60 * 60  # 1 hour
    elif days_old > 1:
        return 10 * 60  # 10 minutes
    else:
        return 2 * 60   # 2 minutes
```

---

### Phase 4: Advanced Optimizations (OPTIONAL)

#### 4.1 Delta Lake Liquid Clustering
For system tables that support it:
```sql
ALTER TABLE main.cost_observability.billing_enriched_mv
CLUSTER BY (usage_date, workspace_id);
```

#### 4.2 Aggregate Tables for Common Views
Pre-compute common aggregations:
```sql
-- Daily workspace spend rollup
CREATE TABLE main.cost_observability.daily_workspace_spend
AS
SELECT
  usage_date,
  workspace_id,
  SUM(spend) as total_spend,
  SUM(usage_quantity) as total_dbus
FROM main.cost_observability.billing_enriched_mv
GROUP BY usage_date, workspace_id;
```

#### 4.3 Result Set Pagination
For large result sets (>1000 rows), add `LIMIT` clauses and pagination.

---

## Implementation Priority

### ✅ CRITICAL (Do Immediately)
1. **Upgrade SQL Warehouse to Large/X-Large** - 5 minutes, instant 2-4x speedup
2. **Enable Serverless SQL** - 10 minutes, instant start + better concurrency
3. **Enable Photon** - 2 minutes, 2-3x speedup

**Expected Total Speedup: 4-10x faster queries**

### ⚡ HIGH PRIORITY (Do This Week)
4. **Parallel query execution** - 2-3 hours dev work, 6-12x page load speedup
5. **Frontend incremental loading** - 3-4 hours dev work, perceived latency improvement

**Expected Total Speedup: 50-100x faster perceived load time**

### 📊 MEDIUM PRIORITY (Do This Month)
6. **Create materialized base table** - 1 day setup, 3-5x individual query speedup
7. **Optimize individual queries** - 2-3 days, 2-3x speedup per query

### 🚀 OPTIONAL (Future)
8. **Liquid clustering** - 1 day
9. **Aggregate tables** - 2-3 days
10. **Result pagination** - 1-2 days

---

## Expected Performance Gains

### Current State
- **First Load (cold cache):** 60-90 seconds
- **Subsequent Load (warm cache):** <1 second

### After Phase 1 (Warehouse Upgrade)
- **First Load:** 15-30 seconds (4-6x faster)
- **Subsequent Load:** <1 second

### After Phase 2 (Parallel Execution)
- **First Load:** 5-10 seconds (6-12x faster than Phase 1)
- **Subsequent Load:** <1 second

### After Phase 3 (Materialized Tables)
- **First Load:** 2-5 seconds (10-20x faster than current)
- **Subsequent Load:** <1 second

---

## Cost Impact

### SQL Warehouse Costs
- **Small → Large:** ~4x cost per hour, but ~4x faster (same cost per query)
- **Classic → Serverless:** 10-20% premium, but instant start (better value)
- **Photon:** Minimal additional cost (<10%)

### Storage Costs
- **Materialized table:** ~50GB for 90 days of billing data (~$2/month)

### Overall ROI
- **User Time Saved:** 55-85 seconds per page load × 100 loads/day = **1.5 hours/day**
- **Infrastructure Cost Increase:** ~$50-100/month
- **Clear win for user experience**

---

## Next Steps

1. **Check current warehouse size:**
   ```bash
   databricks sql-warehouses get dde448100db8752a | jq '.size'
   ```

2. **Upgrade warehouse:**
   ```bash
   databricks sql-warehouses update dde448100db8752a --size LARGE
   ```

3. **Enable serverless (if available in your region):**
   ```bash
   databricks sql-warehouses update dde448100db8752a --enable-serverless-compute
   ```

4. **Implement parallel query execution** (code changes in `server/routers/billing.py`)

5. **Create materialized table** (SQL + scheduled job)

