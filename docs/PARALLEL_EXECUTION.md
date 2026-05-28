# Parallel Query Execution Implementation

## Problem

Currently, the dashboard executes **12 queries sequentially**:
1. Account Info
2. Billing Summary
3. By Product
4. By Workspace
5. Timeseries
6. SQL Breakdown
7. ETL Breakdown
8. Pipeline Objects
9. Interactive Breakdown
10. AWS Cost Estimate
11. AWS Instance Types
12. AWS Timeseries

**Sequential execution:**
```
Query 1 (5s) → Query 2 (5s) → Query 3 (5s) → ... → Query 12 (5s) = 60 seconds
```

**Parallel execution:**
```
┌─ Query 1 (5s) ─┐
├─ Query 2 (5s) ─┤
├─ Query 3 (5s) ─┤
├─ Query 4 (5s) ─┤    } = max(5s) = 5 seconds total
├─ Query 5 (5s) ─┤
└─ Query 6 (5s) ─┘
```

## Solution: ThreadPoolExecutor

Use Python's `concurrent.futures` to execute queries in parallel.

### Updated `server/db.py`

Add parallel execution function:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

def execute_queries_parallel(
    query_funcs: list[tuple[str, Callable]]
) -> dict[str, Any]:
    """Execute multiple queries in parallel.

    Args:
        query_funcs: List of (name, lambda) tuples where lambda executes the query

    Returns:
        Dictionary mapping query names to results
    """
    results = {}

    # Use ThreadPoolExecutor for parallel execution
    # Max 6 workers to avoid overwhelming the warehouse
    with ThreadPoolExecutor(max_workers=6) as executor:
        # Submit all queries
        future_to_name = {
            executor.submit(func): name
            for name, func in query_funcs
        }

        # Collect results as they complete
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                results[name] = future.result()
            except Exception as e:
                logger.error(f"Query {name} failed: {e}")
                results[name] = None

    return results
```

### Usage Example

#### Before (Sequential)
```python
@router.get("/dashboard-data")
async def get_dashboard_data(
    start_date: str = Query(default=None),
    end_date: str = Query(default=None),
):
    params = {
        "start_date": start_date or get_default_start_date(),
        "end_date": end_date or get_default_end_date(),
    }

    # Sequential - SLOW
    summary = execute_query(BILLING_SUMMARY, params)
    products = execute_query(BILLING_BY_PRODUCT, params)
    workspaces = execute_query(BILLING_BY_WORKSPACE, params)
    timeseries = execute_query(BILLING_TIMESERIES, params)
    # ... 8 more queries

    return {
        "summary": summary,
        "products": products,
        # ...
    }
```

#### After (Parallel)
```python
@router.get("/dashboard-data")
async def get_dashboard_data(
    start_date: str = Query(default=None),
    end_date: str = Query(default=None),
):
    params = {
        "start_date": start_date or get_default_start_date(),
        "end_date": end_date or get_default_end_date(),
    }

    # Parallel - FAST
    queries = [
        ("summary", lambda: execute_query(BILLING_SUMMARY, params)),
        ("products", lambda: execute_query(BILLING_BY_PRODUCT, params)),
        ("workspaces", lambda: execute_query(BILLING_BY_WORKSPACE, params)),
        ("timeseries", lambda: execute_query(BILLING_TIMESERIES, params)),
        ("sql_breakdown", lambda: execute_query(SQL_TOOL_ATTRIBUTION, params)),
        ("etl_breakdown", lambda: execute_query(ETL_BREAKDOWN, params)),
        ("pipeline_objects", lambda: execute_query(PIPELINE_OBJECTS, params)),
        ("interactive", lambda: execute_query(INTERACTIVE_BREAKDOWN, params)),
        ("aws_clusters", lambda: execute_query(AWS_COST_ESTIMATE, params)),
        ("aws_instances", lambda: execute_query(AWS_COST_BY_INSTANCE_TYPE, params)),
        ("aws_timeseries", lambda: execute_query(AWS_COST_TIMESERIES, params)),
    ]

    results = execute_queries_parallel(queries)

    return {
        "summary": results["summary"],
        "products": results["products"],
        # ...
    }
