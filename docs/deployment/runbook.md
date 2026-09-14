# SchoolOS Deployment Runbook

> Last updated: 2026-09-14 (القسم 4: التراجعُ الصادق ورمزُ Railway)
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
| 10 | Railway config | Missing `healthcheck: "/health/"` in `.railway/railway.ts` |

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
  |       (pytest + coverage: quality-gate.yml on the same push —
  |        removed from this pipeline 2026-09-13 as a duplicate)
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

لا ويب هوك بعد 2026-09-13 (`RAILWAY_DEPLOY_WEBHOOK` أُزيل). Railway ينشر من
تكامل GitHub بنفسه حين يصل الإيداعُ إلى `main`؛ وإن تعطّل GitHub فمن لوحة
Railway → الخدمة → Deployments → **Redeploy**، أو بـ`railway up` برمز
المشروع (القسم 4، الخيار د).

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

> محدَّث 2026-09-14. Railway ينشر من تكامل GitHub لحظةَ وصول إيداعٍ إلى `main`
> — لا من Actions. فالتراجعُ الصادق إمّا أن **يغيّر `main`** وإمّا أن يقع
> **من داخل Railway** (لوحةً أو CLI برمز). ولا ويب هوك: `RAILWAY_DEPLOY_WEBHOOK`
> أُزيل من `deploy-railway.yml` لأنّه مصدرُ نشرٍ ثانٍ مخبّأ.

### الخيار أ — `rollback.yml`: طلبُ دمجٍ يُعيد شجرةَ main (الافتراضيّ)

1. **Actions** → **Rollback — التراجعُ إلى commit سابق** → **Run workflow**
2. `commit_sha`: ما يُراد أن يخدمه الإنتاج (`git log --oneline main`)
3. `reason`: سببُ التراجع (يُكتب في طلب الدمج)
4. اتركه بلا `verify_only`

ما يفعله: يتحقّق أنّ الهدفَ سلفٌ لـ`main` وأنّ شجرته تخالف شجرةَ `main`،
ثمّ يُنشئ إيداعاً جديداً شجرتُه شجرةُ الهدف حرفيّاً (`git commit-tree` — لا
`git revert` لكلّ إيداعٍ على حدة، فذاك يتعثّر بإيداعات الدمج) على فرع
`rollback/<sha>-<run>`، ويفتح طلبَ دمجٍ يمرّ على البوّابات كأيّ طلب.
**التراجعُ لا يقع قبل دمجه.** بعد الدمج ينشر Railway تلقائيّاً، وكناري
`deploy-railway.yml` يُثبت أنّ إيداعَ الدمج صار حيّاً.

- إن لم تبدأ الفحوصُ على الطلب (طلبٌ يفتحه `GITHUB_TOKEN` لا يُطلق سيرَ عملٍ
  آخر): `gh pr close <n>` ثمّ `gh pr reopen <n>`.
- **الهجراتُ لا تُتراجَع**: راجع `git diff <sha>..main -- '*/migrations/*'`
  قبل الدمج (القسم 5).

### الخيار ب — لوحة Railway (حين يكون GitHub نفسُه هو العطب)

1. Railway → المشروع → الخدمة `shschool_mvp` → **Deployments**
2. النشرُ السابق السليم → ⋯ → **Rollback**
3. وكرّر للعامل `celery-worker` وBeat `celery-beat` إن كان التغييرُ يمسّهما
4. ثمّ تحقّق: `gh workflow run rollback.yml -f commit_sha=<sha> -f verify_only=true`

### الخيار ج — التحقّق وحدَه

```bash
gh workflow run rollback.yml -f commit_sha=<sha> -f verify_only=true
```

يقارن `commit` الذي يخدمه `/health/` بالهدف — 18 محاولة على 12 دقيقة — ويفشل
بصوتٍ عالٍ إن خالفه.

### الخيار د — تراجعٌ من سطر الأوامر برمز Railway (يحتاج المالك)

CLI Railway **لا يملك أمرَ تراجعٍ إلى نشرٍ سابق بعينه**: `railway redeploy`
يُعيد بناءَ آخر نشر، و`railway restart` يُعيد تشغيله بلا بناء، والتراجعُ إلى
نشرٍ أقدم من اللوحة وحدَها (وثائق Railway، «Roll Back a Bad Deploy»). لكنّ
`railway up` ينشر **شجرةَ العمل الحاليّة** كما هي — فالتراجعُ إلى أيّ SHA
يصير: `git checkout <sha>` ثمّ `railway up --service <الخدمة> --detach`.
وذلك يحتاج رمزاً لا يملكه المستودع اليوم (`gh secret list` يوم 2026-09-14:
لا `RAILWAY_TOKEN` في أسرار المستودع ولا في بيئة `production`).

**إنشاءُ الرمز (بيد المالك — لا يستطيعه وكيلٌ ولا CI):**

