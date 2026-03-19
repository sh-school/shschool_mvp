# دليل استخدام حزمة الإصلاحات — quality_fixes_v1.zip
## وحدة الخطة التشغيلية ولجان الجودة

---

## ما الذي يحتويه الملف المضغوط؟

```
final_package/
├── INSTALL.md
├── quality/
│   ├── models.py                          ← استبدل الملف الأصلي
│   ├── views.py                           ← استبدل الملف الأصلي
│   ├── urls.py                            ← استبدل الملف الأصلي
│   ├── migrations/
│   │   └── 0005_merge_committees_add_fields.py   ← أضفه فقط
│   └── management/
│       └── commands/
│           ├── normalize_executors.py     ← أضفه فقط
│           └── overdue_report.py          ← أضفه فقط
└── templates/
    └── quality/
        ├── executor_committee.html        ← أضفه فقط
        └── executor_member_detail.html    ← أضفه فقط
```

---

## الخطوات بالترتيب الصحيح

### الخطوة 1 — نسخ احتياطي أولاً ✋

```bash
# قبل أي شيء — احتفظ بنسخة من ملفاتك الأصلية
cp quality/models.py  quality/models.py.backup
cp quality/views.py   quality/views.py.backup
cp quality/urls.py    quality/urls.py.backup
```

---

### الخطوة 2 — نسخ الملفات إلى مشروعك

```bash
# افك ضغط الملف أولاً
unzip quality_fixes_v1.zip

# استبدل الملفات الثلاثة (models / views / urls)
cp final_package/quality/models.py   your_project/quality/models.py
cp final_package/quality/views.py    your_project/quality/views.py
cp final_package/quality/urls.py     your_project/quality/urls.py

# أضف الـ migration الجديدة (لا تستبدل — فقط أضف)
cp final_package/quality/migrations/0005_merge_committees_add_fields.py \
   your_project/quality/migrations/

# أضف أوامر الإدارة الجديدة
cp final_package/quality/management/commands/normalize_executors.py \
   your_project/quality/management/commands/

cp final_package/quality/management/commands/overdue_report.py \
   your_project/quality/management/commands/

# أضف الـ templates الجديدة
cp final_package/templates/quality/executor_committee.html \
   your_project/templates/quality/

cp final_package/templates/quality/executor_member_detail.html \
   your_project/templates/quality/
```

---

### الخطوة 3 — تنظيف أسماء المنفذين (الإصلاح #3)

```bash
# معاينة أولاً بدون أي تغيير
python manage.py normalize_executors --dry-run

# إذا النتائج صحيحة → طبّق
python manage.py normalize_executors
```

**ماذا يفعل؟**
يصحح الأخطاء الإملائية في أسماء المنفذين مثل:
- "منسق التربيه الاسلاميه" → "منسق التربية الإسلامية"
- "منسق اللغه العربيه" → "منسق اللغة العربية"
- وغيرها (15 تصحيحاً إجمالاً)

---

### الخطوة 4 — تشغيل الـ Migration (الإصلاح #2)

```bash
python manage.py migrate quality
```

**ماذا يفعل؟**
- يدمج نموذجي اللجنتين في نموذج واحد
- يضيف حقل `committee_type` للتمييز بين اللجنتين
- يضيف صلاحيات على مستوى كل فرد
- يضيف حقل `deadline` للإجراءات
- يحول بيانات اللجنة التنفيذية القديمة تلقائياً

---

### الخطوة 5 — إعادة ربط المنفذين بالمستخدمين

```bash
# بعد التطبيع وبعد الـ migration — أعد تطبيق الربط
python manage.py shell -c "
from quality.models import ExecutorMapping
count = 0
for m in ExecutorMapping.objects.filter(user__isnull=False):
    m.apply_mapping()
    count += 1
print(f'تم تحديث {count} ربط')
"
```

---

### الخطوة 6 — تشغيل المشروع والتحقق

```bash
python manage.py runserver
```

**الروابط الجديدة التي ستظهر:**

| الرابط | الوصف |
|--------|-------|
| `/quality/` | لوحة الخطة التشغيلية (محدّثة) |
| `/quality/executor-committee/` | **جديد** — لجنة المنفذين |
| `/quality/executor-committee/member/<id>/` | **جديد** — تقرير منفذ واحد |
| `/quality/committee/` | لجنة المراجعة الذاتية (محدّثة) |

---

## الأوامر اليومية المفيدة

```bash
# تقرير بكل الإجراءات غير المكتملة
python manage.py overdue_report

# تصدير التقرير إلى ملف CSV
python manage.py overdue_report --export

# تقرير مدرسة محددة فقط
python manage.py overdue_report --school SHH
```

---

## التحقق من نجاح التطبيق

```bash
python manage.py shell
```

```python
from quality.models import QualityCommitteeMember

# يجب أن يُظهر: executor و review
print(list(QualityCommitteeMember.objects.values_list('committee_type', flat=True).distinct()))

# عدد أعضاء كل لجنة
from django.db.models import Count
print(QualityCommitteeMember.objects.values('committee_type').annotate(n=Count('id')))
```

---

## إذا واجهتك مشكلة

```bash
# إذا فشل الـ migration
python manage.py migrate quality --fake 0004
python manage.py migrate quality 0005

# للرجوع لما قبل الإصلاحات
cp quality/models.py.backup  quality/models.py
cp quality/views.py.backup   quality/views.py
cp quality/urls.py.backup    quality/urls.py
python manage.py migrate quality 0004
```

---

## ملاحظة مهمة

هذه الحزمة تعدّل **وحدة `quality` فقط**. باقي وحدات منصتك (assessments, operations, behavior, clinic...) لا تتأثر بهذه التغييرات.
