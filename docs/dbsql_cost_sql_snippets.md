# DBSQL Cost Attribution - SQL Code Snippets Comparison

## Quick Reference Guide for Implementation Differences

---

## 1. Warehouse Utilization Tracking (PrPr Only)

### PrPr: Warehouse State Events
```sql
window_events AS (
    SELECT
        warehouse_id,
        event_type,
        event_time,
        cluster_count,
        CASE
            WHEN cluster_count = 0 THEN 'OFF'
            WHEN cluster_count > 0 THEN 'ON'
        END AS warehouse_state
    FROM system.compute.warehouse_events AS we
    WHERE warehouse_id IN (SELECT warehouse_id FROM cte_warehouse)
    AND event_time >= (SELECT timestampadd(day, -1, selected_start_time) FROM table_boundaries)
    AND event_time <= (SELECT selected_end_time FROM table_boundaries)
)
```

### PrPr: Utilization Calculation
```sql
utilization_by_warehouse AS (
  SELECT warehouse_id,
    ts_hour as warehouse_hour,
    COALESCE(SUM(duration) FILTER(WHERE utilization_flag = 'UTILIZED'), 0) as utilized_seconds,
    COALESCE(SUM(duration) FILTER(WHERE utilization_flag = 'ON_IDLE'), 0) as idle_seconds,
    COALESCE(SUM(duration) FILTER(WHERE utilization_flag = 'OFF'), 0) as off_seconds,
    COALESCE(SUM(duration), 0) as total_seconds,
    TRY_DIVIDE(utilized_seconds, utilized_seconds + idle_seconds)::decimal(3,2) as utilization_proportion
  FROM cte_merge_periods
  GROUP BY warehouse_id, ts_hour
)
```

### 2K: No Utilization Tracking
```sql
-- Current implementation does not track warehouse state
-- All hours treated as fully utilized
```

**Impact**: PrPr only charges queries for the proportion of time the warehouse was actually utilized.

---

## 2. Work Calculation

### PrPr: Comprehensive Work Metrics
```sql
cpq_warehouse_query_history AS (
  SELECT
    -- ...
    (COALESCE(CAST(total_task_duration_ms AS FLOAT) / 1000, 0) +
     COALESCE(CAST(result_fetch_duration_ms AS FLOAT) / 1000, 0) +
     COALESCE(CAST(compilation_duration_ms AS FLOAT) / 1000, 0)
    ) AS query_work_task_time,
    start_time,
    end_time,
    timestampadd(MILLISECOND,
      coalesce(waiting_at_capacity_duration_ms, 0) +
      coalesce(waiting_for_compute_duration_ms, 0) +
      coalesce(compilation_duration_ms, 0),
      start_time
    ) AS query_work_start_time,
    timestampadd(MILLISECOND,
      coalesce(result_fetch_duration_ms, 0),
      end_time
    ) AS query_work_end_time
  FROM system.query.history AS h
  WHERE total_task_duration_ms > 0 -- exclude metadata operations
)
```

### 2K: Simple Work Calculation
```sql
queries_with_details AS (
  SELECT
    -- ...
    (UNIX_TIMESTAMP(q.end_time) - UNIX_TIMESTAMP(q.start_time)) AS duration_seconds,
    q.total_task_duration_ms
  FROM system.query.history q
)

-- Later used as:
COALESCE(q.total_task_duration_ms, q.duration_seconds * 1000)
```

**Impact**: PrPr captures compilation and fetch time; excludes waiting time from cost attribution.

---

## 3. Multi-Hour Query Handling

### PrPr: Hour Explosion with Overlap Calculation
```sql
hour_intervals AS (
  SELECT
    statement_id,
    warehouse_id,
    query_work_start_time,
    query_work_end_time,
    query_work_task_time,
    explode(
      sequence(
        0,
        floor((UNIX_TIMESTAMP(query_work_end_time) - UNIX_TIMESTAMP(date_trunc('hour', query_work_start_time))) / 3600)
      )
    ) AS hours_interval,
    timestampadd(hour, hours_interval, date_trunc('hour', query_work_start_time)) AS hour_bucket
  FROM cpq_warehouse_query_history
),

statement_proportioned_work AS (
    SELECT *,
        GREATEST(0,
          UNIX_TIMESTAMP(LEAST(query_work_end_time, timestampadd(hour, 1, hour_bucket))) -
          UNIX_TIMESTAMP(GREATEST(query_work_start_time, hour_bucket))
        ) AS overlap_duration,
        CASE WHEN CAST(query_work_end_time AS DOUBLE) - CAST(query_work_start_time AS DOUBLE) = 0
        THEN 0
        ELSE query_work_task_time * (overlap_duration / (CAST(query_work_end_time AS DOUBLE) - CAST(query_work_start_time AS DOUBLE)))
        END AS proportional_query_work
    FROM hour_intervals
)
```

