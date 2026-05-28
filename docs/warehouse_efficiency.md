# SQL Warehouse Efficiency & Idle Cost Analysis

## Overview

This feature helps customers understand and optimize their SQL warehouse costs by breaking down **actual billing costs** vs. **query-attributed costs** and identifying idle warehouse time that's driving unnecessary spending.

## The Billing Reality

When a SQL warehouse is running (ON state), customers are billed for:
- ✅ **Utilized time** - Actively running queries
- ✅ **Idle time** - No queries running, but warehouse still on

The warehouse only stops charging when it's completely **OFF** (auto-stopped).

## Cost Attribution Models

### Original Model (`dbsql_cost_per_query`)
- **What it shows**: Total cost including all warehouse uptime (utilized + idle)
- **Use case**: Matches actual Databricks billing
- **Example**: $93,199 total cost

### PrPr Model (`dbsql_cost_per_query_prpr`)
- **What it shows**: Only costs during query execution time (utilized time only)
- **Use case**: Fair chargeback to users/teams, identifying expensive queries
- **Example**: $9,583 query-attributed cost

### Idle Warehouse Cost (The Gap)
- **What it shows**: The difference between models = wasted idle time
- **You're still billed for this!**: Yes, this appears on your Databricks bill
- **Example**: $83,616 idle warehouse cost (89.7% of total)

## Key Metrics

### Warehouse Efficiency
```
Utilization % = (PrPr Cost / Original Cost) × 100
Idle % = 100 - Utilization %
```

### Efficiency Grades
| Grade | Utilization % | Status | Action Required |
|-------|---------------|--------|-----------------|
| A | 80%+ | Excellent | Maintain efficiency |
| B | 60-79% | Good | Minor optimizations |
| C | 40-59% | Fair | Review settings |
| D | 20-39% | Poor | Immediate action |
| F | <20% | Critical | Urgent optimization |

## API Endpoints

### Comparison Endpoint
`GET /api/dbsql-prpr/comparison`

Returns side-by-side comparison with efficiency metrics:

```json
{
  "original": {
    "total_spend": 93199.03,
    "description": "Actual Databricks bill (includes all warehouse uptime)"
  },
  "prpr": {
    "total_spend": 9582.70,
    "description": "Query-attributed cost (fair for chargeback)"
  },
  "idle_warehouse_cost": {
    "total_idle_cost": 83616.33,
    "idle_percentage": 89.72,
    "description": "Warehouse idle time cost - you're still billed for this!",
    "status": "critical"
  },
  "warehouse_efficiency": {
    "utilization_percentage": 10.28,
    "idle_percentage": 89.72,
    "status": "critical",
    "grade": "F"
  },
  "recommendations": [...]
}
```

### Warehouse Efficiency Endpoint
`GET /api/dbsql-prpr/warehouse-efficiency`

Returns per-warehouse efficiency analysis:

```json
{
  "summary": {
    "total_warehouses": 113,
    "critical_count": 109,
    "warning_count": 3,
    "good_count": 1,
    "total_idle_cost": 76005.07,
    "overall_utilization_percentage": 10.79,
    "overall_idle_percentage": 89.21
  },
  "top_idle_cost_warehouses": [
    {
      "warehouse_id": "8ded61ab0e9e3e6d",
      "idle_cost": 8197.51,
      "idle_percentage": 90.55,
      "efficiency_grade": "F",
      "status": "critical",
      "recommendations": ["CRITICAL: Enable auto-stop or migrate to serverless"]
    }
  ]
}
```

## Actionable Recommendations

The system automatically generates prioritized recommendations based on efficiency metrics:

### Critical Priority (Idle > 70%)

#### 1. Reduce Auto-Stop Timeout
- **Potential Savings**: ~60% of idle cost
- **Effort**: Low
- **Action**: Set auto-stop timeout to 5-10 minutes in warehouse settings
- **Impact**: Warehouses will stop faster when not in use

#### 2. Enable Serverless SQL Warehouses
- **Potential Savings**: ~95% of idle cost
- **Effort**: Medium
- **Action**: Migrate to Serverless SQL warehouses
- **Impact**: Scales to zero, charges only for query execution
- **Note**: This is the most effective solution for high idle time

#### 3. Consolidate Underutilized Warehouses
- **Potential Savings**: ~40% of idle cost
- **Effort**: High
- **Action**: Review usage patterns and merge warehouses
- **Impact**: Fewer warehouses = better resource utilization

### High Priority (Idle 40-70%)

#### 4. Optimize Auto-Stop Settings
- **Potential Savings**: ~30% of idle cost
- **Effort**: Low
- **Action**: Review and reduce timeouts for low-traffic warehouses
- **Impact**: Reduces idle time between query bursts

#### 5. Right-Size Warehouse Clusters
- **Potential Savings**: ~25% of idle cost
- **Effort**: Medium
- **Action**: Match warehouse sizes to workload requirements
- **Impact**: Smaller warehouses cost less when idle

