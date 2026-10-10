"""محدِّدُ يومِ اللوحة لكلّ الأدوار — عرضٌ للقراءة فقط ضمن العام الدراسيّ (W-20261010-056، قرارُ المالك 2026-10-11).

الحدودُ التي يُحرسها هذا الملفّ، كلٌّ باختبارٍ يفشل إن زالت:
1. المدى من تقويم الباك اند (`academic_year_window`) لا من تاريخٍ مكتوب؛ وخارجه أو نصٌّ لا يُقرأ ← اليومُ الحقيقيّ.
2. كلُّ الأدوار: السابقُ والتالي واليومُ على كلّ لوحةٍ، ولكلٍّ (اليومُ · يومٌ مضى · يومٌ آتٍ · خارجَ المدى).
3. العدّاداتُ من سجلات اليوم المختار لا من اليوم الحقيقيّ.
4. للقراءة فقط: لا رابطَ تسجيلِ حضورٍ ولا لوحاتِ رصدٍ ولا توليدَ حصصٍ في غير اليوم الحقيقيّ.
5. «الحصّة التالية» تخصّ اليومَ الحقيقيَّ وحدَه، بساعة الدوحة.
6. طورُ اليوم (حيّ/نهائيّ) للمدير يتبع اليومَ المعروض لا ساعةَ الجدار.
"""

import datetime as dt

import pytest
from django.utils import timezone

from core import dashboard_day_selectors
from core.dashboard_day_selectors import chosen_day, day_nav, day_window
from operations.class_exit import leave
from operations.day_selectors import PHASE_FINAL, PHASE_LIVE, clock_on, day_phase
from operations.models import Session
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import ENROLLED, SATURDAY, SUNDAY, _staff, at
from tests.conftest import (
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)
from tests.test_dashboard_roles import ROLE_CASES

pytestmark = pytest.mark.django_db

#: العامُ الدراسيّ بفصلَيه كما يعيده التقويم (يُثبَّت ليبقى الاختبارُ ثابتاً).
WINDOW = (dt.date(2026, 9, 1), dt.date(2027, 6, 30))
PAST = dt.date(2026, 9, 10)  # الخميس: قبل «اليوم» المثبَّت
FUTURE = dt.date(2026, 11, 3)  # بعده، داخل المدى
BEFORE_YEAR = dt.date(2026, 8, 31)
AFTER_YEAR = dt.date(2027, 7, 1)


@pytest.fixture(autouse=True)
def _window(monkeypatch):
    monkeypatch.setattr(dashboard_day_selectors, "academic_year_window", lambda *_a, **_k: WINDOW)


def _freeze(monkeypatch, doha_hm=(10, 0), day=SUNDAY):
    """يثبّت اللحظةَ عند ساعةٍ بتوقيت الدوحة (تقابل UTC بفارق ثلاث ساعات)."""
    moment = at(*doha_hm, day=day).astimezone(dt.UTC)
    monkeypatch.setattr(timezone, "now", lambda: moment)


def _get(client_as, user, day=None):
    return client_as(user).get("/dashboard/", {"date": day.isoformat()} if day else {})


