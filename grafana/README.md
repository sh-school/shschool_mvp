# SchoolOS Grafana Cloud Setup

## Quick Start

### 1. Grafana Cloud Instance
- **URL**: https://mesuef1974.grafana.net
- **Org**: mesuef1974

### 2. Import Dashboard
1. Open Grafana → Dashboards → Import
2. Upload `schoolos-dashboard.json`
3. Select your Prometheus data source
4. Click Import

### 3. Connect Prometheus Data Source
SchoolOS exposes metrics at `/metrics` via `django-prometheus`.

**Production URL**: `https://shschoolmvp-production.up.railway.app/metrics`

To scrape metrics into Grafana Cloud Prometheus:
1. Go to Connections → Data Sources → Add Prometheus
2. Set URL to Grafana Cloud Prometheus endpoint
3. Use Grafana Alloy agent or remote_write to push metrics

### 4. Dashboard Panels
| Panel | Metric | SLO Target |
|-------|--------|------------|
| Request Rate | django_http_requests_total | - |
| Response Time p95 | django_http_requests_latency_seconds | < 500ms |
| Error Rate (5xx) | django_http_responses_total | < 0.1% |
| Availability | Calculated from 5xx rate | 99.9% |
| DB Connections | django_db_backends_active | - |
| Cache Hit Rate | django_cache_hits/misses | > 90% |
| Migrations | django_migrations_unapplied | 0 |

### 5. Alerting Rules
Configure in Grafana → Alerts & IRM:
- **P1**: Error rate > 1% for 5min → Slack + Email
- **P2**: p95 latency > 500ms for 10min → Slack
- **P3**: Cache hit rate < 70% for 30min → Email
