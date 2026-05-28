# Cost Observability & Control - Feature Scope

## Overview
This document scopes three new features for the Cost Observability & Control app:
1. Proactive email reporting for consumption changes and anomalies
2. Inverted color scheme for spend anomalies (red=higher, green=lower)
3. Interactive KPI trend views

---

## Feature 1: Proactive Email Reporting & Databricks Alerting

### Business Value
- Reduce manual monitoring burden - stakeholders get notified automatically
- Faster response to cost spikes and anomalies
- Historical record of cost events for compliance and auditing
- Leverage native Databricks alerting infrastructure

### Technical Approach

#### Backend Components

**1. New Module: `server/alerting.py`**
- Anomaly detection algorithms (statistical and ML-based)
  - Z-score based spike detection
  - Week-over-week comparison
  - Moving average deviation
- Alert rule configuration and evaluation
- Email template rendering

**2. New API Router: `server/routers/alerts.py`**
Endpoints:
- `POST /api/alerts/configure` - Create/update alert rules
- `GET /api/alerts/rules` - List all alert rules
- `DELETE /api/alerts/rules/{rule_id}` - Delete alert rule
- `GET /api/alerts/history` - View alert history
- `POST /api/alerts/test` - Test alert with current data

**3. Alert Rule Schema**
```python
class AlertRule(BaseModel):
    rule_id: str
    name: str
    alert_type: Literal["spike", "anomaly", "threshold", "trend"]

    # Conditions
    threshold_percent: float | None  # e.g., 20% increase
    threshold_amount: float | None   # e.g., $1000 increase
    comparison_period: Literal["day_over_day", "week_over_week", "month_over_month"]

    # Filters
    product_filter: list[str] | None  # e.g., ["SQL", "ETL"]
    workspace_filter: list[int] | None

    # Notification
    email_recipients: list[str]
    email_template: str
    notification_frequency: Literal["immediate", "daily_digest", "weekly_digest"]

    # Databricks integration
    use_databricks_alerts: bool
    databricks_alert_id: str | None
```

**4. Scheduled Job: `server/jobs.py`** (enhance existing)
- Add alert evaluation job that runs every hour
- Check for new anomalies in system.billing.usage
- Evaluate all active alert rules
- Trigger email notifications or Databricks alerts

**5. Email Service: `server/email_service.py`**
```python
class EmailService:
    def send_alert(self, alert_data: AlertData, recipients: list[str]):
        """Send formatted email alert"""

    def send_daily_digest(self, date: date, alerts: list[AlertData]):
        """Send daily digest of alerts"""
```

Email templates:
- Spike alert: "Your Databricks costs spiked by $X (Y%) on [date]"
- Anomaly alert: "Unusual spending pattern detected"
- Threshold alert: "Daily spend exceeded $X threshold"
- Weekly digest: Summary of all alerts for the week

**6. Databricks SQL Alerts Integration**
- Create Databricks SQL alerts programmatically via Databricks SDK
- Link to existing queries in the Cost Observability schema
- Alert destinations: Email, Slack, PagerDuty (via Databricks native integration)

Example alert query:
```sql
-- Daily spend spike detector
SELECT
  usage_date,
  daily_spend,
  LAG(daily_spend) OVER (ORDER BY usage_date) as prev_day,
  (daily_spend - LAG(daily_spend) OVER (ORDER BY usage_date)) /
    LAG(daily_spend) OVER (ORDER BY usage_date) * 100 as pct_change
FROM {catalog}.{schema}.daily_usage_summary
WHERE usage_date >= CURRENT_DATE - INTERVAL 7 DAYS
  AND ABS(pct_change) > :threshold_percent
ORDER BY ABS(pct_change) DESC
```

#### Frontend Components

**1. New Page: `client/src/components/AlertsManager.tsx`**
- Alert rule configuration UI
- List of active/inactive rules
- Alert history table with filters
- Test alert button

**2. New Component: `client/src/components/AlertRuleForm.tsx`**
- Form to create/edit alert rules
- Threshold sliders and inputs
- Recipient email chips
- Preview of alert conditions

**3. New Component: `client/src/components/AlertHistory.tsx`**
- Timeline view of triggered alerts
- Filter by date, type, severity
- Mark as acknowledged/resolved

**4. Update Navigation**
- Add "Alerts" tab to main navigation

