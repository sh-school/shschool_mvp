"""[W-20261111-004] بذرُ المعاينة يضع طلبةً بلا مخالفاتٍ في جناح المشرف الوهميّ ليجد البحثُ أحداً.

رفض المالكُ المعاينةَ لأنّ القاعدةَ بلا طلبةٍ في نطاق المشرف. والبذرُ إضافةٌ فقط، متساوي الأثر، ولا يعمل خارج المعاينة.
"""

import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse

from behavior.models import BehaviorInfraction
from core import preview_accounts as pa
from core.models import CustomUser, StudentEnrollment, Wing
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.conftest import ClassGroupFactory
from tests.test_preview_accounts import PREVIEW, _sync, password, preview_env  # noqa: F401

pytestmark = pytest.mark.django_db


def _classes(school, year):
    """شعبتان في جناح المشرف الوهميّ (تُغطّى بـ`--sync`) وشعبةٌ في جناحٍ آخر."""
    first = Wing.objects.create(
        school=school, code="w1", name="جناح 1", academic_year=year, order=1
    )
    other = Wing.objects.create(
        school=school, code="w2", name="جناح 2", academic_year=year, order=2
    )
    mine = [
        ClassGroupFactory(school=school, grade="G7", section=s, academic_year=year, wing=first)
        for s in ("1", "2")
    ]
    theirs = ClassGroupFactory(
        school=school, grade="G8", section="1", academic_year=year, wing=other
    )
    return mine, theirs


def _supervisor_client(client_as):
    return client_as(
        CustomUser.objects.get(employee_number=pa.EMPLOYEE_NUMBERS["admin_supervisor"])
    )


@PREVIEW
def test_sync_seeds_students_in_the_supervisor_wing(school, year, preview_env):  # noqa: F811
    mine, theirs = _classes(school, year)
    _sync()
    inside = StudentEnrollment.objects.filter(class_group__in=mine).count()
    outside = StudentEnrollment.objects.filter(class_group=theirs).count()
    assert (inside, outside) == (6, 1)
    # بلا مخالفةٍ واحدة
    assert not BehaviorInfraction.objects.exists()


@PREVIEW
def test_the_seed_is_idempotent(school, year, preview_env):  # noqa: F811
    _classes(school, year)
    _sync()
    before = CustomUser.objects.filter(national_id__startswith="PV-bs-").count()
    _sync()
    assert CustomUser.objects.filter(national_id__startswith="PV-bs-").count() == before == 7


@PREVIEW
def test_the_seeded_students_do_not_trip_the_accounts_check(school, year, preview_env):  # noqa: F811
    _classes(school, year)
    _sync()
    call_command("preview_accounts", "--check")


@PREVIEW
def test_the_supervisor_search_finds_the_seeded_students_of_his_wing_only(
    school,
    year,
    client_as,
    preview_env,  # noqa: F811
):
    _classes(school, year)
    _sync()
    resp = _supervisor_client(client_as).get(reverse("behavior:dashboard"), {"q": "طالب معاينة"})
    names = [s.full_name for s in resp.context["student_matches"]]
    assert len(names) == 6
    assert all("جناح المشرف" in name for name in names)


def test_the_command_refuses_outside_the_preview(school):
    with pytest.raises(CommandError):
        call_command("seed_preview_behavior_students")
