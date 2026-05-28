# DBSQL Cost Attribution Architecture Comparison

## System Architecture Diagrams

---

## Current Current Implementation Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Data Sources (90 days)                       │
├──────────────────────────┬──────────────────────────────────────┤
│ system.billing.usage     │ system.query.history                 │
│ - warehouse_id           │ - statement_id                       │
│ - usage_start_time       │ - warehouse_id                       │
│ - usage_quantity (DBUs)  │ - start_time / end_time              │
│ - sku_name               │ - total_task_duration_ms             │
└──────────────────────────┴──────────────────────────────────────┘
             │                              │
             │                              │
             ▼                              ▼
┌────────────────────────┐      ┌─────────────────────────────┐
│ warehouse_hourly_usage │      │ queries_with_details        │
├────────────────────────┤      ├─────────────────────────────┤
│ - Hour bucket          │      │ - Query metadata            │
│ - Warehouse ID         │      │ - Duration (wall clock)     │
│ - Total DBUs           │      │ - Task duration (fallback)  │
│ - Total dollars        │      │ - Client app (parsed)       │
│ - JOIN pricing         │      │ - Single hour bucket        │
└────────────────────────┘      └─────────────────────────────┘
             │                              │
             │                              │
             └──────────────┬───────────────┘
                            │
                            ▼
              ┌──────────────────────────┐
              │ warehouse_hourly_work    │
              ├──────────────────────────┤
              │ - Hour bucket            │
              │ - Warehouse ID           │
              │ - Total work (ms)        │
              │ - SUM(task duration)     │
              └──────────────────────────┘
                            │
                            ▼
              ┌──────────────────────────────────────────┐
              │         Cost Attribution                 │
              ├──────────────────────────────────────────┤
              │ Formula:                                 │
              │ cost = (query_work / total_work)         │
              │        × hourly_cost                     │
              │                                          │
              │ NO utilization adjustment                │
              │ NO multi-hour splitting                  │
              └──────────────────────────────────────────┘
                            │
                            ▼
              ┌──────────────────────────────────────────┐
              │         Output Table                     │
              ├──────────────────────────────────────────┤
              │ - statement_id                           │
              │ - query_attributed_dollars (scalar)      │
              │ - query_attributed_dbus (scalar)         │
              │ - Single hour attribution                │
              │ - Pattern-matched source type            │
              └──────────────────────────────────────────┘
