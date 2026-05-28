# Cost Observability Alerting System

## Overview

The Cost Observability & Control alerting system provides proactive monitoring and notification of Databricks cost anomalies. It detects spend spikes, threshold breaches, and other cost-related events, with email notification capabilities.

## Features

### 1. Spend Spike Detection
- **Day-over-day analysis**: Compares daily spend to previous day
- **Configurable thresholds**: Set minimum percent change to flag (e.g., 20%)
- **Severity levels**: High (>50% change) and Medium (15-50% change)
- **Directional tracking**: Identifies both increases and decreases

### 2. Threshold Breach Detection
- **Absolute thresholds**: Alert when daily spend exceeds a dollar amount
- **Customizable limits**: Set organization-specific budget thresholds
- **Excess tracking**: Shows how much over threshold the spend was

### 3. Email Notifications
- **Individual alerts**: Send single alert emails
- **Digest emails**: Combine multiple alerts into one email
- **HTML formatting**: Professional, color-coded alert emails
- **SMTP integration**: Works with Gmail, Office 365, SendGrid, AWS SES, etc.

### 4. Alerts Dashboard
- **Visual timeline**: See all recent alerts in one view
- **Severity indicators**: Color-coded by alert severity
- **Time range filtering**: View alerts for 7, 14, or 30 days
- **Alert details**: See full breakdown of spend changes

## Configuration

### SMTP Email Setup

To enable email notifications, configure the following environment variables:

```bash
# Required
export SMTP_HOST="smtp.gmail.com"              # Your SMTP server
export SMTP_PORT="587"                         # SMTP port (usually 587 for TLS)
export SMTP_USERNAME="your-email@gmail.com"    # SMTP username
export SMTP_PASSWORD="your-app-password"       # SMTP password or app password
export SMTP_FROM_EMAIL="your-email@gmail.com"  # From email address

# Optional
export SMTP_FROM_NAME="Cost Observability & Control"  # Display name for sender
```

#### Gmail Setup Example

1. **Enable 2-Factor Authentication** in your Google Account
2. **Generate an App Password**:
   - Go to https://myaccount.google.com/apppasswords
   - Select "Mail" and your device
   - Copy the generated 16-character password
3. **Set environment variables**:
   ```bash
   export SMTP_HOST="smtp.gmail.com"
   export SMTP_PORT="587"
   export SMTP_USERNAME="your-email@gmail.com"
   export SMTP_PASSWORD="abcd efgh ijkl mnop"  # App password (no spaces)
   export SMTP_FROM_EMAIL="your-email@gmail.com"
   ```

#### Office 365 Setup Example

```bash
export SMTP_HOST="smtp.office365.com"
export SMTP_PORT="587"
export SMTP_USERNAME="your-email@company.com"
export SMTP_PASSWORD="your-password"
export SMTP_FROM_EMAIL="your-email@company.com"
```

#### SendGrid Setup Example

```bash
export SMTP_HOST="smtp.sendgrid.net"
export SMTP_PORT="587"
export SMTP_USERNAME="apikey"
export SMTP_PASSWORD="SG.your-api-key-here"
export SMTP_FROM_EMAIL="noreply@yourdomain.com"
```

### Testing SMTP Configuration

Use the API endpoint to verify your SMTP setup:

```bash
curl http://localhost:8000/api/alerts/test-smtp | jq
```

**Success response:**
```json
{
  "success": true,
  "message": "SMTP connection successful",
  "config": {
    "host": "smtp.gmail.com",
    "port": 587,
    "from_email": "your-email@gmail.com"
  }
}
```

**Failure response:**
```json
{
  "success": false,
  "error": "SMTP authentication failed",
  "config": {
    "host": "smtp.gmail.com",
    "port": 587
  }
}
```

## Using the Alerts UI

### Accessing the Alerts Dashboard

1. Navigate to the Cost Observability & Control app
2. Click the **Alerts** tab in the main navigation
3. The dashboard shows:
   - **Total alerts count**
   - **Date range** of analyzed data
   - **Alert types breakdown**
   - **Individual alert cards** with details

### Understanding Alert Cards

Each alert card displays:

- **Alert Type**: Spend Spike or Threshold Breach
- **Severity**: High (red) or Medium (yellow)
- **Date**: When the anomaly occurred
- **Daily Spend**: Total cost for that day
- **Change Details**: For spikes, shows percent change and dollar amount
- **Threshold Details**: For breaches, shows threshold and excess amount

### Filtering Alerts

Use the time range buttons to view alerts for:
- **7 days** (default)
- **14 days**
- **30 days**

## API Endpoints

### 1. Get Recent Alerts

```bash
GET /api/alerts/recent?days_back=7
```

**Response:**
```json
{
  "spikes": [
    {
      "usage_date": "2026-02-02",
      "daily_spend": 44941.08,
      "prev_day_spend": 40444.62,
      "change_amount": 4496.46,
      "change_percent": 11.12,
      "alert_type": "spike",
      "severity": "medium"
    }
  ],
  "total_alerts": 1,
  "date_range": {
    "start": "2026-01-27",
    "end": "2026-02-03"
  }
}
```

### 2. Detect Spend Spikes

```bash
GET /api/alerts/spikes?threshold_percent=20&days_back=7
```

**Parameters:**
- `threshold_percent`: Minimum percent change to flag (default: 20.0, range: 5-100)
- `days_back`: Days to look back (default: 7, range: 1-90)

### 3. Detect Threshold Breaches