### 2K: Single Hour Attribution
```sql
-- Queries attributed to single hour bucket
DATE_TRUNC('hour', q.start_time) AS query_hour

-- No splitting across hours
-- All cost allocated to start hour
```

**Impact**: PrPr accurately distributes long-running query costs across all hours of execution.

---

## 4. Cost Attribution Formula

### PrPr: Two-Stage Attribution with Utilization
```sql
query_attribution AS (
  SELECT
    -- First stage: Adjust warehouse cost by utilization
    -- Second stage: Allocate to queries proportionally
    (warehouse_utilization_proportion * total_warehouse_period_dollars) *
    (attributed_query_work / total_work_done_on_warehouse) AS query_attributed_dollars_estimation,

    (warehouse_utilization_proportion * total_warehouse_period_dbus) *
    (attributed_query_work / total_work_done_on_warehouse) AS query_attributed_dbus_estimation
  FROM history_with_pricing a
)
```

### 2K: Simple Proportional Attribution
```sql
query_costs AS (
  SELECT
    CASE
      WHEN w.total_work_ms > 0 THEN
        (COALESCE(q.total_task_duration_ms, q.duration_seconds * 1000) / w.total_work_ms) * h.hourly_dbus
      ELSE 0
    END AS query_attributed_dbus_estimation,
    CASE
      WHEN w.total_work_ms > 0 THEN
        (COALESCE(q.total_task_duration_ms, q.duration_seconds * 1000) / w.total_work_ms) * h.hourly_dollars
      ELSE 0
    END AS query_attributed_dollars_estimation
  FROM queries_with_details q
  LEFT JOIN warehouse_hourly_work w ON ...
  LEFT JOIN warehouse_hourly_usage h ON ...
)
```

**Impact**: PrPr's utilization adjustment ensures fairer cost distribution.

---

## 5. Table Boundary Validation

### PrPr: Dynamic Boundary Checking
```sql
table_boundaries AS (
SELECT
  (SELECT MAX(event_time) FROM system.compute.warehouse_events) AS max_events_ts,
  (SELECT MAX(end_time) FROM system.query.history) AS max_query_end_ts,
  (SELECT MAX(usage_end_time) FROM system.billing.usage) AS max_billing_ts,
  (SELECT MIN(event_time) FROM system.compute.warehouse_events) AS min_event_ts,
  (SELECT MIN(start_time) FROM system.query.history) AS min_query_start_ts,
  (SELECT MIN(usage_end_time) FROM system.billing.usage) AS min_billing_ts,
  date_trunc('HOUR', LEAST(max_events_ts, max_query_end_ts, max_billing_ts)) AS selected_end_time,
  (date_trunc('HOUR', GREATEST(min_event_ts, min_query_start_ts, min_billing_ts)) + INTERVAL 1 HOUR)::timestamp AS selected_start_time
)
```

### 2K: Fixed Lookback Window
```sql
WHERE u.usage_start_time >= DATE_SUB(CURRENT_DATE(), 90)
  AND q.start_time >= DATE_SUB(CURRENT_DATE(), 90)
```

**Impact**: PrPr ensures all source tables have complete data for the selected time range.

---

## 6. Query Source Classification

### PrPr: Structured Fields
```sql
CASE
  WHEN query_source.job_info.job_id IS NOT NULL THEN 'JOB'
  WHEN query_source.legacy_dashboard_id IS NOT NULL THEN 'LEGACY DASHBOARD'
  WHEN query_source.dashboard_id IS NOT NULL THEN 'AI/BI DASHBOARD'
  WHEN query_source.alert_id IS NOT NULL THEN 'ALERT'
  WHEN query_source.notebook_id IS NOT NULL THEN 'NOTEBOOK'
  WHEN query_source.sql_query_id IS NOT NULL THEN 'SQL QUERY'
  WHEN query_source.genie_space_id IS NOT NULL THEN 'GENIE SPACE'
  WHEN client_application IS NOT NULL THEN client_application
  ELSE 'UNKNOWN'
END AS query_source_type,

COALESCE(
  query_source.job_info.job_id,
  query_source.legacy_dashboard_id,
  query_source.dashboard_id,
  query_source.alert_id,
  query_source.notebook_id,
  query_source.sql_query_id,
  query_source.genie_space_id,
  'UNKNOWN'
) AS query_source_id
```