```

**Key Characteristics:**
- Simple hourly bucketing
- No warehouse state tracking
- Single hour attribution per query
- Pattern matching for query sources

---

## PrPr Reference Implementation Architecture

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                        Data Sources (Dynamic Boundaries)                       │
├─────────────────────────┬──────────────────────────┬──────────────────────────┤
│ system.billing.usage    │ system.query.history     │ system.compute.          │
│                         │                          │   warehouse_events       │
│ - warehouse_id          │ - statement_id           │ - warehouse_id           │
│ - usage_start_time      │ - warehouse_id           │ - event_time             │
│ - usage_quantity (DBUs) │ - start_time / end_time  │ - event_type             │
│ - sku_name              │ - task_duration_ms       │ - cluster_count          │
│                         │ - compilation_ms         │ - state (ON/OFF)         │
│                         │ - result_fetch_ms        │                          │
│                         │ - query_source struct    │                          │
└─────────────────────────┴──────────────────────────┴──────────────────────────┘
         │                         │                            │
         │                         │                            │
         ▼                         ▼                            ▼
┌──────────────────┐   ┌───────────────────────┐   ┌────────────────────────┐
│table_boundaries  │   │cpq_warehouse_query    │   │ window_events          │
├──────────────────┤   │      _history         │   ├────────────────────────┤
│ Finds safe time  │   ├───────────────────────┤   │ - warehouse_state      │
│ window across    │   │ - query_work_task_time│   │ - ON / OFF             │
│ ALL 3 tables     │   │   (task+compile+fetch)│   │ - event windows        │
│                  │   │ - query_work_start    │   │ - cluster_count        │
│ MIN/MAX checks   │   │ - query_work_end      │   └────────────────────────┘
└──────────────────┘   │ - Structured source   │              │
         │             └───────────────────────┘              │
         │                         │                          │
         │                         │                          ▼
         │                         │           ┌─────────────────────────────┐
         │                         │           │ Warehouse State Aggregation │
         │                         │           ├─────────────────────────────┤
         │                         │           │ - Consecutive period merge  │
         │                         │           │ - ROW_NUMBER() grouping     │
         │                         │           │ - Window functions          │
         │                         │           └─────────────────────────────┘
         │                         │                          │
         │                         ▼                          ▼
         │           ┌──────────────────────────┐  ┌─────────────────────────┐
         │           │   hour_intervals         │  │ Query Event Timeline    │
         │           ├──────────────────────────┤  ├─────────────────────────┤
         │           │ - Explode query across   │  │ - Start/end events      │
         │           │   hours using sequence() │  │ - Running query count   │
         │           │ - Create hour buckets    │  │ - Concurrent load       │
         │           └──────────────────────────┘  └─────────────────────────┘
         │                         │                          │
         │                         │                          │
         │                         ▼                          ▼
         │           ┌──────────────────────────────────────────────┐
         │           │    statement_proportioned_work               │
         │           ├──────────────────────────────────────────────┤
         │           │ Calculate per-hour overlap:                  │
         │           │                                              │
         │           │ overlap = LEAST(query_end, hour_end) -       │
         │           │           GREATEST(query_start, hour_start)  │
         │           │                                              │
         │           │ proportional_work =                          │
         │           │   query_work × (overlap / total_duration)    │
         │           └──────────────────────────────────────────────┘
         │                         │                          │
         │                         │                          │
         │                         ▼                          ▼
         │           ┌─────────────────────────────────────────────────┐
         │           │         Temporal Period Merging                 │
         │           ├─────────────────────────────────────────────────┤
         │           │ Union all time points:                          │
         │           │ - Warehouse events (start/end)                  │
         │           │ - Query events (start/end)                      │
         │           │ - Hour boundaries                               │
         │           │                                                 │
         │           │ Creates complete timeline with no gaps          │
         │           └─────────────────────────────────────────────────┘
         │                         │
         │                         ▼
         │           ┌─────────────────────────────────────────────────┐
         │           │         utilization_by_warehouse                │
         │           ├─────────────────────────────────────────────────┤
         │           │ Per hour, per warehouse:                        │
         │           │ - utilized_seconds (queries running)            │
         │           │ - idle_seconds (ON but no queries)              │
         │           │ - off_seconds                                   │
         │           │                                                 │
         │           │ utilization_proportion =                        │
         │           │   utilized / (utilized + idle)                  │
         │           └─────────────────────────────────────────────────┘
         │                         │
         └─────────────────────────┼─────────────────────┐
                                   │                     │
                                   ▼                     ▼
                     ┌──────────────────────┐  ┌─────────────────────┐
                     │ warehouse_time       │  │filtered_warehouse   │
                     ├──────────────────────┤  │      _usage         │
                     │ - Total work per hour│  ├─────────────────────┤
                     │ - All queries summed │  │ - Hourly DBUs       │
                     └──────────────────────┘  │ - Hourly dollars    │
                                   │           │ - With pricing      │
                                   │           └─────────────────────┘
                                   │                     │
                                   └──────────┬──────────┘
                                              │
                                              ▼
                              ┌────────────────────────────────────────┐
                              │      Cost Attribution (2-stage)        │
                              ├────────────────────────────────────────┤
                              │ Stage 1: Adjust for utilization        │
                              │   adjusted_cost =                      │
                              │     utilization_proportion × hourly_$  │
                              │                                        │
                              │ Stage 2: Allocate to queries           │
                              │   query_cost =                         │
                              │     adjusted_cost ×                    │
                              │     (query_work / total_work)          │
                              └────────────────────────────────────────┘
                                              │
                                              ▼
                              ┌────────────────────────────────────────┐
                              │         Final Aggregation              │
                              ├────────────────────────────────────────┤
                              │ GROUP BY statement_id                  │
                              │                                        │
                              │ - COLLECT_LIST(hour costs) → array     │
                              │ - SUM(hour costs) → total              │
                              │ - Diagnostic metadata                  │
                              │ - Billing record checks                │
                              └────────────────────────────────────────┘
                                              │
                                              ▼
                              ┌────────────────────────────────────────┐
                              │      Materialized View Output          │
                              ├────────────────────────────────────────┤
                              │ SCHEDULED EVERY 1 HOUR                 │
                              │ PARTITIONED BY (start_hour, workspace) │
                              │ Z-ORDERED BY warehouse_id              │
                              │                                        │
                              │ - statement_id                         │
                              │ - statement_hour_bucket_costs (array)  │
                              │ - query_attributed_dollars (sum)       │
                              │ - query_attributed_dbus (sum)          │
                              │ - query_work metrics                   │
                              │ - Billing diagnostics                  │
                              │ - Structured source fields             │
                              └────────────────────────────────────────┘
```

