<p align="center">
  <img src="assets/brand/qatar-emblem-2022.svg" alt="شعار دولة قطر" width="88" />
</p>

<h1 align="center">🏫 SchoolOS v5.1 — منصة الشحانية الذكية</h1>

<p align="center">
  نظام متكامل لإدارة وتشغيل المدارس الحكومية في دولة قطر — يغطّي النطاق الأكاديمي والإداري والسلوكي والصحي والرقمي،<br>
  مع امتثال كامل لـ <strong>QNSA</strong> و<strong>PDPPL</strong>.
</p>

<p align="center">
  <img alt="Django" src="https://img.shields.io/badge/Django-5.2-092E20?logo=django&logoColor=white" />
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" />
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-16-316192?logo=postgresql&logoColor=white" />
  <img alt="Redis" src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white" />
  <img alt="CI" src="https://img.shields.io/badge/CI-GitHub_Actions_%E2%9C%85-2088FF?logo=githubactions&logoColor=white" />
  <img alt="Coverage" src="https://img.shields.io/badge/Coverage-%E2%89%A580%25-brightgreen" />
  <img alt="License" src="https://img.shields.io/badge/License-Internal_Use-8A1538" />
</p>

---

## 📑 فهرس المحتويات

- [نبذة مختصرة](#-نبذة-مختصرة)
- [التقنيات والحزمة التقنية](#️-التقنيات-والحزمة-التقنية)
- [الجديد في v5.1 — مارس 2026](#-الجديد-في-v51--مارس-2026)
- [تشغيل سريع](#-تشغيل-سريع)
- [متغيرات البيئة](#️-متغيرات-البيئة)
- [الوحدات](#-الوحدات)
- [الهيكل المجلدي](#-الهيكل-المجلدي)
- [قواعد البيانات والترحيلات](#️-قواعد-البيانات-والترحيلات)
- [الأمن والامتثال](#-الأمن-والامتثال)
- [الجودة والاختبارات](#-الجودة-والاختبارات)
- [CI/CD](#-cicd)
- [النشر — Docker Compose](#-النشر--docker-compose)
- [النسخ الاحتياطي والاستعادة](#-النسخ-الاحتياطي-والاستعادة)
- [إدارة الإصدارات](#-إدارة-الإصدارات)
- [نماذج ومستندات رسمية](#-نماذج-ومستندات-رسمية)
- [الهوية والشعارات](#-الهوية-والشعارات)
- [الرخصة والدعم](#-الرخصة-والدعم)

---

## 📌 نبذة مختصرة

**SchoolOS v5.1** منصة موحّدة لإدارة عمليات **مدرسة الشحانية الإعدادية الثانوية للبنين** — مدرسة حكومية قطرية مجانية تابعة لوزارة التربية والتعليم والتعليم العالي.

تشمل المنصة: الأشخاص، الحضور، السلوك، الصحة، التقييمات، كنترول الاختبارات، الجداول، الجودة، التحليلات، الإشعارات، المكتبة، النقل، بوابة أولياء الأمور — مع دعم متعدد المدارس (Multi-School) من البنية الأساسية.

> **⚠️ ملاحظة:** لا رسوم مدرسية — المنصة حكومية بالكامل. وحدات الدفع والرسوم خارج نطاق المشروع.

---

## 🏗️ التقنيات والحزمة التقنية

| الطبقة | التقنية |
|--------|---------|
| **Backend** | Django 5.2 (Python 3.11+) |
| **قاعدة البيانات** | PostgreSQL 16 |
| **Cache / Queue** | Redis 7 + Celery 5.3 + django-celery-beat |
| **Frontend** | HTMX 1.9 + Tailwind CSS 3.4 + Tajawal (خط عربي) |
| **تقارير PDF** | WeasyPrint 68 + ReportLab |
| **API** | Django REST Framework 3.15 + drf-spectacular (OpenAPI) |
| **Auth** | Session + JWT (simplejwt) + RBAC مخصص |
| **تشفير البيانات** | Fernet (cryptography) للحقول الحساسة |
| **Push Notifications** | VAPID + pywebpush + Celery |
| **خادم الإنتاج** | Gunicorn + Nginx (Docker Compose) |
| **CI/CD** | GitHub Actions — Ruff / Bandit / pytest / mypy |
| **المراقبة** | صحة الخدمة عبر `/health/` |

---

## 🆕 الجديد في v5.1 — مارس 2026

| الإنجاز | المسار | الحالة |
|---------|--------|--------|
| لائحة مخالفات ABCD (20 مخالفة) | `behavior/models.py → ViolationCategory` | ✅ مكتمل |
| وحدة كنترول الاختبارات (SOP كامل) | `exam_control/` | ✅ مكتمل |
| 10 KPIs رياضية | `analytics/views.py → api_kpis_all` | ✅ مكتمل |
| لوحة KPIs | `templates/analytics/kpi_dashboard.html` | ✅ مكتمل |
| نماذج Word رسمية | `static/forms/*.docx` | ✅ مكتمل |
| CI/CD pipeline كامل | `.github/workflows/ci.yml` + `quality.yml` | ✅ مكتمل |
| اختبارات تلقائية (≥80% coverage) | `tests/` — pytest + coverage | ✅ أخضر |
| تحليل ثابت للأمن | Bandit + Ruff + mypy | ✅ أخضر |
| نظام جودة التحقق | `quality/models.py` — ORM annotations | ✅ مكتمل |

---

## ⚡ تشغيل سريع

```bash
# 1. استنسخ المستودع
git clone <repo-url> shschool_mvp
cd shschool_mvp

# 2. أعدّ متغيرات البيئة
cp .env.example .env
# عدّل .env بمفاتيحك الخاصة

# 3. شغّل بـ Docker Compose (بيئة تطوير)
docker compose up -d

# 4. نفّذ الترحيلات والبذر
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_all

# 5. أنشئ مستخدم مدير
docker compose exec web python manage.py createsuperuser

# 6. بنِ Tailwind CSS
npm install && npm run build

# افتح في المتصفح
# http://localhost:8000
```

> للبيئة المحلية بدون Docker:
> ```bash
> python -m venv venv && source venv/bin/activate
> pip install -r requirements.txt
> cp .env.example .env   # ثم عدّل القيم
> python manage.py migrate && python manage.py runserver
> ```

---

## ⚙️ متغيرات البيئة

انسخ `.env.example` إلى `.env` وعدّل القيم. أهم المتغيرات:

| المتغير | الوصف | مثال |
|---------|-------|------|
| `SECRET_KEY` | مفتاح Django السري (≥50 حرف) | `django-insecure-...` |
| `DEBUG` | وضع التطوير | `False` في الإنتاج |
| `ALLOWED_HOSTS` | النطاقات المسموحة | `schoolos.qa,www.schoolos.qa` |
| `DB_NAME / DB_USER / DB_PASSWORD` | بيانات PostgreSQL | — |
| `DB_HOST / DB_PORT` | مضيف وبورت DB | `db` / `5432` (Docker) |
| `REDIS_URL` | اتصال Redis | `redis://redis:6379/0` |
| `FERNET_KEY` | مفتاح تشفير الحقول الحساسة | ناتج `Fernet.generate_key()` |
| `EMAIL_HOST / EMAIL_PORT` | SMTP للإشعارات | — |
| `VAPID_PRIVATE_KEY / VAPID_PUBLIC_KEY` | Web Push | — |
| `DPO_NAME / DPO_EMAIL / DPO_PHONE` | مسؤول حماية البيانات (PDPPL) | — |
| `SENTRY_DSN` | مراقبة الأخطاء (اختياري) | — |
| `AWS_BACKUP_BUCKET` | نسخ احتياطي S3 (اختياري) | — |

> **قبل الإنتاج — Checklist:**
> - [ ] `SECRET_KEY` و`FERNET_KEY` جديدان وسريّان
> - [ ] `DEBUG=False` و`ALLOWED_HOSTS` محدودة
> - [ ] HTTPS + HSTS على Nginx
> - [ ] مستخدم DB بصلاحيات محدودة
> - [ ] جدولة نسخ احتياطي يومي (02:00 توقيت قطر)
> - [ ] إتمام DPIA وفق PDPPL مادة 11
> - [ ] تعيين DPO موثق

---

## 🧩 الوحدات

| الوحدة | المسار | الوصف |
|--------|--------|-------|
| **Core / RBAC** | `core/` | هوية الموحّدة، أدوار، صلاحيات، مدارس |
| **العمليات والحضور** | `operations/` | الجداول، الحضور، الغياب، الحصص |
| **السلوك** | `behavior/` | لائحة ABCD، 20 مخالفة، الإجراءات التأديبية |
| **التقييمات** | `assessments/` | اختبارات، درجات، نتائج |
| **كنترول الاختبارات** | `exam_control/` | SOP كامل: إصدار / تجميع / مراقبة / رصد |
| **العيادة** | `clinic/` | سجلات طبية مشفرة بـ Fernet |
| **الجودة** | `quality/` | QNSA، لجان، إجراءات، محاضر |
| **التحليلات** | `analytics/` | لوحة KPIs، 10 مؤشرات رياضية |
| **الإشعارات** | `notifications/` | بريد داخلي، push، مهام Celery |
| **المكتبة** | `library/` | كتب، استعارات، فهارس |
| **النقل** | `transport/` | خطوط، حافلات، سائقون |
| **بوابة أولياء الأمور** | `parents/` | عرض الغياب والدرجات والإشعارات |
| **التقارير** | `reports/` | قوالب PDF رسمية (WeasyPrint) |
| **الاستيراد** | `staging/` | ETL لاستيراد البيانات من مصادر خارجية |
| **إدارة الانتهاكات** | `breach/` | تسجيل انتهاكات البيانات (PDPPL 72 ساعة) |
| **API** | `api/` | REST API v1 (DRF + OpenAPI) |

---

## 📁 الهيكل المجلدي

```
shschool_mvp/
├── core/                    # هوية / RBAC / مدارس
├── operations/              # جداول / حضور / غياب
├── assessments/             # تقييمات / درجات
├── behavior/                # سلوك / مخالفات ABCD
├── exam_control/            # كنترول الاختبارات
├── clinic/                  # عيادة (حقول مشفرة)
├── quality/                 # جودة / QNSA / لجان
├── analytics/               # KPIs / تحليلات
├── notifications/           # إشعارات / Celery
├── library/                 # مكتبة
├── transport/               # نقل مدرسي
├── parents/                 # بوابة أولياء الأمور
├── reports/                 # PDF
├── staging/                 # استيراد بيانات
├── breach/                  # انتهاكات PDPPL
├── api/                     # REST API v1
│
├── shschool/                # إعدادات المشروع
│   ├── settings/
│   │   ├── base.py          # الإعدادات المشتركة
│   │   ├── development.py
│   │   ├── production.py
│   │   └── testing.py
│   ├── urls.py
│   ├── wsgi.py
│   └── celery.py
│
├── templates/               # قوالب HTML (HTMX)
│   ├── base/
│   ├── components/          # مكوّنات قابلة للإعادة
│   └── <app>/
│
├── static/
│   ├── css/custom.css       # نظام تصميم قطر (Maroon #8A1538)
│   ├── js/
│   └── forms/               # نماذج Word/Markdown رسمية
│
├── nginx/                   # إعدادات Nginx
├── assets/brand/            # شعارات وهوية بصرية
├── AAdocs/                  # وثائق تحليلية وقانونية
│
├── docker-compose.yml       # بيئة التطوير
├── docker-compose.prod.yml  # بيئة الإنتاج (8 خدمات)
├── Dockerfile               # Python 3.11-slim
├── requirements.txt         # ~125 حزمة
├── pyproject.toml           # Ruff + pytest + mypy + coverage
├── package.json             # Tailwind CSS
├── .env.example             # 52 متغير موثَّق
├── backup.sh                # نسخ احتياطي PostgreSQL يومي
├── Makefile                 # أوامر مختصرة
└── gunicorn.conf.py         # إعداد Gunicorn
```

---

## 🗄️ قواعد البيانات والترحيلات

```bash
# تنفيذ الترحيلات
python manage.py migrate

# إنشاء ترحيل جديد
python manage.py makemigrations <app>

# فحص بدون تطبيق
python manage.py makemigrations --check --dry-run

# بذر البيانات الأولية
python manage.py seed_abcd   # 20 مخالفة ABCD القياسية
python manage.py seed_all    # بيانات النظام الأولية
```

**أفضل الممارسات:**
- ترحيلات **idempotent** قدر الإمكان
- لا تعديل مباشر على جداول الإنتاج — Migration دائمًا
- فهارس مناسبة على الحقول المُستعلَم عنها كثيرًا
- مستخدم DB بصلاحيات محدودة في الإنتاج

---

## 🔐 الأمن والامتثال

| المجال | التفاصيل |
|--------|---------|
| **PDPPL** | DPIA، DPO مُعيَّن، سجلات معالجة، إشعار 72 ساعة عند انتهاك |
| **QNSA** | قائمة تدقيق وحدة `quality/` + إجراءات موثَّقة |
| **تشفير البيانات** | Fernet لحقول العيادة والهوية الحساسة |
| **Auth** | Session + JWT (access 1h / refresh 7d) + RBAC دقيق |
| **CSP** | `django-csp` بـ nonce على الـ scripts — Report-Only → Enforced |
| **Rate Limiting** | 30/min (مجهول) / 120/min (مستخدم) عبر `django-ratelimit` |
| **حماية المستودع** | Branch Protection على `main` — منع force-push + إلزام PR |
| **CodeQL + Secret Scanning** | مفعَّل على المستودع |
| **Bandit** | تحليل أمني ثابت على كل CI run |

---

## 🧪 الجودة والاختبارات

**حد التغطية:** ≥ **80%** (CI تفشل دون ذلك)

```bash
# تشغيل الاختبارات مع التغطية
pytest --cov=. --cov-report=term-missing -q

# تنسيق وفحص الكود
ruff check .
ruff format .

# فحص الأمن
bandit -r . -x tests/,venv/

# فحص الأنواع
mypy . --ignore-missing-imports

# فحص Django
python manage.py check
```

**أوامر Makefile:**
```bash
make test       # pytest كامل مع coverage
make lint       # ruff check
make security   # bandit
make type       # mypy
make ci         # كل الفحوصات معًا
```

---

## 🔄 CI/CD

**GitHub Actions** — 5 jobs تعمل على كل PR وكل push لـ `main`:

| الـ Job | الأداة | الوصف |
|---------|--------|-------|
| `lint` | Ruff | فحص تنسيق الكود وجودته |
| `security` | Bandit | كشف الثغرات الأمنية الثابتة |
| `test` | pytest + coverage | اختبارات تلقائية مع تغطية ≥80% |
| `type-check` | mypy | فحص أنواع Python |
| `ci-summary` | — | تقرير موحَّد بحالة كل الـ jobs |

**إضافي:** `.github/workflows/quality.yml` — فحص أسبوعي شامل للجودة.

**حماية `main`:** لا دمج إلا بعد اجتياز كل الـ jobs + مراجعة PR.

---

## ☁️ النشر — Docker Compose

**بيئة الإنتاج تتكوّن من 8 خدمات:**

| الخدمة | الصورة | الدور |
|--------|--------|-------|
| `web` | `./Dockerfile` | Django — Gunicorn (port 8000) |
| `db` | `postgres:16-alpine` | قاعدة البيانات الرئيسية |
| `redis` | `redis:7-alpine` | Cache + Celery broker (256MB LRU) |
| `celery_worker` | `./Dockerfile` | معالجة المهام غير المتزامنة (2 workers) |
| `celery_beat` | `./Dockerfile` | جدولة المهام المتكررة |
| `backup` | `./Dockerfile` | نسخ احتياطي يومي 02:00 |
| `nginx` | `nginx:alpine` | Reverse proxy + TLS + static files |

**شبكتان منفصلتان:** `internal` (خدمات ↔ خدمات) / `external` (nginx ↔ web فقط)

```bash
# تشغيل الإنتاج
docker compose -f docker-compose.prod.yml up -d

# مراقبة السجلات
docker compose -f docker-compose.prod.yml logs -f web

# فحص الصحة
curl http://localhost/health/
```

---

## 💾 النسخ الاحتياطي والاستعادة

**الآلية الحالية (`backup.sh`):**
- `pg_dump` يومي الساعة 02:00 توقيت قطر
- ضغط gzip تلقائي
- الاحتفاظ بـ **14 يومًا** محليًا
- حذف تلقائي للنسخ الأقدم

```bash
# تشغيل يدوي
./backup.sh

# استعادة من نسخة احتياطية
gunzip -c backups/db_YYYYMMDD.sql.gz | psql -U $DB_USER $DB_NAME
```

**الاحتياجات المستقبلية (قيد التطوير):**
- رفع تلقائي لـ S3 / Wasabi
- RUNBOOK.md للاستعادة في الحوادث
- اختبار استعادة شهري (DR drill)

---

## 🏷️ إدارة الإصدارات

- **Semantic Versioning:** `v5.x.y`
- **الفرع الرئيسي:** `main` — محمي دائمًا
- **استراتيجية الفروع:**
  - ميزات: `feature/<name>`
  - إصلاحات عاجلة: `hotfix/<name>`
  - وثائق: `docs/<name>`
- **الدمج:** Squash فقط على `main`
- **تعليقات الـ Commits:** `feat:` / `fix:` / `refactor:` / `docs:` / `test:`

---

## 🗂️ نماذج ومستندات رسمية

مجلد `static/forms/`:

| الملف | الوصف |
|-------|-------|
| `form_student_warning.docx` | إنذار سلوكي (6 توقيعات) |
| `form_parent_undertaking.docx` | تعهد ولي الأمر |
| `form_student_undertaking.docx` | تعهد الطالب |
| `exam_control_handbook.docx` | دليل كنترول الاختبارات (SOP كامل) |
| `Handbook_SmartSchool_2026.md` | دليل التشغيل الذكي 2026 |
| `Policy_StudentProtection.md` | سياسة الحماية والرعاية |
| `Template_IncidentReport.md` | قالب محضر الحوادث |

---

## 🎨 الهوية والشعارات

**ألوان النظام (Qatar Design System):**

| اللون | الكود | الاستخدام |
|-------|-------|-----------|
| Maroon | `#8A1538` | اللون الأساسي — الأزرار والعناوين |
| Maroon Dark | `#6b0f2a` | Hover states |
| Gold | `#C49A3C` | التمييز والإنجاز |
| Light Green | `#7FD1AE` | الحضور والنجاح |
| Light Blue | `#9ED9FF` | المعلومات |

**الخط:** Tajawal (Google Fonts) — عربي حديث مناسب للواجهات

**مسارات الشعارات:**
```
assets/brand/qatar-emblem-2022.svg   ← شعار الدولة (Placeholder)
assets/brand/school-logo.svg         ← شعار المدرسة
```

**CSS Design System:** `static/css/custom.css` (695+ سطر) — متغيرات CSS، مكوّنات، RTL.

---

## 🔗 روابط النظام السريعة

| الصفحة | المسار |
|--------|--------|
| لوحة التحكم | `/` |
| لوحة KPIs العشرة | `/analytics/kpis/` |
| الحضور والغياب | `/operations/attendance/` |
| السلوك + ABCD | `/behavior/` |
| كنترول الاختبارات | `/exam-control/` |
| إدارة الجودة QNSA | `/quality/` |
| بوابة أولياء الأمور | `/parents/` |
| Django Admin | `/admin/` |
| API Docs (Swagger) | `/api/schema/swagger-ui/` |
| فحص الصحة | `/health/` |

---

## 📬 الرخصة والدعم

**الرخصة:** استخدام داخلي — مدرسة الشحانية الإعدادية الثانوية للبنين، دولة قطر.
يُمنع النشر أو التوزيع الخارجي دون إذن إداري مكتوب.

**الدعم:** تواصل مع مطوّر النظام داخل المدرسة لأي طلبات دعم أو تحسينات.

---

<p align="center">
  <sub>SchoolOS v5.1 — بُنيت بـ ❤️ لمدارس قطر الحكومية | مارس 2026</sub>
</p>
