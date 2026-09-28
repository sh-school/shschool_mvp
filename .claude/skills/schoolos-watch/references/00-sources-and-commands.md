# المصادرُ والأوامر — جولةُ الرصد
> متى تقرأ هذا الملف: قبل أوّل جولةٍ في الجلسة، وكلّما احتجتَ أمراً قرائيّاً لمصدرٍ بعينه أو شككتَ أنّ `watch_once` يغطّيه.

كلُّ أمرٍ هنا جُرِّب قرائيّاً يوم 2026-09-28 (الدوحة ~21:00). الأوامرُ من Git Bash ما لم يُذكر PowerShell. `gh` يُشغَّل من أيّ شجرةٍ للمستودع.

## 1) المصادرُ الثمانية ومن يغطّيها
المصادرُ من ميثاق 0203 (`delivery_manager_work/docs/tab_charters.md`)؛ والتغطيةُ من قراءة `tools/watch_once.py`.

| المصدر | في `watch_once`؟ | كيف يُقرأ (القسم) |
|---|---|---|
| صحّةُ الإنتاج (`/health/` وأخواتها) وقضاياها الآليّة | لا | §3 |
| CI على main | نعم جزئيّاً (`main_red`) | §4 |
| نسخُ قاعدة الإنتاج اليوميّ وتمرينُ الاستعادة | لا | §5 |
| نسخُ `~/.claude` (عمرُ آخر إيداعٍ وملفُّ الفشل) | نعم (`claude_backup`) | §5 |
| حزمةُ git الليليّة للمستودع | لا | §5 |
| ذاكرةُ الجهاز | نعم (`memory`) | §2 |
| تنبيهاتُ أمن GitHub | لا | §6 |
| الأشجارُ اليتيمة | نعم (`orphan_tree`) | §2، §7 |
| طلباتٌ متأخّرةٌ عن main أو فيها تعارض | لا (يقيس العمرَ والعددَ فقط) | §7 |

## 2) المراقب `watch_once.py`
```bash
python ~/delivery_manager_work/tools/watch_once.py            # نصّ، نحو 50 ثانية
python ~/delivery_manager_work/tools/watch_once.py --json     # {generated_doha, alerts:[{code,severity,message,action}]}
python ~/delivery_manager_work/tools/watch_once.py --no-live  # الذاكرة وحدها، بلا gh ولا git
```
- العتباتُ من `delivery_manager_work/projects/schoolos/thresholds.json` («أوّليّةٌ تُضبط بعد ثلاثة أيّام قياس»). درجاتُ الأداة: `critical` و`high` و`warn` و`info` — وهي ليست S1..S3 (الربطُ في المرجع 01).
- رمزُ الخروج 0 دائماً، ولا يكتب شيئاً. يقرأ: `gh pr list`، `gh run list --branch main --limit 6`، `git log` في `~/.claude`، سجلَّ `ledger/`، وحالةَ الأشجار.

| الرمز | متى يطلق | الدرجة |
|---|---|---|
| `memory` | المتاح < 2.0 غيغا: أصفر ≥1.0، أحمر ≥0.5، حرج دونها | warn / high / critical |
| `oldest_pr_age` | أقدمُ طلبٍ غيرِ مسوّدة ≥ 8 س (warn) أو ≥ 24 س (high) | تدفّق |
| `system_wip` | الطلباتُ المفتوحةُ غيرُ المسوّدة > 10 | تدفّق |
| `main_red` | ≥ 2 تشغيلٍ فاشلٍ في آخر 6 على main (أيًّا كان الحدث) | high |
| `claude_backup` | `backups/BACKUP_FAILED.txt` موجود، أو لا إيداعَ في فرع `scoped`، أو آخرُه > 36 س | high |
| `late_start` | بطاقاتُ `ledger` حان بدؤها ولم تبدأ (high إن فيها P0/P1) | تدفّق — لـ0204 |
| `orphan_tree` | شجرةٌ **بلا اسمٍ** في `session_names.json` وحالتُها معلَّقة | warn (`merged_dirty`: info) |
| `gh_unavailable` | فشل `gh pr list` — فحصا الطلبات والأشجار معطَّلان | warn |
| `watch_error` | سقط فحصُ الأشجار باستثناء | warn |

حالاتُ الشجرة من `tools/branch_status.py`: معلَّقةٌ = `no_pr` (عملٌ بلا طلب) و`closed_unmerged` (طلبٌ أُغلق بلا دمج) و`work_after_merge` (إيداعاتٌ فوق طلبٍ مدموج) و`merged_dirty` (اندمج وبقيت ملفّاتٌ غيرُ مودَعة)؛ وغيرُ معلَّقة = `open_pr` و`merged` و`merged_elsewhere` و`clean`. أشجارُ `main-preview` و`integration-preview` مستثناة.