#### Database Schema

**Materialized View: `alert_events`**
```sql
CREATE TABLE {catalog}.{schema}.alert_events (
  alert_id STRING,
  rule_id STRING,
  triggered_at TIMESTAMP,
  usage_date DATE,
  alert_type STRING,
  severity STRING,
  daily_spend DECIMAL(15,2),
  threshold_value DECIMAL(15,2),
  change_amount DECIMAL(15,2),
  change_percent DECIMAL(10,2),
  product STRING,
  workspace_id BIGINT,
  notification_sent BOOLEAN,
  acknowledged_at TIMESTAMP,
  acknowledged_by STRING
);
```

**Materialized View: `alert_rules`**
```sql
CREATE TABLE {catalog}.{schema}.alert_rules (
  rule_id STRING,
  name STRING,
  alert_type STRING,
  threshold_percent DECIMAL(10,2),
  threshold_amount DECIMAL(15,2),
  comparison_period STRING,
  product_filter STRING,  -- JSON array
  workspace_filter STRING,  -- JSON array
  email_recipients STRING,  -- JSON array
  notification_frequency STRING,
  is_active BOOLEAN,
  created_at TIMESTAMP,
  created_by STRING,
  updated_at TIMESTAMP
);
```

### Implementation Steps

1. **Phase 1: Core Alert Engine** (2-3 days)
   - Create alert rule data model
   - Build anomaly detection logic
   - Create alert evaluation engine

2. **Phase 2: Email Service** (1-2 days)
   - Set up email service (SendGrid/AWS SES)
   - Create email templates
   - Implement sending logic

3. **Phase 3: Databricks Integration** (2 days)
   - Create SQL alert queries
   - Programmatically create Databricks SQL alerts via SDK
   - Test alert triggering

4. **Phase 4: Frontend UI** (2-3 days)
   - Build AlertsManager page
   - Create AlertRuleForm component
   - Build AlertHistory timeline

5. **Phase 5: Scheduled Jobs** (1 day)
   - Integrate with existing jobs.py scheduler
   - Add hourly alert evaluation
   - Add daily digest job

### Dependencies
- Email service provider account (SendGrid, AWS SES, or SMTP)
- Databricks workspace with SQL alerts enabled
- Python packages: `sendgrid` or `boto3` (for AWS SES)

---

## Feature 2: Inverted Color Scheme for Spend Anomalies

### Current State
In `SpendAnomalies.tsx`:
- Line 150: Red for increases (`isIncrease ? "text-red-600"`)
- Line 150: Green for decreases (`"text-green-600"`)
- Line 159: Red up arrow for increases
- Line 163: Green down arrow for decreases
- Line 167: Red percentage for increases

### Business Value
- **Intuitive interpretation**: Higher costs = red (bad), lower costs = green (good)
- Aligns with financial reporting conventions
- Reduces cognitive load for stakeholders

### Technical Changes

**File: `client/src/components/SpendAnomalies.tsx`**

Current logic (lines 133-170):
```tsx
const isIncrease = anomaly.change_amount > 0;
// ... uses isIncrease to set red=increase, green=decrease
```

New logic:
```tsx
const isIncrease = anomaly.change_amount > 0;
const isCostIncrease = isIncrease;  // Higher cost = bad = red
```

Changes needed:
1. **Line 150**: Change to `isCostIncrease ? "text-red-600" : "text-green-600"`
2. **Line 159**: Change arrow direction - red up arrow = cost increase (bad)
3. **Line 163**: Change arrow direction - green down arrow = cost decrease (good)
4. **Line 167**: Change color logic to match

Updated code:
```tsx
<span className={isCostIncrease ? "text-red-600" : "text-green-600"}>
  {isIncrease ? "+" : ""}
  {formatCurrency(anomaly.change_amount)}
</span>

{/* Arrow and percentage */}
{isCostIncrease ? (
  // Cost went up = bad = red up arrow
  <svg className="h-4 w-4 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
  </svg>
) : (
  // Cost went down = good = green down arrow
  <svg className="h-4 w-4 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
  </svg>
)}
<span className={`font-medium ${isCostIncrease ? "text-red-600" : "text-green-600"}`}>
  {absChangePercent.toFixed(1)}%
</span>
```

