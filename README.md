# 🏫 SchoolOS v5 — مدرسة الشحانية

> **نظام إدارة مدرسي متكامل | Django 5.2 · PostgreSQL 16 · Redis · Celery · HTMX · WeasyPrint**

---

## 🆕 ما الجديد في v5 (مارس 2026)

| التغيير | الملف | الحالة |
|---------|-------|--------|
| ✅ لائحة مخالفات ABCD (20 مخالفة) | `behavior/models.py` → `ViolationCategory` | مكتمل |
| ✅ وحدة كنترول الاختبارات (SOP كامل) | `exam_control/` — app جديد | مكتمل |
| ✅ 10 KPIs بصيغ Ct.zip الرياضية | `analytics/views.py` → `api_kpis_all` | مكتمل |
| ✅ لوحة KPIs | `templates/analytics/kpi_dashboard.html` | مكتمل |
| ✅ نماذج Word في static/forms/ | `static/forms/*.docx` | مكتمل |
| ✅ حذف release2/ (كود ميت) | — | مكتمل |

---

## 🚀 تشغيل سريع

```bash
# 1. توليد مفاتيح جديدة قبل أي نشر (إلزامي)
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
# → ضع النتيجة في .env → SECRET_KEY=...
# → وكذلك FERNET_KEY جديد

# 2. تثبيت المتطلبات
pip install -r requirements.txt

# 3. Migrations
python manage.py migrate

# 4. تغذية لائحة ABCD (مرة واحدة)
python manage.py seed_abcd

# 5. تغذية البيانات الكاملة
python manage.py seed_all

# 6. تشغيل محلي
python manage.py runserver
```

---

## 📦 الوحدات الـ 19 (18 + كنترول جديد)

| # | الوحدة | المسار |
|---|--------|--------|
| 1 | Auth + RBAC (12 دور) | `core/` |
| 2 | الحضور + HTMX | `operations/` |
| 3 | الجداول + البديل | `operations/` |
| 4 | الجودة + QNSA | `quality/` |
| 5 | تقييم الموظفين Phase 6 | `quality/evaluation_views.py` |
| 6 | التقييمات الأكاديمية | `assessments/` |
| 7 | بوابة أولياء الأمور + PWA | `parents/` |
| 8 | الإشعارات Celery async | `notifications/` |
| 9 | السلوك + ABCD ✅v5 | `behavior/` |
| 10 | التحليلات + KPIs ✅v5 | `analytics/` |
| 11 | العيادة + Fernet | `clinic/` |
| 12 | المكتبة | `library/` |
| 13 | النقل | `transport/` |
| 14 | التقارير PDF | `reports/` |
| 15 | الاستيراد (Staging) | `staging/` |
| 16 | الإشعارات | `notifications/` |
| 17 | البنية التحتية Docker | `docker-compose.yml` |
| 18 | بيانات حقيقية 100% | `core/management/commands/seed_all.py` |
| 19 | **كنترول الاختبارات ✅v5** | **`exam_control/`** |

---

## 📋 متطلبات ما قبل النشر

- [ ] تجديد `SECRET_KEY` و`FERNET_KEY` (مكشوفة في zip)
- [ ] إنشاء أيقونات PWA `icon-192.png` / `icon-512.png` (الألوان: `#8A1538`)
- [ ] تشغيل `npx tailwindcss` لتصريف CSS (إزالة CDN)
- [ ] إعداد وثيقة DPIA (قرار إداري — PDPPL م.11)
- [ ] تعيين DPO وتوثيقه
- [ ] جدولة `backup.sh` (cron يومي 2:00 ص)

---

## 🔗 روابط مهمة

| الصفحة | الرابط |
|--------|--------|
| لوحة KPIs العشرة | `/analytics/kpis/` |
| كنترول الاختبارات | `/exam-control/` |
| لوحة Analytics | `/analytics/` |
| السلوك + ABCD | `/behavior/` |
| إدارة الجودة QNSA | `/quality/` |
| Admin Django | `/admin/` |

---

## 📁 static/forms/ — نماذج Ct.zip

| الملف | الغرض |
|-------|--------|
| `form_student_warning.docx` | إنذار سلوكي (6 توقيعات) |
| `form_parent_undertaking.docx` | تعهد ولي الأمر |
| `form_student_undertaking.docx` | تعهد الطالب |
| `exam_control_handbook.docx` | دليل الكنترول SOP كامل |
| `Handbook_SmartSchool_2026.md` | دليل التشغيل الذكي |
| `Policy_StudentProtection.md` | سياسة الحماية والرعاية |
| `Template_IncidentReport.md` | قالب محضر الحوادث |

---

*v5 — مارس 2026 | SchoolOS × Ct.zip Integration*