```

## Implementation Steps

### 1. Update `server/db.py`
Add the `execute_queries_parallel` function shown above.

### 2. Create New Aggregated Endpoint
Add a new endpoint in `server/routers/billing.py`:

```python
@router.get("/dashboard-bundle")
async def get_dashboard_bundle(
    start_date: str = Query(default=None),
    end_date: str = Query(default=None),
) -> dict[str, Any]:
    """Get all dashboard data in a single request with parallel execution."""
    params = {
        "start_date": start_date or get_default_start_date(),
        "end_date": end_date or get_default_end_date(),
    }

    # Execute all queries in parallel
    queries = [
        ("account", lambda: execute_query(ACCOUNT_INFO)),
        ("summary", lambda: execute_query(BILLING_SUMMARY, params)),
        ("products", lambda: execute_query(BILLING_BY_PRODUCT, params)),
        ("workspaces", lambda: execute_query(BILLING_BY_WORKSPACE, params)),
        ("timeseries", lambda: execute_query(BILLING_TIMESERIES, params)),
        ("sql_breakdown", lambda: execute_query(SQL_TOOL_ATTRIBUTION, params)),
        ("etl_breakdown", lambda: execute_query(ETL_BREAKDOWN, params)),
        ("pipeline_objects", lambda: execute_query(PIPELINE_OBJECTS, params)),
        ("interactive", lambda: execute_query(INTERACTIVE_BREAKDOWN, params)),
        ("aws_clusters", lambda: execute_query(AWS_COST_ESTIMATE, params)),
        ("aws_instances", lambda: execute_query(AWS_COST_BY_INSTANCE_TYPE, params)),
        ("aws_timeseries", lambda: execute_query(AWS_COST_TIMESERIES, params)),
    ]

    results = execute_queries_parallel(queries)

    # Format responses to match existing endpoint structures
    return {
        "account": format_account_response(results["account"]),
        "summary": format_summary_response(results["summary"], params),
        "products": format_products_response(results["products"], params),
        # ... etc
    }
```

### 3. Update Frontend (Optional)
Instead of making 12 separate API calls, make 1 call to `/dashboard-bundle`:

```typescript
// client/src/hooks/useBillingData.ts
export function useDashboardBundle(dateRange?: DateRange) {
  return useQuery({
    queryKey: ["billing", "bundle", dateRange],
    queryFn: () => fetchJson(buildUrl("/api/billing/dashboard-bundle", dateRange)),
  });
}
```

## Performance Impact

### Current (Sequential)
```
12 queries × 5 seconds each = 60 seconds
```

### With Parallel Execution
```
max(query_times) with 6 workers = ~10 seconds
```

**Speedup: 6x faster**

### With Warehouse Upgrade + Parallel
```
max(query_times) with Large warehouse = ~2 seconds
```

**Combined speedup: 30x faster (60s → 2s)**

## Thread Safety

The `databricks-sql-connector` is thread-safe for concurrent queries:
- Each thread gets its own connection from the pool
- Connection pooling is handled automatically
- No race conditions on cache (using thread-safe dict)

## Monitoring

Add logging to track parallel execution:

```python
import logging
import time

logger = logging.getLogger(__name__)

def execute_queries_parallel(query_funcs):
    start_time = time.time()
    results = {}

    with ThreadPoolExecutor(max_workers=6) as executor:
        future_to_name = {
            executor.submit(func): name
            for name, func in query_funcs
        }

        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                query_start = time.time()
                results[name] = future.result()
                query_elapsed = time.time() - query_start
                logger.info(f"✓ {name}: {query_elapsed:.2f}s")
            except Exception as e:
                logger.error(f"✗ {name}: {e}")
                results[name] = None

    total_elapsed = time.time() - start_time
    logger.info(f"Parallel execution completed: {total_elapsed:.2f}s total")

    return results
```

## Next Steps

1. Implement `execute_queries_parallel` in `server/db.py`
2. Create `/dashboard-bundle` endpoint in `server/routers/billing.py`
3. Test with `curl` to verify performance
4. (Optional) Update frontend to use bundle endpoint
5. Monitor logs for performance gains