### Medium Priority (All Scenarios)

#### 6. Optimize Slow Queries
- **Potential Savings**: ~15-20% of total cost
- **Effort**: Medium
- **Action**: Review top expensive queries, add caching, optimize SQL
- **Impact**: Faster queries = less warehouse runtime

#### 7. Implement Warehouse Usage Policies
- **Potential Savings**: ~20% of idle cost
- **Effort**: Low
- **Action**: Configure alerts for idle warehouses, set spending limits
- **Impact**: Prevents waste through monitoring

## Real-World Example

### Before Optimization
```
Total Cost:           $93,199
Query-Attributed:     $9,583  (10.3% utilization)
Idle Warehouse Cost:  $83,616 (89.7% waste!)
Efficiency Grade:     F (Critical)
Warehouses:           113 total
  - Critical (>70% idle): 109 warehouses
  - Warning (40-70%):       3 warehouses
  - Good (<40%):            1 warehouse
```

### Recommended Actions (Ordered by ROI)
1. **Enable Serverless** → Save ~$79K/period (95% of idle cost)
2. **Reduce Auto-Stop to 5min** → Save ~$50K/period (60% of idle cost)
3. **Consolidate Warehouses** → Save ~$33K/period (40% of idle cost)
4. **Implement Usage Policies** → Save ~$17K/period (20% of idle cost)
5. **Optimize Slow Queries** → Save ~$14K/period (mixed savings)

### After Optimization (Serverless Migration)
```
Total Cost:           $12,000  (87% reduction!)
Query-Attributed:     $9,583   (80% utilization)
Idle Warehouse Cost:  $2,417   (20% idle)
Efficiency Grade:     A (Excellent)
Annual Savings:       ~$950K/year
```

## Integration with UI

### Summary Cards
Display three key metrics side-by-side:
1. **Actual Bill** - Original cost (matches Databricks invoice)
2. **Query Cost** - PrPr cost (fair attribution)
3. **Idle Cost** - The waste (with alert badge if critical)

### Efficiency Gauge
Visual progress bar showing utilization percentage with color coding:
- 🟢 Green: 60%+ (Good)
- 🟡 Yellow: 30-60% (Warning)
- 🔴 Red: <30% (Critical)

### Recommendations Panel
Prioritized list of actions with:
- Priority badge (Critical/High/Medium/Low)
- Title and description
- Potential savings amount
- Effort level (Low/Medium/High)
- "Take Action" button linking to warehouse settings

### Per-Warehouse Table
Sortable table showing:
- Warehouse ID (clickable to warehouse settings)
- Total Cost
- Idle Cost
- Utilization %
- Efficiency Grade (A-F)
- Status indicator
- Quick action buttons

## Technical Implementation

### Calculation Logic
```sql
-- Utilization Factor
utilization_proportion = utilized_seconds / (utilized_seconds + idle_seconds)

-- Query Attribution
query_cost = (warehouse_utilization_proportion * total_warehouse_period_dollars)
             * query_task_time_proportion

-- Idle Cost
idle_cost = original_cost - prpr_cost
```

### Data Sources
- **Original**: `system.billing.usage` + `system.query.history`
- **PrPr**: Adds `system.compute.warehouse_events` for utilization tracking
- **Reconciliation**: Both tables use same time periods for accurate comparison

## Best Practices

1. **Monitor Daily**: Track efficiency metrics as part of regular cost review
2. **Set Alerts**: Notify when warehouse efficiency drops below threshold
3. **Start Small**: Optimize worst offenders first (highest idle cost)
4. **Measure Impact**: Track savings after each optimization
5. **Review Quarterly**: Warehouse needs change, re-evaluate sizing
6. **Document Changes**: Track what optimizations worked best

## FAQs

**Q: Is idle cost real or just an accounting artifact?**
A: Real! You're billed for idle warehouse time by Databricks.

**Q: Why not just use PrPr costs for everything?**
A: PrPr is great for chargeback, but won't match your actual Databricks bill. Use both.

**Q: What's the quickest win?**
A: Reduce auto-stop timeout to 5 minutes (low effort, ~60% idle cost savings).

**Q: What's the biggest savings opportunity?**
A: Serverless SQL warehouses (~95% idle cost elimination).

**Q: Can I eliminate all idle cost?**
A: Not entirely, but <20% idle is excellent. Serverless gets you closest.

**Q: How often should I refresh these tables?**
A: Daily refresh recommended to catch issues quickly.

## Resources

- [Databricks SQL Warehouse Settings](https://docs.databricks.com/sql/admin/sql-endpoints.html)
- [Serverless SQL Warehouses](https://docs.databricks.com/sql/admin/serverless.html)
- [Auto-Stop Configuration](https://docs.databricks.com/sql/admin/sql-endpoints.html#auto-stop)
- [Query Optimization Guide](https://docs.databricks.com/sql/user/queries/index.html)
