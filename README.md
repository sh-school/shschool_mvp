<p align="center">
  <!-- Qatar Emblem (Placeholder): replace with the official modern SVG when available -->
  <img src="assets/brand/qatar-emblem-2022.svg" alt="Qatar Emblem" width="96" />
</p>

<h1 align="center">🏫 SchoolOS v5 — منصة الشحانية الذكية</h1>

<p align="center">
  نظام متكامل لإدارة وتشغيل المدارس الحكومية في دولة قطر، يغطي النطاق الأكاديمي والإداري والسلوكي والرقمي، مع امتثال كامل لـ QNSA و‑PDPPL.
</p>

<p align="center">
  <!-- Badges -->
  <img alt="Django" src="https://img.shields.io/badge/Django-5.2-092E20?logo=django&logoColor=ffffff" />
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-16-316192?logo=postgresql&logoColor=ffffff" />
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=ffffff" />
  <img alt="Security" src="https://img.shields.io/badge/Security-CodeQL%20%2B%20Secrets%20Scanning-success" />
  <img alt="License" src="https://img.shields.io/badge/License-Internal--Use-maroon" />
</p>

---

## 📑 فهرس المحتويات
- [نبذة مختصرة](#-نبذة-مختصرة)
- [التقنيات والهيكل العام](#-التقنيات-والهيكل-العام)
- [الجديد في v5 (مارس 2026)](#-الجديد-في-v5-مارس-2026)
- [تشغيل سريع (Quick Start)](#-تشغيل-سريع-quick-start)
- [الإعداد والتهيئة (Configuration)](#-الإعداد-والتهيئة-configuration)
- [الوحدات (Domains/Modules)](#-الوحدات-domainsmodules)
- [الهيكل المجلدي](#-الهيكل-المجلدي)
- [قواعد البيانات والترحيلات (Migrations)](#-قواعد-البيانات-والترحيلات-migrations)
- [الأمن والامتثال](#-الأمن-والامتثال)
- [الجودة والاختبارات](#-الجودة-والاختبارات)
- [النشر (Deployment)](#-النشر-deployment)
- [CI/CD](#-cicd)
- [النسخ الاحتياطي والاستعادة](#-النسخ-الاحتياطي-والاستعادة)
- [إدارة الإصدارات والتغيير](#-إدارة-الإصدارات-والتغيير)
- [روابط مهمة](#-روابط-مهمة)
- [نماذج ومستندات رسمية](#-نماذج-ومستندات-رسمية)
- [المساهمة وحوكمة المستودع](#-المساهمة-وحوكمة-المستودع)
- [الهوية والشعارات](#-الهوية-والشعارات)
- [الرخصة والدعم](#-الرخصة-والدعم)

---

## 📌 نبذة مختصرة
**SchoolOS v5** منصة موحّدة لإدارة عمليات المدرسة: الأشخاص، الحضور، السلوك، الصحة، التقييم والاختبارات، الكنترول، الجداول، الجودة واللجان، التحليلات وKPIs، الإشعارات، المكتبة، النقل… إلخ.  
مصممة وفق **أفضل الممارسات** في التصميم المستدام (20+ سنة)، الأمن، الامتثال، والنسخ الاحتياطي.

> **ملاحظة الشعار:** الملف الحالي في `assets/brand/qatar-emblem-2022.svg` هو *Placeholder*. عند استبداله بالنسخة الرسمية الحديثة (SVG)، سيظهر تلقائيًا دون أي تعديل إضافي.

---

## 🏗️ التقنيات والهيكل العام
- **Backend:** Django 5.2 (Python 3.11+)
- **Database:** PostgreSQL 16 (دعم ميزات متقدمة لاحقًا مثل RLS/Partitions)
- **Cache/Queue:** Redis + Celery
- **Frontend:** HTMX + Tailwind (أو Vue 3 حسب الوحدة)
- **Reports:** WeasyPrint (PDF)
- **Auth/RBAC:** هوية موحّدة وأدوار
- **Admin:** واجهة عربية مخصصة

---

## 🆕 الجديد في v5 (مارس 2026)
| التغيير | الملف/المسار | الحالة |
|---|---|---|
| لائحة مخالفات ABCD (20 مخالفة) | `behavior/models.py → ViolationCategory` | ✔ مكتمل |
| وحدة كنترول الاختبارات (SOP كامل) | `exam_control/` (تطبيق جديد) | ✔ مكتمل |
| 10 KPIs رياضية | `analytics/views.py → api_kpis_all` | ✔ مكتمل |
| لوحة KPIs | `templates/analytics/kpi_dashboard.html` | ✔ مكتمل |
| نماذج Word رسمية | `static/forms/*.docx` | ✔ مكتمل |
| حذف مجلد إصدار قديم | `release2/` | ✔ مكتمل |

> *تم دمج العناصر كما وردت في ملف README الذي رفعته.* `

---

## ⚙️ الإعداد والتهيئة (Configuration)

ضع المتغيرات الحساسة في **.env** (ولا تُضمّنها في Git):

| المتغير         | الوصف                                 | مثال                                |
| --------------- | ------------------------------------- | ----------------------------------- |
| `SECRET_KEY`    | مفتاح Django السري                    | `django-secret-...`                 |
| `FERNET_KEY`    | مفتاح تشفير بيانات حساسة (عيادة/هوية) | مفتاح آمن 32 بايت base64            |
| `DATABASE_URL`  | اتصال PostgreSQL                      | `postgres://user:pass@host:5432/db` |
| `REDIS_URL`     | اتصال Redis                           | `redis://127.0.0.1:6379/0`          |
| `ALLOWED_HOSTS` | نطاقات موثوقة                         | `school.example.qa`                 |
| `EMAIL_*`       | إعداد البريد للإشعارات                | SMTP رسمي                           |
| `TIME_ZONE`     | المنطقة الزمنية                       | `Asia/Qatar`                        |

> **قبل الإنتاج (Checklist):**  
> ☐ توليد `SECRET_KEY` و`FERNET_KEY` جديدة (سريًا) • ☐ إنشاء أيقونات PWA (`icon-192.png` / `icon-512.png`) بألوان الهوية (#8A1538) • ☐ تشغيل بناء Tailwind محليًا • ☐ إتمام DPIA وفق PDPPL مـ11 • ☐ تعيين DPO موثق • ☐ جدولة نسخ احتياطي يومي 02:00. [1](https://qatareducation-my.sharepoint.com/personal/s_mesyef0904_education_qa/Documents/Microsoft%20Copilot%20Chat%20Files/README.md)

---

## 🧩 الوحدات (Domains/Modules)

- **Core/Identity/RBAC** — بنية الهوية والأدوار.  
- **People** — الطلاب/الموظفون/أولياء الأمور.  
- **Attendance** — الغياب/التأخر (HTMX).  
- **Behavior** — لائحة ABCD والإجراءات.  
- **Clinic** — سجلات صحية + تشفير حقول حساسة.  
- **Assessment & Exams** — تقييمات/اختبارات.  
- **Exam Control** — SOP الكنترول (إصدار/تجميع/مرقبة/رصد).  
- **Timetable** — الجداول والبدائل.  
- **Library** — استعارات وفهارس.  
- **Transport** — خطوط وحافلات.  
- **Quality & Committees** — QNSA/لجان/محاضر.  
- **Analytics** — لوحات KPIs ومؤشرات رقمية.  
- **Notifications** — بريد/رسائل/مهام Celery.  
- **Reports** — قوالب PDF رسمي.  
- **Staging/Import** — استيراد بيانات من مصادر خارجية.  
- **Infrastructure (Docker)** — إن وُجِد.  
> *تم توحيد قائمة الوحدات مع نسختك الأصلية.* [1](https://qatareducation-my.sharepoint.com/personal/s_mesyef0904_education_qa/Documents/Microsoft%20Copilot%20Chat%20Files/README.md)

---

## 📁 الهيكل المجلدي

```txt
shschool_mvp/
├─ assets/brand/                  # شعارات وهوية (يُحفظ الشعار الرسمي هنا)
│  └─ qatar-emblem-2022.svg       # Placeholder حالياً (استبدله بالرسمي عند توفره)
├─ core/                          # هوية/مرجعيات أساسية
├─ people/                        # أفراد وعلاقاتهم
├─ attendance/                    # حضور/غياب
├─ behavior/                      # السلوك ولائحة ABCD
├─ exam_control/                  # كنترول الاختبارات
├─ analytics/                     # تحليلات ولوحات
├─ clinic/                        # العيادة (حقول مشفرة)
├─ quality/                       # الجودة واللجان
├─ reports/                       # قوالب Report/PDF
├─ staging/                       # استيراد وتجهيز
├─ static/forms/                  # نماذج Word/MD رسمية
├─ templates/                     # قوالب HTML
├─ docker-compose.yml             # بنية Docker (إن وُجد)
└─ requirements.txt
```

---

## 🗄️ قواعد البيانات والترحيلات (Migrations)

- نفّذ الترحيلات عبر `python manage.py migrate`.  
- استخدم seeders الرسمية:
  - `seed_abcd` — يغذّي 20 مخالفة قياسية.
  - `seed_all` — بيانات نظام أولية.
- **أفضل الممارسات:**
  - ترحيلات **idempotent** قدر الإمكان.
  - لا تغييرات مباشرة على جداول الإنتاج دون Migration.
  - فهارس مناسبة، وتنظيف دوري للبيانات المكررة.
  - استخدام مستخدم DB محدود الصلاحيات في الإنتاج.

---

## 🔐 الأمن والامتثال

- **GitHub:** قواعد Rulesets لحماية `main` (منع force‑push، إلزام PR + مراجعة).  
- **Security & Analysis:** مفعّل (CodeQL, Secret Scanning + Push Protection, Dependabot Alerts).  
- **PDPPL/QNSA:** حد أدنى من الامتثال (DPIA، DPO، ممارسات الخصوصية).  
- **حساسية البيانات:** تشفير حقول العيادة والهوية، سجلات تدقيق (Audit) لاحقًا.  
- **نفاذ الأقل (Least Privilege):** أدوار RBAC واضحة، وتعطيل الميزات غير الضرورية.  
- **سجلات:** تدوين أحداث حساسة (دخول/تغيير صلاحية/تصدير بيانات).  

> ⚠️ **تنبيه استخدام الشعار:** الملف الحالي Placeholder لأغراض العرض حتى استبداله بالنسخة الرسمية الحديثة (SVG).

---

## 🧪 الجودة والاختبارات

- **تنسيق الكود:** `ruff`/`black` (اختياري).  
- **اختبارات:** `pytest` (إن وُجدت حزمة الاختبارات).  
- **تحليل ثابت:** CodeQL عبر GitHub Actions.  
- **سياسة PR:** موافقة مطلوبة + حالة خضراء قبل الدمج (Squash/Rebase فقط).

أوامر شائعة:

```bash
pytest -q
python manage.py check
python manage.py makemigrations --check --dry-run
```

---

## ☁️ النشر (Deployment)

**خيارات نموذجية:**  
- Oracle Cloud (Free Tier) + Docker + PostgreSQL  
- خادم داخلي بالمدرسة (VM) مع Nginx/Redis  
- Docker Compose (خدمات: web, db, redis, worker, scheduler)

**إرشادات مختصرة:**
1. ضبط `.env` للإنتاج (مفاتيح قوية + `DEBUG=False`).  
2. تفعيل HTTPS وHSTS على Nginx.  
3. استخدام مستخدم DB مقيّد الصلاحيات.  
4. سياسة نسخ احتياطي يومية.  
5. مراقبة (uptime + logs).  

---

## 🔄 CI/CD

- **GitHub Actions** (إعداد آمن موصى به):
  - السماح فقط بـ GitHub‑owned + verified actions.
  - صلاحيات **Read-only** للـ workflows.
  - الموافقة مطلوبة لتشغيل fork PRs.
- **وظائف نموذجية:**
  - lint + tests على كل PR.
  - CodeQL أسبوعي.
  - بناء صور Docker (خاصة) عند الإصدار.

---

## 💾 النسخ الاحتياطي والاستعادة

- نسخ احتياطي PostgreSQL يومي (02:00 AM Asia/Qatar).  
- تدوير احتفاظ: **7 أيام** يومي + **4 أسابيع** أسبوعي + **12 شهرًا** شهري.  
- تشفير النسخ (PGP أو خزنة مُدارة).  
- اختبار استعادة شهري (DR drill).  
- نسخ نسخ الـ `.env` (مشفّر) ومفاتيح التشفير بحماية منفصلة.

---

## 🏷️ إدارة الإصدارات والتغيير

- **Semantic Versioning** داخلية (v5.x.y).  
- **الفرع الرئيسي:** `main` — محمي.  
- **استراتيجية الفروع:**
  - ميزات: `feature/<name>`
  - إصلاحات عاجلة: `hotfix/<name>`
  - وثائق: `docs/<name>`
- **الدمج:** Squash/Rebase فقط.  
- **CHANGELOG:** توثيق كل تغيير مهم.

---

## 🔗 روابط مهمة

- لوحة KPIs العشرة → `/analytics/kpis/`  
- كنترول الاختبارات → `/exam-control/`  
- لوحة Analytics → `/analytics/`  
- السلوك + ABCD → `/behavior/`  
- إدارة الجودة QNSA → `/quality/`  
- Admin Django → `/admin/`  

> *تم ترحيل الروابط كما في نسختك الأصلية.* [1](https://qatareducation-my.sharepoint.com/personal/s_mesyef0904_education_qa/Documents/Microsoft%20Copilot%20Chat%20Files/README.md)

---

## 🗂️ نماذج ومستندات رسمية

مجلد `static/forms/` يتضمن:

- `form_student_warning.docx` — إنذار سلوكي (ستة توقيعات).  
- `form_parent_undertaking.docx` — تعهد ولي الأمر.  
- `form_student_undertaking.docx` — تعهد الطالب.  
- `exam_control_handbook.docx` — دليل الكنترول SOP كامل.  
- `Handbook_SmartSchool_2026.md` — دليل التشغيل الذكي.  
- `Policy_StudentProtection.md` — سياسة الحماية والرعاية.  
- `Template_IncidentReport.md` — قالب محضر الحوادث.  

> *نُقلت هذه القائمة كما وردت في ملفك المرفوع مع تحسين الصياغة.* [1](https://qatareducation-my.sharepoint.com/personal/s_mesyef0904_education_qa/Documents/Microsoft%20Copilot%20Chat%20Files/README.md)

---

## 👥 المساهمة وحوكمة المستودع

- المستودع حاليًا **مغلق للمساهمات العامة** — الوصول لصاحب المستودع فقط.  
- عند الفتح لاحقًا:
  - **CODEOWNERS** لتوجيه المراجعات.  
  - **Issue/PR Templates** لتوحيد البلاغات.  
  - سياسة أمنية `SECURITY.md` لاستقبال تقارير الثغرات.  
- **قواعد GitHub Branch Protection**: منع force‑push، إلزام PR واحد على الأقل، Code Owners على المسارات الحرجة.

---

## 🎨 الهوية والشعارات

- ضع الشعار الرسمي الحديث في: `assets/brand/qatar-emblem-2022.svg`.  
- يمكنك إضافة شعار المدرسة في: `assets/brand/school-logo.svg`.  
- **ألوان الهوية المقترحة:**
  - Maroon `#8A1538`
  - Light Green `#7FD1AE`
  - Light Blue `#9ED9FF`
  - Light Red `#FFB3B3`
  - Black `#000000`
  - White `#FFFFFF`

---

## 📬 الرخصة والدعم

**الرخصة:** استخدام داخلي لمدرسة الشحانية. يُمنع النشر أو التوزيع الخارجي دون إذن إداري مكتوب.  
**الدعم:** لطلبات الدعم والتحسينات والتكاملات، تواصل مع مطوّر النظام داخل المدرسة.

---
