"""حذفُ صلاحيّات نموذجَين حُذفا من المنصّة — بياناتٌ فقط، بلا تغييرٍ في المخطّط (OWN-19).

`operations.StaffEvaluation` (هجرة حذفه في #436) و`academic_management.TeacherSubjectQualification` (قرار
2026-09-05: لا مؤهّلات معلّم للموادّ) حُذف جدولاهما، وبقي نوعُ محتواهما وصلاحيّاتُهما الأربعُ لكلٍّ في جدول الصلاحيّات
(ثمانٍ) — تظهر في صفحة المجموعة والمستخدم بصيغة «academic_management | teachersubjectqualification | …» ولا نموذجَ يقابلها.

يُحذف من الصلاحيّات ما كان نوعُ محتواه أحدَ هذين الاثنين **وما زال النموذجُ غيرَ موجودٍ في المنصّة** (فإن عاد يوماً
نموذجٌ بالاسم نفسِه لم تُمسّ صلاحيّاتُه). ويتسلسل الحذفُ إلى ربطها بالمجموعات والمستخدمين. ونوعُ المحتوى نفسُه يبقى:
حذفُه تنظيفٌ أوسع (`remove_stale_contenttypes`) يمسّ سجلَّ الإدارة، وليس مقصوداً هنا.

لا رجوعَ: الصلاحيّاتُ تُنشأ من النماذج وهذان لا وجودَ لهما، فلا شيءَ يُعاد.
"""

from django.apps import apps as live_apps
from django.db import migrations

#: (التطبيق، النموذج) — لا قائمةَ عامّةً: ما يُحذف يُسمّى.
ORPHANED_MODELS = (
    ("academic_management", "teachersubjectqualification"),
    ("operations", "staffevaluation"),
)


def delete_orphan_permissions(apps, schema_editor):
    permission = apps.get_model("auth", "Permission")
    alias = schema_editor.connection.alias
    for app_label, model_name in ORPHANED_MODELS:
        try:
            live_apps.get_model(app_label, model_name)
        except LookupError:
            permission.objects.using(alias).filter(
                content_type__app_label=app_label, content_type__model=model_name
            ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0071_arabic_field_labels"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(delete_orphan_permissions, migrations.RunPython.noop),
    ]
