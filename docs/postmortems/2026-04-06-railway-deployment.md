# Postmortem: SchoolOS Railway Deployment Crisis

**Date:** 2026-04-06
**Author:** Engineering Team
**Status:** Final
**Severity:** P1 -- Production Blocked

---

## Incident Summary

| Field | Detail |
|-------|--------|
| **Duration** | ~5+ hours (2026-04-05 evening through 2026-04-06) |
| **Impact** | Production deployment completely blocked. CEO frustrated to the point of near-cancellation of the Railway approach. Zero users could access the system for the entire window. |
| **Severity** | P1 -- Production deployment blocked, stakeholder trust damaged |
| **Detection** | Manual -- engineer watching deploy logs |
| **Resolution** | Series of 5+ hotfix commits over multiple hours |
| **Commits involved** | 5ad0aaf, d952a5d, 308c0c5, 0688615, ded0a04 |

---

## Timeline

All times approximate. Reconstructed from commit history and deploy logs.

| Time | Event | Severity |
|------|-------|----------|
| T+0:00 | Initial deploy attempt to Railway. gunicorn starts silently, then dies. No error in Railway dashboard -- just "deploy failed." | Critical |
| T+0:30 | **Root cause #1 found:** `gunicorn.conf.py` has `worker_class = "uvicorn.workers.UvicornWorker"` but uvicorn is not in requirements. `ModuleNotFoundError` kills the process. Railway shows no useful error because gunicorn swallows it on startup. | Critical |
| T+0:45 | **Fix deployed:** `--worker-class sync` added to `railway-release.sh` (commit `5ad0aaf`). Bypass the broken config file. | |
| T+1:00 | Build failed on commit `d952a5d`. Wasted cycle. | High |
| T+1:30 | Deploy succeeds but Railway healthcheck fails. App returning **301 redirect** instead of **200 OK** on the health endpoint. | Critical |
| T+1:45 | **Root cause #2 found:** `SECURE_SSL_REDIRECT = True` in production settings. Railway's internal healthcheck probe hits the app over HTTP. Django redirects it to HTTPS. Railway sees 301, marks the deploy as unhealthy, kills it. | Critical |
| T+2:00 | **Fix deployed:** Added `SECURE_PROXY_SSL_HEADER` and `SECURE_REDIRECT_EXEMPT` for the `/health/` path (commit `308c0c5`). Healthcheck now returns 200. | |
| T+2:15 | Deploy succeeds. `/health/` returns 200. `/` returns the login page. First moment of hope. | |
| T+2:30 | **Login fails.** Team attempts to log in using email address. SchoolOS uses `national_id` as the username field. Nobody remembered this. | High |
| T+2:45 | Multiple failed login attempts trigger **django-axes** account lockout. Now even the correct credentials are blocked. | Critical |
| T+3:00 | **Fix deployed:** Added `RESET_AXES` environment variable logic to `railway-release.sh` so axes lockouts can be cleared on deploy (commit `0688615`). | |
| T+3:30 | Login works but the database is **completely empty**. No students, no teachers, no courses. Nobody planned the data migration from the local/staging database to Railway's Postgres. | Critical |
| T+4:00 | **Final config fix:** `gunicorn.conf.py` fully rewritten -- sync worker, reads `$PORT` from environment, stdout logging (commit `ded0a04`). This replaces the earlier workaround. | |
| T+4:30 | `pg_dump` from source database, `pg_restore` to Railway Postgres. Password reset for admin account. | |
| T+5:00 | **Incident resolved.** App is live, login works, data is present. | |

---

## Root Cause Analysis

### Root Cause #1: gunicorn.conf.py with UvicornWorker

**5 Whys:**

1. **Why did gunicorn die on startup?** -- It tried to import `uvicorn.workers.UvicornWorker`, which raised `ModuleNotFoundError`.
2. **Why was UvicornWorker configured?** -- The `gunicorn.conf.py` was copied from an ASGI project template or tutorial without adapting it to our WSGI Django app.
3. **Why wasn't uvicorn in requirements?** -- Because we don't use ASGI. The config file was wrong, not the requirements.
4. **Why wasn't this caught before deploy?** -- Nobody ran `gunicorn` locally with the production config. Local dev uses `manage.py runserver`.
5. **Why is there no pre-deploy smoke test?** -- There is no deployment checklist or CI pipeline that validates the production entrypoint.

### Root Cause #2: SECURE_SSL_REDIRECT without healthcheck exemption

**5 Whys:**

