# CLAUDE.md — تعليمات العمل على منصة SchoolOS
> التفصيل الكامل (منقول حرفيًّا): `docs/governance/claude_md_details.md`؛ التاريخي: `AAdocs/claude/claude-config/CLAUDE.md`.

## القاعدة 1
اعمل في شجرة عملك وراقبها على منفذها؛ لا تعبر إلى مسار عمل آخر. خادم الشجرة عند الحاجة (`docs/deployment/session_server.md`)، والمعاينة المركزية `:8500` الوحيدة المقيمة؛ لا `pin` ولا `release` ولا `up/down`، ولا تنتزع تثبيت غيرك.

## غيت
لا تبدّل فرع شجرة لست فيها · لا `git add -A` ولا `commit -a` (مسارات صريحة) · لا `git stash` · لا `pull --rebase` على شجرة متّسخة · `git status` قبل كل إيداع، وملف لا تعرفه فقف واسأل · حارس غيت يحجب stash وforce-push وreset --hard و`--no-verify`؛ التجاوز بإذن المالك الصريح في المحادثة فقط.

## سير العمل
عدّل في شجرتك · لا دفع قبل نجاح `make prepush` · لا دفع إلى `main` · المسار الوحيد: طلبٌ من صفحة طلب جديد ← `tools/runner.py` ← فحوص CI وبوابة الدمج ← النشر الآلي.

## الخارطة الحيّة
يُحدَّث `/roadmap/` مع اندماج كل طلب؛ لا إغلاق بند بلا رقم طلبه. التفصيل: `.claude/rules/roadmap.md`.

## نافذة النشر
لا دمج ولا نشر الأحد–الخميس 07:00–14:00 بتوقيت الدوحة إلا بإذن المالك الصريح في اليوم نفسه (وسم «نشر-عاجل» لا يضعه أحد بلا إذنه)؛ دفعتا نشر: بعد 14:30 وبعد 19:00. التفصيل: `.claude/rules/deploy-window.md`.

## قواعد بالمسار
`.claude/rules/`: design-system (static/templates) · migrations · dashboards · deploy-window · roadmap.
