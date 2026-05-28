# DBSQL Cost Per Query Attribution - Methodology Comparison

## Overview
Comparison between Databricks Labs reference implementation (PrPr) and the existing Current Implementation implementation.

**Date**: 2026-02-06
**Reference**: https://github.com/databrickslabs/sandbox/tree/main/dbsql/cost_per_query/PrPr

---

## Executive Summary

Both implementations aim to attribute warehouse costs to individual SQL queries proportionally based on work performed. However, they differ significantly in sophistication and accuracy:

- **Current Implementation**: Simpler hourly bucketing with basic proportional allocation
- **PrPr Implementation**: Advanced second-level precision with warehouse utilization tracking

**Key Finding**: The PrPr implementation is significantly more sophisticated and accurate, particularly in handling warehouse utilization states and multi-hour queries.

---

## Methodology Comparison

### 1. Time Granularity

**Current Implementation:**
- Uses hourly buckets (`DATE_TRUNC('hour', ...)`)
- Allocates costs at hour-level granularity
- Simple approach: queries get attributed to the hour they started in

**PrPr Implementation:**
- Uses second-level precision (`date_trunc('second', ...)`)
- Calculates exact overlap between query execution and hourly periods
- Handles queries spanning multiple hours with proportional work distribution
- More accurate temporal alignment

**Impact**: PrPr's second-level precision provides much more accurate cost attribution, especially for long-running queries that span multiple hours.

---

### 2. Warehouse Utilization Tracking

**Current Implementation:**
- **Does NOT track warehouse state** (ON/OFF/IDLE)
- Assumes all time in an hour is equally billable
- No distinction between utilized vs idle time
- Simpler but less accurate

**PrPr Implementation:**
- **Tracks warehouse events** from `system.compute.warehouse_events`
- Calculates three states:
  - `UTILIZED`: Warehouse on and running queries
  - `ON_IDLE`: Warehouse on but no active queries
  - `OFF`: Warehouse stopped
- Computes `utilization_proportion` = utilized_seconds / (utilized_seconds + idle_seconds)
- Only attributes costs to queries during UTILIZED periods
- Accounts for warehouse idle time that queries shouldn't pay for

**Impact**: This is the most significant difference. PrPr ensures queries only pay for the portion of warehouse time actually utilized, not idle time.

---

### 3. Work Measurement

**Current Implementation:**
```sql
COALESCE(total_task_duration_ms, duration_seconds * 1000)
```
- Uses `total_task_duration_ms` if available
- Falls back to wall-clock duration if not
- Simple fallback strategy

**PrPr Implementation:**
```sql
(COALESCE(CAST(total_task_duration_ms AS FLOAT) / 1000, 0) +
 COALESCE(CAST(result_fetch_duration_ms AS FLOAT) / 1000, 0) +
 COALESCE(CAST(compilation_duration_ms AS FLOAT) / 1000, 0)) AS query_work_task_time
```
- Sums three components: task duration, result fetch, compilation
- Defines separate time windows:
  - `query_work_start_time`: Start + waiting + compilation time
  - `query_work_end_time`: End + result fetch time
  - `query_work_duration_seconds`: Actual work duration
- More comprehensive work calculation

**Impact**: PrPr captures more complete query work metrics, including compilation and result fetch time.

---

### 4. Multi-Hour Query Handling

**Current Implementation:**
- Queries attributed to single hour bucket (start hour)
- No proportional splitting across hours
- Multi-hour queries get all cost in first hour

**PrPr Implementation:**
- Uses `hour_intervals` CTE with `sequence()` to explode queries across hours
- Calculates `overlap_duration` for each hour bucket
- Proportionally distributes query work: `proportional_query_work = query_work_task_time * (overlap_duration / total_duration)`
- Accurate per-hour cost breakdown stored in `statement_hour_bucket_costs` array

**Impact**: Critical difference for long-running queries. PrPr correctly spreads costs across the actual execution period.

---

### 5. Query Source Classification

