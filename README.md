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
├── data/                          ◄ ملفات البيانات الحقيقية (CSV)
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
├── core/                  المستخدمون، الأدوار، الفصول
├── operations/            الحضور، الجداول، البدلاء
├── quality/               الخطة التشغيلية، لجنة الجودة
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

**ملاحظة هامة:** في بيئة الإنتاج، يجب استخدام نظام مصادقة آمن (مثل OAuth2) أو متغيرات بيئة لتخزين بيانات الدخول.

| الدور | الرقم الوطني | كلمة المرور |
|-------|-------------|-------------|
| مدير المدرسة | `28763400678` | `school@2026` |
| معلم / منسق | الرقم الوطني | `school@2026` |
| طالب | الرقم الوطني | `student@2026` |
| ولي أمر | الرقم الوطني | `parent@2026` |

**لإعداد بيانات الدخول في بيئة الإنتاج، يرجى استخدام متغيرات البيئة أو نظام إدارة الأسرار (Secret Management System).**

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

## ✅ المراحل المكتملة

| المرحلة | الوصف |
|---------|-------|
| 0 | Auth + RBAC + Django Admin عربي |
| 1 | تسجيل الحضور الفوري بـ HTMX |
| 2 | الجداول الذكية + نظام البديل |
| 5 | الخطة التشغيلية + لجنة الجودة |

## 🔲 المراحل القادمة: 3 (التقييمات) · 4 (السلوك) · 6 (تقييم الموظفين) · 7 (التحليلات)

---

**Tech Stack:** Django 5 · PostgreSQL 16 · HTMX · Tailwind CSS · Docker