أدواتٌ مساعدةٌ قرائيّة (لا تكتب):
```bash
python ~/delivery_manager_work/tools/session_load_v2.py --no-fetch   # ~10 ث: حِملُ الجلسات، أشجارٌ بلا اسم، طلباتٌ بلا صاحب
python ~/delivery_manager_work/tools/archive_check.py <مجلّد-الشجرة> --title "<عنوان>"   # ~10 ث: حقيقةُ شجرةٍ واحدة (branch_status)
```
`branch_status.py` مكتبةٌ بلا واجهة أوامر (تشغيلُه لا يطبع شيئاً)؛ يُستعمل عبر الأداتين أعلاه. و`archive_check` يُستعمل هنا للحقائق وحدها — قرارُ الأرشفة ليس لـ0203.

## 3) صحّةُ الإنتاج
المراقبُ الأوّل Sentry Uptime (كلَّ 60 ث على `/`) ولوحتُه عند المالك؛ وفحصا GitHub المجدولان ثانويّان بأفضل جهد. المصدر: تعليقُ `.github/workflows/monitor.yml`.

قراءةٌ مباشرة — العنوانُ يُستخرج من السكربت وقتَ التشغيل فلا يُكتب في أيّ ملفٍّ أو رسالة (من شجرةٍ فيها `scripts/preview.sh`):
```bash
PROD="$(sed -n 's/^PROD_URL="\${PRODUCTION_URL:-\([^}]*\)}".*/\1/p' scripts/preview.sh)"
for p in health/ ready/ health/worker/ auth/login/; do printf '%-15s %s\n' "$p" "$(curl -s -m 15 -o /dev/null -w '%{http_code}' "$PROD/$p")"; done
curl -s -m 15 "$PROD/health/" | python -c "import json,sys; d=json.load(sys.stdin); print(d['status'], d['commit'], d['checks'])"
```
- `/health/`: `status` = ok|degraded، و`checks` = `db` و`cache` و`static`، و`commit` (7 خانات). 503 إن سقط أحدُها. `/health/worker/`: 503 إن غابت نبضةُ العامل > 15 د. المصدر: `core/views_health.py` في main — أمّا `docs/monitoring/health-endpoints.md` فقديمٌ لا يذكر `static` ولا `commit` ولا `/health/worker/`.
- لا تكتب المسارَ بشرطةٍ أولى داخل `-w` أو وسيطٍ في Git Bash (`/auth/login/` يتحوّل إلى مسار ويندوز)؛ الصيغةُ أعلاه تتجنّبه.
- `commit` الإنتاج مقابل main (قرائيّ؛ يجلب main في شجرة المعاينة وحدها): `bash scripts/preview.sh status` ← سطرا «main:» و«الإنتاج:». جذرُ `D:/shschool_mvp` قد يكون على فرعٍ قديمٍ بلا هذا السكربت (قيس 09-28) — شغّله من شجرتك.

القضايا الآليّة (تُفتح عند الفشل المتّصل وتُغلق عند أوّل نجاح):
```bash
for l in uptime-failure deploy-failure worker-heartbeat-failure; do printf '%-26s %s\n' "$l" "$(gh issue list --state open --label "$l" --json number --jq length)"; done
```
| الوسم | العنوانُ يبدأ بـ | من يفتحها |
|---|---|---|
| `uptime-failure` | 🔴 UPTIME FAILED | `monitor.yml` (كلَّ 15 د اسميّاً، محاولتان بينهما دقيقة) |
| `deploy-failure` | 🔴 DEPLOY FAILED | `post-deploy-canary.yml` بعد كلّ نشرٍ ناجحٍ في Railway: الـcommit لم يصر حيّاً أو صفحةُ الدخول لا تُرسم |
| `worker-heartbeat-failure` | 🔴 WORKER HEARTBEAT STALE | `worker-heartbeat.yml` (كلَّ 10 د اسميّاً، ثلاثُ محاولات) |

`scripts/verify_deploy.py` ليس في المستودع؛ هو أداةُ جلسة النشر خارجه ويقرأ Railway — ليس لـ0203 (`schoolos-deploy`).

## 4) CI على main
```bash
gh run list --branch main --limit 12 --json name,event,conclusion,createdAt --jq '.[]|[.createdAt,.event,.conclusion,.name]|@tsv'
gh run list --branch main --limit 12 --json event,conclusion --jq '[.[]|select(.event=="push" or .event=="dynamic")|select(.conclusion=="failure")]|length'   # فشلُ فحوص الدفع وحدها
gh run list --branch main --status failure --limit 20 --json name,event,createdAt --jq '.[]|[.createdAt,.event,.name]|@tsv'
```
الأحداثُ على main: `push` و`dynamic` (فحوصُ الدفع: Quality Gate، Code Quality، Security Scan…) و`schedule` (Nightly، Uptime، Worker heartbeat، Quality الأسبوعيّ). `main_red` في `watch_once` لا يفرّق بينها.

