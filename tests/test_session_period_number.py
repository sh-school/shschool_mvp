"""رقمُ الحصّة في `Session` (2026-09-24).

الحصّةُ ليوم بلا رقمها كانت تُستنتج من الوقت: فيخطئ الاستنتاجُ بين الطوابق والخميس والتعويض
(كلّها أوقاتٌ لا تطابق جرساً واحداً). فصار الرقمُ محفوظاً من الخانة التي وُلّدت منها، وتُعبَّأ
الحصصُ القائمةُ مرّةً في الهجرة 0059: من خانتها النشطة، ثمّ من جرس نطاق شعبتها.
"""

import datetime as dt
from importlib import import_module

import pytest
from django.apps import apps
from django.core.management import call_command
from django.urls import reverse

from core.models import TimeBand
from operations.models import ScheduleSlot, Session, Subject
from operations.services import ScheduleService, SubstituteService
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"
SUNDAY = dt.date(2026, 10, 11)
THURSDAY = dt.date(2026, 10, 15)


def _teacher(school, name):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


@pytest.fixture
def world(school, seeded_calendar, monkeypatch):
    from django.utils import timezone

    # التعويضُ لا يقع في الماضي، وتواريخُ التقويم المبذور ثابتة: يومُ الاختبار مثبَّت.
    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: dt.date(2026, 10, 6))
    call_command("seed_time_bands")
    bands = {b.code: b for b in TimeBand.objects.filter(school=school)}
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    ground = ClassGroupFactory(
        school=school, grade="G7", level_type="prep", academic_year=YEAR, time_band=bands["ground"]
    )
    upper = ClassGroupFactory(
        school=school,
        grade="G10",
        level_type="sec",
        academic_year=YEAR,
        time_band=bands["secondary"],
    )
    return {
        "school": school,
        "subject": subject,
        "ground": ground,
        "upper": upper,
        "teacher": _teacher(school, "معلّم"),
        "other": _teacher(school, "بديل"),
    }


def _slot(world, klass, day, period, start, end, teacher=None, active=True):
    return ScheduleSlot.objects.create(
        school=world["school"],
        teacher=teacher or world["teacher"],
        class_group=world[klass],
        subject=world["subject"],
        day_of_week=day,
        period_number=period,
        start_time=start,
        end_time=end,
        academic_year=YEAR,
        is_active=active,
    )


def _session(world, klass, day, start, end, period=None, teacher=None):
    return Session.objects.create(
        school=world["school"],
        teacher=teacher or world["teacher"],
        class_group=world[klass],
        subject=world["subject"],
        date=day,
        start_time=start,
        end_time=end,
        period_number=period,
    )


class TestEveryWriterStoresTheNumber:
    def test_generation_copies_the_slots_number(self, world):
        _slot(world, "upper", 0, 5, dt.time(10, 50), dt.time(11, 35))

        ScheduleService.ensure_sessions_for_date(world["school"], SUNDAY, academic_year=YEAR)

        assert Session.objects.get(date=SUNDAY).period_number == 5

    def test_resync_creates_missing_lessons_with_the_number(self, world):
        slot = _slot(world, "upper", 0, 3, dt.time(8, 40), dt.time(9, 20))
        ScheduleService.ensure_sessions_for_date(world["school"], SUNDAY, academic_year=YEAR)
        Session.objects.all().delete()
        assert slot.period_number == 3

        ScheduleService.resync_sessions_for_date(world["school"], SUNDAY, academic_year=YEAR)

        assert Session.objects.get(date=SUNDAY).period_number == 3

    def test_a_handed_over_lesson_keeps_its_number(self, world):
        slot = _slot(world, "upper", 0, 5, dt.time(10, 50), dt.time(11, 35))

        lesson = SubstituteService.hand_over_session(world["school"], slot, SUNDAY, world["other"])

        assert (lesson.teacher, lesson.period_number) == (world["other"], 5)

    def test_a_compensation_lesson_on_an_empty_period_carries_it(self, world, principal_user):
        from operations.models import TeacherAbsence
        from operations.services import CompensatoryService

        missed = _slot(world, "upper", 1, 3, dt.time(8, 40), dt.time(9, 20))
        absence = TeacherAbsence.objects.create(
            school=world["school"], teacher=world["teacher"], date=SUNDAY - dt.timedelta(days=7)
        )
        comp = CompensatoryService.request_compensatory(
            school=world["school"],
            teacher=world["teacher"],
            original_slot=missed,
            absence=absence,
            compensatory_date=THURSDAY,
            compensatory_period=6,
        )
        CompensatoryService.approve_compensatory(comp, approved_by=principal_user)

        lesson = comp.__class__.objects.get(pk=comp.pk).session_created
        assert (lesson.start_time, lesson.period_number) == (dt.time(11, 10), 6)


