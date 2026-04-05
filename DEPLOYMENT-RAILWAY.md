# 🚀 نشر SchoolOS على Railway — دليل خطوة بخطوة

> **وقت النشر المتوقع:** 30-45 دقيقة
> **الدومين التجريبي:** `schoolos-mvp-production.up.railway.app` (يُنشأ تلقائياً)

---

## 📋 المتطلبات المسبقة

- ✅ حساب GitHub (متوفر: `sh-school/shschool_mvp`)
- ⬜ حساب Railway ([railway.app](https://railway.app))
- ⬜ بطاقة ائتمان (اختياري — للتفعيل الكامل، $5 credit مجاني شهرياً)

---

## 🎯 الخطوات الكاملة

### 1️⃣ إنشاء حساب Railway (5 دقائق)

```
1. اذهب إلى: https://railway.app
2. انقر "Login" → "Login with GitHub"
3. وافق على صلاحيات GitHub
4. ستحصل على $5 credit مجاني شهرياً
```

### 2️⃣ إنشاء مشروع جديد (3 دقائق)

```
1. في Railway Dashboard → "New Project"
2. اختر: "Deploy from GitHub repo"
3. اختر: sh-school/shschool_mvp
4. Branch: main
5. Railway سيكتشف Dockerfile تلقائياً
```

### 3️⃣ إضافة Services (5 دقائق)

في نفس الـ Project:

**PostgreSQL:**
```
+ New → Database → PostgreSQL
Railway يُنشئ:
  - PostgreSQL 16 instance
  - يحقن DATABASE_URL تلقائياً
```

**Redis:**
```
+ New → Database → Redis
Railway يُنشئ:
  - Redis instance
  - يحقن REDIS_URL تلقائياً
```

### 4️⃣ تحضير Environment Variables (10 دقائق)

**أ) توليد المفاتيح الحرجة (من الـ terminal المحلي):**

```bash
# SECRET_KEY
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# FERNET_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**ب) في Railway → شركة Variables:**

انسخ من `.env.railway.example` وأضف القيم التالية (الحدّ الأدنى):

| المتغير | القيمة |
|---------|--------|
| `DJANGO_SETTINGS_MODULE` | `shschool.settings.production` |
| `SECRET_KEY` | (من الأمر أعلاه) |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `.up.railway.app,.railway.app` |
| `FERNET_KEY` | (من الأمر أعلاه) |
| `SECURE_SSL_REDIRECT` | `True` |
| `CELERY_BROKER_URL` | `${{Redis.REDIS_URL}}` |
| `CELERY_RESULT_BACKEND` | `${{Redis.REDIS_URL}}` |
| `TIME_ZONE` | `Asia/Qatar` |
| `LANGUAGE_CODE` | `ar` |

> **ملاحظة:** `DATABASE_URL` و `REDIS_URL` يُحقنان تلقائياً من Plugins.

### 5️⃣ Deploy + Watch Logs (15 دقيقة)

```
1. Railway يبني Docker image تلقائياً
2. يُنفّذ scripts/railway-release.sh:
   - Migrations
   - Collectstatic
3. يُشغّل gunicorn
4. يولّد domain: schoolos-mvp-production.up.railway.app
```

راقب Logs في Railway Dashboard → Deployments → View Logs

### 6️⃣ اختبار النشر (5 دقائق)

```bash
# Health check
curl https://schoolos-mvp-production.up.railway.app/health/

# Ready check
curl https://schoolos-mvp-production.up.railway.app/ready/

# Admin (بعد createsuperuser)
https://schoolos-mvp-production.up.railway.app/admin/
```

---

## 🔧 إضافة Worker + Beat (Celery)

في Railway Project:

```
+ New → Empty Service
  Name: worker
  Start Command: celery -A shschool worker --loglevel=info

+ New → Empty Service
  Name: beat
  Start Command: celery -A shschool beat --loglevel=info
```

**ملاحظة:** كلاهما يحتاج نفس environment variables + DATABASE_URL + REDIS_URL.

---

## 🌐 إضافة Custom Domain (عندما تشتري الدومين)

```
1. Railway → Settings → Domains
2. Click "Generate Domain" (للتجريبي) أو "Custom Domain"
3. أدخل: schoolos.qa (مثال)
4. أضف DNS record (CNAME) في مزوّد الدومين:
   CNAME @  → schoolos-mvp-production.up.railway.app
5. انتظر 5-60 دقيقة لـ DNS propagation
6. Railway يُصدر SSL certificate تلقائياً (Let's Encrypt)
```

---

## 💰 التكاليف المتوقعة (Railway)

| المكون | التكلفة الشهرية |
|--------|-----------------|
| Django Web Service | ~$3 |
| PostgreSQL 16 | ~$5 |
| Redis | ~$3 |
| Celery Worker | ~$3 |
| Celery Beat | ~$2 |
| **الإجمالي** | **~$16/شهر** |

> **Free tier:** $5 credit شهرياً → يغطي جزءاً من التكلفة.
> **Hobby plan:** $5/شهر + usage-based pricing.

---

## 🔄 Auto-Deploy على كل Push

Railway مُفعّل تلقائياً:
- كل push إلى `main` → Auto deploy
- Preview deployments للـ PRs (اختياري)

---

## 🆘 استكشاف الأخطاء

### المشكلة: "Application failed to start"
**الحل:** راجع Logs، الأسباب الشائعة:
- `SECRET_KEY` مفقود
- `DATABASE_URL` غير مربوط بـ PostgreSQL plugin
- Dependencies غير مثبتة في Dockerfile

### المشكلة: "static files not loading"
**الحل:**
```bash
# تأكد من Whitenoise في MIDDLEWARE:
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # ← أضفه
    ...
]

STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
```

### المشكلة: "CSRF verification failed"
**الحل:** أضف في settings/production.py:
```python
CSRF_TRUSTED_ORIGINS = [
    'https://*.up.railway.app',
    'https://*.railway.app',
]
```

---

## ✅ Checklist النشر الأول

- [ ] حساب Railway مُنشأ
- [ ] GitHub repo مربوط
- [ ] PostgreSQL plugin مُضاف
- [ ] Redis plugin مُضاف
- [ ] Environment variables مُعدّة
- [ ] `SECRET_KEY` مُولّد
- [ ] `FERNET_KEY` مُولّد
- [ ] Deploy نجح
- [ ] `/health/` يُرجع 200
- [ ] `/admin/` يعمل
- [ ] Worker + Beat مُضافان
- [ ] Custom domain (اختياري)

---

## 📞 بعد النشر الناجح

أخبرني بالرابط الذي تحصل عليه وسأ:
1. أختبر endpoints الأساسية
2. أُحدّث `context.json` → `deployment.environment: "staging-live"`
3. أكتب ADR-016: "First Production Deploy"
4. أُضيف الـ URL إلى portfolio registry

---

**تاريخ الإعداد:** 2026-04-05
**المسؤول:** elite-devops
**الإصدار:** v5.4