**Current Implementation:**
```sql
CASE
  WHEN q.client_application LIKE '%genie%' THEN 'GENIE SPACE'
  WHEN q.client_application LIKE '%dashboard%' THEN
    CASE
      WHEN q.client_application LIKE '%lakeview%' THEN 'AI/BI DASHBOARD'
      ELSE 'LEGACY DASHBOARD'
    END
  WHEN q.client_application LIKE '%notebook%' THEN 'NOTEBOOK'
  WHEN q.client_application LIKE '%job%' THEN 'JOB'
  -- ...
END
```
- Pattern matching on `client_application` string
- Uses `REGEXP_EXTRACT` for source IDs
- Manual parsing approach

**PrPr Implementation:**
```sql
CASE
  WHEN query_source.job_info.job_id IS NOT NULL THEN 'JOB'
  WHEN query_source.legacy_dashboard_id IS NOT NULL THEN 'LEGACY DASHBOARD'
  WHEN query_source.dashboard_id IS NOT NULL THEN 'AI/BI DASHBOARD'
  WHEN query_source.alert_id IS NOT NULL THEN 'ALERT'
  -- Uses structured query_source fields
END
```
- Uses structured `query_source` object from system.query.history
- Direct field access instead of pattern matching
- More reliable and future-proof

**Impact**: PrPr's approach is more robust as it uses native system fields rather than parsing client strings.

---

### 6. Cost Attribution Formula

**Current Implementation:**
```sql
-- Cost = (Query Work / Total Hour Work) × Hourly Cost
(COALESCE(q.total_task_duration_ms, q.duration_seconds * 1000) / w.total_work_ms) * h.hourly_dbus
```
- Simple proportional allocation within hour
- No utilization adjustment
- Direct ratio of query work to total work

**PrPr Implementation:**
```sql
-- Cost = (Utilization Rate × Hourly Cost) × (Query Work / Total Work)
(warehouse_utilization_proportion * total_warehouse_period_dollars) * query_task_time_proportion
```
- Two-stage calculation:
  1. Adjust hourly cost by utilization rate
  2. Proportionally allocate adjusted cost
- Accounts for idle time
- More accurate cost attribution

**Impact**: PrPr's formula ensures queries don't pay for warehouse idle time, making attribution more fair and accurate.

---

### 7. Data Boundary Handling

**Current Implementation:**
```sql
WHERE u.usage_start_time >= DATE_SUB(CURRENT_DATE(), 90)
AND q.start_time >= DATE_SUB(CURRENT_DATE(), 90)
```
- Fixed 90-day lookback window
- No cross-table boundary verification
- Simple time filtering

**PrPr Implementation:**
```sql
table_boundaries AS (
  SELECT
    LEAST(max_events_ts, max_query_end_ts, max_billing_ts) AS selected_end_time,
    GREATEST(min_event_ts, min_query_start_ts, min_billing_ts) AS selected_start_time
  FROM (subqueries checking all 3 tables)
)
```
- Dynamically determines safe time window
- Ensures all 3 source tables have complete data
- Prevents partial/missing data issues
- More robust for production use

**Impact**: PrPr's boundary checks prevent incorrect calculations when source tables have different refresh schedules.

---

### 8. Output Schema

**Current Implementation:**
- Flat structure with single cost values
- No per-hour breakdown
- Simple scalar fields

**PrPr Implementation:**
- Includes `statement_hour_bucket_costs` array
- Per-hour cost breakdown with structure:
  ```sql
  array<struct<
    hour_bucket:timestamp,
    hour_attributed_cost:double,
    hour_attributed_dbus:double
  >>
  ```
- Richer metadata: `query_work_start_time`, `query_work_end_time`, `query_work_duration_seconds`
- Diagnostic fields: `billing_record_check`, `most_recent_billing_hour`

**Impact**: PrPr provides much better auditability and debugging capabilities with detailed hour-level breakdown.

---

### 9. Performance Optimizations

**Current Implementation:**
- No explicit partitioning or optimization hints
- Standard materialized view refresh

**PrPr Implementation:**
```sql
SCHEDULE EVERY 1 HOUR
PARTITIONED BY (query_start_hour, workspace_id)
TBLPROPERTIES ('pipelines.autoOptimize.zOrderCols' = 'warehouse_id')
```
- Hourly refresh schedule
- Partitioned by query start hour and workspace
- Z-ordered by warehouse_id for query performance
- Uses hints like `/*+ broadcast(r) */` and `/*+ repartition(64, ...) */`

