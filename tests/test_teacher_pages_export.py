"""جداولُ المعلّمين مفردة — صفحةٌ لكلّ معلّم، وقسمُه من سجلّ المدرسة.

قرارُ الإدارة 2026-09-06: القسمُ ما يقوله السجلّ **بغضّ النظر عمّا يدرّسه
المعلّم**. فالورقةُ تُوزَّع على المنسّقين، ورجلٌ ينتقل من قسمٍ إلى قسمٍ لأنّ
جدوله تغيّر ورقةٌ لا تُصدَّق. وكان الاشتقاقُ من الموادّ هو المصدرَ الوحيد.

ومعها: منسّقُ المشاريع الإلكترونيّة يعاين الجداول كالمنسّق (قرارُ المدير)،
ومن لا حصّةَ له يُذكر في الفهرس ولا تُطبع له صفحةٌ فارغة.
"""

from datetime import time

import pytest
from django.urls import reverse

from core.models import Department, Membership
from operations.models import ScheduleSlot, Subject
from operations.services import ScheduleService
from tests.conftest import ClassGroupFactory

pytestmark = pytest.mark.django_db
YEAR = "2026-2027"


@pytest.fixture
def arts(school):
    return Department.objects.create(
        school=school, name="الفنون البصرية", code="art", sort_order=10
    )


def _link(user, school, department, specialty=""):
    membership = Membership.objects.filter(user=user, school=school, is_active=True).first()
    membership.department_obj = department
    membership.specialty = specialty
    membership.save(update_fields=["department_obj", "specialty"])
    return membership


def _lesson(school, teacher, subject_name="الرياضيات", code="MAT", *, day=0, period=1):
    subject, _ = Subject.objects.get_or_create(school=school, name_ar=subject_name, code=code)
    return ScheduleSlot.objects.create(
        school=school,
        class_group=ClassGroupFactory(
            school=school, grade="G8", level_type="prep", academic_year=YEAR
        ),
        teacher=teacher,
        subject=subject,
        day_of_week=day,
        period_number=period,
        start_time=time(7, 30),
        end_time=time(8, 15),
        academic_year=YEAR,
        is_active=True,
    )


# ══════════════════════ القسم من السجلّ ═══════════════════════════


def test_the_registered_department_beats_what_he_teaches(school, teacher_user, arts):
    """يدرّس الرياضيات ومسجَّلٌ في الفنون — فالورقةُ تقول الفنون."""
    _lesson(school, teacher_user)
    _link(teacher_user, school, arts)

    pages, _ = ScheduleService.teacher_pages(school, YEAR)

    assert [p["department"]["name"] for p in pages] == ["الفنون البصرية"]
    assert pages[0]["department"]["registered"] is True


def test_an_unregistered_teacher_still_gets_a_department(school, teacher_user):
    """الاشتقاقُ احتياطٌ لا أصل — ومن لا سجلَّ له لا يسقط من الورق."""
    _lesson(school, teacher_user)

    pages, _ = ScheduleService.teacher_pages(school, YEAR)

    assert pages[0]["department"]["name"] == "الرياضيات"
    assert pages[0]["department"]["registered"] is False


def test_the_specialty_rides_beside_the_department(school, teacher_user, arts):
    """مدرّسُ إدارة الأعمال وحدَه: قسمُه بقرار المدير، وتخصّصُه يُكتب بجانبه."""
    _lesson(school, teacher_user)
    _link(teacher_user, school, arts, specialty="إدارة أعمال")

    pages, _ = ScheduleService.teacher_pages(school, YEAR)

    assert pages[0]["department"]["specialty"] == "إدارة أعمال"


def test_the_head_of_the_department_is_carried(school, teacher_user, principal_user, arts):
    arts.head = principal_user
    arts.save(update_fields=["head"])
    _lesson(school, teacher_user)
    _link(teacher_user, school, arts)

    pages, _ = ScheduleService.teacher_pages(school, YEAR)

    assert pages[0]["department"]["head"] == principal_user.full_name


# ══════════════════════ النطاق ════════════════════════════════════


def test_a_department_scope_keeps_only_its_members(school, teacher_user, coordinator_user, arts):
    _lesson(school, teacher_user)
    _lesson(school, coordinator_user, day=1)
    _link(teacher_user, school, arts)

    pages, _ = ScheduleService.teacher_pages(school, YEAR, department="art")

    assert [p["teacher"] for p in pages] == [teacher_user]


def test_a_single_teacher_scope_is_one_page(school, teacher_user, coordinator_user):
    _lesson(school, teacher_user)
    _lesson(school, coordinator_user, day=1)

    pages, absent = ScheduleService.teacher_pages(school, YEAR, teacher_id=teacher_user.id)

    assert [p["teacher"] for p in pages] == [teacher_user]
    assert absent == [], "ورقةُ معلّمٍ واحدٍ لا فهرسَ لها"


def test_a_teacher_without_lessons_is_listed_not_printed(school, teacher_user, arts):
    """صفحةٌ فارغةٌ لا تنفع أحداً — والفهرسُ يقول إنّه لم يُنسَ."""
    _link(teacher_user, school, arts)

    pages, absent = ScheduleService.teacher_pages(school, YEAR)

    assert pages == []
    assert [a["teacher"] for a in absent] == [teacher_user]


# ══════════════════════ الشبكة تُقلب للورقة ═══════════════════════


def test_the_page_grid_is_period_by_day(school, teacher_user):
    """السطرُ حصّةٌ والعمودُ يوم — والمصفوفةُ الأصليّة معكوسةٌ عن ذلك."""
    _lesson(school, teacher_user, day=2, period=3)

    pages, _ = ScheduleService.teacher_pages(school, YEAR)
    by_period = pages[0]["by_period"]

    assert len(by_period) == 7 and len(by_period[0]) == 5
    assert by_period[2][2], "الحصّةُ الثالثةَ يومَ الثلاثاء"
    assert not by_period[0][0]


# ══════════════════════ الصلاحيّة ═════════════════════════════════


@pytest.mark.parametrize(
    "fixture", ["principal_user", "coordinator_user", "e_projects_coordinator_user"]
)
def test_the_leadership_and_both_coordinators_may_open_it(client, school, request, fixture):
    user = request.getfixturevalue(fixture)
    client.force_login(user)

    response = client.get(reverse("teacher_pages"))

    assert response.status_code == 200


def test_a_plain_teacher_may_not_browse_the_school(client, school, teacher_user):
    client.force_login(teacher_user)

    response = client.get(reverse("teacher_pages"))

    assert response.status_code in (302, 403)


def test_the_page_shows_the_department_and_the_specialty(
    client, school, principal_user, teacher_user, arts
):
    _lesson(school, teacher_user)
    _link(teacher_user, school, arts, specialty="إدارة أعمال")
    client.force_login(principal_user)

    body = client.get(reverse("teacher_pages")).content.decode()

    assert teacher_user.full_name in body
    assert "الفنون البصرية" in body
    assert "إدارة أعمال" in body
