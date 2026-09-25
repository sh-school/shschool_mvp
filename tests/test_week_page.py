"""الجدولُ الأسبوعيّ الديناميكيّ (2/3): الصفحةُ على الأسبوع الفعليّ وأزرارُ التنقّل (2026-09-25).

قراراتُ المالك: الصفحةُ تفتح على الأسبوع الفعليّ من حصص الأيّام، والخطّةُ المعتمدةُ زرٌّ يبقى؛ وأسبوعٌ لم
يُولَّد يُعرض من الخطّة بوسمها؛ وعلاماتٌ لونيّةٌ و«عن فلان». والطباعةُ والتصديرُ يبقيان على الخطّة ما لم
يُطلب الأسبوعُ الفعليّ صراحةً — فالجدولُ المعلَّقُ في المدرسة هو الخطّةُ لا أسبوعٌ بعينه.
"""

import datetime as dt

import pytest
from django.core.management import call_command
from django.urls import reverse

from core.models import TimeBand
from operations.models import ScheduleSlot, Subject
from operations.services import ScheduleService, SubstituteService
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"
SUNDAY = dt.date(2026, 10, 11)
TODAY = dt.date(2026, 10, 14)  # أربعاءُ ذلك الأسبوع
BREAK_SUNDAY = dt.date(2026, 10, 25)


def _teacher(school, name):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


def _slot(w, teacher, day, period, start, end, subject):
    return ScheduleSlot.objects.create(
        school=w["school"],
        teacher=teacher,
        class_group=w["upper"],
        subject=subject,
        day_of_week=day,
        period_number=period,
        start_time=start,
        end_time=end,
        academic_year=YEAR,
    )


@pytest.fixture
def world(school, seeded_calendar, principal_user, monkeypatch):
    from django.utils import timezone

    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: TODAY)
    call_command("seed_time_bands")
    band = TimeBand.objects.get(school=school, code="secondary")
    w = {
        "school": school,
        "principal": principal_user,
        "math": Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT"),
        "science": Subject.objects.create(school=school, name_ar="العلوم", code="SCI"),
        "t1": _teacher(school, "معلّمٌ أوّل"),
        "t2": _teacher(school, "معلّمٌ ثانٍ"),
        "sub": _teacher(school, "البديل"),
        "upper": ClassGroupFactory(
            school=school, grade="G10", level_type="sec", academic_year=YEAR, time_band=band
        ),
    }
    w["s1"] = _slot(w, w["t1"], 0, 1, dt.time(7, 10), dt.time(8, 0), w["math"])
    for day in (1, 2, 3, 4):  # حصّةٌ في كلّ يوم: يومٌ بلا حصصٍ للمدرسة كلّها يبدو «لم يُولَّد»
        _slot(w, w["t2"], day, 2, dt.time(8, 0), dt.time(8, 45), w["science"])
    return w


def _teacher_page(client, w, who, **params):
    client.force_login(w["principal"])
    query = {"view": "teacher", "teacher": str(who.id), "year": YEAR, **params}
    return client.get(reverse("weekly_schedule"), query, HTTP_HOST="localhost")


def _generate(w):
    ScheduleService.ensure_sessions_for_date(w["school"], SUNDAY, academic_year=YEAR)


class TestThePageOpensOnTheActualWeek:
    def test_default_is_the_current_week_with_navigation(self, world, client):
        body = _teacher_page(client, world, world["t1"]).content.decode()

        assert "الأسبوع السابق" in body and "الأسبوع التالي" in body
        assert "11 أكتوبر" in body and "15 أكتوبر 2026" in body, "نطاقُ الأسبوع الجاريّ"
        assert "الخطّة المعتمدة" in body
        assert "هذا الأسبوع" not in body, "لا زرَّ «هذا الأسبوع» وأنت فيه"

    def test_a_substitution_appears_in_the_holders_week_with_its_note(self, world, client):
        _generate(world)
        SubstituteService.hand_over_session(world["school"], world["s1"], SUNDAY, world["sub"])

        body = _teacher_page(client, world, world["sub"]).content.decode()

        assert "تبديل — كانت لـمعلّمٌ أوّل" in body
        assert "k-swap" in body, "الخانةُ ملوَّنة"
        assert "week-legend__swatch is-swap" in body, "ومفتاحُ الألوان يفسّرها"

    def test_the_original_teachers_week_no_longer_has_it(self, world, client):
        _generate(world)
        SubstituteService.hand_over_session(world["school"], world["s1"], SUNDAY, world["sub"])

        body = _teacher_page(client, world, world["t1"]).content.decode()

        assert "الرياضيات" not in body.split("<tbody", 1)[1]

    def test_days_not_generated_yet_are_marked_as_from_the_plan(self, world, client):
        # الأسبوعُ الجاري يولّده الوسيطُ عند أوّل طلبٍ في اليوم، فالخطّةُ تظهر في الأسابيع القادمة.
        body = _teacher_page(client, world, world["t1"], week="2026-10-18").content.decode()

        assert "فتُعرض وفق الخطّة المعتمدة" in body
        assert "الأحد" in body.split("لم تُولَّد حصصُ", 1)[1].split("بعد", 1)[0]


