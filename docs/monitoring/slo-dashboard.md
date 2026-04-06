# SLO Dashboard and Error Budget Tracking

> Service Level Objective definitions, error budget calculations, burn rate alerting, and monthly reporting for SchoolOS.

---

## SLO Definitions

### SLO 1: Availability -- 99.9%

**Definition**: The percentage of health check probes that return HTTP 200 from `/health/`.

| Parameter | Value |
|-----------|-------|
| SLI | `successful_health_checks / total_health_checks * 100` |
| Target | 99.9% |
| Measurement | Rolling 30-day window |
| Data Source | monitor-cron.sh (5-min interval), UptimeRobot, Sentry Uptime |
| Error Budget | 43.2 minutes/month (0.1% of 43,200 minutes) |

### SLO 2: Latency (p95) -- < 500ms

**Definition**: The 95th percentile response time across all HTTP transactions must be below 500ms.

| Parameter | Value |
|-----------|-------|
| SLI | `p95(transaction.duration) < 500ms` |
| Target | 99.9% of 5-minute windows meet the target |
| Measurement | Rolling 30-day window, sampled at 5-min intervals |
| Data Source | Sentry APM Performance |
| Error Budget | 43 five-minute windows/month can exceed 500ms |

### SLO 3: Latency (p99) -- < 2s

**Definition**: The 99th percentile response time must be below 2 seconds.

| Parameter | Value |
|-----------|-------|
| SLI | `p99(transaction.duration) < 2000ms` |
| Target | 99.9% of 5-minute windows meet the target |
| Measurement | Rolling 30-day window |
| Data Source | Sentry APM Performance |
| Error Budget | 43 five-minute windows/month can exceed 2s |

### SLO 4: Error Rate -- < 0.1%

**Definition**: The percentage of HTTP requests that result in a 5xx server error.

| Parameter | Value |
|-----------|-------|
| SLI | `5xx_responses / total_responses * 100` |
| Target | < 0.1% |
| Measurement | Rolling 30-day window |
| Data Source | Sentry error events / Sentry transaction count |
| Error Budget | 1 error per 1,000 requests |

---

## Error Budget Calculations

### What Is an Error Budget?

The error budget is the maximum amount of unreliability allowed before the SLO is breached. It is calculated as:

```
error_budget = 1 - SLO_target
```

For a 99.9% availability SLO:

```
error_budget = 1 - 0.999 = 0.001 = 0.1%
```

### Monthly Error Budgets

Assuming a 30-day month (43,200 minutes):

| SLO | Target | Error Budget (time) | Error Budget (events*) |
|-----|--------|--------------------|-----------------------|
| Availability | 99.9% | 43.2 min downtime | 8.6 failed checks (at 5-min interval) |
| Latency p95 | 99.9% good windows | 43 bad 5-min windows | ~43 slow windows |
| Latency p99 | 99.9% good windows | 43 bad 5-min windows | ~43 slow windows |
| Error Rate | < 0.1% | N/A | 1 per 1,000 requests |

*Event counts depend on traffic volume and check frequency.

### Error Budget Consumption Formula

```
budget_consumed_pct = (bad_minutes / total_error_budget_minutes) * 100
```

Example: If SchoolOS was down for 15 minutes this month:

```
budget_consumed = (15 / 43.2) * 100 = 34.7%
budget_remaining = 100% - 34.7% = 65.3%
```

### Error Budget Policy

| Budget Remaining | Action |
|-----------------|--------|
| > 75% | Normal development velocity. Ship features. |
| 50-75% | Caution. Review recent incidents. Prioritize reliability work. |
| 25-50% | Slow down feature work. Focus on stability and performance. |
| < 25% | Feature freeze. All engineering effort on reliability. |
| 0% (exhausted) | Full stop. Postmortem required. No deploys until budget recovers. |

---

## Burn Rate Alerting

### What Is Burn Rate?

Burn rate measures how fast the error budget is being consumed relative to the SLO window. A burn rate of 1.0 means the budget will be exactly exhausted at the end of the window.

```
burn_rate = (error_rate_observed / error_rate_budget)
```

For 99.9% availability SLO:

```
error_rate_budget = 0.1%

If current error rate = 0.5%:
burn_rate = 0.5% / 0.1% = 5x

At 5x burn rate, the 30-day budget will be exhausted in 6 days.
```

### Burn Rate Alert Windows

Google SRE recommends multi-window burn rate alerts. These catch both fast-burning incidents and slow degradation.