### 2K: String Pattern Matching
```sql
CASE
  WHEN q.client_application LIKE '%genie%' OR q.client_application LIKE '%Genie%' THEN 'GENIE SPACE'
  WHEN q.client_application LIKE '%dashboard%' OR q.client_application LIKE '%Dashboard%' THEN
    CASE
      WHEN q.client_application LIKE '%lakeview%' OR q.client_application LIKE '%aibi%' THEN 'AI/BI DASHBOARD'
      ELSE 'LEGACY DASHBOARD'
    END
  WHEN q.client_application LIKE '%notebook%' OR q.client_application LIKE '%Notebook%' THEN 'NOTEBOOK'
  WHEN q.client_application LIKE '%job%' OR q.client_application LIKE '%Job%' OR q.statement_type = 'JOB' THEN 'JOB'
  WHEN q.client_application LIKE '%alert%' OR q.client_application LIKE '%Alert%' THEN 'ALERT'
  WHEN q.client_application LIKE '%sql-editor%' OR q.client_application LIKE '%SQL Editor%' THEN 'SQL QUERY'
  ELSE 'SQL QUERY'
END AS query_source_type,

CASE
  WHEN q.client_application LIKE '%genie%' THEN REGEXP_EXTRACT(q.client_application, 'genie[/-]([a-zA-Z0-9-]+)', 1)
  WHEN q.client_application LIKE '%dashboard%' THEN REGEXP_EXTRACT(q.client_application, 'dashboard[/-]([a-zA-Z0-9-]+)', 1)
  ELSE NULL
END AS query_source_id
```

**Impact**: PrPr's approach is more reliable and doesn't depend on string patterns that could change.

---

## 7. Output Schema with Per-Hour Breakdown

### PrPr: Array of Hour-Level Costs
```sql
-- Final aggregation with per-hour breakdown
SELECT
  qq.statement_id,
  -- ... other fields ...
  COLLECT_LIST(
    NAMED_STRUCT(
      'hour_bucket', qa.hour_bucket,
      'hour_attributed_cost', query_attributed_dollars_estimation,
      'hour_attributed_dbus', query_attributed_dbus_estimation
    )
  ) AS statement_hour_bucket_costs,
  -- ... metadata fields ...
  FIRST(most_recent_billing_hour) AS most_recent_billing_hour,
  FIRST(billing_record_check) AS billing_record_check,
  SUM(query_attributed_dollars_estimation) AS query_attributed_dollars_estimation,
  SUM(query_attributed_dbus_estimation) AS query_attributed_dbus_estimation
FROM query_attribution qa
LEFT JOIN cpq_warehouse_query_history AS qq ON qa.statement_id = qq.statement_id
GROUP BY qq.statement_id
```

### 2K: Flat Scalar Values
```sql
SELECT
  statement_id,
  -- ... other fields ...
  query_attributed_dollars_estimation,
  query_attributed_dbus_estimation
FROM query_costs
WHERE query_attributed_dollars_estimation > 0
   OR query_attributed_dbus_estimation > 0
   OR duration_seconds > 0
ORDER BY start_time DESC
```

**Impact**: PrPr provides hour-by-hour audit trail; Current only has totals.

---

## 8. Materialized View Definition

### PrPr: Scheduled with Partitioning
```sql
CREATE OR REPLACE MATERIALIZED VIEW main.default.dbsql_cost_per_query
(
  statement_id string,
  -- ... full schema ...
  statement_hour_bucket_costs array<struct<
    hour_bucket:timestamp,
    hour_attributed_cost:double,
    hour_attributed_dbus:double
  >>,
  -- ... more fields ...
)
SCHEDULE EVERY 1 HOUR
PARTITIONED BY (query_start_hour, workspace_id)
TBLPROPERTIES ('pipelines.autoOptimize.zOrderCols' = 'warehouse_id')
AS
```

### 2K: Simple Table Creation
```sql
CREATE OR REPLACE TABLE {catalog}.{schema}.dbsql_cost_per_query AS
WITH
  -- ... CTEs ...
SELECT
  -- ... fields ...
FROM query_costs
```

**Impact**: PrPr optimized for production scale with partitioning and Z-ordering.

---

## Key Takeaways for Implementation

### Most Critical Improvements to Adopt:

1. **Warehouse Utilization** (Highest Impact)
   - Add warehouse event tracking
   - Calculate utilization proportion
   - Apply to cost formula

2. **Multi-Hour Query Splitting** (High Impact)
   - Use `sequence()` to explode across hours
   - Calculate overlap duration
   - Distribute work proportionally

3. **Enhanced Work Calculation** (Medium Impact)
   - Add compilation and fetch time
   - Define work start/end times
   - Exclude waiting periods

4. **Table Boundary Validation** (Medium Impact)
   - Check all source tables
   - Use intersection of valid ranges
   - Add diagnostic fields

5. **Structured Query Source** (Low Impact)
   - Use native query_source fields
   - Remove regex parsing
   - More future-proof

### Implementation Complexity:
- **Simple**: Query source improvements (1-2 days)
- **Moderate**: Work calculation enhancements (3-5 days)
- **Complex**: Multi-hour splitting (1-2 weeks)
- **Most Complex**: Warehouse utilization tracking (2-3 weeks)

### Recommended Adoption Order:
1. Start with table boundary validation (low risk, immediate benefit)
2. Add enhanced work calculation (moderate complexity, good accuracy gain)
3. Implement multi-hour query splitting (complex but critical for accuracy)
4. Add warehouse utilization tracking (most complex, highest accuracy impact)
5. Switch to structured query source (low complexity, nice-to-have)
