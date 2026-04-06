# SchoolOS Observability Stack

> Complete monitoring and observability architecture for SchoolOS on Railway.

## Architecture Overview

```
                         SchoolOS Observability Stack
 ============================================================================

  Layer 6: Dashboards          Grafana Cloud (Free Tier)
                                  |         |         |
                                  v         v         v
  Layer 5: Log Aggregation     Railway Logs + Structured JSON Logging
  Layer 4: Uptime Monitoring   smoke-test.sh + monitor-cron.sh + GH Actions
  Layer 3: Infrastructure      Railway Built-in Metrics (CPU, RAM, Network)
  Layer 2: APM / Traces        Sentry Performance (traces_sample_rate=0.1)
  Layer 1: Error Tracking      Sentry (DjangoIntegration + Celery + Redis)

 ============================================================================

  Data Flow:

  Django App ──> Sentry SDK ──> Sentry Cloud ──> Grafana (via data source)
       |                                              ^
       |──> stdout (JSON) ──> Railway Logs ───────────|
       |                                              |
       |──> /health/ ──> monitor-cron.sh ──> Slack ──>|
       |──> /status/ ──> Grafana HTTP probe ──────────|

  Alerting:

  Sentry Alerts ──> Slack #schoolos-alerts
  Cron Monitor  ──> Slack #schoolos-alerts
  Grafana       ──> Slack #schoolos-alerts (unified)
```

---

## Layer 1: Error Tracking (Sentry)

**Status: CONFIGURED** -- see [sentry-setup.md](./sentry-setup.md)

Sentry captures unhandled exceptions, Celery task failures, and Redis errors. The SDK is initialized in `shschool/settings/production.py` with PDPPL-compliant settings (`send_default_pii=False`).

### Current Configuration

| Setting | Value | Purpose |
|---------|-------|---------|
| `traces_sample_rate` | `0.1` (10%) | Performance tracing |
| `profiles_sample_rate` | `0.1` (10%) | Code profiling |
| `send_default_pii` | `False` | PDPPL compliance |
| Integrations | Django, Celery, Redis | Auto-instrumentation |

### Integrations Active

- **DjangoIntegration** -- captures view exceptions, middleware errors, template errors
- **CeleryIntegration** -- captures task failures, timeouts, retries
- **RedisIntegration** -- captures connection failures, command errors

### What to Monitor in Sentry

- **Issues > Unresolved** -- new errors requiring triage
- **Performance > Transactions** -- slowest endpoints
- **Profiling > Functions** -- CPU hotspots
- **Crons** -- Celery beat task health (if configured)

---

## Layer 2: Application Performance Monitoring (Sentry APM)

**Status: CONFIGURED** at 10% sample rate.

Sentry APM provides distributed traces for Django requests and Celery tasks.

### Trace Anatomy

```
Request: GET /api/students/
  |
  |-- Middleware chain (auth, session, CSRF)         [2ms]
  |-- View: StudentListView.get()                    [45ms]
  |     |-- DB: SELECT * FROM students_student       [12ms]
  |     |-- DB: SELECT * FROM students_enrollment    [8ms]
  |     |-- Serializer                               [15ms]
  |-- Template render                                [10ms]
  |-- Response                                       [1ms]
  Total: 93ms
```

### Key Transactions to Watch

| Transaction | SLI Target | Alert Threshold |
|-------------|-----------|-----------------|
| `GET /` (login page) | p95 < 200ms | p95 > 500ms for 5 min |
| `GET /api/students/` | p95 < 500ms | p95 > 1s for 5 min |
| `GET /admin/` | p95 < 300ms | p95 > 1s for 5 min |
| `POST /api/grades/` | p95 < 500ms | p95 > 2s for 5 min |
| Celery: `generate_report_pdf` | p95 < 30s | p95 > 60s |
| Celery: `send_notification` | p95 < 5s | p95 > 15s |

### Adjusting Sample Rate

For production with moderate traffic (< 10k requests/day), 10% is sufficient. If traffic grows:

```python
# In production.py -- adjust based on traffic volume
traces_sample_rate=0.1,   # 10% -- up to ~50k req/day
# traces_sample_rate=0.05,  # 5% -- 50k-200k req/day
# traces_sample_rate=0.01,  # 1% -- 200k+ req/day
```

