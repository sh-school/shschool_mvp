"""كلُّ نموذجٍ يصل إليه مديرُ المدرسة في `/admin/` مقيَّدٌ بمدرسته — عزلُ المستأجرين.

بعد أن صار المديرُ `is_staff` بصلاحياتٍ صريحةٍ (`core.admin_access`) لا `is_superuser`،
صارت قوائمُ `FULL_ACCESS_MODELS` و`VIEW_ONLY_MODELS` هي كلَّ ما يراه. وكانت أربعةَ عشرَ
نموذجاً منها تقرأ الجدولَ كاملاً: مديرُ مدرسةٍ يقرأ ويعدّل ويحذف صفوفَ مدرسةٍ أخرى بفتح
رابطها، وقوائمُه المنسدلة تعرض مدارسَ غيره وأشخاصَها.

الحارسُ بنيويٌّ لا سلوكيّ فقط: نموذجٌ يُضاف إلى صلاحيّات المدير بلا `SchoolScopedAdmin`
يُسقط هذا الملفَّ، فلا يمرّ صامتاً.
"""

from __future__ import annotations

import pytest
from django.apps import apps
from django.contrib.admin.sites import site
from django.test import RequestFactory

from core.admin import SchoolScopedAdmin
from core.admin_access import FULL_ACCESS_MODELS, VIEW_ONLY_MODELS
from tests.conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory

pytestmark = pytest.mark.django_db

#: نماذجُ في قوائم المدير بلا مستأجرٍ أصلاً — محاولاتُ دخولٍ وجلساتٌ ورموزٌ قبل معرفة المدرسة.
NO_TENANT = {
    ("axes", "accessattempt"),
    ("axes", "accessfailurelog"),
    ("axes", "accesslog"),
    ("token_blacklist", "blacklistedtoken"),
    ("token_blacklist", "outstandingtoken"),
}


def _principal_models():
    return sorted((FULL_ACCESS_MODELS | VIEW_ONLY_MODELS) - NO_TENANT)


@pytest.mark.parametrize("app_label,model_name", _principal_models())
def test_every_model_the_principal_reaches_is_school_scoped(app_label, model_name):
    model = apps.get_model(app_label, model_name)
    model_admin = site._registry[model]
    assert isinstance(model_admin, SchoolScopedAdmin), (
        f"{app_label}.{model_name} في صلاحيّات المدير بلا عزلٍ بين المدارس — "
        "ورِّث `core.admin.SchoolScopedAdmin` وسمِّ `school_lookup`."
    )


def _request_for(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def _principal(school):
    user = UserFactory(is_staff=True)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="principal"))
    return user


@pytest.fixture
def two_schools():
    return SchoolFactory(), SchoolFactory()


def _scoped_models_with_a_direct_school_path():
    """كلُّ نموذجٍ مقيَّدٍ بمساره: يُبنى له صفٌّ في كلّ مدرسة ويُتحقَّق ممّا يراه المدير."""
    return [
        m
        for m in _principal_models()
        if isinstance(site._registry[apps.get_model(*m)], SchoolScopedAdmin)
    ]


def test_the_lookup_path_of_each_scoped_admin_reaches_school():
    """كلُّ `school_lookup` صالحٌ فعلاً — خطأٌ إملائيٌّ فيه كان سيُسقط الصفحةَ بـ`FieldError`."""
    for app_label, model_name in _scoped_models_with_a_direct_school_path():
        model_admin = site._registry[apps.get_model(app_label, model_name)]
        model = model_admin.model
        parts = model_admin.school_lookup.split("__")
        for part in parts:
            if part == "pk":
                break
            model = model._meta.get_field(part).related_model
        assert model.__name__ == "School" or parts[-1] == "pk"


def test_the_school_field_only_offers_the_principals_own_school(two_schools):
    here, there = two_schools
    principal = _principal(here)
    from core.models import ClassGroup

    model_admin = site._registry[ClassGroup]
    field = model_admin.formfield_for_foreignkey(
        ClassGroup._meta.get_field("school"), _request_for(principal)
    )
    offered = set(field.queryset.values_list("pk", flat=True))
    assert here.pk in offered and there.pk not in offered


def test_the_school_field_offers_every_school_to_the_platform_developer(two_schools):
    here, there = two_schools
    developer = UserFactory(is_staff=True, is_superuser=True)
    from core.models import ClassGroup

    field = site._registry[ClassGroup].formfield_for_foreignkey(
        ClassGroup._meta.get_field("school"), _request_for(developer)
    )
    assert {here.pk, there.pk} <= set(field.queryset.values_list("pk", flat=True))


def test_a_principal_cannot_open_another_schools_class_group(two_schools):
    here, there = two_schools
    principal = _principal(here)
    from tests.conftest import ClassGroupFactory

    mine = ClassGroupFactory(school=here)
    theirs = ClassGroupFactory(school=there)
    from core.models import ClassGroup

    rows = site._registry[ClassGroup].get_queryset(_request_for(principal))
    assert mine in rows and theirs not in rows
    assert (
        site._registry[ClassGroup].get_object(_request_for(principal), str(theirs.pk)) is None
    ), "رابطُ صفٍّ من مدرسةٍ أخرى يُرجع لا شيء لا الصفّ"


def test_semester_and_school_admins_reach_school_through_their_paths(two_schools):
    here, there = two_schools
    principal = _principal(here)
    from core.models import AcademicYear, School, Semester

    for school in (here, there):
        year = AcademicYear.objects.create(
            school=school, name="2026-2027", start_date="2026-09-01", end_date="2027-06-30"
        )
        Semester.objects.create(
            academic_year=year,
            code="S1",
            start_date="2026-09-01",
            end_date="2027-01-15",
            max_grade=40,
        )

    request = _request_for(principal)
    assert list(site._registry[School].get_queryset(request)) == [here]
    seen = site._registry[Semester].get_queryset(request)
    assert {s.academic_year.school_id for s in seen} == {here.pk}


def test_a_principal_without_a_school_sees_nothing():
    orphan = UserFactory(is_staff=True)
    from core.models import Wing

    assert not site._registry[Wing].get_queryset(_request_for(orphan)).exists()


def test_direct_foreign_key_paths_do_not_pay_for_distinct(two_schools):
    """`distinct()` على جدولٍ بمئات الآلاف (سجلّ الإشعارات) بلا حاجة كان فرزاً مجّانيّاً مكلفاً."""
    from notifications.models import NotificationLog

    here, _ = two_schools
    queryset = site._registry[NotificationLog].get_queryset(_request_for(_principal(here)))
    assert queryset.query.distinct is False

    from core.models import CustomUser

    users = site._registry[CustomUser].get_queryset(_request_for(_principal(here)))
    assert users.query.distinct is True, "العلاقةُ العكسيّة (memberships) تحتاجه فعلاً"