### Implementation Steps
1. Update `SpendAnomalies.tsx` color logic (15 min)
2. Test with existing data to verify colors match intent (10 min)
3. Update any related documentation or tooltips (5 min)

**Total effort: 30 minutes**

---

## Feature 3: Interactive KPI Trend Views

### Business Value
- Understand KPI trends over time, not just point-in-time values
- Identify patterns: Is spend growing? Stabilizing? Declining?
- Better context for decision-making
- Interactive exploration of cost drivers

### Current State
`SummaryCards.tsx` shows 4 static KPIs:
1. Total Spend
2. Total DBUs
3. Avg Daily Spend
4. Workspaces

Each is a simple card with a single number.

### New Functionality

#### User Experience
- Click on any KPI card → Modal/drawer opens with trend chart
- Chart shows selected KPI over the date range
- Additional metrics in the modal:
  - Trend direction (↑ up, ↓ down, → flat)
  - Change from period start to end
  - Min/max values in period
  - Average value
- Ability to change chart granularity (daily/weekly/monthly)

#### Backend Components

**New Endpoint: `GET /api/billing/kpi-trend`**

Query parameters:
- `kpi`: Which KPI to show (`total_spend`, `total_dbus`, `avg_daily_spend`, `workspace_count`)
- `start_date`: Start date
- `end_date`: End date
- `granularity`: `daily`, `weekly`, `monthly`

Response:
```json
{
  "kpi": "total_spend",
  "granularity": "daily",
  "data_points": [
    {"date": "2025-02-01", "value": 12500},
    {"date": "2025-02-02", "value": 13200},
    ...
  ],
  "summary": {
    "period_start_value": 12500,
    "period_end_value": 15800,
    "change_amount": 3300,
    "change_percent": 26.4,
    "min_value": 11200,
    "max_value": 16500,
    "avg_value": 13850,
    "trend": "increasing"
  }
}
```

**New Query: `KPI_TREND_DAILY_SPEND`**
```sql
-- Daily spend trend
SELECT
  usage_date,
  SUM(list_cost) as daily_spend
FROM system.billing.usage
WHERE usage_date BETWEEN :start_date AND :end_date
  AND cloud = 'aws'  -- or from config
GROUP BY usage_date
ORDER BY usage_date
```

**New Query: `KPI_TREND_TOTAL_DBUS`**
```sql
-- Daily DBU consumption trend
SELECT
  usage_date,
  SUM(usage_quantity) as total_dbus
FROM system.billing.usage
WHERE usage_date BETWEEN :start_date AND :end_date
  AND cloud = 'aws'
GROUP BY usage_date
ORDER BY usage_date
```

**New Query: `KPI_TREND_WORKSPACE_COUNT`**
```sql
-- Active workspaces per day
SELECT
  usage_date,
  COUNT(DISTINCT workspace_id) as workspace_count
FROM system.billing.usage
WHERE usage_date BETWEEN :start_date AND :end_date
  AND cloud = 'aws'
GROUP BY usage_date
ORDER BY usage_date
```

#### Frontend Components

**1. Update: `client/src/components/SummaryCards.tsx`**

Make each card clickable:
```tsx
function Card({ title, value, subtitle, isLoading, onClick }: CardProps) {
  return (
    <div
      className="rounded-lg bg-white p-6 shadow cursor-pointer hover:shadow-lg transition-shadow"
      onClick={onClick}
    >
      {/* existing content */}
    </div>
  );
}
```

**2. New Component: `client/src/components/KPITrendModal.tsx`**

