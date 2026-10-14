"""تنظيفُ مخالفي قيود الغياب قبل فرضها (W-20261004-021، المرحلة أ١) — هجرةُ بياناتٍ موثَّقةٌ متساويةُ الأثر.

عدٌّ قراءةً فقط على الإنتاج بأمر المالك (D-412م، 2026-10-15): 297 خروجاً منها 2 بمدّةٍ سالبة، ولا خروجَ مفتوحاً مكرَّراً،
ولا تنبيهَ مكرَّراً، ولا عذراً بمدىً معكوس. فالمخالفُ الوحيد خروجان عودتُهما قبل خروجهما، ويُصحَّح بلا حذف: العودةُ = الخروج
(مدّةٌ صفر) فتبقى السطرُ والعدّادُ. وما سواه معالجٌ احتياطاً لا يمسّ شيئاً إن لم يوجد:
- خروجان مفتوحان لطالبٍ في حصّة: يُغلَق الأقدمُ بعودةٍ = خروجه (مدّةٌ صفر) ويبقى الأحدثُ مفتوحاً.
- تنبيهٌ مكرَّرٌ بالمفتاح نفسِه: يبقى الأقدمُ ويُحذف الباقي (لا يحمل سوى العددِ والحالة، والمفتاحُ واحد).
- عذرٌ بمدىً معكوس: يُبدَّل التاريخان.
لا عكسَ: البياناتُ المصحَّحةُ لا يُعاد إفسادُها.
"""

from django.db import migrations
from django.db.models import F


def clean(apps, schema_editor):
    ClassExit = apps.get_model("operations", "ClassExit")
    AbsenceAlert = apps.get_model("operations", "AbsenceAlert")
    AbsenceExcuse = apps.get_model("operations", "AbsenceExcuse")

    ClassExit.objects.filter(returned_at__lt=F("left_at")).update(returned_at=F("left_at"))

    seen = set()
    for row in ClassExit.objects.filter(returned_at__isnull=True).order_by("-left_at", "-id"):
        key = (row.session_id, row.student_id)
        if key in seen:
            ClassExit.objects.filter(pk=row.pk).update(returned_at=row.left_at)
        seen.add(key)

    seen = set()
    for row in AbsenceAlert.objects.order_by("created_at", "id"):
        key = (row.school_id, row.student_id, row.gate, row.period_start, row.period_end)
        if key in seen:
            row.delete()
        seen.add(key)

    for row in AbsenceExcuse.objects.filter(date_from__gt=F("date_to")):
        AbsenceExcuse.objects.filter(pk=row.pk).update(date_from=row.date_to, date_to=row.date_from)


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0085_absence_followup_logs_student_nullable"),
    ]

    operations = [migrations.RunPython(clean, migrations.RunPython.noop)]