**Key Characteristics:**
- Second-level precision
- Warehouse state tracking (ON/OFF/IDLE)
- Multi-hour query splitting
- Utilization-adjusted cost attribution
- Per-hour cost breakdown
- Structured query source
- Dynamic time boundaries

---

## Data Flow Comparison

### Current Implementation: Simple Pipeline
```
System Tables → Hourly Aggregation → Simple Join → Proportional Split → Output
     (2)              (2 CTEs)           (3 CTEs)         (1 CTE)       (Flat)

Total CTEs: 5
Complexity: Low
Accuracy: Basic
```

### PrPr Implementation: Advanced Pipeline
```
System Tables → Boundary Check → Warehouse Events → Query Timeline → Temporal Merge
     (3)            (1 CTE)          (5 CTEs)          (4 CTEs)        (5 CTEs)
                                          ↓                                ↓
                                    Utilization ←─────────────────────────┘
                                    Calculation
                                    (2 CTEs)
                                          ↓
                             Hour Explosion → Overlap → Cost Attribution → Aggregation
                                (2 CTEs)      (2 CTEs)      (3 CTEs)        (1 CTE)

Total CTEs: ~25
Complexity: High
Accuracy: Advanced
```

---

## Temporal Precision Comparison

### 2K: Hour-Level Granularity
```
Timeline (2 hours):
│──────────── Hour 1 ────────────│──────────── Hour 2 ────────────│
0:00                         1:00                              2:00

Query A: Starts 0:30, ends 1:30 (spans 2 hours)
├─────────────────────────────────┤
        ↓
Cost allocated to Hour 1 only
All cost in single bucket
```

### PrPr: Second-Level with Overlap
```
Timeline (2 hours):
│──────────── Hour 1 ────────────│──────────── Hour 2 ────────────│
0:00                         1:00                              2:00

Query A: Starts 0:30, ends 1:30 (spans 2 hours)
├────── 30min overlap ──────┼────── 30min overlap ──────┤
        work_start                                work_end

Overlap Hour 1: 1800 seconds (0:30 to 1:00)
Overlap Hour 2: 1800 seconds (1:00 to 1:30)

Cost proportionally split:
- Hour 1: 50% of query cost
- Hour 2: 50% of query cost
```

---

## Warehouse State Tracking

### 2K: No State Tracking
```
Warehouse Timeline:
│───── Always Assumed Utilized ─────│

No distinction between:
- Warehouse ON with queries
- Warehouse ON but idle
- Warehouse OFF
```

### PrPr: Full State Tracking
```
Warehouse Timeline:
│─ OFF ─│─ ON (IDLE) ─│─ ON (UTILIZED) ─│─ ON (IDLE) ─│─ OFF ─│
  ^           ^               ^                 ^           ^
  │           │               │                 │           │
Events:  START    Query1   Query2          Query3       STOP
                  starts   starts           ends

Utilization Calculation:
- utilized_seconds: Time with active queries
- idle_seconds: ON but no queries
- off_seconds: Warehouse stopped

utilization_proportion = utilized / (utilized + idle)

Cost Attribution:
- Only UTILIZED time is billable to queries
- IDLE time absorbed by warehouse owner
- OFF time: no cost
```

---

## Cost Attribution Formula Comparison

### Current Formula
```
┌─────────────────────────────────────────────────┐
│  Simple Proportional Allocation                │
├─────────────────────────────────────────────────┤
│                                                 │
│  query_cost = (query_work / total_hour_work)    │
│               × hourly_warehouse_cost           │
│                                                 │
│  Where:                                         │
│  - query_work: total_task_duration_ms           │
│  - total_hour_work: SUM(all query work in hour) │
│  - hourly_warehouse_cost: billing.usage cost    │
│                                                 │
│  Assumptions:                                   │
│  ✗ All warehouse time is utilized               │
│  ✗ Query in single hour bucket                  │
│  ✗ Wall clock = billable time                   │
└─────────────────────────────────────────────────┘
```