class TestNavigationBetweenWeeks:
    def test_the_arrows_move_a_week_and_keep_the_selection(self, world, client):
        body = _teacher_page(client, world, world["t2"], week="2026-10-18").content.decode()

        assert "18 أكتوبر" in body and "22 أكتوبر 2026" in body
        assert "week=2026-10-11" in body, "السابقُ"
        assert "week=2026-10-25" in body, "والتالي"
        assert f"teacher={world['t2'].id}" in body, "المعلّمُ محمولٌ في الروابط"
        assert "هذا الأسبوع" in body, "خارجَ الأسبوع الجاري يظهر زرُّ العودة"

    def test_a_holiday_week_says_why_there_are_no_lessons(self, world, client):
        body = _teacher_page(
            client, world, world["t1"], week=BREAK_SUNDAY.isoformat()
        ).content.decode()

        assert "إجازة منتصف الفصل الأول" in body and "لا حصص" in body

    def test_a_broken_or_far_week_falls_back_to_the_current_one(self, world, client):
        for raw in ("not-a-date", "2031-01-01", ""):
            body = _teacher_page(client, world, world["t1"], week=raw).content.decode()
            assert "11 أكتوبر" in body and "15 أكتوبر 2026" in body, raw

    def test_any_day_of_a_week_lands_on_that_week(self, world, client):
        body = _teacher_page(
            client, world, world["t2"], week="2026-10-21"
        ).content.decode()  # أربعاء

        assert "18 أكتوبر" in body


class TestThePlanIsAButton:
    def test_the_plan_view_has_no_week_arrows_but_a_way_back(self, world, client):
        _generate(world)
        SubstituteService.hand_over_session(world["school"], world["s1"], SUNDAY, world["sub"])

        body = _teacher_page(client, world, world["sub"], source="plan").content.decode()

        assert "الأسبوع السابق" not in body
        assert "الأسبوع الفعليّ" in body and "source=actual" in body
        assert "تبديل — كانت" not in body, "الخطّةُ كما اعتُمدت لا كما جرت"


class TestPrintAndExportStayOnThePlan:
    def test_the_print_sheet_without_a_source_is_the_plan(self, world, client):
        _generate(world)
        SubstituteService.hand_over_session(world["school"], world["s1"], SUNDAY, world["sub"])
        client.force_login(world["principal"])
        query = {"view": "teacher", "teacher": str(world["sub"].id), "year": YEAR}

        body = client.get(reverse("schedule_print"), query, HTTP_HOST="localhost").content.decode()

        assert "تبديل — كانت" not in body and "الرياضيات" not in body.split("<tbody", 1)[-1]

    def test_the_print_sheet_follows_an_explicit_actual_week(self, world, client):
        _generate(world)
        SubstituteService.hand_over_session(world["school"], world["s1"], SUNDAY, world["sub"])
        client.force_login(world["principal"])
        query = {
            "view": "teacher",
            "teacher": str(world["sub"].id),
            "year": YEAR,
            "source": "actual",
            "week": SUNDAY.isoformat(),
        }

        body = client.get(reverse("schedule_print"), query, HTTP_HOST="localhost").content.decode()

        assert "تبديل — كانت لـمعلّمٌ أوّل" in body

    def test_the_pages_own_print_and_export_links_carry_the_chosen_week(self, world, client):
        body = _teacher_page(client, world, world["t1"], week="2026-10-18").content.decode()

        assert "source=actual" in body and "week=2026-10-18" in body
        assert reverse("schedule_export_pdf") + "?" in body

    def test_the_general_schedule_frame_follows_the_week(self, world, client):
        client.force_login(world["principal"])

        body = client.get(
            reverse("weekly_schedule"),
            {"view": "all_teachers", "year": YEAR, "week": "2026-10-18"},
            HTTP_HOST="localhost",
        ).content.decode()

        frame = body.split('id="schedule-print-frame"', 1)[1].split(">", 1)[0]
        assert "source=actual" in frame and "week=2026-10-18" in frame