### Custom Spans

Add custom spans for business-critical operations:

```python
import sentry_sdk

def generate_report_card(student_id):
    with sentry_sdk.start_span(op="report", description="Generate report card"):
        # ... report generation logic
        with sentry_sdk.start_span(op="db", description="Fetch grades"):
            grades = Grade.objects.filter(student_id=student_id)
        with sentry_sdk.start_span(op="render", description="Render PDF"):
            pdf = render_pdf(grades)
    return pdf
```

---

## Layer 3: Infrastructure Metrics (Railway)

**Status: AVAILABLE** via Railway dashboard.

Railway provides built-in metrics for each service.

### Available Metrics

| Metric | Location | Alert When |
|--------|----------|------------|
| CPU Usage | Railway Dashboard > Service > Metrics | > 80% sustained 5 min |
| Memory Usage | Railway Dashboard > Service > Metrics | > 85% of limit |
| Network I/O | Railway Dashboard > Service > Metrics | Unusual spikes |
| Disk Usage | Railway Dashboard > Service > Metrics | > 90% |
| Deploy Status | Railway Dashboard > Deployments | Failed deploy |

### Railway CLI for Metrics

```bash
# View recent logs
railway logs --tail

# Check service status
railway status

# View environment variables (never log these)
railway variables
```

### Resource Limits (Hobby Plan -- $5/mo)

| Resource | Limit | Recommendation |
|----------|-------|----------------|
| RAM | 512 MB (soft), 8 GB (hard) | Keep under 400 MB |
| CPU | Shared vCPU | Monitor for throttling |
| Disk | 1 GB ephemeral | Use S3 for media files |
| Network | 100 GB/month | Sufficient for school traffic |

### PostgreSQL Metrics (Railway)

Railway-managed PostgreSQL exposes:

- Active connections (max typically 20-100 depending on plan)
- Database size
- Query performance via `pg_stat_statements`

Monitor via:

```sql
-- Active connections
SELECT count(*) FROM pg_stat_activity WHERE state = 'active';

-- Slow queries (> 1s)
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Database size
SELECT pg_size_pretty(pg_database_size(current_database()));
```

---

## Layer 4: Uptime Monitoring

**Status: CONFIGURED** -- see [alerting-setup.md](./alerting-setup.md) and [health-endpoints.md](./health-endpoints.md)

### Components

| Component | Interval | What It Checks |
|-----------|----------|----------------|
| `smoke-test.sh` | Post-deploy | 5 endpoints: /health/, /ready/, /status/, /, /admin/ |
| `monitor-cron.sh` | Every 5 min | /health/ with 3-failure threshold |
| GitHub Actions | Every 15 min | Full smoke test suite |
| Sentry Uptime (optional) | Every 1 min | /health/ endpoint |

### Adding UptimeRobot (Free Tier)

