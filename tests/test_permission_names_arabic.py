"""[I18N] أسماءُ الصلاحيات عربيّةٌ في الإدارة — «إضافة مستخدم» لا «Can add مستخدم» (OWN-19).

جانغو يسمّي صلاحيّاتِه بالإنجليزيّة ثابتةً، فكانت صفحةُ المجموعة والمستخدم تعرض 560 صلاحيّةً بنصفٍ إنجليزيّ.
والتعريبُ في `post_migrate` (`core/permission_names.py`) لا بهجرةِ بيانات — فيصل الإنتاجَ مع أوّل نشرٍ
(preDeploy يشغّل `migrate`، وهو يُصدر الإشارةَ ولو بلا هجرةٍ جديدة).
"""

import pytest
from django.apps import apps
from django.contrib.auth.models import Permission

from core.permission_names import ACTIONS, arabize_permission_names, permission_name

pytestmark = pytest.mark.django_db


def test_no_permission_keeps_the_english_prefix():
    english = list(
        Permission.objects.filter(name__startswith="Can ").values_list("name", flat=True)
    )

    assert not english, f"صلاحيّاتٌ بالإنجليزيّة ({len(english)}): {english[:5]}"


def test_a_permission_is_named_from_its_action_and_its_model():
    from core.models import CustomUser

    perm = Permission.objects.get(content_type__app_label="core", codename="add_customuser")

    assert perm.name == f"{ACTIONS['add']} {CustomUser._meta.verbose_name}" == "إضافة مستخدم"


def test_every_default_permission_of_every_action_is_covered():
    names = set(
        Permission.objects.filter(content_type__app_label="core", codename__endswith="_customuser")
        .order_by("codename")
        .values_list("name", flat=True)
    )

    assert names == {permission_name(a, "مستخدم") for a in ACTIONS}


def test_django_own_models_are_arabic_too():
    group = Permission.objects.get(content_type__app_label="auth", codename="change_group")

    assert group.name.startswith(ACTIONS["change"]) and "Can" not in group.name


def test_an_english_name_is_restored_and_a_second_run_changes_nothing():
    perm = Permission.objects.get(content_type__app_label="core", codename="view_school")
    expected = perm.name
    Permission.objects.filter(pk=perm.pk).update(name="Can view school")

    arabize_permission_names(sender=apps.get_app_config("core"))
    perm.refresh_from_db()
    assert perm.name == expected

    # التطبيقُ الثاني: لا كتابةَ (لا bulk_update) — استعلاماتُ القراءة وحدَها: أنواعُ المحتوى ثمّ الصلاحيّات
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as queries:
        arabize_permission_names(sender=apps.get_app_config("core"))
    assert not [q for q in queries.captured_queries if q["sql"].lstrip().startswith("UPDATE")]


def test_a_sender_without_a_label_is_ignored():
    """الإشارةُ قد تصل بمُرسِلٍ ليس تطبيقاً — لا تنكسر."""
    arabize_permission_names(sender=None)
    arabize_permission_names(sender=object())


def test_the_permissions_of_a_deleted_model_are_arabised_and_a_custom_one_is_left_alone():
    from django.contrib.contenttypes.models import ContentType

    ghost = ContentType.objects.create(app_label="core", model="deletedmodel")
    Permission.objects.create(
        content_type=ghost, codename="add_deletedmodel", name="Can add نموذجٌ محذوف"
    )
    real = ContentType.objects.get(app_label="core", model="school")
    Permission.objects.create(content_type=real, codename="view_reports", name="Can view reports")

    arabize_permission_names(sender=apps.get_app_config("core"))

    assert Permission.objects.get(codename="add_deletedmodel").name == "إضافة نموذجٌ محذوف"
    assert Permission.objects.get(codename="view_reports").name == "Can view reports"
