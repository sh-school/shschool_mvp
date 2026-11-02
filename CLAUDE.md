# CLAUDE.md — تعليمات العمل على منصة SchoolOS
> التفصيل الكامل (منقول حرفيًّا): `docs/governance/claude_md_details.md`؛ التاريخي: `AAdocs/claude/claude-config/CLAUDE.md`.

## القاعدة 1
كل جلسة تعمل في شجرة عملها وتراها على منفذها؛ لا تعبر إلى مسار جلسة أخرى. خادم الجلسة عند الحاجة (`docs/deployment/session_server.md`)، والمعاينة المركزية `:8500` الوحيدة المقيمة (تثبّتها 0501 وحدها؛ لا `pin` ولا `release` ولا `up/down`، ولا تنتزع تثبيت غيرك).

## غيت
لا تبدّل فرع شجرة لست فيها · لا `git add -A` ولا `commit -a` (مسارات صريحة) · لا `git stash` · لا `pull --rebase` على شجرة متّسخة · `git status` قبل كل إيداع، وملف لا تعرفه فقف واسأل · حارس غيت يحجب stash وforce-push وreset --hard و`--no-verify`؛ التجاوز بإذن المالك الصريح في المحادثة فقط.

## سير العمل
عدّل في شجرتك · لا دفع قبل نجاح `make prepush` · لا دفع إلى `main` · الاعتماد والدفع والتسليم لـ0501 ثم 0601 كما في `docs/governance/flow.md` ومهارة `schoolos-flow` (تُستدعى قبل أي دفع أو طلب أو دمج).

## الخارطة الحيّة
كل جلسة تحدّث `/roadmap/` فور اندماج طلبها؛ لا إغلاق بند بلا رقم طلبه. التفصيل: `.claude/rules/roadmap.md`.

## نافذة النشر
لا دمج ولا نشر الأحد–الخميس 07:00–14:00 بتوقيت الدوحة إلا بإذن المالك الصريح في اليوم نفسه (وسم «نشر-عاجل» لا يضعه أحد بلا إذنه)؛ دفعتا نشر: بعد 14:30 وبعد 19:00. التفصيل: `.claude/rules/deploy-window.md`.

## قواعد بالمسار
`.claude/rules/`: design-system (static/templates) · migrations · dashboards · deploy-window · roadmap.