```bash
GET /api/alerts/threshold-breaches?threshold_amount=40000&days_back=7
```

**Parameters:**
- `threshold_amount`: Dollar threshold (required, must be >= 0)
- `days_back`: Days to look back (default: 7, range: 1-90)

### 4. Send Alert Email

```bash
POST /api/alerts/send-alert
Content-Type: application/json

{
  "to_email": "user@example.com",
  "alert_data": {
    "usage_date": "2026-02-02",
    "daily_spend": 44941.08,
    "prev_day_spend": 40444.62,
    "change_amount": 4496.46,
    "change_percent": 11.12,
    "alert_type": "spike",
    "severity": "medium"
  },
  "to_name": "John Doe"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Email sent to user@example.com"
}
```

### 5. Send Alert Digest

```bash
POST /api/alerts/send-digest
Content-Type: application/json

{
  "to_email": "user@example.com",
  "to_name": "John Doe",
  "days_back": 7
}
```

Sends a single email with all alerts from the specified time period.

### 6. Test Email Formatting

```bash
POST /api/alerts/test-email-format
Content-Type: application/json

{
  "usage_date": "2026-02-02",
  "daily_spend": 44941.08,
  "prev_day_spend": 40444.62,
  "change_amount": 4496.46,
  "change_percent": 11.12,
  "alert_type": "spike",
  "severity": "medium"
}
```

Returns the formatted HTML email without sending it.

## Alert Detection Logic

### Spend Spike Detection

1. **Calculate daily spend** from `system.billing.usage` × `system.billing.list_prices`
2. **Compare to previous day** using SQL LAG() window function
3. **Calculate percent change**: `(current - previous) / previous * 100`
4. **Flag if exceeds threshold**: Default 15-20% change
5. **Assign severity**:
   - High: >50% change
   - Medium: 15-50% change

**SQL Pattern:**
```sql
WITH daily_spend AS (
  SELECT usage_date, SUM(usage_quantity * price_per_dbu) as daily_spend
  FROM system.billing.usage JOIN system.billing.list_prices
  GROUP BY usage_date
),
with_prev AS (
  SELECT
    usage_date,
    daily_spend,
    LAG(daily_spend) OVER (ORDER BY usage_date) as prev_day_spend
  FROM daily_spend
)
SELECT * FROM with_prev
WHERE ABS((daily_spend - prev_day_spend) / prev_day_spend * 100) >= threshold
```

### Threshold Breach Detection

1. **Calculate daily spend** (same as above)
2. **Compare to configured threshold**
3. **Flag days exceeding threshold**
4. **Calculate excess amount**: `daily_spend - threshold`

## Scheduled Alerting (Future Enhancement)

### Planned Features

1. **Hourly Evaluation**: Check for new alerts every hour
2. **Daily Digest**: Send summary email once per day
3. **Alert Rules**: Configure custom alert rules with:
   - Alert type (spike, threshold, anomaly)
   - Threshold values
   - Recipients
   - Schedule (immediate, daily, weekly)
4. **Alert History**: Track all triggered alerts in database

### Implementation Approach

Using Databricks Jobs or background scheduler:

```python
# Example scheduled job structure
def hourly_alert_check():
    """Run every hour to check for new alerts."""
    alerts = detect_spend_spikes(threshold_percent=20.0, days_back=1)

    if alerts:
        for alert in alerts:
            # Check if alert already sent
            if not alert_already_sent(alert):
                send_alert_email(
                    to_email="alerts@company.com",
                    alert_data=alert
                )
                mark_alert_sent(alert)

def daily_digest():
    """Run once per day to send digest."""
    alerts = get_recent_alerts(days_back=1)

    if alerts['total_alerts'] > 0:
        send_alert_digest(
            to_email="team@company.com",
            alerts=alerts['spikes']
        )
```

## Troubleshooting

### Email Not Sending

1. **Check SMTP configuration**:
   ```bash
   curl http://localhost:8000/api/alerts/test-smtp | jq
   ```

2. **Verify environment variables are set**:
   ```bash
   echo $SMTP_USERNAME
   echo $SMTP_FROM_EMAIL
   ```

3. **Check for authentication errors** in application logs

4. **Gmail users**: Ensure you're using an **App Password**, not your regular password

5. **Office 365 users**: May need to enable "SMTP AUTH" in Exchange Online

### No Alerts Showing

1. **Check date range**: Extend to 30 days to see more history
2. **Lower threshold**: Try 10% threshold for spike detection
3. **Verify billing data**: Ensure `system.billing.usage` has recent data
4. **Check logs** for query errors

### Alert False Positives

1. **Increase threshold**: Use 30-50% for high-variance workloads
2. **Add filters**: Consider filtering by workspace or product
3. **Weekly comparison**: Compare to same day last week instead of previous day

## Best Practices

1. **Start with higher thresholds** (30%+) and adjust down based on false positive rate
2. **Send digest emails** instead of individual alerts to reduce email volume
3. **Configure alert recipients** at the team/group level, not individuals
4. **Monitor alert accuracy** and tune thresholds over time
5. **Document your thresholds** and update them as usage patterns change
6. **Test email delivery** before enabling production alerting
7. **Use different thresholds** for different environments (dev vs prod)

## Related Documentation

- [Feature Scope: Proactive Alerts](./feature_scope_proactive_alerts.md)
- [System Tables Reference](https://docs.databricks.com/administration-guide/system-tables/index.html)
- [Databricks SQL Alerts](https://docs.databricks.com/sql/user/alerts/index.html)