1. Create account at [uptimerobot.com](https://uptimerobot.com)
2. Add monitor:
   - Type: HTTP(s)
   - URL: `https://shschoolmvp-production.up.railway.app/health/`
   - Interval: 5 minutes (free tier)
   - Alert contacts: email + Slack webhook
3. Add a second monitor for `/ready/` as a keyword monitor:
   - Expected keyword: `"ready": true`

---

## Layer 5: Log Aggregation

**Status: PARTIALLY CONFIGURED** -- file-based logging exists, structured JSON logging recommended.

See [structured-logging.md](./structured-logging.md) for implementation details.

### Current State

The production logging config (`production.py`) uses:

- `RotatingFileHandler` for `django.log` (10 MB x 5 copies)
- `RotatingFileHandler` for `security.log` (5 MB x 10 copies)
- `StreamHandler` for console (captured by Railway)
- `PIIMaskingFilter` on all handlers (PDPPL compliance)

### Railway Log Explorer

Railway captures all stdout/stderr output. With structured JSON logging, you can search and filter logs in the Railway dashboard.

### Log Levels in Production

| Logger | Level | Rationale |
|--------|-------|-----------|
| `root` | WARNING | Avoid noise |
| `django` | WARNING | Only errors and warnings |
| `django.security` | WARNING | Security events |
| `django.request` | WARNING | Failed requests |
| `notifications` | INFO | Track notification delivery |
| `celery` | INFO | Track task execution |
| `axes` | WARNING | Failed login attempts |
| `channels` / `daphne` | WARNING | WebSocket errors only |

---

## Layer 6: Custom Dashboards (Grafana Cloud Free Tier)

**Status: NOT YET CONFIGURED** -- setup steps below.

Grafana Cloud free tier provides:

- 10,000 series for metrics
- 50 GB logs
- 50 GB traces
- 3 users
- 14-day retention

### Setup Steps

#### Step 1: Create Grafana Cloud Account

1. Go to [grafana.com/products/cloud](https://grafana.com/products/cloud/)
2. Sign up for the **Free Forever** plan
3. Note your Grafana Cloud URL: `https://<your-slug>.grafana.net`

#### Step 2: Add Sentry as a Data Source

1. In Grafana, go to **Connections > Data Sources > Add data source**
2. Search for **Sentry**
3. Configure:
   - **URL**: `https://sentry.io`
   - **Auth Token**: Generate at Sentry > Settings > Auth Tokens (scopes: `project:read`, `event:read`, `org:read`)
   - **Organization Slug**: your Sentry org slug
4. Click **Save & Test**

#### Step 3: Add Railway Metrics (via Prometheus endpoint)

If you have the `/metrics` Prometheus endpoint enabled:

1. Add a **Prometheus** data source in Grafana
2. URL: Your metrics endpoint (requires authentication -- use `METRICS_ALLOWED_IPS`)
3. Note: Railway does not natively export Prometheus metrics. You would need to use `django-prometheus` and expose the `/metrics` endpoint.

Alternative: Use Grafana's **JSON API** data source to poll `/status/` endpoint:

1. Add **JSON API** data source
2. URL: `https://shschoolmvp-production.up.railway.app/status/`
3. Parse the JSON response for uptime, latency, and component status

#### Step 4: Import Recommended Dashboards

| Dashboard | Grafana ID | Purpose |
|-----------|-----------|---------|
| Django Monitoring | 17658 | Request rates, response times, error rates |
| PostgreSQL Overview | 9628 | Connections, query performance, cache hit ratio |
| Redis Dashboard | 11835 | Memory, commands/sec, connected clients |
| Celery Monitoring | 15169 | Task success/failure, queue depth, worker status |

To import:

1. Go to **Dashboards > Import**
2. Enter the dashboard ID
3. Select the appropriate data source
4. Adjust variables (hostname, database name, etc.)

#### Step 5: Create a SchoolOS Overview Dashboard

Create a custom dashboard with these panels:

```
+----------------------------------+----------------------------------+
|  System Health (from /status/)   |  Error Rate (Sentry)             |
|  - DB: connected/disconnected    |  - Errors/hour sparkline         |
|  - Redis: connected/disconnected |  - Unresolved issues count       |
|  - Migrations: applied/pending   |                                  |
+----------------------------------+----------------------------------+
|  Response Time p95 (Sentry APM)  |  Uptime % (calculated)           |
|  - By transaction name           |  - Last 24h / 7d / 30d           |
|  - SLO line at 500ms             |  - SLO target line at 99.9%      |
+----------------------------------+----------------------------------+
|  Active Users (from /status/)    |  Celery Task Status (Sentry)     |
|  - Current sessions              |  - Success / Failure / Retry     |
|  - Uptime seconds                |  - Queue depth                   |
+----------------------------------+----------------------------------+
```

---

## SLO / SLI Definitions

### Service Level Indicators (SLIs)

| SLI | Measurement | Source |
|-----|------------|--------|
| **Availability** | % of /health/ checks returning 200 | monitor-cron.sh, UptimeRobot |
| **Latency** | p95 and p99 response time across all transactions | Sentry APM |
| **Error Rate** | % of requests resulting in 5xx responses | Sentry error count / total transactions |
| **Throughput** | Requests per second | Sentry APM transaction count |

### Service Level Objectives (SLOs)

| SLO | Target | Error Budget (30 days) | Measurement Window |
|-----|--------|------------------------|-------------------|
| **Availability** | 99.9% | 43.2 minutes downtime | Rolling 30 days |
| **Latency (p95)** | < 500ms | 0.1% of requests can exceed | Rolling 30 days |
| **Latency (p99)** | < 2s | 1% of requests can exceed | Rolling 30 days |
| **Error Rate** | < 0.1% | 1 in 1,000 requests can fail | Rolling 30 days |

See [slo-dashboard.md](./slo-dashboard.md) for detailed SLO tracking and error budget calculations.

### Alert Rules for SLI Breaches

#### Availability Alerts

| Condition | Severity | Action |
|-----------|----------|--------|
| /health/ returns non-200 for 3 consecutive checks (15 min) | P1 - High | Slack alert, page on-call |
| /health/ returns non-200 for 6 consecutive checks (30 min) | P0 - Critical | Escalation to Lead Dev + DevOps |
| Monthly availability drops below 99.95% | P2 - Medium | Review in weekly ops meeting |
| Monthly availability drops below 99.9% (SLO breach) | P1 - High | Incident review required |

#### Latency Alerts

| Condition | Severity | Action |
|-----------|----------|--------|
| p95 > 500ms for 5 minutes | P2 - Medium | Slack alert |
| p95 > 1s for 5 minutes | P1 - High | Slack alert, investigate immediately |
| p99 > 2s for 5 minutes | P1 - High | Slack alert, page on-call |
| p99 > 5s for any duration | P0 - Critical | Immediate response |

#### Error Rate Alerts

| Condition | Severity | Action |
|-----------|----------|--------|
| Error rate > 0.1% for 5 minutes | P2 - Medium | Slack alert |
| Error rate > 1% for 5 minutes | P1 - High | Slack alert, page on-call |
| Error rate > 5% for 1 minute | P0 - Critical | Immediate response, consider rollback |
| New unhandled exception type | P2 - Medium | Slack alert, triage in next standup |

#### Implementing Alerts in Sentry

```
Sentry > Alerts > Create Alert Rule:

1. Availability:
   - Type: Uptime Monitor
   - URL: https://shschoolmvp-production.up.railway.app/health/
   - Check interval: 1 minute
   - Alert after: 3 consecutive failures

2. Latency (p95):
   - Type: Performance Alert
   - Metric: Transaction Duration p95
   - Threshold: > 500ms
   - Time window: 5 minutes
   - Action: Slack #schoolos-alerts

3. Error Rate:
   - Type: Issue Alert
   - Condition: Number of events > 10 in 10 minutes
   - Filter: level:error
   - Action: Slack #schoolos-alerts

4. Error Budget Warning:
   - Type: Metric Alert
   - Metric: Failure rate
   - Threshold: > 0.05% (50% of budget)
   - Time window: 1 hour
   - Action: Slack #schoolos-alerts
```

#### Implementing Alerts in Grafana

```yaml
# Example Grafana alert rule (provisioned via YAML or UI)
apiVersion: 1
groups:
  - orgId: 1
    name: SchoolOS SLOs
    folder: SchoolOS
    interval: 5m
    rules:
      - uid: availability-slo
        title: "Availability SLO Breach"
        condition: C
        data:
          - refId: A
            queryType: ""
            # Query /health/ status from JSON data source
        for: 15m
        labels:
          severity: critical
        annotations:
          summary: "SchoolOS availability has dropped below 99.9% SLO"
```

---

## Operational Runbook Quick Reference

| Scenario | First Step | Escalation |
|----------|-----------|------------|
| /health/ returns 503 | Check Railway logs: `railway logs --tail` | Page on-call if DB is down |
| p95 latency spike | Check Sentry Performance > Transactions | Look for slow DB queries |
| Error rate spike | Check Sentry Issues > sort by frequency | Deploy hotfix or rollback |
| Memory usage > 85% | Check for memory leaks in Sentry Profiling | Restart service, increase limit |
| Celery tasks failing | Check Sentry > filter by `celery` tag | Check Redis connectivity |
| Railway deploy failed | Check Railway deployment logs | Rollback: `railway rollback` |

---

## References

- [Sentry Setup](./sentry-setup.md) -- Sentry configuration details
- [Health Endpoints](./health-endpoints.md) -- /health/, /ready/, /status/ documentation
- [Alerting Setup](./alerting-setup.md) -- Slack webhooks, cron monitoring, GitHub Actions
- [Structured Logging](./structured-logging.md) -- JSON logging implementation
- [SLO Dashboard](./slo-dashboard.md) -- SLO tracking and error budget calculations
- [Incident Response](../INCIDENT_RESPONSE.md) -- Incident response procedures
