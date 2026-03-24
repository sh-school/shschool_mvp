# SchoolOS — منصة مدرسة الشحانية الذكية

> منصة إدارة مدرسية شاملة مبنية بـ Django 5.2 + PostgreSQL لمدرسة الشحانية الإعدادية الثانوية للبنين — دولة قطر

## المميزات الرئيسية

- **إدارة أكاديمية** — تقييمات وباقات درجات (40/60) حسب نظام وزارة التعليم القطري
- **حضور وجدولة** — حصص يومية + جدول أسبوعي ذكي مع كشف التعارضات + نظام البديل
- **سلوك الطلاب** — لائحة ABCD (20 مخالفة) + نقاط + استعادة نقاط
- **بوابة أولياء الأمور** — درجات + حضور + إشعارات (Email/SMS/Push/In-App)
- **ضمان الجودة** — خطة تشغيلية + لجان + مراجعة ذاتية + تقارير تقدم
- **كنترول الاختبارات** — جدولة + قاعات + مشرفين + محاضر مظاريف + حوادث
- **خدمات مدرسية** — عيادة + مكتبة + نقل مدرسي
- **تحليلات وتقارير** — KPIs + PDF/Excel + لوحات بيانات
- **حماية البيانات (PDPPL)** — تشفير Fernet + سجلات تدقيق غير قابلة للتعديل + إدارة الموافقات + طلبات المسح
- **Dark Mode** — وضع داكن تلقائي مع تبديل يدوي

## التقنيات

| المكون | التقنية |
|--------|---------|
| Backend | Django 5.2.12 + DRF 3.15 |
| Database | PostgreSQL 16 |
| Cache/Broker | Redis 7 |
| Real-time | Channels + Daphne (WebSocket) |
| Task Queue | Celery + celery-beat |
| Frontend | HTMX + Tailwind CSS + Vanilla JS |
| PDF | WeasyPrint + ReportLab |
| Excel | openpyxl + pandas |
| Auth | Session + JWT (SimpleJWT) + TOTP 2FA |
| Security | CSP + CORS + Rate Limiting + Fernet Encryption |
| Monitoring | Prometheus + Sentry |
| Deploy | Docker + Gunicorn + Nginx |

## المتطلبات

- Python 3.11+
- PostgreSQL 16+
- Redis 7+
- Node.js 18+ (لـ Tailwind فقط)

## التثبيت السريع

```bash
# 1. استنساخ المشروع
git clone https://github.com/your-org/shschool_mvp.git
cd shschool_mvp

# 2. إنشاء بيئة افتراضية
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 3. تثبيت المتطلبات
pip install -r requirements.txt

# 4. إعداد المتغيرات البيئية
cp .env.example .env
# عدّل .env: DATABASE_URL, SECRET_KEY, FERNET_KEY

# 5. تشغيل التهجيرات
python manage.py migrate

# 6. إنشاء مستخدم مدير
python manage.py createsuperuser

# 7. تغذية البيانات الأولية
python manage.py seed_all

# 8. تشغيل الخادم
python manage.py runserver
```

## التشغيل بـ Docker

```bash
# تطوير
docker compose up -d

# إنتاج
docker compose -f docker-compose.prod.yml up -d
```

## هيكل المشروع

```
shschool_mvp/
├── core/           # المستخدمون + الأدوار + التدقيق + التشفير
├── operations/     # الحصص + الحضور + الجداول + البدلاء
├── assessments/    # التقييمات + الباقات + الدرجات + النتائج
├── behavior/       # السلوك + لائحة ABCD + استعادة النقاط
├── quality/        # الجودة + الخطة التشغيلية + اللجان
├── notifications/  # Email + SMS + Push + In-App
├── parents/        # بوابة أولياء الأمور
├── analytics/      # التحليلات + KPIs
├── reports/        # تقارير PDF + Excel
├── clinic/         # العيادة المدرسية
├── library/        # المكتبة
├── transport/      # النقل المدرسي
├── exam_control/   # كنترول الاختبارات
├── breach/         # إبلاغ خروقات البيانات (PDPPL)
├── api/            # REST API v1
├── staging/        # استيراد البيانات
├── shschool/       # إعدادات Django
├── templates/      # قوالب HTML
├── static/         # CSS + JS + خطوط + أيقونات
└── tests/          # 1,002 اختبار
```

## API

- **Swagger UI:** `/api/v1/docs/`
- **ReDoc:** `/api/v1/redoc/`
- **OpenAPI Schema:** `/api/v1/schema/`

### المصادقة
```bash
# الحصول على JWT Token
curl -X POST /api/v1/auth/token/ -d '{"national_id":"12345","password":"..."}'

# استخدام Token
curl -H "Authorization: Bearer <token>" /api/v1/students/
```

## الأدوار والصلاحيات

| الدور | الرمز | الوصول |
|-------|-------|--------|
| مدير المدرسة | `principal` | كامل |
| نائب إداري | `vice_admin` | كامل (بتفويض) |
| نائب أكاديمي | `vice_academic` | أكاديمي + جودة |
| منسق | `coordinator` | قسمه |
| معلم | `teacher` | شُعَبه ومواده |
| أخصائي اجتماعي | `social_specialist` | سلوك الطلاب |
| ولي أمر | `parent` | أبناءه (قراءة) |
| طالب | `student` | بياناته (قراءة) |
| ممرض | `nurse` | العيادة |
| أمين مكتبة | `librarian` | المكتبة |
| مشرف حافلة | `bus_supervisor` | النقل |

## الاختبارات

```bash
# تشغيل كل الاختبارات
pytest

# مع تغطية
pytest --cov=. --cov-report=html

# اختبار تطبيق محدد
pytest tests/test_assessments.py
```

## CI/CD

- **GitHub Actions:** اختبارات + Ruff + Bandit + mypy عند كل push
- **تدقيق أسبوعي:** pip-audit + radon + vulture (كل أحد 6 صباحاً UTC)

## المعايير المطبقة

- **PDPPL** (قانون قطر 13/2016) — حماية البيانات الشخصية
- **OWASP Top 10** — أمن التطبيقات
- **WCAG 2.1 AA** — إمكانية الوصول
- **قرار 32/2019** — نظام التعليم القطري

## الترخيص

ملكية خاصة — مدرسة الشحانية الإعدادية الثانوية للبنين
