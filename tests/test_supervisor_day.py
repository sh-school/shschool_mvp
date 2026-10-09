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


def test_the_home_page_shows_each_sections_schedule_state_on_its_chip_without_a_table(
    client_as, school, klass, kid, teacher, holder, bells, wing, _today
):
    """W-20261008-007 (قياسُ 2026-10-08): حالةُ جدول الشعبة في رقاقتها لا في جدولٍ مكرَّر يطيل الصفحةَ 343px؛ وبلا أسماء طلبة."""
    _day_of(school, klass, teacher, kid)

    page = client_as(holder).get("/dashboard/").content.decode()

    assert "غياب جناحي اليوم" in page and "شعبُ جناحي اليوم" not in page
    assert f'data-key="section.{klass.id}.state_label"' in page
    assert f'data-key="section.{klass.id}.recorded"' in page
    assert "<table" not in page.split("غياب جناحي اليوم")[1].split("ui-actions")[0]
    assert kid.full_name not in page
    assert "data-director-live" in page


def test_the_other_wings_holder_sees_the_other_wing_and_not_this_one(
    client_as, school, klass, kid, teacher, holder, bells, wing, other_wing_section, _today
):
    """التناظر: المشرفُ الآخر يقرأ جناحَه وحدَه — لا يصله ما لجناح الأوّل (W-20261008-007)."""
    _day_of(school, klass, teacher, kid)
    section, _student = other_wing_section
    other_holder = Wing.objects.get(code="w2", school=school).supervisor

    data = client_as(other_holder).get(URL).json()

    assert [row["code"] for row in data["sections"]] == [section.short_code]
    assert [row["name"] for row in data["wings"]] == ["جناح 2"]
    assert klass.short_code not in json.dumps(data, ensure_ascii=False)


def test_a_school_wide_holder_gets_403_because_his_screen_is_the_five_wings(
    client_as, school, bells, wing, _today
):
    """حاصرُ الغياب العامّ يرى الخمسةَ في «رصد الغياب»: لا حمولةَ مشرفٍ له، فيتوقّف عميلُه ولا يعيد المحاولة."""
    coordinator = _staff(school, "student_affairs_coordinator", "منسّق شؤون الطلبة", "29000001050")

    assert client_as(coordinator).get(URL).status_code in (403, 302)


def test_the_live_endpoint_costs_a_fixed_number_of_queries_and_the_second_read_hits_the_cache(
    client_as,
    school,
    klass,
    kid,
    teacher,
    holder,
    bells,
    wing,
    other_wing_section,
    _today,
    django_assert_max_num_queries,
):
    """سقفُ الاستعلامات: الأجنحةُ الإضافيّةُ لا تضاعفه، والقراءةُ الثانيةُ من الذاكرة المشتركة (20 ث) أرخص."""
    _day_of(school, klass, teacher, kid)
    client = client_as(holder)
    client.get(URL)  # يسخّن الجلسةَ والصلاحيّاتِ ويملأ المخزَّن

    with django_assert_max_num_queries(16) as warm:  # مقيس 13: جلسةٌ وصلاحيّاتٌ وأجنحةٌ بلا حساب الملخّص
        assert client.get(URL).status_code == 200
    cache.clear()
    with django_assert_max_num_queries(30) as cold:  # مقيس 25: حساب الملخّص مرّةً واحدةً لكلّ المدرسة
        assert client.get(URL).status_code == 200
    assert len(warm.captured_queries) < len(cold.captured_queries)


def test_the_poll_script_stops_in_a_hidden_tab_and_the_endpoint_comes_from_the_page():
    """الاستطلاعُ يتوقّف حين تُخفى الصفحة ويستأنف عند ظهورها، والمسارُ من السمة لا من مُدخَلٍ في الطلب."""
    from pathlib import Path

    from django.conf import settings

    source = (Path(settings.BASE_DIR) / "static" / "js" / "director-live.js").read_text(
        encoding="utf-8"
    )

    assert "document.hidden" in source
    assert "visibilitychange" in source
    assert 'getAttribute("data-live-url")' in source
    assert "clearTimeout" in source
