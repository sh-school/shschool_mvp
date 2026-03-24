# CLAUDE.md — تعليمات العمل على منصة SchoolOS

## قواعد العمل الأساسية

### مسار المشروع المحلي
- **المسار الأصلي:** `D:\shschool_mvp`
- **جميع التعديلات تُجرى مباشرة على الملفات في المسار الأصلي** — لا على worktree أو نسخة معزولة
- بعد التعديل: commit ثم push إلى GitHub مباشرة

### سير العمل
1. عدّل الملفات في `D:\shschool_mvp` مباشرة
2. `git add` + `git commit` على الـ main branch
3. `git push origin main` إلى GitHub
4. لا تستخدم worktrees — عدّل مباشرة على المشروع المحلي

### Cache-busting
عند تعديل CSS أو JS، ارفع رقم الإصدار في `base.html`:
- CSS: `custom.css?v=17` → `?v=18`
- JS: `base.js?v=6.1` → `?v=6.2` و `app.js?v=6.1` → `?v=6.2`
