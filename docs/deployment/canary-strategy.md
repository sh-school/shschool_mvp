# SchoolOS Canary / Progressive Deployment Strategy

> Last updated: 2026-04-06

## Overview

Railway does not natively support traffic-splitting canary deployments (as of
2026-Q2). This document defines a three-phase progressive deployment strategy
that works within Railway's capabilities today and evolves as the platform adds
features.

---

## Phase 1 — Deploy + Smoke + Rollback (Current)

This is the strategy already implemented in `deploy-railway.yml`.

```
push main
  -> CI preflight (10 checks)
  -> pytest suite
  -> Railway webhook deploy
  -> 60 s stabilization wait
  -> smoke tests (/health/, / HTML)
  -> FAIL? -> manual rollback via rollback.yml
```

**Canary surface:** the smoke-test job acts as a "canary gate." If it fails,
the deploy is flagged and the on-call engineer triggers `rollback.yml` from
the Actions tab.

**Limitations:**
- All traffic hits the new version immediately after Railway finishes building.
- No preview URL before production traffic is routed.
- Rollback is manual (requires someone to trigger the workflow).

---

## Phase 2 — Railway PR Environments (Next)

Railway supports **PR environments**: ephemeral deployments triggered by pull
requests. Each PR gets its own isolated URL with the same environment variables
(database can be shared read-only or use a staging DB).

### Setup

1. **Enable PR Deploys in Railway dashboard:**
   - Project Settings -> Environments -> Enable "PR Deploys"
   - Each PR automatically gets `https://<service>-pr-<number>.up.railway.app`

2. **Add a `railway.pr.json`** (optional override for PR environments):

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "Dockerfile"
  },
  "deploy": {
    "startCommand": "bash scripts/railway-release.sh",
    "healthcheckPath": "/health/",
    "healthcheckTimeout": 100,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

3. **Environment variables for PR environments:**
   - `DATABASE_URL` -> point to a staging/read-only replica, NOT production
   - `DJANGO_SETTINGS_MODULE` -> `shschool.settings.staging` (create if needed)
   - `ALLOWED_HOSTS` -> `*.up.railway.app`

4. **Manual QA on PR URL:**
   - Reviewer opens the PR environment URL
   - Runs `scripts/smoke-test.sh <PR_URL>` locally
   - Approves PR only after verifying on the preview environment

### Workflow Addition

Add a comment bot or status check that posts the PR environment URL on each PR:

```yaml
# .github/workflows/pr-preview-comment.yml (future)
name: PR Preview URL
on:
  pull_request:
    types: [opened, synchronize]
jobs:
  comment:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/github-script@v7
        with:
          script: |
            const prNumber = context.payload.pull_request.number;
            const url = `https://shschoolmvp-pr-${prNumber}.up.railway.app`;
            await github.rest.issues.createComment({
              ...context.repo,
              issue_number: prNumber,
              body: `Preview environment: ${url}\n\nRun smoke test: \`./scripts/smoke-test.sh ${url}\``
            });
```

---

## Phase 3 — Traffic Splitting (Future)

When Railway (or an external load balancer / Cloudflare Workers) supports
weighted traffic routing:

```
                    ┌─── 95% ──→ [current production]
  Cloudflare/LB ───┤
                    └───  5% ──→ [canary (new version)]
```

### Implementation options (when available):

| Option | How | Pros | Cons |
|--------|-----|------|------|
| Railway native | Railway weighted routing (not yet available) | Zero config | Waiting on Railway |
| Cloudflare Workers | Route X% of requests to canary service URL | Full control | Extra infra cost |
| Application-level | Django middleware checks cookie/header, routes to canary logic | No infra changes | Complex, risky |

### Canary metrics to monitor:
- Error rate (5xx) on canary vs stable
- Response time p95 on canary vs stable
- Database query count per request
- Sentry error volume

### Promotion criteria:
1. Canary runs for >= 15 minutes
2. Error rate delta < 0.5% vs stable
3. p95 latency delta < 200ms vs stable
4. Zero critical Sentry alerts
5. Manual approval from on-call engineer

---

## Manual Canary Process Using Railway CLI

For high-risk deploys (schema migrations, large refactors), use this manual
process before merging to main:

```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login and link project
railway login
railway link

# 3. Create a temporary canary service
railway service create schoolos-canary

# 4. Deploy the branch to the canary service
railway up --service schoolos-canary

# 5. Run smoke tests against canary URL
./scripts/smoke-test.sh https://schoolos-canary-production.up.railway.app

# 6. Monitor logs for 10-15 minutes
railway logs --service schoolos-canary

# 7. If satisfied, merge to main (triggers normal deploy pipeline)
# 8. Tear down canary
railway service delete schoolos-canary
```

---

## Decision Matrix: Canary vs Full Deploy

| Change Type | Risk | Strategy | Notes |
|-------------|------|----------|-------|
| CSS/template only | Low | Full deploy | Smoke test is sufficient |
| New feature (no migration) | Low-Med | Full deploy | Feature flag recommended |
| Bug fix (no migration) | Low | Full deploy | Fast-track acceptable |
| New Django migration (additive) | Medium | PR environment first | Test migration on staging DB |
| Migration with data transform | High | Manual canary (CLI) | Test with production data copy |
| Dependency upgrade (major) | High | Manual canary (CLI) | Watch for import errors |
| Settings/env var change | Medium | PR environment first | Verify env vars load correctly |
| Gunicorn/infrastructure change | High | Manual canary (CLI) | Watch boot logs carefully |
| Emergency hotfix | Critical | Full deploy + immediate monitoring | Use rollback.yml if it fails |

---

## References

- `deploy-railway.yml` — current CI/CD pipeline
- `rollback.yml` — emergency rollback workflow
- `scripts/deploy-preflight.sh` — pre-deploy validation (10 checks)
- `scripts/smoke-test.sh` — post-deploy verification (5 checks)
- `railway.json` — Railway service configuration