## 5) النسخُ الاحتياطيّ
```bash
gh run list --workflow backup.yml --limit 3 --json conclusion,createdAt,event --jq '.[]|[.createdAt,.event,.conclusion]|@tsv'
gh run list --workflow backup-restore-test.yml --limit 2 --json conclusion,createdAt --jq '.[]|[.createdAt,.conclusion]|@tsv'
git -C ~/.claude log -1 --format='%ci %s' scoped
ls ~/.claude/backups/BACKUP_FAILED.txt ~/.claude/backups/LAST_STATUS.json
ls -l ~/git-backups/shschool_mvp/LAST_OK.txt
```
- `backup.yml`: pg_dump مشفّرٌ يوميّاً؛ الجدولةُ 01:00 UTC لكنّ التشغيلاتِ الفعليّة 05:42–06:08 UTC (قيس 09-26..09-28) — فلا تعدّه متأخّراً قبل ظهر الدوحة. التعليقُ فيه «RPO ≤ 24h». ورقمُ الوركفلو 299994709 في ورقة U-01 هو `backup.yml` نفسُه.
- `backup-restore-test.yml`: تمرينُ استعادةٍ أسبوعيٌّ السبت 02:30 UTC؛ آخرُ نجاحٍ 09-26.
- `~/.claude`: مهمّةُ ويندوز `Claude_DailyBackup` يوميّاً 03:00؛ الحدُّ 36 س (`thresholds.json`). `LAST_STATUS.json` يكتبه السكربتُ v2 ابتداءً من أوّل تشغيلٍ فعليٍّ له (09-29 03:00)؛ غيابُه قبل ذلك متوقَّع. ومجلّدُ `backups/` فيه أيضاً نسخُ `.claude.json.backup.*` من التطبيق — لا علاقةَ لها بالسكربت.
- حزمةُ git الليليّة: مهمّةُ `SchoolOS-GitBundle-Nightly` يوميّاً 02:00 تكتب `LAST_OK.txt` و`nightly.log` (قيس 09-28 02:01). لا حدَّ عمرٍ موثَّقاً لها؛ المهمّةُ يوميّة.
- حالُ المهامّ المجدولة (PowerShell؛ النتيجةُ 0 لا تثبت النجاح):
  `Get-ScheduledTask | ? TaskName -match 'Claude_DailyBackup|GitBundle' | % { $i = $_ | Get-ScheduledTaskInfo; "$($_.TaskName) last=$($i.LastRunTime) result=$($i.LastTaskResult)" }`

## 6) أمنُ GitHub (عبر API — لا بالبحث في ملفّات الوركفلو)
```bash
gh api "repos/{owner}/{repo}/secret-scanning/alerts?state=open&per_page=100" --jq length
gh api "repos/{owner}/{repo}/dependabot/alerts?state=open&per_page=100" --jq 'group_by(.security_advisory.severity)|map({s:.[0].security_advisory.severity,n:length})'
gh api "repos/{owner}/{repo}/code-scanning/alerts?state=open&per_page=100" --jq 'group_by(.rule.security_severity_level)|map({s:.[0].rule.security_severity_level,n:length})'
```
خطُّ الأساس 09-28: secret 0، dependabot 0، code-scanning 2 (medium). الإنذارُ هو الجديدُ عن الأساس لا القائم. وCodeQL مفعّلٌ بالإعداد الافتراضيّ بلا ملفّ وركفلو — غيابُ الملفّ لا يعني غيابَ الميزة. المصدر: `feedback_audit_github_security_via_api`.

## 7) الطلباتُ والأشجار
```bash
gh pr list --state open --json number,isDraft,mergeable,mergeStateStatus,author,headRefName --jq '.[]|[.number,.isDraft,.mergeable,.mergeStateStatus,.author.login,.headRefName]|@tsv'
```
`mergeable=CONFLICTING` أو `mergeStateStatus=DIRTY` = تعارض؛ `BEHIND` = متأخّرٌ عن main. `app/dependabot` طلباتٌ آليّة.

## 8) الذاكرةُ والمعاينة
- `python .../watch_once.py --no-live`، أو PowerShell: `Get-CimInstance Win32_OperatingSystem | Select FreePhysicalMemory,TotalVisibleMemorySize` (ك.ب). المصدر: `docs/incident_runbook.md` §4.
- المعاينة 8500: `bash scripts/preview.sh status` ← سطرُ «الخادم: running (healthy)». لا `up` ولا `down` (للمالك وجلسة النشر — CLAUDE.md).

## أنماطٌ مضادّة
- الاكتفاءُ بـ`watch_once` جولةً كاملة: لا يرى الإنتاجَ ولا الأمنَ ولا نسخَ قاعدة الإنتاج.
- نسخُ عنوان الإنتاج من السكربت إلى رسالةٍ أو ملفّ.
- `railway logs` أو `railway ssh` للتشخيص: قراءةُ إنتاجٍ يحجبها المصنِّف، وليست لـ0203.
- الحكمُ على وجود ميزة أمانٍ من مجلّد `.github/workflows/` وحده.
- قراءةُ `docs/monitoring/*.md` مرجعاً للحقول دون مطابقتها بالشيفرة.