1. Railway → المشروع `shschool_mvp` → **Settings** → **Tokens** →
   **Create Token**. اختر **Project Token** لا Account Token: رمزُ المشروع
   محصورٌ في بيئةٍ واحدة (`production`) ولا يفعل إلّا ما يخصّ النشر —
   إن سُرّب لا يمسّ حساب المالك ولا مشاريعَه الأخرى.
2. انسخ الرمزَ مرّةً واحدة (لا يُعرض ثانية) وضعه في GitHub **بيئةِ**
   `production` لا في أسرار المستودع العامّة — فلا يبلغه سيرُ عملٍ يعمل على
   طلب دمجٍ من فرعٍ غريب:
   ```bash
   gh secret set RAILWAY_TOKEN --env production
   ```
3. تحقّق: `gh secret list --env production` يُظهر `RAILWAY_TOKEN` بلا قيمة.
4. سجّل في هذا الملفّ تاريخَ الإنشاء واسمَ الرمز في Railway، ودوّره كلَّ
   90 يوماً كسائر أسرار الكادر (سياسة التدوير).

**ربطُه بـ`rollback.yml` (يُنفَّذ بعد الرمز لا قبله — الـworkflow اليوم كما هو):**

تُضاف وظيفةٌ ثالثة `railway-up` تعمل بـ`environment: production` (فتقرأ السرَّ
منها) عند مدخلٍ جديد `via_cli=true`:

```yaml
  railway-up:
    if: ${{ inputs.via_cli }}
    runs-on: ubuntu-latest
    environment: production
    timeout-minutes: 20
    env:
      RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
    steps:
      - uses: actions/checkout@v4
        with: { ref: "${{ inputs.commit_sha }}", fetch-depth: 1 }
      - run: npm i -g @railway/cli
      - run: railway up --service shschool_mvp --environment production --detach
      - run: railway up --service celery-worker --environment production --detach
      - run: railway up --service celery-beat --environment production --detach
```

ثمّ وظيفةُ `verify` بعدها بالـSHA نفسِه (تُشغَّل بـ`needs: railway-up`) —
فلا يُطبع PASS إلّا إن خدم `/health/` الهدفَ فعلاً. ويبقى الخيار أ هو
المسارَ الموثّق في التاريخ: `railway up` ينشر شجرةً **لا تُطابق `main`**،
فبعد إطفاء الحريق يُفتح طلبُ تراجعٍ (الخيار أ) أو يُصلَح `main` — وإلّا عاد
النشرُ التالي من GitHub إلى الشيفرة المعطوبة.

**بديلٌ للتحقّق لاحقاً:** واجهةُ GraphQL العامّة لـRailway تحمل تحويلاً
`deploymentRollback(id)` يُعيد نشراً سابقاً بعينه بلا بناء — وهو ما تفعله
اللوحة. لم يُختبر هنا؛ إن ثبت مع رمز المشروع فهو أدقّ من `railway up`
(النشرُ نفسُه لا إعادةُ بنائه).

### Option E: Git revert (for non-emergency)

```bash
# Revert the problematic commit
git revert -m 1 <bad-merge-sha>   # -m 1 for a merge commit
git push origin HEAD:refs/heads/claude/revert-<sha>
# open a PR — the gates run, main deploys on merge
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
`.railway/railway.ts` (timeout: 100s) handles this. If it persists:
1. Increase `healthcheckTimeout` in `.railway/railway.ts`, then `railway config plan` / `apply`
2. Ensure `/health/` responds quickly (no DB queries in health view)

### Issue: Redis connection refused

**Cause:** Redis plugin not provisioned or `REDIS_URL` not set.
**Fix:**
1. Check Railway dashboard for Redis plugin status
2. Verify `REDIS_URL` environment variable: `railway variables | grep REDIS`
3. If using Redis for caching only, the app should degrade gracefully
   (check `CACHES` setting has a fallback)

### Issue: Rollback workflow fails at "التحقّق من الهدف"

**Cause:** the SHA is unknown, is not an ancestor of `main` (a branch commit or
a force-pushed one), or its tree already equals `main`'s tree.
**Fix:**
1. `git log --oneline main` — pick a commit that was on `main`
2. Or roll back from the Railway dashboard (Section 4, Option ب), then verify
   with `verify_only=true`

### Issue: Worker/Beat logs show only the banner in `railway logs`

**Cause (fixed 2026-09-14):** Celery hijacked the root logger on start-up and
emptied the `celery` logger's handlers; with `propagate: False` in
`production.py` its INFO lines went nowhere. `shschool/celery.py` now
receives the `setup_logging` signal, which stops the hijack and keeps
Django's `LOGGING` (with the `pii_masking` filter) in charge.
**Check:** `railway logs --service celery-worker` should show
`Task … received` / `succeeded`, and `--service celery-beat` should show
`Scheduler: Sending due task …`. Guard: `tests/test_celery_logs_reach_stdout.py`.
