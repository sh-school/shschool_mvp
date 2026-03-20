# SchoolOS — منصة مدرسة الشحانية

نظام إدارة مدرسي متكامل | مدرسة الشحانية الإعدادية الثانوية للبنين | دولة قطر

---

## 🚀 التشغيل الفوري (Docker)

```bash
# 1. شغّل المشروع
docker-compose up --build

# 2. في terminal آخر — حقن البيانات الكاملة
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py seed_all --no-input

# 3. افتح المتصفح على http://localhost:8000
```

---

## 💻 التشغيل المحلي

```bash
# المتطلبات: Python 3.11+ و PostgreSQL 16

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
createdb shschool_db               # أو عدّل .env
python manage.py migrate
python manage.py seed_all          # حقن البيانات الكاملة
python manage.py runserver
```

---

## 📁 هيكل المشروع

```
shschool_mvp/
│
├── data/                          ◄ ملفات البيانات الحقيقية (CSV) — محمية في .gitignore
│   ├── 2_Normalized_Staff_List.csv       (126 موظف)
│   ├── new_students_full.csv             (742 طالب + أولياء أمور)
│   ├── 1_Clean_Operational_Plan.csv      (2896 إجراء)
│   ├── 4_Quality_Structure_v2.csv        (لجنة الجودة)
│   └── 3_Unique_Executors_Inventory.csv  (32 منفذ فريد)
│
├── scripts/
│   ├── seed_all.py        ★ حقن موحّد لكل المراحل
│   ├── real_seed.py         موظفون + طلاب + أولياء
│   └── seed_quality.py      خطة تشغيلية + لجنة جودة
│
├── core/                  المستخدمون، الأدوار، الفصول، النماذج المشتركة
├── operations/            الحضور، الجداول، البدلاء
├── assessments/           التقييمات، الدرجات، النتائج السنوية
├── quality/               الخطة التشغيلية، لجنة الجودة
├── parents/               بوابة أولياء الأمور (PWA)
├── notifications/         الإشعارات — Email + SMS
├── behavior/              السلوك الطلابي، لجنة الضبط
├── clinic/                العيادة المدرسية، السجل الصحي
├── transport/             الحافلات المدرسية
├── library/               المكتبة، الإعارة
├── analytics/             لوحة الإحصاءات والتحليلات
├── reports/               تقارير PDF، الشهادات
├── staging/               استيراد Excel
└── shschool/              إعدادات Django
```

---

## 🗂️ أوامر الحقن

| الأمر | الوظيفة |
|-------|---------|
| `python manage.py seed_all` | ★ حقن كامل — كل شيء بأمر واحد |
| `python manage.py real_seed` | موظفون + طلاب + أولياء الأمور |
| `python manage.py seed_quality` | خطة تشغيلية + لجنة الجودة |
| `python manage.py seed` | بيانات تجريبية (للتطوير فقط) |

---

## 🔑 بيانات الدخول (للتطوير فقط)

> **تحذير:** في بيئة الإنتاج يجب تغيير كل كلمات المرور فور أول تشغيل.
> النظام يُجبر على تغيير كلمة المرور عبر `must_change_password = True`.

| الدور | الرقم الوطني | كلمة المرور |
|-------|-------------|-------------|
| مدير المدرسة | `28763400678` | `school@2026` |
| معلم / منسق | الرقم الوطني | `school@2026` |
| طالب | الرقم الوطني | `student@2026` |
| ولي أمر | الرقم الوطني | `parent@2026` |

---

## 📊 البيانات المحقونة

| | العدد |
|-|-------|
| موظفون | 126 |
| طلاب | 742 |
| أولياء أمور | ~562 |
| فصول دراسية | 28 |
| إجراءات الخطة | 2,896 |
| مجالات الخطة | 7 |
| لجنة الجودة | 11 عضو |

---

## 👨‍👩‍👧 بوابة أولياء الأمور

بوابة مكتملة تُتيح لولي الأمر متابعة أبنائه مباشرة.

### الوصول
- الرابط: `/parents/`
- يتطلب دور `parent` في النظام
- يدعم الموظف الذي هو أيضاً ولي أمر (dual role)