1. **Why did the healthcheck return 301?** -- `SECURE_SSL_REDIRECT = True` redirects all HTTP requests to HTTPS.
2. **Why does Railway's healthcheck use HTTP?** -- Railway probes the container internally over HTTP on the bound port. This is standard PaaS behavior.
3. **Why didn't we exempt the health endpoint?** -- We didn't know Railway's probe behavior. We assumed HTTPS end-to-end.
4. **Why didn't we test the healthcheck?** -- No staging environment on Railway. First deploy was directly to production.
5. **Why no staging environment?** -- Budget constraints ($5 Hobby plan) and time pressure. "Just ship it."

### Root Cause #3: Hardcoded port 8000 instead of $PORT

**5 Whys:**

1. **Why was gunicorn binding to port 8000?** -- The `gunicorn.conf.py` had `bind = "0.0.0.0:8000"` hardcoded.
2. **Why does Railway need a different port?** -- Railway dynamically assigns a port via the `$PORT` environment variable. This is standard PaaS behavior.
3. **Why was 8000 hardcoded?** -- Copy-pasted config from local development setup.
4. **Why wasn't this caught?** -- Same answer as above: no pre-deploy validation, no staging.
5. **Why don't we have a PaaS deployment reference?** -- We had never deployed to a PaaS before. All prior deployments were VPS with fixed ports.

### Root Cause #4: No data migration plan

**5 Whys:**

1. **Why was the production database empty?** -- Railway provisioned a fresh Postgres instance. Nobody migrated data into it.
2. **Why wasn't data migration part of the deploy plan?** -- There was no deploy plan. The "plan" was "push to Railway and see what happens."
3. **Why no deploy plan?** -- Time pressure from CEO. Sprint deadline. "Just get it live."
4. **Why didn't the team push back on the timeline?** -- Lack of experience estimating deployment complexity. Assumed it would be a 30-minute task.
5. **Why was deployment complexity underestimated?** -- First PaaS deployment. Team had no mental model for what could go wrong.

### Root Cause #5: Wrong login credentials (email vs national_id)

**5 Whys:**

1. **Why did login fail?** -- Team used email addresses. SchoolOS authenticates via `national_id`.
2. **Why didn't anyone know the correct field?** -- The person deploying was not the person who built the auth system. No documentation.
3. **Why no documentation?** -- Auth was built in a rush during an earlier sprint. "We'll document it later."
4. **Why did axes lock the account?** -- Multiple rapid failed attempts with wrong username format. Axes did exactly what it's supposed to do.
5. **Why was there no way to unlock without a code deploy?** -- No admin backdoor, no management command exposed, no Railway-friendly reset mechanism.

---

## What Went Well

- **Persistence.** The team did not give up despite 5+ hours of cascading failures. Every problem was eventually solved.
- **Each fix was committed individually.** Clean commit history makes this postmortem possible.
- **The health endpoint existed.** At least someone had the foresight to create `/health/`. Without it, debugging the 301 issue would have been much harder.
- **pg_dump/pg_restore worked first try.** The data migration, once someone thought to do it, was clean.

## What Went Wrong

- **No deployment checklist.** Not even a basic one. We went in blind.
- **No staging environment.** First deploy was production. Every mistake was visible to stakeholders.
- **Cargo-culted configuration.** `gunicorn.conf.py` was copied from an unrelated project and never reviewed. It contained UvicornWorker (wrong), hardcoded port (wrong), and no stdout logging (wrong).
- **Zero PaaS knowledge.** The team had never deployed to Railway before and did not read Railway's documentation on healthchecks, port binding, or proxy headers.
- **No data migration in the plan.** This is embarrassing. Deploying an app with an empty database is not deploying an app.
- **Authentication field not documented.** The `national_id` login requirement was tribal knowledge locked in one developer's head.
- **CEO was in the room.** Debugging under executive pressure made every minute feel like ten. Bad decisions were made faster. Testing was skipped to "just try it."
- **django-axes had no emergency override.** A security feature became a deployment blocker because there was no break-glass procedure.

## Where We Got Lucky

- **Railway's $5 Hobby plan didn't run out of build minutes.** We burned through many deploys. On a metered plan, we could have been blocked by billing.
- **The database dump was available.** If the source database had been lost or corrupted, we would have had nothing to restore.
- **No real users were waiting.** This was a first deploy, not a production outage affecting students and teachers. If this had happened with live users, it would have been a disaster, not just an embarrassment.
- **CEO didn't actually cancel.** It was close. The frustration was real and justified.

---

## Action Items