**Impact**: PrPr is optimized for production-scale performance with proper partitioning and query hints.

---

## Key Technical Innovations in PrPr

### 1. Temporal Period Merging
PrPr uses sophisticated window functions to merge warehouse state periods:
```sql
cte_agg_events_prep AS (
  select warehouse_id, warehouse_state, event_time,
    row_number() over W1 - row_number() over W2 as grp
  -- Creates grouping for consecutive same-state periods
)
```
This consolidates consecutive ON/OFF events into continuous periods.

### 2. Query Event Timeline
Creates a timeline of all query start/end events to calculate concurrent query load:
```sql
cte_queries_event_cnt AS (
  select warehouse_id,
    case num when 1 then query_work_start_time else query_work_end_time end,
    sum(num) as num_queries  -- +1 for start, -1 for end
)
```
Then uses windowing to calculate running count of active queries.

### 3. Union of All Time Points
Merges all relevant time points (events, queries, hourly buckets) to create complete timeline:
```sql
cte_all_time_union AS (
  select ... from cte_all_events
  union select ... from cte_raw_history_byday
  union select ... from table_bound_expld
)
```
Ensures no gaps in time coverage.

### 4. Proportional Work Distribution
For multi-hour queries, calculates exact overlap with each hour:
```sql
overlap_duration =
  UNIX_TIMESTAMP(LEAST(query_work_end_time, hour_end)) -
  UNIX_TIMESTAMP(GREATEST(query_work_start_time, hour_start))

proportional_query_work =
  query_work_task_time * (overlap_duration / total_query_duration)
```

---

## Recommendations

### High Priority Improvements
1. **Add warehouse utilization tracking** - Most impactful change
   - Track warehouse state from `system.compute.warehouse_events`
   - Calculate utilization proportion
   - Adjust costs by utilization rate

2. **Implement multi-hour query splitting** - Critical for accuracy
   - Use `sequence()` to explode queries across hours
   - Calculate overlap duration per hour
   - Store per-hour costs in array structure

3. **Add table boundary validation** - Prevents data quality issues
   - Check all source tables for data availability
   - Use intersection of valid time ranges
   - Add diagnostic fields for billing record availability

### Medium Priority Improvements
4. **Enhance work calculation** - Better accuracy
   - Include compilation and result fetch time
   - Define separate work start/end times
   - Exclude waiting time from work duration

5. **Switch to structured query_source** - More robust
   - Use `query_source.job_info.job_id` instead of parsing
   - Leverage native system fields
   - Remove regex pattern matching

6. **Add performance optimizations**
   - Partition by query_start_hour and workspace_id
   - Add Z-ordering on warehouse_id
   - Use broadcast/repartition hints where appropriate

### Low Priority Improvements
7. **Enrich output schema**
   - Add per-hour cost breakdown array
   - Include diagnostic metadata
   - Add query work duration metrics

---

## Migration Path

If adopting PrPr methodology, recommended phased approach:

**Phase 1: Foundation** (Weeks 1-2)
- Add warehouse event tracking
- Implement table boundary checks
- Add diagnostic fields

**Phase 2: Core Logic** (Weeks 3-4)
- Implement multi-hour query splitting
- Add overlap duration calculations
- Update cost attribution formula with utilization

**Phase 3: Optimization** (Week 5)
- Add partitioning and Z-ordering
- Implement query hints
- Performance testing and tuning

**Phase 4: Validation** (Week 6)
- Run both implementations in parallel
- Compare results and validate accuracy
- Document differences and cutover

---

## Conclusion

The PrPr implementation represents a significantly more sophisticated and accurate approach to DBSQL cost attribution. The most impactful differences are:

1. **Warehouse utilization tracking** - Ensures queries only pay for utilized time
2. **Multi-hour query handling** - Accurate temporal cost distribution
3. **Second-level precision** - Better alignment of query work and billing periods

The current Current implementation provides reasonable estimates but could be substantially improved by adopting PrPr's methodology, particularly the utilization tracking and multi-hour splitting logic.

**Recommendation**: Consider migrating to PrPr methodology in phases, prioritizing warehouse utilization tracking as it provides the most immediate accuracy improvement.