```tsx
interface KPITrendModalProps {
  kpi: 'total_spend' | 'total_dbus' | 'avg_daily_spend' | 'workspace_count';
  kpiLabel: string;
  isOpen: boolean;
  onClose: () => void;
  startDate: string;
  endDate: string;
}

export function KPITrendModal({ kpi, kpiLabel, isOpen, onClose, startDate, endDate }: KPITrendModalProps) {
  const [granularity, setGranularity] = useState<'daily' | 'weekly' | 'monthly'>('daily');
  const { data, isLoading } = useKPITrend(kpi, startDate, endDate, granularity);

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>{kpiLabel} Trend</DialogTitle>
        </DialogHeader>

        {/* Granularity selector */}
        <div className="flex gap-2">
          <Button onClick={() => setGranularity('daily')}>Daily</Button>
          <Button onClick={() => setGranularity('weekly')}>Weekly</Button>
          <Button onClick={() => setGranularity('monthly')}>Monthly</Button>
        </div>

        {/* Summary stats */}
        <div className="grid grid-cols-4 gap-4">
          <StatCard label="Start" value={data?.summary.period_start_value} />
          <StatCard label="End" value={data?.summary.period_end_value} />
          <StatCard label="Change" value={data?.summary.change_percent + '%'} />
          <StatCard label="Avg" value={data?.summary.avg_value} />
        </div>

        {/* Trend chart */}
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data?.data_points}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="value" stroke="#8884d8" />
          </LineChart>
        </ResponsiveContainer>

        {/* Trend indicator */}
        <div className="flex items-center gap-2">
          {data?.summary.trend === 'increasing' && (
            <>
              <TrendingUp className="text-red-500" />
              <span>Trending upward</span>
            </>
          )}
          {data?.summary.trend === 'decreasing' && (
            <>
              <TrendingDown className="text-green-500" />
              <span>Trending downward</span>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

**3. New Hook: `client/src/hooks/useKPITrend.ts`**
```tsx
export function useKPITrend(
  kpi: string,
  startDate: string,
  endDate: string,
  granularity: string
) {
  return useQuery({
    queryKey: ['kpi-trend', kpi, startDate, endDate, granularity],
    queryFn: async () => {
      const response = await fetch(
        `/api/billing/kpi-trend?kpi=${kpi}&start_date=${startDate}&end_date=${endDate}&granularity=${granularity}`
      );
      return response.json();
    },
  });
}
```

**4. Update: `client/src/components/SummaryCards.tsx`**

Add click handlers and modal state:
```tsx
export function SummaryCards({ data, isLoading }: SummaryCardsProps) {
  const [selectedKPI, setSelectedKPI] = useState<string | null>(null);

  return (
    <>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card
          title="Total Spend"
          value={data ? formatCurrency(data.total_spend) : "$0"}
          subtitle={data ? `${data.days_in_range} days` : undefined}
          isLoading={isLoading}
          onClick={() => setSelectedKPI('total_spend')}
        />
        {/* ... other cards */}
      </div>

      {selectedKPI && (
        <KPITrendModal
          kpi={selectedKPI}
          kpiLabel={getKPILabel(selectedKPI)}
          isOpen={!!selectedKPI}
          onClose={() => setSelectedKPI(null)}
          startDate={...}
          endDate={...}
        />
      )}
    </>
  );
}
```

### Implementation Steps

1. **Phase 1: Backend API** (1 day)
   - Create `/api/billing/kpi-trend` endpoint
   - Write SQL queries for each KPI trend
   - Implement trend calculation logic (increasing/decreasing/flat)

2. **Phase 2: Frontend Hook & Types** (0.5 days)
   - Create `useKPITrend` hook
   - Add TypeScript types for KPI trend data

3. **Phase 3: Modal Component** (1 day)
   - Build KPITrendModal component
   - Add Recharts LineChart
   - Add summary stats cards
   - Add granularity selector

4. **Phase 4: Integration** (0.5 days)
   - Make SummaryCards clickable
   - Wire up modal open/close
   - Pass correct date range to modal

5. **Phase 5: Polish** (0.5 days)
   - Add loading states
   - Add error handling
   - Add animations/transitions
   - Test responsiveness

**Total effort: 3.5 days**

---

## Summary Timeline

| Feature | Effort | Priority |
|---------|--------|----------|
| **Proactive Email Reporting** | 8-10 days | High |
| **Inverted Color Scheme** | 30 minutes | Quick Win |
| **Interactive KPI Trends** | 3.5 days | Medium |

**Total: ~2 weeks** for all three features

---

## Open Questions

1. **Email Service**: Which provider? (SendGrid, AWS SES, SMTP)
2. **Alert Frequency**: Default to hourly checks? Configurable?
3. **Databricks Alerts**: Should we create them in a specific workspace folder?
4. **KPI Modal**: Should it be a modal or a slide-out drawer?
5. **Historical Data**: How far back should KPI trends go? (Limited by date picker)

---

## Next Steps

1. Review and approve scope
2. Prioritize features (suggest: Color scheme → KPI Trends → Email Alerts)
3. Set up email service account
4. Create feature branches
5. Begin implementation