| Alert | Burn Rate | Long Window | Short Window | Budget Consumed | Time to Exhaust |
|-------|-----------|-------------|--------------|-----------------|-----------------|
| **P0 - Page** | 14.4x | 1 hour | 5 min | 2% in 1 hour | 2.08 days |
| **P1 - Ticket** | 6x | 6 hours | 30 min | 5% in 6 hours | 5 days |
| **P2 - Warning** | 3x | 1 day | 2 hours | 10% in 1 day | 10 days |
| **P3 - Log** | 1x | 3 days | 6 hours | 10% in 3 days | 30 days |

### How Multi-Window Works

Both windows must be in violation simultaneously to fire the alert. This prevents:
- **Long window only**: would alert on past incidents already resolved
- **Short window only**: would alert on brief transient blips

```
Alert fires when:
  burn_rate(long_window) > threshold
  AND
  burn_rate(short_window) > threshold
```

### Implementing Burn Rate Alerts

#### In Sentry

Sentry does not natively support burn rate alerting, but you can approximate it:

1. **P0 equivalent**: Error count > 50 in 5 minutes (fast burn)
2. **P1 equivalent**: Error count > 100 in 30 minutes (moderate burn)
3. **P2 equivalent**: Error count > 200 in 2 hours (slow burn)

Adjust thresholds based on your traffic volume.

#### In Grafana (if configured)

```yaml
# Grafana alert rule for burn rate
apiVersion: 1
groups:
  - name: SchoolOS Burn Rate
    folder: SchoolOS
    interval: 1m
    rules:
      - uid: burn-rate-p0
        title: "P0: Fast error budget burn (14.4x)"
        condition: B
        data:
          - refId: A
            # Error rate over last 5 minutes
            # Must exceed 14.4 * 0.1% = 1.44% error rate
          - refId: B
            # Error rate over last 1 hour
            # Must also exceed 1.44%
        for: 0m  # Alert immediately
        labels:
          severity: page
        annotations:
          summary: "Error budget burning at 14.4x rate. Budget exhausted in ~2 days."

      - uid: burn-rate-p1
        title: "P1: Moderate error budget burn (6x)"
        condition: B
        data:
          - refId: A
            # Error rate over last 30 minutes > 0.6%
          - refId: B
            # Error rate over last 6 hours > 0.6%
        for: 0m
        labels:
          severity: ticket
        annotations:
          summary: "Error budget burning at 6x rate. Budget exhausted in ~5 days."
```

---

## Calculating Availability from Railway Metrics

### Method 1: Health Check Based (Recommended)

Use the cron monitor (`monitor-cron.sh`) logs:

```bash
# Count total checks and failures from the log file
TOTAL=$(wc -l < /tmp/schoolos-monitor.log)
FAILURES=$(grep -c "FAIL" /tmp/schoolos-monitor.log)
SUCCESSES=$((TOTAL - FAILURES))
AVAILABILITY=$(echo "scale=4; $SUCCESSES / $TOTAL * 100" | bc)
echo "Availability: ${AVAILABILITY}%"
```

### Method 2: UptimeRobot API

If using UptimeRobot (free tier):

```bash
# Get uptime ratio for last 30 days
curl -s "https://api.uptimerobot.com/v2/getMonitors" \
  -d "api_key=YOUR_API_KEY" \
  -d "custom_uptime_ratios=30" \
  -d "format=json" | jq '.monitors[0].custom_uptime_ratio'
```

### Method 3: Sentry Uptime Monitor

If using Sentry's Uptime feature:

1. Navigate to Sentry > Alerts > Uptime Monitors
2. Select the `/health/` monitor
3. View the uptime percentage for the selected time range

### Method 4: Manual Calculation from Incidents

```
downtime_minutes = sum of all incident durations in the month
total_minutes = days_in_month * 24 * 60
availability = (total_minutes - downtime_minutes) / total_minutes * 100
```

Example for April 2026 (30 days):

```
total_minutes = 30 * 24 * 60 = 43,200
downtime_minutes = 12 (two incidents: 8 min + 4 min)
availability = (43,200 - 12) / 43,200 * 100 = 99.972%
SLO met: Yes (99.972% > 99.9%)
Budget consumed: 12 / 43.2 = 27.8%
```

---

## Monthly SLO Report Template

Copy and fill out this template at the end of each month. Store in `docs/postmortems/slo-reports/YYYY-MM.md`.

