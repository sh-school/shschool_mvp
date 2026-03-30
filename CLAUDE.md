# CLAUDE.md — تعليمات العمل على منصة SchoolOS
> **ملاحظة:** هذا الملف يجب أن يبقى في جذر المشروع حتى يقرأه Claude Code تلقائياً.
> النسخة الكاملة + التاريخية محفوظة في: `AAdocs/claude/claude-config/CLAUDE.md`

## !!! القاعدة رقم 1 — الأهم على الإطلاق !!!

> **كل التعديلات تتم على المسار المحلي `D:\shschool_mvp` مباشرة — بدون استثناء.**
>
> **ممنوع منعاً باتاً:**
> - التعديل في worktree أو أي مسار آخر
> - التعديل في `D:\shschool_mvp\.claude\worktrees\*`
> - استخدام أي مسار غير `D:\shschool_mvp`
>
> **حتى لو كانت الجلسة تعمل في worktree، يجب استخدام المسار المحلي الأصلي فقط:**
> - `Read("D:\shschool_mvp\file.py")` ✅
> - `Edit("D:\shschool_mvp\file.py", ...)` ✅
> - `Read("D:\shschool_mvp\.claude\worktrees\...\file.py")` ❌ ممنوع
> - `Edit("D:\shschool_mvp\.claude\worktrees\...\file.py", ...)` ❌ ممنوع
>
> **بعد كل تعديل CSS/JS:** شغّل `collectstatic` ثم أعد تشغيل السيرفر.

## قواعد العمل الأساسية

### مسار المشروع المحلي
- **المسار الأصلي والوحيد:** `D:\shschool_mvp`
- **جميع التعديلات تُجرى مباشرة على الملفات في المسار الأصلي** — لا على worktree أو نسخة معزولة
- بعد التعديل: commit ثم push إلى GitHub مباشرة
- بعد تعديل static files: `python manage.py collectstatic --noinput`

### سير العمل
1. عدّل الملفات في `D:\shschool_mvp` مباشرة — **هذا المسار فقط ولا غيره**
2. `python manage.py collectstatic --noinput` (عند تعديل CSS/JS)
3. `git add` + `git commit` على الـ main branch
4. `git push origin main` إلى GitHub
5. **لا تستخدم worktrees أبداً** — عدّل مباشرة على المشروع المحلي

### Cache-busting
عند تعديل CSS أو JS، ارفع رقم الإصدار في `base.html` و `login.html`:
- CSS: `custom.css?v=100` → `?v=101`
- JS: `base.js?v=100` → `?v=101` و `app.js?v=100` → `?v=101`
