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
    user_model = apps.get_model("core", "CustomUser")
    group_model = apps.get_model("auth", "Group")
    alias = schema_editor.connection.alias
    for app_label, model_name in ORPHANED_MODELS:
        try:
            live_apps.get_model(app_label, model_name)
            continue  # النموذجُ قائم: ليست يتيمة
        except LookupError:
            pass
        orphans = permission.objects.using(alias).filter(
            content_type__app_label=app_label, content_type__model=model_name
        )
        ids = list(orphans.values_list("pk", flat=True))
        if not ids:
            continue
        # ما سيتسلسل حذفُه من إسناداتٍ يُسجَّل قبل الحذف (لا رجوع بعده) — عددٌ ثمّ الأزواجُ نفسُها
        # (معرّفُ المستخدم أو المجموعة ← اسمُ الصلاحيّة) فتُستعاد يدويّاً من سجلّ النشر إن لزم.
        codenames = dict(orphans.values_list("pk", "codename"))
        assignments = []
        for kind, holder, through in (
            ("مستخدم", user_model, user_model.user_permissions.through),
            ("مجموعة", group_model, group_model.permissions.through),
        ):
            holder_field = next(
                f for f in through._meta.fields if f.is_relation and f.related_model is holder
            ).attname
            rows = through.objects.using(alias).filter(permission_id__in=ids)
            assignments += [
                (kind, str(getattr(row, holder_field)), codenames[row.permission_id])
                for row in rows
            ]
        by_users = sum(1 for kind, _, _ in assignments if kind == "مستخدم")
        by_groups = len(assignments) - by_users
        orphans.delete()
        print(  # noqa: T201 — سجلُّ النشر
            f"  core/0072: حُذفت {len(ids)} صلاحيّةً يتيمةً لـ{app_label}.{model_name} "
            f"(إسناداتٌ مباشرةٌ لمستخدمين: {by_users}، ولمجموعات: {by_groups})"
        )
        for kind, holder_id, codename in sorted(assignments):
            print(f"  core/0072:   إسنادٌ محذوف — {kind} {holder_id} ← {codename}")  # noqa: T201


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0071_arabic_field_labels"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(delete_orphan_permissions, migrations.RunPython.noop),
    ]
