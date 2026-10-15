---
paths:
  - ".github/workflows/**"
  - "scripts/deploy_window.py"
  - "scripts/railway-*"
  - "railway.*"
  - "**/sw*.js"
  - "**/service-worker*.js"
---

# نافذةُ النشر — تفصيلٌ يُحمَّل عند لمس النشر

نُقل حرفياً من `CLAUDE.md` (حدودُ الحكم الثلاثة ورفعُ رقم عامل الخدمة بقيت هناك).

### الهجرات وإعادة تشغيل daphne

- **الهجراتُ آمنةٌ الآن بلا هذه القاعدة** (`preDeployCommand`، انظر
  `scripts/railway-predeploy.sh`) — لكنّ إعادة تشغيل daphne نفسِها تقطع طلباتٍ
  مفتوحة، فالقاعدةُ عن توقيت النشر لا عن سلامة الهجرة وحدها.

### اسم ذاكرة عامل الخدمة

الاسمُ الحاليّ جزءٌ من مفتاح الذاكرة
  (`CACHE_NAME`؛ مثلاً `schoolos-global-v2`، `schoolos-parents-v3`)، فرفعُ
  الرقم يُبطل النسخةَ القديمة على أجهزة المستخدمين دون انتظار Ctrl+Shift+R.
