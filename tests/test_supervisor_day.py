"""[DASHBOARD] غيابُ جناحي اليوم في لوحة المشرف وبديله (W-20261008-00x، D-249م القسم 8 و9.3).

المُجمِّعُ نفسُه مقتطَعاً لأجنحة المستخدم: لا جناحَ غيرِه في الحمولة، 403 لمن لا يحمل جناحاً أو انتهى تكليفُه، لا أسماءَ، `no-store`.
"""

import datetime as dt
import json

import pytest
from django.core.cache import cache
from django.utils import timezone

from core.models import Wing
from core.models.academic import WingCoverage
from operations.models import Session, StudentAttendance
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import ENROLLED, SUNDAY, _staff
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory

pytestmark = pytest.mark.django_db

URL = "/wings/live/"


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def _today(monkeypatch):
    """يومُ الاختبار الأحد المعلوم: اللوحةُ تقرأ `localdate()`."""
    monkeypatch.setattr(timezone, "localdate", lambda *args, **kwargs: SUNDAY)
    return SUNDAY


def _day_of(school, klass, teacher, student):
    for start, end in ((dt.time(7, 10), dt.time(7, 55)), (dt.time(8, 0), dt.time(8, 45))):
        session = Session.objects.create(
            school=school,
            class_group=klass,
            teacher=teacher,
            date=SUNDAY,
            start_time=start,
            end_time=end,
            status="scheduled",
        )
        StudentAttendance.objects.create(
            school=school, session=session, student=student, status="absent"
        )


@pytest.fixture
def other_wing_section(school, year, teacher, other_teacher, band):
    other = Wing.objects.create(
        school=school,
        code="w2",
        name="جناح 2",
        academic_year=year,
        supervisor=_staff(school, "admin_supervisor", "مشرف آخر", "29000001030"),
    )
    section = ClassGroupFactory(
        school=school, grade="G8", section="2", level_type="prep", academic_year=year, wing=other
    )
    student = UserFactory(full_name="طالب الجناح الآخر", national_id="29000009999")
    StudentEnrollmentFactory(student=student, class_group=section, enrolled_at=ENROLLED)
    _day_of(school, section, other_teacher, student)
    return section, student


def test_a_wing_holder_gets_only_their_own_wing(
    client_as, school, klass, kid, teacher, holder, bells, wing, other_wing_section, _today
):
    _day_of(school, klass, teacher, kid)
    section, other_student = other_wing_section

    response = client_as(holder).get(URL)

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    data = response.json()
    assert [row["code"] for row in data["sections"]] == [klass.short_code]
    assert [row["name"] for row in data["wings"]] == ["جناح 1"]
    assert section.short_code not in json.dumps(data, ensure_ascii=False)
    for person in (kid, other_student):
        assert person.full_name not in json.dumps(data, ensure_ascii=False)


def test_a_teacher_without_a_wing_gets_403(client_as, school, teacher, bells, _today):
    assert client_as(teacher).get(URL).status_code == 403


def test_a_substitute_sees_the_wing_only_while_the_coverage_is_live(
    client_as, school, wing, klass, kid, teacher, holder, bells, _today
):
    _day_of(school, klass, teacher, kid)
    substitute = _staff(school, "student_observer", "ملاحظ الطلبة", "29000001040")
    cover = WingCoverage.objects.create(
        wing=wing,
        substitute=substitute,
        start_date=SUNDAY - dt.timedelta(days=3),
        end_date=SUNDAY,
        assigned_by=holder,
    )
    assert client_as(substitute).get(URL).status_code == 200

    cover.end_date = SUNDAY - dt.timedelta(days=1)
    cover.save(update_fields=["end_date"])
    cache.clear()

    assert client_as(substitute).get(URL).status_code == 403


def test_the_home_page_shows_the_wing_table_without_student_names(
    client_as, school, klass, kid, teacher, holder, bells, wing, _today
):
    _day_of(school, klass, teacher, kid)

    page = client_as(holder).get("/dashboard/").content.decode()

    assert "غياب جناحي اليوم" in page and "شعبُ جناحي اليوم" in page
    assert klass.short_code in page
    assert kid.full_name not in page
    assert "data-director-live" in page
