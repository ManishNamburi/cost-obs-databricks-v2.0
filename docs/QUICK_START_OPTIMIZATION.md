# Quick Start Performance Optimization

## Immediate Actions (15 minutes total)

### 1. Upgrade SQL Warehouse Size (5 minutes)

**Option A: Via Databricks UI (Recommended)**
1. Open Databricks workspace: https://fevm-cmegdemos.cloud.databricks.com
2. Navigate to **SQL** → **Warehouses**
3. Find warehouse with ID `dde448100db8752a`
4. Click **Edit**
5. Change settings:
   - **Size:** Large or X-Large (currently likely Small/Medium)
   - **Type:** Serverless (if available) - CHECK THIS BOX
   - **Photon:** Enabled - CHECK THIS BOX
6. Click **Save**

**Expected Impact:** 4-6x faster query execution

**Option B: Via Databricks API**
If you have admin access and know the Databricks CLI:
```bash
# First check current size
databricks warehouses get dde448100db8752a

# Then update (adjust as needed)
databricks warehouses update dde448100db8752a \
  --size "LARGE" \
  --enable-photon true
```

---

### 2. Update Cache TTL for Better Performance (5 minutes)

**Current:** 10-minute cache for all queries
**Problem:** Even recent data is cached for 10 minutes

**Quick Fix:** Adjust cache TTL in `.env.local`:
```bash
# Add to .env.local
QUERY_CACHE_TTL=600  # 10 minutes for historical data
```

Then update `server/db.py` to use smarter caching (see below).

---

### 3. Enable Parallel Query Execution (Will implement in code)

See `PARALLEL_EXECUTION.md` for implementation details.

---

## Performance Gains Expected

### Current Performance
| Metric | Time |
|--------|------|
| First page load (cold cache) | 60-90 seconds |
| Page load (warm cache) | <1 second |

### After Warehouse Upgrade (Phase 1)
| Metric | Time | Improvement |
|--------|------|-------------|
| First page load | 15-25 seconds | **4-6x faster** |
| Page load (warm cache) | <1 second | Same |

### After Parallel Execution (Phase 2)
| Metric | Time | Improvement |
|--------|------|-------------|
| First page load | **5-10 seconds** | **6-12x faster** |
| Page load (warm cache) | <1 second | Same |

---

## Cost Impact

### Warehouse Size Upgrade
- **Small → Medium:** ~2x cost, 2x performance (neutral cost per query)
- **Small → Large:** ~4x cost, 4x performance (neutral cost per query)
- **Small → X-Large:** ~8x cost, 8x performance (neutral cost per query)

### Serverless Premium
- Additional 10-20% cost
- Benefits:
  - Instant cold start (no spin-up delay)
  - Better auto-scaling
  - Pay only for actual compute used

### Recommended Configuration
**Size:** Large (4x compute)
**Type:** Serverless
**Photon:** Enabled
**Est. Cost:** $4-8/hour (vs current ~$1-2/hour)
**Daily Usage:** ~2-3 hours → **~$12-24/day** vs current ~$3-6/day

**ROI:** User time saved (1-2 hours/day) >> Additional cost ($10-20/day)

---

## Warehouse Commands Reference

### Check Current Configuration
```sql
-- Run this in Databricks SQL Editor
SELECT
  warehouse_id,
  warehouse_name,
  cluster_size,
  warehouse_type,
  enable_photon,
  enable_serverless_compute
FROM system.compute.warehouse_events
WHERE warehouse_id = 'dde448100db8752a'
ORDER BY timestamp DESC
LIMIT 1;
```

### Check Warehouse Query Performance
```sql
-- See recent query performance
SELECT
  query_start_time,
  execution_duration,
  rows_produced,
  warehouse_id
FROM system.query.history
WHERE warehouse_id = 'dde448100db8752a'
  AND query_start_time >= CURRENT_TIMESTAMP - INTERVAL 1 DAY
ORDER BY query_start_time DESC
LIMIT 20;
```

---

## Next Steps After Warehouse Upgrade

1. **Test Performance:** Refresh the dashboard and observe load times
2. **Implement Parallel Queries:** See `PARALLEL_EXECUTION.md`
3. **Monitor Costs:** Check Databricks billing dashboard after 24 hours
4. **Consider Materialized Tables:** For further optimization (see `PERFORMANCE_OPTIMIZATION.md`)

---

## Questions to Answer

Before upgrading, please check:

1. **Current warehouse size:** Small / Medium / Large / X-Large?
2. **Serverless available:** Yes / No in your region?
3. **Daily query volume:** How many dashboard refreshes per day?
4. **Cost budget:** What's acceptable daily/monthly cost for this app?

---

## Monitoring After Changes

### Dashboard Performance Metrics
Add this to check query times:
```python
# In server/db.py
import time
import logging

logger = logging.getLogger(__name__)

def execute_query(query: str, params: dict[str, Any] | None = None):
    start = time.time()
    result = ... # existing code
    elapsed = time.time() - start
    logger.info(f"Query executed in {elapsed:.2f}s - {query[:100]}")
    return result
```

### Watch Logs
```bash
tail -f /tmp/databricks-app-watch.log | grep "Query executed"
```