| # | Action | Owner | Deadline | Status |
|---|--------|-------|----------|--------|
| 1 | Create a Railway/PaaS deployment checklist covering: port binding, healthcheck, SSL settings, worker class, data migration, credentials | Engineering Lead | 2026-04-08 | TODO |
| 2 | Add `gunicorn.conf.py` validation to CI -- verify worker class is importable, port reads from `$PORT` | DevOps | 2026-04-10 | TODO |
| 3 | Create a staging environment on Railway (even a free-tier one) for pre-production validation | Engineering Lead | 2026-04-12 | TODO |
| 4 | Document all authentication flows: what field is the username, what lockout policies exist, how to reset | Auth Developer | 2026-04-08 | TODO |
| 5 | Add a `manage.py reset_axes` step to `railway-release.sh` gated by env var (already done in commit 0688615 -- verify it's permanent) | DevOps | 2026-04-07 | TODO |
| 6 | Write a data migration runbook: pg_dump command, pg_restore command, verification queries, rollback steps | Engineering Lead | 2026-04-10 | TODO |
| 7 | Add `SECURE_REDIRECT_EXEMPT` for `/health/` to the default production settings template so this never happens again | Backend Dev | 2026-04-07 | TODO |
| 8 | Add a CI step that boots gunicorn with production config and hits `/health/` before deploy | DevOps | 2026-04-15 | TODO |
| 9 | Remove or rewrite all cargo-culted config files. Audit every config file against what we actually use. | Engineering Lead | 2026-04-12 | TODO |
| 10 | Post this postmortem in the team channel. No blame, full transparency. | Engineering Lead | 2026-04-07 | TODO |

---

## Lessons Learned

### 1. "Works on my machine" is not a deployment strategy
`manage.py runserver` hides every production configuration problem. If you haven't run `gunicorn` with your actual `gunicorn.conf.py` locally, you have not tested your deployment.

### 2. PaaS is not "just push and it works"
Railway, Render, Fly -- they all have opinions about ports, healthchecks, and proxy headers. Read the docs BEFORE the first deploy, not during a 5-hour firefight.

### 3. Copy-pasted config files are time bombs
The `gunicorn.conf.py` with `UvicornWorker` was clearly copied from somewhere and never questioned. Every config file must be reviewed line by line and understood.

### 4. Never deploy to production first
A 10-minute staging test would have caught every single issue in this incident. Every one. The $0-5 cost of a staging environment is nothing compared to 5+ hours of engineering time and damaged stakeholder trust.

### 5. Security features need break-glass procedures
django-axes locking out the only admin account during initial deployment is a predictable failure mode. Every security mechanism needs a documented emergency bypass.

### 6. Data migration is part of deployment
An app without its data is not deployed. Data migration must be an explicit, planned, tested step in every deployment checklist.

### 7. Don't debug under executive pressure
When the CEO is watching, the instinct is to skip testing and "just try things." This makes everything take longer. Next time: give a realistic timeline, ask for space, and work methodically.

---

## Prevention Plan

### Immediate (this week)
- [ ] Deployment checklist created and added to repo as `docs/DEPLOY_CHECKLIST.md`
- [ ] `gunicorn.conf.py` audited and locked down
- [ ] Auth documentation written

### Short-term (this sprint)
- [ ] Staging environment provisioned on Railway
- [ ] CI pipeline includes production config validation
- [ ] Data migration runbook created and tested

### Long-term (this quarter)
- [ ] All deployments go through staging first -- no exceptions
- [ ] Automated deploy pipeline: CI passes -> staging deploy -> smoke tests -> production deploy
- [ ] Monthly "deploy drill" -- practice deploying to a fresh environment to catch config drift

---

## Cost of This Incident

| Category | Estimated Cost |
|----------|---------------|
| Engineering time (5+ hours, 1-2 engineers) | ~$500-1000 in labor |
| Railway build minutes burned | ~$2-5 |
| Stakeholder trust | **Significant damage** |
| CEO confidence in the team | **Near-breaking point** |
| Delayed launch | ~1 day |
| Morale impact | Moderate -- team was demoralized |

**Total real cost: The trust damage far exceeds the dollar amount.** A CEO who almost cancels a deployment approach will remember this incident for months. Every future deployment will carry the shadow of this failure until we prove we've learned from it.

---

## Final Note

This incident was entirely preventable. Not one of the five root causes was exotic or surprising. They are all well-documented PaaS deployment pitfalls that a 15-minute checklist would have caught. The failure was not technical -- it was process. We had no checklist, no staging, no runbook, and no documentation. We deployed hope instead of software.

The only acceptable outcome from this postmortem is that it never happens again.