BACKFILL = import_module("operations.migrations.0059_session_period_number")


class TestBackfill:
    def _run(self):
        BACKFILL.backfill_period_number(apps, None)

    def test_the_active_slot_gives_the_number_even_if_the_teacher_changed(self, world):
        _slot(world, "upper", 0, 5, dt.time(10, 50), dt.time(11, 35))
        swapped = _session(
            world,
            "upper",
            SUNDAY,
            dt.time(10, 50),
            dt.time(11, 35),
            teacher=world["other"],
        )

        self._run()

        swapped.refresh_from_db()
        assert swapped.period_number == 5

    def test_a_lesson_of_a_replaced_plan_takes_its_bands_bell(self, world):
        # الخانةُ الأصليّةُ لم تعد نشطة: الرقمُ من جرس الطابق الأوّل (الثالثة 8:40 يومَ الخميس).
        _slot(world, "upper", 4, 3, dt.time(8, 40), dt.time(9, 20), active=False)
        old = _session(world, "upper", THURSDAY, dt.time(8, 40), dt.time(9, 20))

        self._run()

        old.refresh_from_db()
        assert old.period_number == 3

    def test_thursday_uses_the_thursday_bell_not_sundays(self, world):
        # 11:10 سادسةُ الثانويّ الخميس؛ ويومَ الأحد 11:10 لا حصّةَ تبدأ فيه.
        thursday = _session(world, "upper", THURSDAY, dt.time(11, 10), dt.time(11, 50))
        sunday = _session(world, "upper", SUNDAY, dt.time(11, 10), dt.time(11, 50))

        self._run()

        thursday.refresh_from_db()
        sunday.refresh_from_db()
        assert (thursday.period_number, sunday.period_number) == (6, None)

    def test_each_band_reads_its_own_bell(self, world):
        # 8:50 ثالثةُ الأرضيّ الأحد، ولا تطابق في جرس الطابق الأوّل (8:45).
        ground = _session(world, "ground", SUNDAY, dt.time(8, 50), dt.time(9, 35))
        upper = _session(
            world, "upper", SUNDAY, dt.time(8, 50), dt.time(9, 35), teacher=world["other"]
        )

        self._run()

        ground.refresh_from_db()
        upper.refresh_from_db()
        assert (ground.period_number, upper.period_number) == (3, None)

    def test_an_unmatched_lesson_stays_unknown_and_a_set_one_is_untouched(self, world):
        odd = _session(world, "upper", SUNDAY, dt.time(9, 0), dt.time(9, 45))
        kept = _session(
            world,
            "upper",
            SUNDAY,
            dt.time(10, 50),
            dt.time(11, 35),
            period=7,
            teacher=world["other"],
        )
        _slot(world, "upper", 0, 5, dt.time(10, 50), dt.time(11, 35))

        self._run()

        odd.refresh_from_db()
        kept.refresh_from_db()
        assert (odd.period_number, kept.period_number) == (None, 7)


class TestThePeriodFilterUsesTheStoredNumber:
    def test_leadership_filters_todays_lessons_by_period(self, world, principal_user, client):
        # حصّتان في يومٍ واحد: الثانيةُ 7:55 والخامسةُ 10:50 — لا تطابق أوقاتُهما جرساً واحداً.
        _slot(world, "upper", 0, 2, dt.time(7, 55), dt.time(8, 40))
        _slot(world, "ground", 0, 5, dt.time(10, 50), dt.time(11, 35), teacher=world["other"])
        client.force_login(principal_user)

        def rows(period):
            return (
                client.get(
                    reverse("teacher_schedule"),
                    {"date": SUNDAY.isoformat(), "period": period, "all": "1"},
                    HTTP_HOST="localhost",
                )
                .content.decode()
                .count("data-filter-row data-text=")  # صفٌّ لكلّ حصّة؛ ذكرُه في السكربت لا يُعدّ
            )

        assert (rows("5"), rows("2"), rows("")) == (1, 1, 2)

    def test_a_bad_period_value_is_ignored_not_a_server_error(self, world, principal_user, client):
        _slot(world, "upper", 0, 2, dt.time(7, 55), dt.time(8, 40))
        client.force_login(principal_user)

        response = client.get(
            reverse("teacher_schedule"),
            {"date": SUNDAY.isoformat(), "period": "abc", "all": "1"},
            HTTP_HOST="localhost",
        )

        assert response.status_code == 200
