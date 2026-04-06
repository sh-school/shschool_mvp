# SchoolOS Deployment Runbook

> Last updated: 2026-04-06
> Production URL: `https://shschoolmvp-production.up.railway.app`
> Platform: Railway (Hobby plan)

---

## Table of Contents

1. [Pre-Deploy Checklist](#1-pre-deploy-checklist)
2. [Deploy Steps](#2-deploy-steps)
3. [Post-Deploy Verification](#3-post-deploy-verification)
4. [Rollback Procedure](#4-rollback-procedure)
5. [Database Migration Rollback](#5-database-migration-rollback)
6. [Emergency Procedures](#6-emergency-procedures)
7. [Contact List](#7-contact-list)
8. [Common Issues and Fixes](#8-common-issues-and-fixes)

---

## 1. Pre-Deploy Checklist

Run the preflight script locally before pushing to main:

```bash
./scripts/deploy-preflight.sh
```

This validates 10 checks:

| # | Check | What it catches |
|---|-------|-----------------|
| 1 | Dependencies | Missing packages in requirements.txt |
| 2 | Gunicorn config | Wrong bind address, missing worker_class |
| 3 | Gunicorn boot | Import errors, WSGI misconfiguration |
| 4 | Health endpoint | /health/ not returning 200 |
| 5 | Superuser exists | No admin access after deploy |
| 6 | DATABASE_URL | Missing or malformed connection string |
| 7 | Static files | collectstatic errors (broken references) |
| 8 | Migrations | Unapplied or inconsistent migrations |
| 9 | Security settings | Missing SECURE_PROXY_SSL_HEADER |
| 10 | Railway config | Missing healthcheckPath in railway.json |

**Do not deploy if any check FAILs.** Warnings are acceptable but should be
reviewed.

### Additional manual checks:

- [ ] All tests pass locally: `pytest tests/ -v`
- [ ] No untracked migration files: `git status`
- [ ] PR has been reviewed and approved (if applicable)
- [ ] For high-risk changes: canary deploy completed (see canary-strategy.md)

---

## 2. Deploy Steps

SchoolOS uses a webhook-triggered deploy pipeline. Pushing to `main` triggers
the full CI/CD sequence automatically.

### Automatic flow (push to main):

```
git push origin main
  |
  v
GitHub Actions: deploy-railway.yml
  |
  ├── Job 1: preflight (CI subset of deploy-preflight.sh)
  ├── Job 2: test (pytest + coverage)
  |       (both run in parallel)
  v
  ├── Job 3: deploy (Railway webhook POST)
  |       -> Railway builds Docker image
  |       -> Railway runs scripts/railway-release.sh
  |       -> Railway health check on /health/
  |       -> 60s stabilization wait
  v
  └── Job 4: smoke-test
          -> /health/ HTTP 200 (5 retries, 15s apart)
          -> / returns HTML
```

### Manual deploy (if CI is broken):

```bash
# Only use in emergencies when CI is down
curl -X POST "$RAILWAY_DEPLOY_WEBHOOK"
```

### Monitoring the deploy:

1. **GitHub Actions:** Check the workflow run at
   `https://github.com/<org>/shschool_mvp/actions`
2. **Railway dashboard:** Watch build logs at
   `https://railway.app/project/<project-id>`
3. **Railway CLI:** `railway logs` for real-time log streaming

---

## 3. Post-Deploy Verification

### Automated (runs in CI):

The `smoke-test` job in `deploy-railway.yml` checks:
- `/health/` returns HTTP 200
- `/` returns HTML content

### Manual verification:

Run the full smoke test script:

```bash
./scripts/smoke-test.sh
# or against a specific URL:
./scripts/smoke-test.sh https://shschoolmvp-production.up.railway.app
```

This checks 5 endpoints:

| # | Endpoint | Expected |
|---|----------|----------|
| 1 | /health/ | HTTP 200 |
| 2 | /ready/ | HTTP 200 |
| 3 | /status/ | HTTP 200 + valid JSON |
| 4 | / | HTTP 200 + contains "login" |
| 5 | /admin/ | HTTP 200 or 302 |

### With Slack/Discord notification:

```bash
./scripts/smoke-test.sh --webhook https://hooks.slack.com/services/XXX/YYY/ZZZ
```

### Additional post-deploy checks:

- [ ] Log in as a test user and verify core workflow
- [ ] Check Sentry for new errors (first 15 minutes)
- [ ] Verify Railway resource usage is normal (memory, CPU)

---

## 4. Rollback Procedure

### Option A: GitHub Actions workflow (preferred)

1. Go to **Actions** -> **Rollback -- Railway Emergency Rollback**
2. Click **Run workflow**
3. Enter the commit SHA to roll back to (find it with `git log --oneline`)
4. Enter the reason for rollback
5. Click **Run workflow**

The rollback workflow (`rollback.yml`):
- Validates the target commit exists
- Checks out that commit
- Triggers Railway deploy webhook
- Waits 60s for stabilization
- Runs post-rollback smoke tests
- Reports results in the workflow summary

### Option B: Railway dashboard

1. Open Railway dashboard -> project -> service
2. Click **Deployments** tab
3. Find the last known-good deployment
4. Click the three-dot menu -> **Redeploy**

### Option C: Git revert (for non-emergency)

```bash
# Revert the problematic commit
git revert <bad-commit-sha>
git push origin main
# This triggers the normal CI/CD pipeline
```

### Rollback decision criteria:

| Signal | Action |
|--------|--------|
| /health/ returns non-200 | Rollback immediately |
| Error rate spikes >5% in Sentry | Rollback immediately |
| Slow responses (p95 > 5s) | Investigate, rollback if not resolved in 10 min |
| Single user report | Investigate, do not rollback yet |
| Data corruption suspected | Rollback immediately + page on-call |

---

## 5. Database Migration Rollback

Django migrations are the riskiest part of any deploy. Follow these steps
carefully.

### Before deploying migrations:

1. **Review the migration SQL:**
   ```bash
   python manage.py sqlmigrate <app_label> <migration_number>
   ```

2. **Check if the migration is reversible:**
   ```bash
   python manage.py migrate <app_label> <previous_migration> --plan
   ```
   If it says "irreversible," you need a manual rollback plan.

3. **For destructive migrations** (column drop, table drop, data transform):
   - Back up the database first (Railway Postgres -> Backups tab)
   - Test on a staging database copy
   - Deploy during low-traffic hours

### Rolling back a migration:

```bash
# Via Railway CLI (connects to production DB):
railway run python manage.py migrate <app_label> <previous_migration_number>

# Example: roll back app "students" to migration 0005
railway run python manage.py migrate students 0005
```

### If the migration is irreversible:

1. **Restore from backup:**
   - Railway dashboard -> Postgres plugin -> Backups
   - Select the backup taken before the deploy
   - Restore to a new database instance
   - Update DATABASE_URL to point to the restored instance

2. **Manual SQL fix:**
   ```bash
   railway run python manage.py dbshell
   # Then manually undo the schema changes
   ```

### Migration safety rules:

| Migration type | Safe to auto-run? | Rollback complexity |
|----------------|-------------------|-------------------|
| Add column (nullable) | Yes | Low - drop column |
| Add column (non-null + default) | Yes | Low - drop column |
| Add index | Yes | Low - drop index |
| Add table | Yes | Low - drop table |
| Remove column | NO - canary first | High - restore from backup |
| Remove table | NO - canary first | High - restore from backup |
| Rename column/table | NO - canary first | Medium - rename back |
| Data migration (RunPython) | Depends | Varies - write reverse |
| Alter column type | NO - canary first | High - may lose data |

---

## 6. Emergency Procedures

### Production is completely down

1. **Check Railway status:** https://status.railway.app
2. **Check deploy logs:** Railway dashboard -> Deployments -> latest -> logs
3. **If Railway is healthy but app is down:**
   ```bash
   # Check if the health check is timing out
   curl -v --max-time 30 https://shschoolmvp-production.up.railway.app/health/
   ```
4. **Rollback to last known-good commit** (see Section 4)
5. **If rollback also fails:** contact Railway support and check if the
   database is accessible

### Database connection errors

1. **Check Railway Postgres plugin status** in the dashboard
2. **Verify DATABASE_URL** is set correctly:
   ```bash
   railway variables
   ```
3. **Check connection limit:**
   ```sql
   -- Via railway run python manage.py dbshell
   SELECT count(*) FROM pg_stat_activity;
   SELECT max_conn FROM pg_settings WHERE name = 'max_connections';
   ```
4. **If max connections reached:** restart the app (Railway dashboard ->
   Restart) to clear stale connections

### Memory/CPU exhaustion

1. **Check Railway metrics** in the dashboard (Memory, CPU graphs)
2. **Common causes:**
   - Gunicorn workers too many: check `gunicorn.conf.py` workers count
   - Memory leak in a view: check Sentry for OOM events
   - Large queryset loaded into memory: add `.iterator()` or pagination
3. **Immediate fix:** Railway dashboard -> Restart service
4. **Long-term fix:** reduce workers, add `--max-requests` to gunicorn

### Static files returning 404

1. **Verify collectstatic ran during deploy:**
   ```bash
   # Check railway-release.sh includes collectstatic
   cat scripts/railway-release.sh
   ```
2. **Check STATIC_URL and STATIC_ROOT** in production settings
3. **Verify whitenoise is in MIDDLEWARE** (should be second, after
   SecurityMiddleware)
4. **Manual fix:**
   ```bash
   railway run python manage.py collectstatic --noinput
   ```

---

## 7. Contact List

| Role | Contact | When to page |
|------|---------|--------------|
| On-call engineer | (update with team contact) | Any production incident |
| Project lead | (update with lead contact) | Rollback needed or data loss |
| Railway support | https://help.railway.app | Platform-level issues |
| Database admin | (update with DBA contact) | Migration rollback or data corruption |

**Escalation timeline:**
- 0-5 min: On-call engineer investigates
- 5-15 min: If not resolved, rollback and notify project lead
- 15-30 min: If rollback fails, contact Railway support
- 30+ min: All-hands incident response

---

## 8. Common Issues and Fixes

### Issue: Railway build fails with "no matching manifest for linux/amd64"

**Cause:** Base image in Dockerfile does not support the target platform.
**Fix:** Ensure Dockerfile uses a standard base image:
```dockerfile
FROM python:3.12-slim
```

### Issue: Deploy succeeds but /health/ returns 503

**Cause:** Gunicorn workers are crashing during startup (import error, missing
env var).
**Fix:**
1. Check Railway deploy logs for tracebacks
2. Verify all required environment variables are set: `railway variables`
3. Common missing vars: `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`

### Issue: "DisallowedHost" error after deploy

**Cause:** `ALLOWED_HOSTS` does not include the Railway domain.
**Fix:** Add `shschoolmvp-production.up.railway.app` to `ALLOWED_HOSTS` in
production settings, or use:
```python
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")
```

### Issue: Static files missing (CSS broken, images 404)

**Cause:** `collectstatic` did not run, or whitenoise is misconfigured.
**Fix:**
1. Ensure `scripts/railway-release.sh` runs `python manage.py collectstatic --noinput`
2. Ensure `whitenoise.middleware.WhiteNoiseMiddleware` is in MIDDLEWARE
3. Run manually: `railway run python manage.py collectstatic --noinput`

### Issue: Migration timeout during deploy

**Cause:** A data migration is running on a large table and exceeds Railway's
build timeout.
**Fix:**
1. Run the migration manually before deploying the code:
   ```bash
   railway run python manage.py migrate <app_label>
   ```
2. For very large data migrations, batch the operation in the RunPython
   function

### Issue: 502 Bad Gateway intermittently after deploy

**Cause:** Railway is routing to the old container while the new one is still
starting.
**Fix:** This is expected for a few seconds during deploy. The healthcheck in
`railway.json` (timeout: 100s) handles this. If it persists:
1. Increase `healthcheckTimeout` in `railway.json`
2. Ensure `/health/` responds quickly (no DB queries in health view)

### Issue: Redis connection refused

**Cause:** Redis plugin not provisioned or `REDIS_URL` not set.
**Fix:**
1. Check Railway dashboard for Redis plugin status
2. Verify `REDIS_URL` environment variable: `railway variables | grep REDIS`
3. If using Redis for caching only, the app should degrade gracefully
   (check `CACHES` setting has a fallback)

### Issue: Rollback workflow fails at "Validate commit SHA"

**Cause:** The commit SHA was not found -- it may have been from a squashed
merge or force-push.
**Fix:**
1. Use `git log --all --oneline` to find the correct SHA
2. Alternatively, use Railway dashboard to redeploy a previous deployment
   (see Section 4, Option B)
