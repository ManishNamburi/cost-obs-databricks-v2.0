# Idle Warehouse Cost - Quick Reference

## The Problem

**You're paying for warehouse idle time, not just query execution!**

## Key Numbers (Example)

| Metric | Amount | % |
|--------|--------|---|
| **Actual Databricks Bill** | $93,199 | 100% |
| Query Execution Cost | $9,583 | 10.3% |
| **Idle Warehouse Cost** | $83,616 | 89.7% |

**Annual Impact**: ~$1M+ in idle warehouse costs! 💸

## Quick Wins (ROI Ranked)

### 🏆 #1: Enable Serverless SQL
- **Savings**: ~$950K/year (95% of idle cost)
- **Effort**: Medium (migration required)
- **Timeline**: 1-2 weeks
- **Action**: Workspace Settings → SQL Warehouses → Enable Serverless

### 🥈 #2: Reduce Auto-Stop to 5 Minutes
- **Savings**: ~$600K/year (60% of idle cost)
- **Effort**: Low (just change settings)
- **Timeline**: 1 day
- **Action**: Each warehouse → Configuration → Auto Stop → 5 minutes

### 🥉 #3: Consolidate Warehouses
- **Savings**: ~$400K/year (40% of idle cost)
- **Effort**: High (analyze patterns, migrate users)
- **Timeline**: 1-2 months
- **Action**: Identify 10+ low-usage warehouses, merge into 2-3

## Critical Warehouses to Fix First

Use `/api/dbsql-prpr/warehouse-efficiency` to identify:
- Warehouses with >90% idle time
- High absolute idle cost (>$1K)
- Low query volume (<100 queries/day)

**Example**: Warehouse `ad5c034e470ae7a3` → 99.3% idle ($3,290 waste)
→ **Action**: Enable auto-stop or migrate to serverless ASAP

## API Endpoints

```bash
# Overall comparison and recommendations
curl "http://localhost:8000/api/dbsql-prpr/comparison"

# Per-warehouse analysis
curl "http://localhost:8000/api/dbsql-prpr/warehouse-efficiency?min_cost=100"
```

## Efficiency Targets

| Grade | Utilization | Status | Annual Idle Cost (est) |
|-------|-------------|--------|------------------------|
| A | 80%+ | ✅ Excellent | <$200K |
| B | 60-79% | ✅ Good | $200-400K |
| C | 40-59% | ⚠️ Fair | $400-600K |
| D | 20-39% | ❌ Poor | $600-800K |
| F | <20% | 🚨 Critical | >$800K |

**Current**: Grade F (10.3% utilization) → ~$1M idle cost/year

## Next Steps

1. **Today**: Review `/warehouse-efficiency` endpoint results
2. **This Week**: Reduce auto-stop to 5 min on top 10 idle warehouses
3. **This Month**: Plan serverless migration for critical warehouses
4. **This Quarter**: Consolidate underutilized warehouses

## Monitoring

Set up alerts when:
- Overall utilization drops below 30%
- Any warehouse exceeds $500/month in idle costs
- New warehouses created without auto-stop configured

## Remember

⚠️ **Idle cost is real billing, not accounting!**
✅ **PrPr shows fair query costs for chargeback**
📊 **Original shows actual bill for reconciliation**
💡 **Gap = optimization opportunity**