### المميزات
| الميزة | الوصف |
|--------|-------|
| **لوحة التحكم** | ملخص فوري: الدرجات + الغياب + الحالة |
| **الدرجات** | نتائج كل مادة — الفصل الأول والثاني والمجموع السنوي |
| **الغياب** | سجل الحضور والغياب لآخر 30 يوماً |
| **الموافقة على البيانات** | إدارة الموافقة على معالجة البيانات (PDPPL) |
| **تعدد الأبناء** | يعرض كل أبناء ولي الأمر في صفحة واحدة |

### PWA (تطبيق الجوال)
البوابة تدعم PWA — يمكن تثبيتها كتطبيق على الجوال:
- ملف `manifest.json` موجود في `/templates/parents/pwa/`
- ملف `sw.js` (Service Worker) يدعم التشغيل بدون إنترنت
- لتفعيل Push Notifications يحتاج إعداد إضافي (مهمة مستقبلية)

### ربط ولي الأمر بأبنائه
```bash
# ربط أولياء الأمور بأبنائهم من CSV
python manage.py import_students_parents

# أو يدوياً عبر Admin
# /admin/core/parentstudenlink/
```

---

## ✅ المراحل المكتملة

| المرحلة | الوصف | الحالة |
|---------|-------|--------|
| 0 | Auth + RBAC (12 دور) + Django Admin عربي | ✅ مكتمل |
| 1 | تسجيل الحضور الفوري بـ HTMX + إشعارات غياب | ✅ مكتمل |
| 2 | الجداول الذكية + نظام البديل + كشف التعارضات | ✅ مكتمل |
| 3 | التقييمات + الدرجات + معادلات MOEHE (40/60) | ✅ مكتمل |
| 4 | السلوك + لجنة الضبط + استعادة النقاط | ✅ مكتمل |
| 5 | الخطة التشغيلية + لجنة الجودة + QNSA | ✅ مكتمل |
| — | بوابة أولياء الأمور + PWA | ✅ مكتمل |
| — | الإشعارات Email + Twilio SMS | ✅ مكتمل |
| — | التحليلات + لوحة الإحصاءات | ✅ مكتمل |
| — | العيادة + السجل الصحي (Fernet) | ✅ مكتمل |
| — | المكتبة + الإعارة | ✅ مكتمل |
| — | النقل + الحافلات | ✅ مكتمل |
| — | تقارير PDF (WeasyPrint) | ✅ مكتمل |

## 🔲 المراحل القادمة

| المرحلة | الوصف |
|---------|-------|
| 6 | تقييم أداء الموظفين (مطلوب قانونياً — قانون 9/2017) |
| — | Celery + Redis للإشعارات async |
| — | Push Notifications للـ PWA |
| — | تكامل GPS لتتبع الحافلات |

---

## 🔐 الأمان والامتثال

- **PDPPL**: بيانات صحية مشفرة بـ Fernet + ConsentRecord لأولياء الأمور
- **2FA**: مصادقة ثنائية للمدير والنواب (TOTP)
- **Brute Force**: قفل الحساب بعد 5 محاولات لمدة 15 دقيقة
- **AuditLog**: سجل شامل لكل العمليات الحساسة (IP + UserAgent + timestamp)
- **CSP**: Content Security Policy مضبوط في الإنتاج

### قبل النشر الإنتاجي
```bash
# تأكد من ضبط هذه المتغيرات في .env
SECRET_KEY=<مفتاح قوي جديد>
FERNET_KEY=<مفتاح Fernet جديد>
DEBUG=False
ALLOWED_HOSTS=<الدومين الحقيقي>
DB_PASSWORD=<كلمة مرور قوية>

# توليد مفتاح سري جديد
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# توليد مفتاح Fernet جديد
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# فحص الإعدادات
python manage.py check --deploy --settings=shschool.settings.production
```

---

**Tech Stack:** Django 5 · PostgreSQL 16 · HTMX · Tailwind CSS · Docker · WeasyPrint · Twilio
