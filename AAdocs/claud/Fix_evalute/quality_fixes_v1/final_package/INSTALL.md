# دليل تطبيق الإصلاحات الأربعة

## الترتيب الصحيح للتطبيق

### الخطوة 1 — تنظيف البيانات (الإصلاح #3)
```bash
# معاينة أولاً بدون تغيير
python manage.py normalize_executors --dry-run

# تطبيق التطبيع
python manage.py normalize_executors

# تطبيع إعادة ربط المنفذين
python manage.py shell -c "
from quality.models import ExecutorMapping
for m in ExecutorMapping.objects.filter(user__isnull=False):
    m.apply_mapping()
print('Done')
"
```

### الخطوة 2 — ترحيل قاعدة البيانات (الإصلاح #2)
```bash
# نسخ الملفات أولاً
cp quality/models.py → (استبدل models.py الأصلي)
cp quality/migrations/0005_... → quality/migrations/

# تشغيل الـ migration
python manage.py migrate quality
```

### الخطوة 3 — تحديث views و urls
```bash
cp quality/views.py → (استبدل views.py الأصلي)
cp quality/urls.py  → (استبدل urls.py الأصلي)
```

### الخطوة 4 — نسخ Templates
```bash
cp templates/quality/executor_committee.html      → templates/quality/
cp templates/quality/executor_member_detail.html  → templates/quality/
```

### الخطوة 5 — اختبار
```bash
# تقرير المتأخرات (الإصلاح #1)
python manage.py overdue_report
python manage.py overdue_report --export

# تصفح الروابط الجديدة
/quality/executor-committee/
/quality/executor-committee/member/<uuid>/
```

## التحقق من نجاح التطبيق
```python
from quality.models import QualityCommitteeMember
# تحقق من وجود committee_type
print(QualityCommitteeMember.objects.values('committee_type').distinct())
# يجب أن تظهر: executor و review
```
