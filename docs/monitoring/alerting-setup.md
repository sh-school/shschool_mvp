# SchoolOS Alerting & Monitoring Setup

## Overview

SchoolOS uses a multi-layer monitoring approach:

| Layer | Tool | What it watches |
|-------|------|----------------|
| Post-deploy | `smoke-test.sh` | All endpoints after each deploy |
| Continuous | `monitor-cron.sh` | `/health/` every 5 minutes |
| Error tracking | Sentry | Exceptions, performance, errors |
| CI/CD | GitHub Actions | Scheduled smoke tests |

---

## 1. Slack Webhook Setup

### Create a Slack Incoming Webhook

1. Go to https://api.slack.com/apps and click **Create New App**
2. Choose **From scratch**, name it `SchoolOS Alerts`, select your workspace
3. Navigate to **Incoming Webhooks** and toggle **Activate**
4. Click **Add New Webhook to Workspace**
5. Select the channel (recommended: `#schoolos-alerts`)
6. Copy the webhook URL (format: `https://hooks.slack.com/services/T.../B.../xxx`)

### Discord Alternative

1. Open Discord channel settings > **Integrations** > **Webhooks**
2. Click **New Webhook**, name it `SchoolOS Alerts`
3. Copy the webhook URL
4. Append `/slack` to the URL for Slack-compatible payloads:
   ```
   https://discord.com/api/webhooks/1234567890/abcdef/slack
   ```

### Test the Webhook

```bash
# Quick test
curl -X POST -H "Content-Type: application/json" \
  -d '{"text":"SchoolOS alerting test -- if you see this, the webhook works."}' \
  YOUR_WEBHOOK_URL
```

---

## 2. Post-Deploy Smoke Test

Run `smoke-test.sh` after every Railway deploy:

```bash
# Basic usage (default Railway URL)
./scripts/smoke-test.sh

# Custom URL
./scripts/smoke-test.sh https://your-custom-domain.com

# With Slack/Discord notification
./scripts/smoke-test.sh --webhook https://hooks.slack.com/services/T.../B.../xxx

# With custom timeout
./scripts/smoke-test.sh --timeout 15 --webhook YOUR_WEBHOOK_URL
```

### What It Tests

| # | Endpoint | Expected | Validates |
|---|----------|----------|-----------|
| 1 | `/health/` | HTTP 200 | App is alive |
| 2 | `/ready/` | HTTP 200 | DB + dependencies ready |
| 3 | `/status/` | HTTP 200 + JSON | Status API works |
| 4 | `/` | HTTP 200 + login HTML | Frontend loads |
| 5 | `/admin/` | HTTP 200 or 302 | Admin accessible |

### Integration with Railway Deploy

Add to `scripts/railway-release.sh` (post-deploy hook):

```bash
# At the end of railway-release.sh:
if [ -n "${ALERT_WEBHOOK:-}" ]; then
    ./scripts/smoke-test.sh --webhook "$ALERT_WEBHOOK" || true
fi
```

Set `ALERT_WEBHOOK` as a Railway environment variable.

---

## 3. Cron Monitoring Setup

### Install on a Server (VPS, Raspberry Pi, etc.)

```bash
# 1. Copy the script
scp scripts/monitor-cron.sh user@monitor-server:/opt/schoolos/

# 2. Make executable
chmod +x /opt/schoolos/monitor-cron.sh

# 3. Set environment variables
export SCHOOLOS_URL="https://shschoolmvp-production.up.railway.app"
export SCHOOLOS_WEBHOOK="https://hooks.slack.com/services/T.../B.../xxx"

# 4. Add to crontab
crontab -e
```

Add this line to crontab:

```cron
*/5 * * * * SCHOOLOS_URL="https://shschoolmvp-production.up.railway.app" SCHOOLOS_WEBHOOK="https://hooks.slack.com/services/T.../B.../xxx" /opt/schoolos/monitor-cron.sh
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SCHOOLOS_URL` | Railway production URL | Base URL to monitor |
| `SCHOOLOS_WEBHOOK` | (none) | Slack/Discord webhook |
| `SCHOOLOS_LOG` | `/tmp/schoolos-monitor.log` | Log file location |
| `SCHOOLOS_THRESHOLD` | `3` | Failures before alerting (3 = 15 min) |

### Alert Behavior

- **3 consecutive failures** (15 min): First alert sent
- **6 consecutive failures** (30 min): Escalation alert sent
- **Recovery**: Recovery notification when service comes back
- Alerts are sent only at threshold boundaries (not every failure)

### Check Monitor Status

```bash
# View recent logs
tail -20 /tmp/schoolos-monitor.log

# Check current failure count
cat /tmp/schoolos-monitor-failures.count
```

---

## 4. GitHub Actions Monitoring

Create `.github/workflows/monitor.yml`:

```yaml
name: SchoolOS Health Monitor

on:
  schedule:
    # Every 15 minutes
    - cron: '*/15 * * * *'
  workflow_dispatch:

jobs:
  smoke-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run smoke test
        env:
          PRODUCTION_URL: ${{ vars.PRODUCTION_URL || 'https://shschoolmvp-production.up.railway.app' }}
          ALERT_WEBHOOK: ${{ secrets.ALERT_WEBHOOK }}
        run: |
          chmod +x scripts/smoke-test.sh
          if [ -n "$ALERT_WEBHOOK" ]; then
            ./scripts/smoke-test.sh "$PRODUCTION_URL" --webhook "$ALERT_WEBHOOK"
          else
            ./scripts/smoke-test.sh "$PRODUCTION_URL"
          fi

      - name: Notify on failure
        if: failure()
        uses: slackapi/slack-github-action@v1.25.0
        with:
          payload: |
            {
              "text": ":red_circle: *SchoolOS Smoke Test Failed*\nWorkflow: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}\nTime: ${{ github.event.head_commit.timestamp || 'scheduled' }}"
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.ALERT_WEBHOOK }}
```

### Required GitHub Secrets

| Secret | Value |
|--------|-------|
| `ALERT_WEBHOOK` | Slack/Discord webhook URL |

### Required GitHub Variables

| Variable | Value |
|----------|-------|
| `PRODUCTION_URL` | Production URL (optional, has default) |

---

## 5. Sentry Alert Rules

### Recommended Alert Rules

Configure these in Sentry under **Alerts > Create Alert Rule**:

#### Rule 1: High Error Rate

- **Condition**: Number of events > 10 in 5 minutes
- **Filter**: `level:error`
- **Action**: Send Slack notification to `#schoolos-alerts`
- **Frequency**: Alert at most once every 30 minutes

#### Rule 2: New Issue Detected

- **Condition**: A new issue is created
- **Filter**: `level:error OR level:fatal`
- **Action**: Send Slack notification
- **Frequency**: Alert at most once every 10 minutes

#### Rule 3: P1 Performance Regression

- **Condition**: Transaction duration p95 > 2000ms for 5 minutes
- **Filter**: Transaction name matches `/api/*`
- **Action**: Send Slack notification
- **Frequency**: Alert at most once every 1 hour

#### Rule 4: Unhandled Exception Spike

- **Condition**: Number of events > 5 in 1 minute
- **Filter**: `mechanism.handled:false`
- **Action**: Send Slack notification + PagerDuty (if configured)
- **Frequency**: Alert at most once every 15 minutes

#### Rule 5: Health Check Failure (Sentry Uptime)

- **Condition**: Uptime check fails
- **URL**: `https://shschoolmvp-production.up.railway.app/health/`
- **Interval**: Every 1 minute
- **Action**: Send Slack notification

### Sentry Django SDK Configuration

Ensure `sentry_sdk` is configured in `shschool/settings/production.py`:

```python
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN", ""),
    integrations=[DjangoIntegration()],
    traces_sample_rate=0.1,       # 10% of transactions
    profiles_sample_rate=0.1,     # 10% profiling
    send_default_pii=False,       # GDPR compliance
    environment=os.environ.get("RAILWAY_ENVIRONMENT", "production"),
    release=os.environ.get("RAILWAY_GIT_COMMIT_SHA", "unknown"),
)
```

---

## 6. Escalation Matrix

### Severity Levels

| Level | Trigger | Response Time | Who |
|-------|---------|---------------|-----|
| **P0 - Critical** | Site completely down (all smoke tests fail) | 15 minutes | Lead Dev + DevOps |
| **P1 - High** | Core feature broken (login, admin, API) | 1 hour | Lead Dev |
| **P2 - Medium** | Non-critical feature broken, elevated errors | 4 hours | Assigned Dev |
| **P3 - Low** | Cosmetic issue, warning-level alerts | Next business day | Assigned Dev |

### Escalation Flow

```
Monitor detects failure
    |
    v
[0-15 min] Slack alert to #schoolos-alerts
    |
    v
[15-30 min] Escalation alert (auto, via monitor-cron.sh)
    |
    v
[30+ min] Manual escalation:
    - Check Railway dashboard: https://railway.app/dashboard
    - Check Railway logs: railway logs --tail
    - Check Sentry: https://sentry.io (look for new errors)
    - Rollback if needed: railway rollback
    |
    v
[Resolved] Recovery alert sent automatically
    |
    v
[Post-incident] Create postmortem in docs/postmortems/
```

### Key Contacts

| Role | Responsibility |
|------|---------------|
| **On-call Dev** | First responder, triage, quick fixes |
| **Lead Dev** | Escalation point, deploy decisions |
| **DevOps** | Infrastructure issues, Railway config |

### Runbook Quick Links

- [Incident Response](../INCIDENT_RESPONSE.md)
- [Deployment Signoff](../protocols/deployment-signoff.md)
- [Change Approval](../protocols/change-approval.md)

---

## 7. Quick Start Checklist

- [ ] Create Slack webhook and save URL
- [ ] Set `ALERT_WEBHOOK` in Railway environment variables
- [ ] Set `ALERT_WEBHOOK` in GitHub repository secrets
- [ ] Run `./scripts/smoke-test.sh --webhook YOUR_URL` to verify
- [ ] Set up cron monitoring on a separate server
- [ ] Configure Sentry alert rules (at least rules 1, 2, and 5)
- [ ] Add `monitor.yml` GitHub Actions workflow
- [ ] Test the full alert chain end-to-end
