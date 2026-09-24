"""[DATA] هجرةُ حذف صلاحيّات نموذجَين حُذفا (OWN-19) — تُحذف اليتيمةُ المسمّاةُ وحدَها.

ثمانُ صلاحيّاتٍ (`StaffEvaluation` و`TeacherSubjectQualification`) بقيت في جدول الصلاحيّات بلا نموذجٍ يقابلها.
الهجرةُ بياناتٌ فقط؛ وهذا الاختبارُ يشغّل دالّتَها على قاعدةٍ فيها الحالاتُ الأربع: اليتيمةُ المسمّاة، ونموذجٌ قائمٌ بالاسم
المسمّى (لا تُمسّ)، وصلاحيّةٌ لنموذجٍ محذوفٍ غيرِ مسمّى (لا تُمسّ)، وربطُ مجموعةٍ بصلاحيّةٍ يتيمة (يزول بالحذف).
"""

import importlib

import pytest
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection

pytestmark = pytest.mark.django_db

migration = importlib.import_module("core.migrations.0072_delete_orphan_model_permissions")


class _Schema:
    connection = connection


def _permission(app_label, model, action="add"):
    content_type, _ = ContentType.objects.get_or_create(app_label=app_label, model=model)
    return Permission.objects.create(
        content_type=content_type, codename=f"{action}_{model}", name=f"إضافة {model}"
    )


def _run():
    from django.apps import apps

    migration.delete_orphan_permissions(apps, _Schema)


def test_the_named_orphans_are_deleted_with_their_group_links():
    orphan = _permission("operations", "staffevaluation")
    other = _permission("academic_management", "teachersubjectqualification", "view")
    group = Group.objects.create(name="مجموعةٌ بصلاحيّةٍ يتيمة")
    group.permissions.add(orphan, other)

    _run()

    assert not Permission.objects.filter(pk__in=[orphan.pk, other.pk]).exists()
    assert group.permissions.count() == 0


def test_a_permission_of_a_live_model_is_never_touched():
    live = Permission.objects.get(content_type__app_label="core", codename="view_school")

    _run()

    assert Permission.objects.filter(pk=live.pk).exists()


def test_an_unnamed_deleted_model_is_left_alone():
    """اليتيمةُ غيرُ المسمّاة قرارٌ مستقلّ — تنظيفٌ عامٌّ لا تُخفيه هجرةٌ بعينها."""
    ghost = _permission("core", "someotherdeletedmodel")

    _run()

    assert Permission.objects.filter(pk=ghost.pk).exists()


def test_a_named_model_that_exists_again_keeps_its_permissions(monkeypatch):
    """إن عاد نموذجٌ بالاسم نفسِه (`core.school` هنا) فصلاحيّاتُه ليست يتيمة."""
    monkeypatch.setattr(migration, "ORPHANED_MODELS", (("core", "school"),))
    live = Permission.objects.get(content_type__app_label="core", codename="view_school")

    _run()

    assert Permission.objects.filter(pk=live.pk).exists()


def test_running_twice_changes_nothing_more():
    _permission("operations", "staffevaluation")

    _run()
    before = Permission.objects.count()
    _run()

    assert Permission.objects.count() == before


def test_the_migration_is_data_only_and_reversible():
    operations = migration.Migration.operations
    assert len(operations) == 1
    assert operations[0].reverse_code is not None  # noop، فلا يمنع الرجوعَ عن الهجرات التي قبله
