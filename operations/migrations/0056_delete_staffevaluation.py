"""
حذفُ `operations.StaffEvaluation` — الخطوة 2 من 2 (ADR-0002 §4، «توسيعٌ ثمّ تقليص»، CLAUDE.md).

تقييمُ الأداء في `quality.EmployeeEvaluation` (مستوياتُ المادة 16 والاستماراتُ الوزاريّة). والنموذجُ
القديم (خمسةُ معايير 1–5) لا قارئَ له ولا كاتب منذ #417 (الخطوة 1، مدموجةٌ في 2026-09-19)، وعدُّ الإنتاج
**صفر** (2026-09-19). فلا بياناتٍ تُنقل ولا تُؤرشف؛ وتُحذف معه سياساتُ RLS (`core/0033`) بحذف الجدول.

**قبل دمج هذه الهجرة:** تأكّد أنّ #417 مُنشَرٌ (وإلّا فنسخةٌ تعمل ما زالت تلمس الجدول)، وأعِد عدَّ الإنتاج قبل
النشر: `railway ssh` ثمّ
`python manage.py shell -c "from operations.models import StaffEvaluation as S; print(S.objects.count())"`
— يجب أن يكون 0. ومدقّقُ الهجرات يُستثنى لها بالاسم في `shschool/settings/testing.py` عمداً (`DROP TABLE`).

والخيارُ `("StaffEvaluation", …)` في `core/models/audit.py` يبقى: سجلّاتُ التدقيق القديمةُ قد تحمله.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0055_attendance_exit_partial_index"),
    ]

    operations = [
        migrations.DeleteModel(
            name="StaffEvaluation",
        ),
    ]
