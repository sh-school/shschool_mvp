# دليل نشر إصدار الإصلاحات (2026-07-06) على Railway

> إصدار يحوي **ترحيلات تشفّر بيانات PII قائمة** لقُصّر (عيادة/سلوك/نقل) + token_blacklist + DLQ.
> اقرأ كل القسم «قبل النشر» — Railway ينشر تلقائياً عند الدفع إلى `main` ويشغّل `migrate` بنفسه.

---

## ⚠️ 0. ما الجديد الذي سيُطبَّق تلقائياً

`railway-release.sh` يشغّل `python manage.py migrate --noinput` في مرحلة الإصدار، فيطبّق:
- **ترحيلات تشفير** تحوّل بيانات موجودة من نصّ صريح → مشفّر (Fernet): `clinic.0004`, `behavior.0013`, `transport.0003`.
- `token_blacklist.*` (جداول JWT blacklist) + `notifications.0007` (جدول DLQ).

**تشفير البيانات القائمة عملية تحويلية** — قابلة للعكس عبر `migrate <app> <prev>` (backward يفكّ التشفير)، لكنها تمسّ بيانات إنتاج حقيقية. **النسخ الاحتياطي إلزامي.**

---

## ✅ 1. قبل النشر (حرج — بالترتيب)

1. **تأكّد من متغيّرات Railway (Variables):**
   - `FERNET_KEY` — **مضبوط** (التطبيق لا يُقلع بدونه في الإنتاج). **لا تغيّره ولا تحذفه** — كل PII المشفّرة تعتمد عليه.
   - `APP_DB_PASSWORD` — **مضبوط** (release script يرفض الإقلاع بدونه في الإنتاج لفرض RLS).
   - `SECRET_KEY`, `ALLOWED_HOSTS`, `DJANGO_SETTINGS_MODULE=shschool.settings.production`.
   - `CSRF_TRUSTED_ORIGINS` يشمل نطاقك (`https://*.up.railway.app` أو نطاقك المخصّص).

2. **خذ نسخة احتياطية من قاعدة الإنتاج** قبل أي شيء:
   ```bash
   # من Railway CLI أو لوحة PostgreSQL:
   pg_dump "$DATABASE_URL" -Fc -f schoolos_backup_pre_encrypt_2026-07-06.dump
   ```
   احتفظ بها في مكان آمن — هي خطة التراجع النهائية.

3. **جرّب على staging أولاً** (لديك `shschool.settings.staging`):
   - انشر الفرع على بيئة staging (يفضّل بنسخة من بيانات الإنتاج).
   - شغّل `migrate` وراقب، ثم تحقّق أنّ سجلاً صحياً/سلوكياً يُقرأ صحيحاً (التشفير شفّاف).
   - لا تنتقل للإنتاج قبل نجاح staging.

---

## 🚀 2. النشر

4. **ادفع إلى `main`** (بعد commit):
   ```bash
   git add -A
   git commit -m "security/privacy/perf remediation + PDF fallback fix (75->90)"
   git push origin main
   ```
   Railway يبني الصورة ويشغّل `railway-release.sh`: `migrate` → seed → `collectstatic --clear` → `check --deploy` → daphne (بدور `shschool_app` مع RLS مُفرَض).

5. **راقب Logs مباشرةً** (Railway → Deployments → View Logs):
   - أثناء `clinic.0004`/`behavior.0013`/`transport.0003` قد تظهر آثار `InvalidToken` من `decrypt_field` — **غير ضارّة** (مسار fail-open أثناء تشفير النصّ الصريح القديم). المهم أن ينتهي كل migration بـ `OK`.
   - `check --deploy` يجب أن يمرّ.

---

## 🔍 3. بعد النشر — تحقّق

6. الصحّة: `curl https://<domain>/health/` و`/ready/` → 200.
7. سجّل الدخول، وافتح **سجلاً صحياً وسجل سلوك وحافلة** — تأكّد أنّ الحقول تُقرأ **نصاً صريحاً** (التشفير شفّاف؛ لو ظهر نصّ مشفّر فالمفتاح خطأ — راجع FERNET_KEY فوراً).
8. تأكّد أنّ توليد **PDF** يعمل (على Railux/Linux تتوفّر WeasyPrint) → 200 لا 503.
9. JWT: تسجيل خروج/تدوير توكن → التوكن القديم يُرفَض (blacklist فعّال).

---

## 🔄 4. التراجع (إن لزم)

- **الأسرع:** أعِد نشر الـ commit السابق في Railway (Deployments → Redeploy previous). لكن هذا **لا يفكّ تشفير البيانات** — الحقول تبقى مشفّرة والكود القديم (CharField) سيعرضها مشفّرة.
- **التراجع الكامل للتشفير:**
  ```bash
  python manage.py migrate clinic 0003
  python manage.py migrate behavior 0012
  python manage.py migrate transport 0002
  ```
  (backward يفكّ التشفير ويعيد الحقول). أو استعِد النسخة الاحتياطية من الخطوة 2.

---

## 🚫 5. محاذير

- **لا تشغّل `rotate_fernet_key` الآن** — فقط عند تدوير المفتاح، وبعد وضع القديم في `FERNET_OLD_KEYS`.
- **لا تحذف `FERNET_KEY` أبداً بعد النشر** — كل PII المشفّرة (وطنية/هاتف/صحة/سلوك) تصبح غير قابلة للفك.
- التشفير شفّاف للواجهات، لكن **الحقول المشفّرة لا يُبحَث فيها** — أُزيل `driver_phone` من بحث الإدارة مسبقاً؛ لا تُضِف بحثاً على حقل مشفّر.

---
*إصدار الإصلاحات مُتحقَّق منه محلياً (حزمة اختبارات خضراء). النشر عملية إنتاجية — النسخ الاحتياطي وstaging أولاً.*