class TestWindowAndChoice:
    def test_the_range_is_the_backend_calendar_window_not_a_written_date(self, school):
        assert day_window(school, SUNDAY) == WINDOW

    def test_no_window_means_only_today(self, monkeypatch, school):
        monkeypatch.setattr(dashboard_day_selectors, "academic_year_window", lambda *_a, **_k: None)

        assert day_window(school, SUNDAY) == (SUNDAY, SUNDAY)
        assert chosen_day(school, SUNDAY, PAST.isoformat()) == SUNDAY

    @pytest.mark.parametrize("day", [WINDOW[0], PAST, FUTURE, WINDOW[1]], ids=str)
    def test_a_day_inside_the_year_is_honoured_both_semesters_and_both_edges(self, school, day):
        assert chosen_day(school, SUNDAY, day.isoformat()) == day

    @pytest.mark.parametrize("day", [BEFORE_YEAR, AFTER_YEAR], ids=str)
    def test_a_day_just_outside_the_year_goes_back_to_today(self, school, day):
        assert chosen_day(school, SUNDAY, day.isoformat()) == SUNDAY

    @pytest.mark.parametrize("raw", [None, "", "garbage", "2026-13-40", "13/09/2026", "٢٠٢٦-٠٩-١٣"])
    def test_unreadable_input_goes_back_to_today_silently(self, school, raw):
        assert chosen_day(school, SUNDAY, raw) == SUNDAY

    def test_nav_links_stop_at_the_edges_and_today_has_no_parameter(self, school):
        first = day_nav(school, SUNDAY, WINDOW[0], "/dashboard/")
        last = day_nav(school, SUNDAY, WINDOW[1], "/dashboard/")
        today = day_nav(school, SUNDAY, SUNDAY, "/dashboard/")
        eve = day_nav(school, SUNDAY, SATURDAY, "/dashboard/")

        assert first["prev_url"] is None and first["next_url"] == "/dashboard/?date=2026-09-02"
        assert last["next_url"] is None and last["prev_url"] == "/dashboard/?date=2027-06-29"
        assert today["is_today"] and today["prev_url"] == "/dashboard/?date=2026-09-12"
        assert eve["next_url"] == "/dashboard/", "التالي لأمسِ هو اليومُ الحقيقيّ بلا وسيط"
        assert (today["min"], today["max"]) == ("2026-09-01", "2027-06-30")


class TestEveryRoleGetsThePicker:
    """أحدَ عشرَ دوراً + الطالبُ وحاملُ الجناح: اللوحةُ نفسُها تحمل المحدِّدَ، ولكلّ حالةٍ سياقُها."""

    CASES = [
        pytest.param(None, False, SUNDAY, id="today"),
        pytest.param(PAST, True, PAST, id="past-day"),
        pytest.param(FUTURE, True, FUTURE, id="future-day"),
        pytest.param(AFTER_YEAR, False, SUNDAY, id="outside-range-falls-back"),
        pytest.param(BEFORE_YEAR, False, SUNDAY, id="before-year-falls-back"),
    ]

    @pytest.mark.parametrize("role_name,_marker", ROLE_CASES)
    @pytest.mark.parametrize("asked,read_only,shown", CASES)
    def test_role_by_day_matrix(
        self, monkeypatch, client_as, school, role_name, _marker, asked, read_only, shown
    ):
        _freeze(monkeypatch)
        user = UserFactory(full_name="مستخدمُ اختبار")
        MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))

        resp = _get(client_as, user, asked)

        assert resp.status_code == 200
        assert resp.context["today"] == shown
        assert resp.context["view_only"] is read_only
        body = resp.content.decode()
        assert 'class="day-picker"' in body
        assert ("عرضٌ للقراءة فقط" in body) is read_only

    @pytest.mark.parametrize("asked,read_only,shown", CASES)
    def test_student_and_wing_holder_too(
        self, monkeypatch, client_as, kid, holder, wing, klass, asked, read_only, shown
    ):
        _freeze(monkeypatch)

        for user in (kid, holder):
            resp = _get(client_as, user, asked)

            assert resp.status_code == 200
            assert resp.context["today"] == shown and resp.context["view_only"] is read_only
            assert 'class="day-picker"' in resp.content.decode()

    def test_the_subtitle_carries_the_chosen_date_not_the_real_one(
        self, monkeypatch, client_as, teacher
    ):
        _freeze(monkeypatch)

        resp = _get(client_as, teacher, PAST)

        assert resp.context["subtitle"].endswith("10/09/2026")

    def test_the_edges_render_disabled_steps_not_dead_links(self, monkeypatch, client_as, teacher):
        _freeze(monkeypatch)

        first = _get(client_as, teacher, WINDOW[0]).content.decode()
        last = _get(client_as, teacher, WINDOW[1]).content.decode()

        assert 'rel="prev"' not in first and 'rel="next"' in first
        assert 'rel="next"' not in last and 'rel="prev"' in last


