# جردُ المهامّ الدوريّة — أين تعيش كلٌّ وما يُنقل

متى تقرأ هذا الملف: قبل أن تبني أيَّ أتمتة (قد تكون موجودة)، وحين تُسأل «ما الذي يعمل وحدَه الآن؟»، وحين تحصر ما بقي في Claude Code.

> لقطةُ 2026-09-28 (main عند #725). الجدولُ يتقادم: أعِد قراءةَ المصدر الحيّ قبل الاعتماد عليه —
> `shschool/celery.py` (beat)، و`.github/workflows/*.yml` (Actions)، و`Get-ScheduledTask` (ويندوز)، وأداةُ المهامّ المجدولة (Claude).
> في Git Bash اسبق `git show origin/main:<path>` بـ`export MSYS_NO_PATHCONV=1` وإلّا تشوّه المسار. المصدر: `feedback_windows_shell_classifier_pitfalls`.

## 1) داخل المنصّة — Celery beat (خدمة `celery-beat`، نسخةٌ واحدة، توقيتُ قطر)
المصدر: `shschool/celery.py`، `scripts/railway-beat.sh`، `.railway/railway.ts`.

| المدخل | المهمّة | الموعد (الدوحة) |
|---|---|---|
| send-absence-alerts-daily | notifications.send_pending_absence_alerts_all_schools | يوميّاً 07:00 |
| check-breach-deadlines-hourly | notifications.check_breach_deadlines | كلَّ ساعة :00 (مهلةُ PDPPL 72 س) |
| send-monthly-kpi-report | analytics.send_monthly_kpi_report | أوّلَ الشهر 06:00 |
| staff-monthly-absence-notices | staff_affairs.send_monthly_absence_notices | أوّلَ الشهر 07:30 |
| revoke-expired-temp-permissions | operations.revoke_expired_temp_permissions | كلَّ دقيقة |
| weekly-behavior-risk-check | behavior.weekly_risk_check | الأحد 06:00 |
| finalize-period-exits | operations.finalize_period_exits | كلَّ 5 د، 06–15، الأحد–الخميس |
| behavior-auto-infraction-digest | behavior.send_auto_infraction_digest | 15:00 الأحد–الخميس |
| enforce-data-retention-weekly | core.enforce_data_retention | الجمعة 03:30 |
| worker-heartbeat | core.worker_heartbeat | كلَّ 5 د (المراقَبُ الوحيد في Sentry Crons) |
| refresh-backup-status | core.refresh_backup_status | كلَّ 30 د |
| qcc-collect-local | command_center.collect_local | كلَّ دقيقة |
| qcc-collect-remote | command_center.collect_remote | كلَّ 4 د |
| purge-expired-export-jobs | operations.purge_expired_export_jobs | كلَّ ساعة :05 |
| expire-overdue-compensatory | operations.expire_overdue_compensatory | يوميّاً 04:15 |

حرّاسُها: `tests/test_beat_tasks_registered.py` (كلُّ مدخلٍ مسجَّل)، و`tests/test_celery_beat_is_deployed.py` (الخدمةُ معلنة والسكربتُ يرفض العملَ أعمى، والاحتفاظُ فجراً، والنبضةُ ≤ 5 د).

## 2) خارج المنصّة — GitHub Actions المجدولة (cron بـUTC)
المصدر: `.github/workflows/`.

| الملفّ | الموعد UTC ← الدوحة | ما يفعله | إبلاغُ الفشل |
|---|---|---|---|
| monitor.yml | كلَّ 15 د (بأفضل جهد) | فحصُ الإنتاج من الخارج (`scripts/smoke-test.sh`) بمحاولتين | قضيّةٌ `uptime-failure` تُغلق بالنجاح |
| worker-heartbeat.yml | كلَّ 10 د (بأفضل جهد) | يقرأ `/health/worker/` بثلاث محاولات | قضيّةٌ `worker-heartbeat-failure` |
| nightly.yml | 02:00 ← 05:00 | المجموعةُ كاملةً متسلسلة + Playwright + Lighthouse | قضيّةٌ `nightly-failure` |
| backup.yml | 01:00 ← 04:00 | pg_dump مشفَّرٌ إلى R2 (أو artifact) | لا قضيّة؛ تظهر حالتُه في بطاقة الإدارة عبر `core/backup_status.py` |
| backup-restore-test.yml | السبت 02:30 ← 05:30 | استعادةُ أحدث نسخة والتحقّق منها | **لا شيء** (ملخّصُ التشغيل فقط) |
| identity-kpis.yml | الأحد 03:00 ← 06:00 | `scripts/measure_identity_kpis.py` ← JSON artifact | **لا شيء**، ولا `timeout-minutes` |
| quality.yml | الأحد 06:00 ← 09:00 | pip-audit وفحوصٌ أسبوعيّة | **لا شيء** |
| security-scan.yml | الأحد 04:00 ← 07:00 (ومع كلّ طلب) | SAST وCVEs | لا قضيّة للتشغيل المجدول |
| post-deploy-canary.yml | حدث `deployment_status` لا جدول | أصار الـcommit المنشور حيّاً؟ | قضيّةٌ `deploy-failure` |

## 3) على جهاز المالك — جدولةُ ويندوز (منطقةُ الجهاز `Arab Standard Time`، قيست 2026-09-28)
| المهمّة | الموعد | السكربت | إشارةُ الصحّة | يقرؤها `watch_once`؟ |
|---|---|---|---|---|
| Claude_DailyBackup | يوميّاً 03:00 (`StartWhenAvailable`، سقفٌ 10 د) | `~/.claude/scripts/auto_backup.ps1` v2 | `backups/LAST_STATUS.json`، `BACKUP_FAILED.txt`، عمرُ آخر إيداع | نعم (≥ 36 س أو ملفُّ الفشل ← high) |
| `\SchoolOS\SchoolOS-GitBundle-Nightly` (REP-01) | يوميّاً 02:00 | `~/git-backups/rep01_backup.py` (bundle + تحقّق + استعادةٌ أسبوعيّة) | رمزُ خروج 0..5، `nightly.log`، `run.log` | **لا** |
| SchoolOS-BranchesReport-Weekly (REP-10 المحلّيّ) | الأحد 06:30 | `~/git-backups/weekly_branches_report.py` | `branches_report.json` و`.log` | **لا** |
المصدر: `Get-ScheduledTask` (2026-09-28)، `project_claude_backup_stale_lock_2026_09_28`. المهامُّ الأخرى على الجهاز لمشاريعَ أخرى: خارج النطاق.

## 4) في Claude Code — الهدفُ صفرُ مهمّةٍ مفعَّلة
أداةُ المهامّ المجدولة (2026-09-28): ثلاثُ مهامّ **كلُّها موقوفة** — REP-10 `rep10-weekly-rk-reading` (كلَّ 6 س، أُوقفت D-42م بلا حذف)، وتذكيران لمرّةٍ واحدةٍ انقضيا. الجلساتُ التي أنشأتها REP-10 أُرشفت (D-41م). المؤشّر: عددُ المفعَّل = 0، ويُفحص بعد كلّ نقل.

## 5) ما يُنقل (أعمالُ 0801 الأولى) — المصدر: ميثاقُ 0801 في `tabs.json`، و`roadmap_intake_MAE_2026-09-28.md`
| العمل | اليوم | الوجهة المقترحة | ملاحظة |
|---|---|---|---|
| REP-10 قراءةُ RK1..RK3 | مهمّةُ Claude موقوفة | البعيد: مجمِّعٌ في `command_center/collectors/` عبر واجهة GitHub + beat؛ المحلّيّ: التقريرُ الأسبوعيّ القائم في ويندوز | كانت كلَّ 6 س والقائمُ أسبوعيّ: الوتيرةُ قرارُ المالك |
| MAE-06 المراقب `watch_once.py` | يدويّ | جدولةُ ويندوز كلَّ 30 د (يحتاج `gh` والذاكرةَ المحلّيّة) | الميثاقُ يقول ويندوز لا Claude؛ قناةُ إيصال high/critical للمالك **غيرُ محسومة** |
| MAE-09 حزمةُ الأدلّة | يدويّ (`evidence_pack.py`) | Actions على حدث `pull_request` لا على جدول | تعليقٌ على الطلب بلا بياناتٍ شخصيّة؛ فشلٌ عند تجاوزٍ مقيس |
| MAE-11 مزامنةُ الخارطة بالدمج | يدويّ | يُصمَّم مع «0701» (مالكِ هجرات `roadmap/`) | الأتمتةُ تُنتج مدخلَ الطابور فقط، لا هجرة |
| مواعيدُ الجلسات الثابتة | لا شيء | **دراسةٌ لا تنفيذ** | `05-session-wakeup-study.md` |
| النسخُ الاحتياطيّ والحزمةُ الليليّة | ويندوز | **تبقى كما هي** | فجوتُها في الرصد لا في المكان |

## 6) فجواتٌ معروفة (كلٌّ بطاقةٌ مرشَّحة إلى «0204» لا إصلاحٌ ضمنيّ)
- أربعةُ مساراتٍ مجدولةٍ بلا إبلاغ فشل: backup-restore-test وidentity-kpis وquality وsecurity-scan (المجدول) — فشلُها صامتٌ حتى يُفتح Actions.
- مهمّتا ويندوز للمستودع (REP-01 وتقريرُ الفروع) لا يقرؤهما المراقب؛ فشلُهما لا يظهر إلّا في «آخر نتيجة» المهمّة.
- `worker-heartbeat.yml` يحمل عنوانَ إنتاجٍ احتياطيّاً حرفيّاً؛ النمطُ الصحيح `vars.PRODUCTION_URL` وحدَه. لا تنسخه.
- `docs/scheduled_tasks_study_2026-09.md` (09-21) سابقٌ لـD-50م: يقترح مهامَّ Claude «للحكم» ويذكر تنظيفَ التصدير «يوميّاً 04:00» والشيفرةُ كلَّ ساعة :05. والتعليقُ في `core/sentry_config.py` يقول «11» مدخلاً والجدولُ 15. الشيفرةُ أصحّ.

## أنماطٌ مضادّة
- البناءُ قبل الجرد: مراقبٌ ثانٍ للإنتاج أو نسخٌ ثانٍ بجانب القائم.
- عدُّ «آخرُ نتيجةٍ 0» في جدولة ويندوز دليلَ نجاح.
- نقلُ الجدول من هذه الوثيقة بلا قراءة المصدر الحيّ.
- حذفُ مهمّة Claude بدل إيقافها قبل أن تُنشر بديلتُها وتُرى تعمل.
