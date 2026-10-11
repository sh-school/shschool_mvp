"""تنبيها المعلّم «خارج لم يعد» و«حصّة بلا رصد» (W-20261010-042).

ما يُثبَت: المستلمُ المعلّمُ وحدَه، إشعارٌ واحدٌ لكلّ (معلّم، كائن، يوم) مهما تكرّرت المهمّة، لا اسمَ طالبٍ في النصّ،
استعلاماتُ المسح ثابتةٌ بعدد الخروج والحصص، والجدولةُ معطَّلةٌ ما لم يُفعَّل المتغيّر، ونوعا الحدث مسجَّلان.
"""

import datetime as dt

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext, override_settings

from notifications import teacher_alerts as ta
from notifications.models import InAppNotification
from notifications.teacher_alerts_beat import teacher_alerts_beat
from operations.class_exit import leave
from operations.models import AttendanceEntry, Session, StudentAttendance
from tests.test_period_register import (  # noqa: F401 — التجهيزاتُ نفسُها
    SUNDAY,
    _periods,
    at,
    klass,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _provisional_door_closed(settings):
    """بيئةُ الاختبار قد تُشغّل «الرصد المؤقّت» (يُخفي حصصَ المنصّة)؛ نُطفئه إلا في اختباره الصريح."""
    settings.PROVISIONAL_GRID_ENABLED = False


@pytest.fixture
def kids(school, klass):
    """طلابُ الشعبة — قيدُهم قبل يوم الاختبار (القيدُ الافتراضيّ «اليوم الحقيقيّ» وحصصُنا في 2026-09-13)."""
    from tests.conftest import StudentEnrollmentFactory, UserFactory

    made = []
    for i in range(4):
        student = UserFactory(full_name=f"طالب {i}", national_id=f"2930000000{i}")
        StudentEnrollmentFactory(
            student=student, class_group=klass, enrolled_at=SUNDAY - dt.timedelta(days=30)
        )
        made.append(student)
    return made


def _mine(user, event_type):
    return InAppNotification.objects.filter(user=user, event_type=event_type)


class TestUnreturnedExit:
    def test_alerts_the_teacher_once_after_the_threshold(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        leave(period, kids[0], "restroom", by=teacher, now=at(7, 20))

        assert ta.alert_unreturned_exits(school, now=at(7, 30)) == 0, "دون العتبة (15 دقيقة)"
        assert ta.alert_unreturned_exits(school, now=at(7, 40)) == 1

        note = _mine(teacher, ta.EXIT_NOT_RETURNED).get()
        assert note.priority == "high"
        assert note.related_object_id and note.related_url.endswith(f"?date={SUNDAY.isoformat()}")

    def test_running_the_task_twice_leaves_one_notification(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        leave(period, kids[0], "restroom", by=teacher, now=at(7, 20))

        assert ta.alert_unreturned_exits(school, now=at(7, 40)) == 1
        assert ta.alert_unreturned_exits(school, now=at(7, 41)) == 0
        assert ta.alert_unreturned_exits(school, now=at(7, 50)) == 0

        assert _mine(teacher, ta.EXIT_NOT_RETURNED).count() == 1

    def test_each_exit_gets_its_own_notification(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        leave(period, kids[0], "restroom", by=teacher, now=at(7, 20))
        leave(period, kids[1], "restroom", by=teacher, now=at(7, 22))

        assert ta.alert_unreturned_exits(school, now=at(7, 40)) == 2
        assert _mine(teacher, ta.EXIT_NOT_RETURNED).count() == 2

    def test_silent_once_the_student_is_back(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        from operations.class_exit import come_back

        (period,) = _periods(school, klass, teacher, 1)
        leave(period, kids[0], "restroom", by=teacher, now=at(7, 20))
        come_back(period, kids[0], now=at(7, 30))

        assert ta.alert_unreturned_exits(school, now=at(7, 45)) == 0

    def test_silent_after_the_bell(self, school, seeded_calendar, klass, kids, teacher, supervisor):
        """بعد الجرس يُغلق الخروجُ ويرحَّل — التنبيهُ لحصّةٍ جاريةٍ فقط."""
        (period,) = _periods(school, klass, teacher, 1)
        leave(period, kids[0], "restroom", by=teacher, now=at(7, 20))

        assert ta.alert_unreturned_exits(school, now=at(8, 5)) == 0

    def test_recipient_is_only_the_session_teacher_and_the_text_has_no_name(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        leave(period, kids[0], "admin", by=teacher, now=at(7, 20))
        InAppNotification.objects.all().delete()  # إشعارُ المشرف عن بطاقة الخروج ليس موضوعَنا

        ta.alert_unreturned_exits(school, now=at(7, 40))

        notes = list(InAppNotification.objects.all())
        assert {n.user_id for n in notes} == {teacher.pk}, "لا ولي أمرٍ ولا طالب ولا مشرف"
        text = " ".join(f"{n.title} {n.body}" for n in notes)
        for kid in kids:
            assert kid.full_name not in text and kid.national_id not in text

    def test_threshold_comes_from_the_environment(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        leave(period, kids[0], "restroom", by=teacher, now=at(7, 20))
        env = {"TEACHER_EXIT_ALERT_MINUTES": "30"}

        assert ta.alert_unreturned_exits(school, now=at(7, 40), environ=env) == 0
        assert ta.alert_unreturned_exits(school, now=at(7, 51), environ=env) == 1

    def test_scan_queries_do_not_grow_with_the_number_of_exits(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 2)
        leave(periods[0], kids[0], "restroom", by=teacher, now=at(7, 20))
        with CaptureQueriesContext(connection) as one:
            ta.unreturned_exits(school, at(7, 40), 15)
        for kid in kids[1:]:
            leave(periods[0], kid, "restroom", by=teacher, now=at(7, 21))
        leave(periods[1], kids[0], "restroom", by=teacher, now=at(8, 20))
        with CaptureQueriesContext(connection) as many:
            found = ta.unreturned_exits(school, at(8, 40), 15)
            found += ta.unreturned_exits(school, at(7, 40), 15)

        assert len(found) >= 4
        assert len(many) == 2 * len(one)


class TestUnmarkedSession:
    def test_flags_an_ended_session_without_any_entry(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        first, second = _periods(school, klass, teacher, 2)

        assert ta.alert_unmarked_sessions(school, now=at(8, 0)) == 0, "مهلةُ السماح عشر دقائق"
        assert ta.alert_unmarked_sessions(school, now=at(8, 10)) == 1

        note = _mine(teacher, ta.SESSION_UNMARKED).get()
        assert note.related_object_id == str(first.pk)
        assert note.priority == "medium"
        assert second.pk != first.pk

    def test_twice_leaves_one_notification(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _periods(school, klass, teacher, 1)

        assert ta.alert_unmarked_sessions(school, now=at(8, 10)) == 1
        assert ta.alert_unmarked_sessions(school, now=at(8, 11)) == 0
        assert ta.alert_unmarked_sessions(school, now=at(9, 0)) == 0

        assert _mine(teacher, ta.SESSION_UNMARKED).count() == 1

    def test_a_marked_session_is_not_flagged(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        StudentAttendance.objects.create(
            session=period, student=kids[0], school=school, status="present", source="teacher"
        )

        assert ta.alert_unmarked_sessions(school, now=at(8, 10)) == 0

    def test_a_ledger_entry_counts_as_marked(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        AttendanceEntry.objects.create(
            school=school, session=period, student=kids[0], status="present", entered_by=teacher
        )

        assert ta.alert_unmarked_sessions(school, now=at(8, 10)) == 0

    def test_system_derived_rows_do_not_count_as_marking(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)
        StudentAttendance.objects.create(
            session=period, student=kids[0], school=school, status="absent", source="teacher_out"
        )

        assert ta.alert_unmarked_sessions(school, now=at(8, 10)) == 1

    def test_cancelled_and_provisional_sessions_are_skipped(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        cancelled, provisional = _periods(school, klass, teacher, 2)
        Session.objects.filter(pk=cancelled.pk).update(status="cancelled")
        Session.objects.filter(pk=provisional.pk).update(provisional=True)

        assert ta.alert_unmarked_sessions(school, now=at(9, 30)) == 0

    def test_a_class_without_active_students_is_skipped(
        self, school, seeded_calendar, klass, teacher, supervisor
    ):
        _periods(school, klass, teacher, 1)  # `kids` غير مطلوبة: شعبةٌ بلا قيود

        assert ta.alert_unmarked_sessions(school, now=at(8, 10)) == 0

    def test_silent_after_the_writing_window_closes(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _periods(school, klass, teacher, 1)

        assert ta.alert_unmarked_sessions(school, now=at(14, 30)) == 0

    @override_settings(PROVISIONAL_GRID_ENABLED=True)
    def test_silent_while_the_provisional_door_hides_platform_sessions(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _periods(school, klass, teacher, 1)

        assert ta.alert_unmarked_sessions(school, now=at(8, 10)) == 0

    def test_only_the_teacher_is_notified_and_no_name_in_text(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _periods(school, klass, teacher, 1)

        ta.alert_unmarked_sessions(school, now=at(8, 10))

        notes = list(InAppNotification.objects.all())
        assert {n.user_id for n in notes} == {teacher.pk}
        text = " ".join(f"{n.title} {n.body}" for n in notes)
        for kid in kids:
            assert kid.full_name not in text and kid.national_id not in text

    def test_scan_queries_do_not_grow_with_the_number_of_sessions(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _periods(school, klass, teacher, 1)
        with CaptureQueriesContext(connection) as one:
            ta.unmarked_sessions(school, at(9, 30), 10)
        Session.objects.filter(class_group=klass).delete()
        _periods(school, klass, teacher, 6)
        with CaptureQueriesContext(connection) as many:
            found = ta.unmarked_sessions(school, at(14, 0), 10)

        assert len(found) == 6
        assert len(many) == len(one)


class TestTheScheduledTasks:
    def test_the_task_creates_once_and_skips_a_non_school_day(
        self, school, seeded_calendar, klass, kids, teacher, supervisor, monkeypatch
    ):
        (period,) = _periods(school, klass, teacher, 1)
        leave(period, kids[0], "restroom", by=teacher, now=at(7, 20))
        monkeypatch.setattr("django.utils.timezone.now", lambda: at(7, 40))

        first = ta.alert_teachers_unreturned_exits_task()
        second = ta.alert_teachers_unreturned_exits_task()

        assert (first["created"], second["created"]) == (1, 0)
        assert first["failed_schools"] == 0

        friday = SUNDAY + dt.timedelta(days=5)
        monkeypatch.setattr(
            "django.utils.timezone.now",
            lambda: at(7, 40, friday),
        )
        assert ta.alert_teachers_unmarked_sessions_task()["created"] == 0

    def test_a_failing_school_is_counted_not_raised(self, school, seeded_calendar, monkeypatch):
        def boom(_school):
            raise RuntimeError("عطب")

        monkeypatch.setattr("django.utils.timezone.now", lambda: at(9, 0))
        monkeypatch.setattr(ta, "alert_unreturned_exits", boom)

        result = ta.alert_teachers_unreturned_exits_task()

        assert result["failed_schools"] >= 1 and result["created"] == 0

    def test_both_tasks_are_discoverable_by_the_worker(self):
        from shschool.celery import app

        app.loader.import_default_modules()

        assert "notifications.alert_teachers_unreturned_exits" in app.tasks
        assert "notifications.alert_teachers_unmarked_sessions" in app.tasks


class TestBeatIsOffByDefault:
    def test_empty_without_the_variable_or_with_any_other_value(self):
        assert teacher_alerts_beat({}) == {}
        assert teacher_alerts_beat({"TEACHER_ALERTS_BEAT": "0"}) == {}
        assert teacher_alerts_beat({"TEACHER_ALERTS_BEAT": "true"}) == {}

    def test_enabled_by_the_variable_with_both_tasks(self):
        schedule = teacher_alerts_beat({"TEACHER_ALERTS_BEAT": "1"})

        assert {entry["task"] for entry in schedule.values()} == {
            "notifications.alert_teachers_unreturned_exits",
            "notifications.alert_teachers_unmarked_sessions",
        }

    def test_the_project_schedule_does_not_carry_them_in_the_test_environment(self):
        from shschool.celery import app

        names = {entry["task"] for entry in app.conf.beat_schedule.values()}

        assert not {n for n in names if n.startswith("notifications.alert_teachers_")}


class TestThresholds:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("", 15), ("abc", 15), ("0", 15), ("-5", 15), ("20", 20)],
    )
    def test_bad_values_fall_back_to_the_default(self, raw, expected):
        assert ta._minutes("X", 15, {"X": raw}) == expected


class TestEventTypesAreRegistered:
    def test_in_the_model_choices_the_hub_and_within_the_column_width(self):
        from notifications.hub import DEFAULT_CHANNELS, DEFAULT_PRIORITY, _map_event_type

        stored = {code for code, _ in InAppNotification.EVENT_TYPES}
        for code in (ta.EXIT_NOT_RETURNED, ta.SESSION_UNMARKED):
            assert code in stored
            assert code in DEFAULT_CHANNELS and code in DEFAULT_PRIORITY
            assert _map_event_type(code) == code
            assert len(code) <= InAppNotification._meta.get_field("event_type").max_length
        assert "push" not in DEFAULT_CHANNELS[ta.SESSION_UNMARKED]
        assert not {"sms", "whatsapp", "email"} & set(DEFAULT_CHANNELS[ta.EXIT_NOT_RETURNED])