class TestCountersFollowTheChosenDay:
    def test_a_prior_day_shows_its_own_exits_not_todays(
        self, monkeypatch, client_as, school, klass, teacher, session, bells
    ):
        _freeze(monkeypatch)
        a, b = (UserFactory(full_name=f"طالبٌ {i}", national_id=f"2900000{i:04d}") for i in range(2))
        for student in (a, b):
            StudentEnrollmentFactory(student=student, class_group=klass, enrolled_at=ENROLLED)
        earlier = Session.objects.create(
            school=school,
            class_group=klass,
            teacher=teacher,
            date=PAST,
            start_time=dt.time(7, 10),
            end_time=dt.time(7, 55),
            status="completed",
        )
        leave(session, a, "restroom", by=teacher, now=at(7, 20))  # اليوم: خروجٌ واحدٌ لم يعد.
        leave(
            earlier, a, "restroom", by=teacher, now=at(7, 20, day=PAST)
        )  # الماضي: خروجان لم يعد منهما أحد.
        leave(earlier, b, "clinic", by=teacher, now=at(7, 30, day=PAST))

        today = _get(client_as, teacher).context["my_students"]
        past = _get(client_as, teacher, PAST).context["my_students"]

        assert (today["exit_total"], today["out_now"]) == (1, 1)
        assert (past["exit_total"], past["out_now"]) == (2, 2)
        assert [s.pk for s in _get(client_as, teacher, PAST).context["sessions"]] == [earlier.pk]


class TestViewOnly:
    def test_a_past_day_lists_sessions_without_an_attendance_link(
        self, monkeypatch, client_as, school, klass, teacher, session, bells
    ):
        from operations.services import provisional_session

        monkeypatch.setattr(provisional_session, "enabled", lambda: False)
        _freeze(monkeypatch)
        earlier = Session.objects.create(
            school=school,
            class_group=klass,
            teacher=teacher,
            date=PAST,
            start_time=dt.time(7, 10),
            end_time=dt.time(7, 55),
            status="scheduled",
        )

        today_html = _get(client_as, teacher).content.decode()
        past_html = _get(client_as, teacher, PAST).content.decode()

        assert f"/teacher/attendance/{session.pk}/" in today_html
        assert f"/teacher/attendance/{earlier.pk}/" not in past_html, "لا فتحَ رصدٍ من يومٍ غير اليوم"
        assert "تسجيل حضور" not in past_html

    def test_provisional_recording_button_is_today_only(
        self, monkeypatch, client_as, teacher, session, bells
    ):
        from operations.services import provisional_session

        monkeypatch.setattr(provisional_session, "enabled", lambda: True)
        _freeze(monkeypatch)

        today = _get(client_as, teacher).content.decode()
        past = _get(client_as, teacher, PAST).content.decode()

        assert "شُعبي للرصد" in today
        assert "شُعبي للرصد" not in past and "عرضٌ للقراءة فقط" in past

    def test_the_supervisor_gets_no_recording_panels_and_no_generated_sessions(
        self, monkeypatch, client_as, holder, wing, klass, bells
    ):
        from operations.services import ScheduleService

        _freeze(monkeypatch)
        calls = []
        monkeypatch.setattr(
            ScheduleService, "ensure_sessions_for_date", lambda _school, day: calls.append(day)
        )

        # وسيطُ التوليد التلقائيّ يطلب اليومَ الحقيقيَّ في كلّ طلب؛ فالمحروسُ ألّا يُطلب يومٌ غيرُه.
        past = _get(client_as, holder, PAST)
        assert PAST not in calls, "يومٌ مضى لا يُولَّد له حصص"
        assert past.context["record_panels"] == [], "ولا لوحاتِ رصدٍ تُفتح"
        _get(client_as, holder, FUTURE)
        assert FUTURE not in calls, "ولا يومٌ آتٍ"
        _get(client_as, holder)
        assert SUNDAY in calls, "اليومُ الحقيقيّ كما كان"

    def test_the_supervisor_header_has_no_recording_button_off_today(
        self, monkeypatch, client_as, holder, wing, klass, bells
    ):
        _freeze(monkeypatch)

        today = _get(client_as, holder).content.decode()
        past = _get(client_as, holder, PAST).content.decode()

        button = '<a href="/wings/record/" class="btn-primary btn-sm">'  # زرُّ ترويسة اللوحة لا قائمةُ التنقّل
        assert button in today
        assert button not in past