```markdown
# SchoolOS SLO Report -- [Month Year]

## Report Period
- **Start**: YYYY-MM-01
- **End**: YYYY-MM-DD (last day of month)
- **Total minutes**: [days * 1440]
- **Prepared by**: [Name]
- **Date prepared**: YYYY-MM-DD

---

## SLO Summary

| SLO | Target | Actual | Status | Budget Used |
|-----|--------|--------|--------|-------------|
| Availability | 99.9% | __.__% | MET / BREACHED | __% |
| Latency p95 | < 500ms | ___ms | MET / BREACHED | __% |
| Latency p99 | < 2s | ____ms | MET / BREACHED | __% |
| Error Rate | < 0.1% | __.__% | MET / BREACHED | __% |

---

## Availability Details

- **Total health checks**: ____
- **Failed health checks**: ____
- **Downtime minutes**: ____
- **Incidents**: ____

### Incident Summary

| # | Date | Duration | Impact | Root Cause | Postmortem |
|---|------|----------|--------|------------|------------|
| 1 | MM-DD | __min | [description] | [cause] | [link] |
| 2 | MM-DD | __min | [description] | [cause] | [link] |

---

## Latency Details

- **p50 response time**: ___ms
- **p95 response time**: ___ms
- **p99 response time**: ___ms
- **Slowest transaction**: [name] at ___ms

### Top 5 Slowest Endpoints

| Endpoint | p50 | p95 | p99 | Calls |
|----------|-----|-----|-----|-------|
| | | | | |

---

## Error Rate Details

- **Total requests**: _____
- **5xx errors**: _____
- **Error rate**: __.___%
- **Top error types**: [list]

### Top 5 Errors

| Error | Count | First Seen | Status |
|-------|-------|------------|--------|
| | | | |

---

## Error Budget Status

| SLO | Budget (month) | Consumed | Remaining | Trend |
|-----|---------------|----------|-----------|-------|
| Availability | 43.2 min | __ min | __ min | improving / worsening |
| Error Rate | 0.1% | __% | __% | improving / worsening |

---

## Action Items

| # | Action | Owner | Due Date | Status |
|---|--------|-------|----------|--------|
| 1 | | | | |
| 2 | | | | |

---

## Notes

[Any additional context, upcoming risks, planned maintenance, etc.]
```

---

## Dashboard Panel Definitions

If using Grafana, create these panels on a "SchoolOS SLO" dashboard:

### Panel 1: Availability Over Time (Time Series)

- **Query**: Health check success rate, grouped by hour
- **Visualization**: Time series with SLO line at 99.9%
- **Thresholds**: Green > 99.9%, Yellow > 99.5%, Red < 99.5%

### Panel 2: Error Budget Remaining (Gauge)

- **Query**: `(1 - (downtime_minutes / 43.2)) * 100`
- **Visualization**: Gauge, 0-100%
- **Thresholds**: Green > 50%, Yellow > 25%, Red < 25%

### Panel 3: Burn Rate (Stat)

- **Query**: Current burn rate over last 1 hour
- **Visualization**: Stat with sparkline
- **Thresholds**: Green < 1x, Yellow < 6x, Red > 6x

### Panel 4: Latency p95 Over Time (Time Series)

- **Query**: Sentry APM p95 transaction duration, 5-min buckets
- **Visualization**: Time series with SLO line at 500ms
- **Thresholds**: Green < 500ms, Yellow < 1s, Red > 1s

### Panel 5: Error Rate Over Time (Time Series)

- **Query**: Sentry error events / total transactions, 5-min buckets
- **Visualization**: Time series with SLO line at 0.1%
- **Thresholds**: Green < 0.1%, Yellow < 0.5%, Red > 0.5%

### Panel 6: Monthly SLO Status (Table)

- **Query**: Calculated monthly SLO values
- **Visualization**: Table with status icons
- **Columns**: SLO Name, Target, Actual, Status (pass/fail), Budget Remaining

---

## References

- [Observability Stack](./observability-stack.md) -- Full architecture and Grafana setup
- [Alerting Setup](./alerting-setup.md) -- Alert configuration and escalation
- [Health Endpoints](./health-endpoints.md) -- /health/, /ready/, /status/ API reference
- [Incident Response](../INCIDENT_RESPONSE.md) -- What to do when an SLO is breached
- Google SRE Book: [Implementing SLOs](https://sre.google/workbook/implementing-slos/)
- Google SRE Book: [Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