### PrPr Formula
```
┌─────────────────────────────────────────────────────────────┐
│  Two-Stage Utilization-Adjusted Allocation                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Stage 1: Adjust warehouse cost by utilization             │
│    adjusted_hourly_cost =                                   │
│      utilization_proportion × hourly_warehouse_cost         │
│                                                             │
│  Stage 2: Allocate to queries proportionally               │
│    query_hour_cost =                                        │
│      (proportional_query_work / total_hour_work)            │
│      × adjusted_hourly_cost                                 │
│                                                             │
│  Stage 3: Sum across all hours                             │
│    total_query_cost = SUM(query_hour_cost)                  │
│                                                             │
│  Where:                                                     │
│  - proportional_query_work:                                 │
│      query_work × (hour_overlap / total_duration)           │
│  - utilization_proportion:                                  │
│      utilized_seconds / (utilized + idle_seconds)           │
│  - adjusted_hourly_cost:                                    │
│      Only the utilized portion of warehouse cost            │
│                                                             │
│  Benefits:                                                  │
│  ✓ Accounts for warehouse idle time                        │
│  ✓ Multi-hour query support                                │
│  ✓ Accurate temporal overlap                               │
│  ✓ Fair cost distribution                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Example Cost Calculation

### Scenario:
- Warehouse cost: $10/hour
- Hour 1 state: 30min utilized, 30min idle (50% utilization)
- Query A: 15min of work in hour 1
- Query B: 15min of work in hour 1
- Total work: 30min

### Current Calculation:
```
Query A cost = (15min / 30min) × $10 = $5.00
Query B cost = (15min / 30min) × $10 = $5.00
Total attributed: $10.00

Issue: Queries pay for idle time
```

### PrPr Calculation:
```
Adjusted cost = 50% × $10 = $5.00 (only utilized portion)

Query A cost = (15min / 30min) × $5.00 = $2.50
Query B cost = (15min / 30min) × $5.00 = $2.50
Total attributed: $5.00

Idle cost: $5.00 (absorbed, not attributed to queries)

Benefit: Fair allocation, queries only pay for utilized time
```

---

## Performance Characteristics

### Current Implementation
```
Storage:
- Single scalar cost per query
- Minimal storage overhead

Query Performance:
- No partitioning specified
- Simple filtering
- Fast aggregations

Refresh:
- Manual or scheduled
- Full table refresh
- ~5-10 min for 90 days
```

### PrPr Implementation
```
Storage:
- Array of hourly costs per query
- Higher storage overhead
- Richer metadata

Query Performance:
- Partitioned by (query_start_hour, workspace_id)
- Z-ordered by warehouse_id
- Optimized for common queries
- Broadcast/repartition hints

Refresh:
- Scheduled every 1 hour
- Incremental possible
- ~15-30 min for full window
```

---

## Key Architectural Differences Summary

| Aspect | Current Implementation | PrPr Implementation |
|--------|------------------|---------------------|
| **Time Precision** | Hour-level | Second-level |
| **Warehouse State** | None | ON/OFF/IDLE tracking |
| **Multi-hour Queries** | Single bucket | Proportional split |
| **Cost Formula** | Simple proportional | Utilization-adjusted |
| **Query Source** | Pattern matching | Structured fields |
| **Output Schema** | Flat scalars | Arrays + metadata |
| **Complexity** | ~5 CTEs | ~25 CTEs |
| **Accuracy** | Basic | Advanced |
| **Storage** | Minimal | Higher |
| **Auditability** | Limited | Extensive |

---

## Migration Considerations

### Backward Compatibility
If migrating from Current to PrPr:

1. **Schema changes required:**
   - Add `statement_hour_bucket_costs` array column
   - Add `query_work_start_time`, `query_work_end_time`
   - Add `billing_record_check`, `most_recent_billing_hour`

2. **Query changes required:**
   - Dashboards must handle array column or use aggregated total
   - Filter logic may need adjustment for new time fields

3. **Cost differences expected:**
   - Lower costs (due to utilization adjustment)
   - Different temporal distribution (multi-hour split)
   - More accurate attribution overall

4. **Testing strategy:**
   - Run both in parallel for validation period
   - Compare totals and distributions
   - Reconcile differences before cutover

### Hybrid Approach Option
```sql
-- Maintain both calculations during transition
SELECT
  statement_id,
  -- New PrPr calculation
  prpr_cost,
  prpr_hour_buckets,
  -- Old Current calculation for comparison
  legacy_cost,
  -- Variance
  (prpr_cost - legacy_cost) AS cost_difference,
  (prpr_cost / NULLIF(legacy_cost, 0)) AS cost_ratio
FROM ...
```

This allows gradual migration and validation.