class TestNextSessionIsTodayOnly:
    def test_next_session_exists_today_but_never_on_another_day(
        self, monkeypatch, client_as, school, klass, teacher, session, bells
    ):
        _freeze(monkeypatch, (7, 0))  # قبل الحصّة الأولى (07:10) بتوقيت الدوحة.
        Session.objects.create(
            school=school,
            class_group=klass,
            teacher=teacher,
            date=FUTURE,
            start_time=dt.time(7, 10),
            end_time=dt.time(7, 55),
            status="scheduled",
        )

        assert _get(client_as, teacher).context["next_session"] == session
        assert _get(client_as, teacher, FUTURE).context["next_session"] is None
        assert _get(client_as, teacher, PAST).context["next_session"] is None

    def test_just_after_doha_midnight_yesterday_is_a_past_day(
        self, monkeypatch, client_as, school, klass, teacher, session, bells
    ):
        """21:30 UTC من الأحد = 00:30 من الاثنين بالدوحة: «اليوم» الاثنين، والأحدُ يومٌ مضى للقراءة فقط."""
        moment = timezone.make_aware(dt.datetime(2026, 9, 14, 0, 30)).astimezone(dt.UTC)
        assert moment.date() == SUNDAY
        monkeypatch.setattr(timezone, "now", lambda: moment)

        default = _get(client_as, teacher)
        sunday = _get(client_as, teacher, SUNDAY)

        assert default.context["today"] == dt.date(2026, 9, 14) and not default.context["view_only"]
        assert sunday.context["today"] == SUNDAY and sunday.context["view_only"] is True
        assert sunday.context["next_session"] is None, "00:30 لا تجعل حصّةَ الأحد 07:10 «تالية»"

    def test_therapist_context_too(self, monkeypatch, client_as, school, klass, bells):
        _freeze(monkeypatch, (7, 0))
        therapist = _staff(school, "speech_therapist", "معالج", "29000001040")
        mine = Session.objects.create(
            school=school,
            class_group=klass,
            teacher=therapist,
            date=SUNDAY,
            start_time=dt.time(7, 10),
            end_time=dt.time(7, 55),
            status="scheduled",
        )

        assert _get(client_as, therapist).context["next_session"] == mine
        assert _get(client_as, therapist, PAST).context["next_session"] is None


class TestDirectorPhaseFollowsTheShownDay:
    """`day_phase` كان يقرأ ساعةَ الجدار لأيّ يوم: لوحةُ المدير ليومٍ مضى تُرى «حيّةً» صباحاً."""

    def test_clock_on_other_days(self):
        morning = at(10, 0)

        assert clock_on(SUNDAY, morning) == dt.time(10, 0)
        assert clock_on(PAST, morning) == dt.time.max
        assert clock_on(FUTURE, morning) == dt.time.min

    def test_phase_of_a_past_day_is_final_even_in_the_morning(self, school, bells):
        morning = at(10, 0)

        assert day_phase(school, SUNDAY, morning) == PHASE_LIVE
        assert day_phase(school, SUNDAY, at(14, 0)) == PHASE_FINAL
        assert day_phase(school, dt.date(2026, 9, 6), morning) == PHASE_FINAL, "أحدٌ سابق: حكمُ يومه"
        assert day_phase(school, dt.date(2026, 9, 20), morning) == PHASE_LIVE, "أحدٌ آتٍ: لم يبدأ"

    def test_director_page_shows_a_past_school_day_as_final_and_does_not_poll(
        self, monkeypatch, client_as, school, principal_user, bells
    ):
        _freeze(monkeypatch)  # الأحد 10:00 — لو قرأ الطورَ من الساعة لبدا «حيّاً».
        past_sunday = dt.date(2026, 9, 6)

        resp = _get(client_as, principal_user, past_sunday)

        assert resp.status_code == 200
        assert resp.context["day"].phase == PHASE_FINAL
        assert resp.context["day_final"] is True
        assert "js/director-live.js" not in resp.content.decode(), "لا استطلاعَ حيّاً ليومٍ مضى"
