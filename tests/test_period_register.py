"""[LEGAL] كشفُ الحصص — رصدُ مشرف الجناح حصّةً حصّة، وما يترتّب على كلّ رصد.

قراراتُ المدرسة (2026-09-13) التي تحرسها هذه الاختبارات:
- الرصدُ لكلّ حصّة، يبدأ «الكلُّ حاضر»؛ ولا تُسحب إلى حصّةٍ حالةٌ لم تُرصد فيها.
- الحصّةُ «فائتة» إن لم تُثبَّت حتى **5 دقائق بعد نهايتها**.
- «متأخّر» تُحسب دقائقُه تلقائيّاً في نافذة الحصّة، وبيد المشرف خارجَها؛ وبعد
  **5 دقائق** مخالفةُ التأخّر (1-01) نافذة.
- الغائبُ بعد حضورٍ في حصّةٍ سابقة **هارب** (2-02) بمادّة الحصّة، ما لم يكن في
  عيادةٍ أو نشاطٍ أو خارجاً بإذن؛ ويُعدّ لكلّ مادّةٍ على حدة.
- التصحيحُ يُزيل ما أنشأه الرصدُ من مخالفات، ولا يمسّ ما كُتب باليد.
- لا نسخَ من حصّةٍ إلى أخرى، ووقتُ أوّل تثبيتٍ ووسمُ «ثُبّتت متأخّرة» لا يُمحيان.
- والمعلّمُ لا يرصد في شُعب الأجنحة (قرارُ المدير).
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from behavior.models import BehaviorInfraction
from core.academic_calendar import academic_year_for_school
from core.models import Wing
from operations.absence_standing import standing_for
from operations.models import PeriodConfirmation, Session, StudentAttendance, Subject
from operations.period_register import confirm_period, periods_of
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

SUNDAY = dt.date(2026, 9, 13)


def at(hour, minute, day=SUNDAY):
    return timezone.make_aware(dt.datetime.combine(day, dt.time(hour, minute)))


@pytest.fixture
def year(school):
    return academic_year_for_school(school)


@pytest.fixture
def klass(school, year):
    return ClassGroupFactory(
        school=school, grade="G7", section="1", level_type="prep", academic_year=year
    )


@pytest.fixture
def kids(school, klass):
    made = []
    for i in range(4):
        student = UserFactory(full_name=f"طالب {i}", national_id=f"2930000000{i}")
        StudentEnrollmentFactory(student=student, class_group=klass)
        made.append(student)
    return made


@pytest.fixture
def teacher(school):
    user = UserFactory(full_name="معلّم الحصّة", national_id="29300000090")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


@pytest.fixture
def other_teacher(school):
    """معلّمٌ ثانٍ — زوجُ الاختيار معلّمان، وقيدُ `no_teacher_time_overlap` صادق."""
    user = UserFactory(full_name="معلّم الزوج الثاني", national_id="29300000092")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


@pytest.fixture
def supervisor(school, klass, year):
    user = UserFactory(full_name="مشرف الجناح", national_id="29300000091")
    MembershipFactory(
        user=user, school=school, role=RoleFactory(school=school, name="admin_supervisor")
    )
    wing = Wing.objects.create(
        school=school, code="w1", name="جناح 1", academic_year=year, supervisor=user
    )
    klass.wing = wing
    klass.save(update_fields=["wing"])
    return user


@pytest.fixture
def subjects(school):
    return [
        Subject.objects.create(school=school, name_ar=name, code=code)
        for name, code in (("الرياضيات", "MATH"), ("العلوم", "SCI"))
    ]


def _periods(school, klass, teacher, count=7, day=SUNDAY, at_hour=7):
    """حصصُ اليوم — تبدأ :10 وتنتهي :55 من كلّ ساعة، فتُعرف نوافذُها."""
    return [
        Session.objects.create(
            school=school,
            class_group=klass,
            teacher=teacher,
            date=day,
            start_time=dt.time(at_hour + i, 10),
            end_time=dt.time(at_hour + i, 55),
            status="scheduled",
        )
        for i in range(count)
    ]


def _elective_twin(school, klass, other_teacher, day=SUNDAY, index=3):
    """خانةٌ واحدةٌ حصّتان: مادّتان ومعلّمان، كزوج الاختيار في الواقع."""
    first = Session.objects.filter(class_group=klass, date=day).order_by("start_time")[index]
    first.elective_group = "تكنولوجيا"
    first.save(update_fields=["elective_group"])
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=other_teacher,
        date=day,
        start_time=first.start_time,
        end_time=first.end_time,
        status="scheduled",
        elective_group="فنون بصريّة",
    )


def _confirm(klass, session, marks, by, now=None, day=SUNDAY):
    """يثبّت حصّةَ `session`. و`marks` = {طالب: حالة} أو {طالب: {status, whereabouts, late_minutes}}."""
    payload = {
        str(student.id): (value if isinstance(value, dict) else {"status": value})
        for student, value in marks.items()
    }
    return confirm_period(klass, day, session.start_time, payload, by=by, now=now or at(23, 0, day))


def _auto(student, rule):
    return BehaviorInfraction.objects.filter(student=student, auto_rule=rule)


# ══════════════════════════════════════════════════════════════════
# الحصّةُ وحدَها
# ══════════════════════════════════════════════════════════════════


class TestThePeriodIsRecordedAlone:
    def test_confirming_a_period_writes_only_its_sessions(
        self, school, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 7)

        _confirm(klass, periods[0], {kids[0]: "absent"}, supervisor)

        assert StudentAttendance.objects.filter(session=periods[0]).count() == 4
        assert not StudentAttendance.objects.filter(session__in=periods[1:]).exists()

    def test_whoever_is_not_touched_is_present(self, school, klass, kids, teacher, supervisor):
        periods = _periods(school, klass, teacher, 7)

        result = _confirm(klass, periods[0], {kids[0]: "absent"}, supervisor)

        assert (result.present, result.absent, result.late) == (3, 1, 0)

    def test_an_unknown_state_falls_back_to_present(self, school, klass, kids, teacher, supervisor):
        periods = _periods(school, klass, teacher, 7)

        _confirm(klass, periods[0], {kids[0]: "excused"}, supervisor)

        row = StudentAttendance.objects.get(session=periods[0], student=kids[0])
        assert row.status == "present"

    def test_confirming_again_replaces_it(self, school, klass, kids, teacher, supervisor):
        periods = _periods(school, klass, teacher, 7)
        _confirm(klass, periods[0], {kids[0]: "absent"}, supervisor)

        _confirm(klass, periods[0], {kids[1]: "absent"}, supervisor)

        assert StudentAttendance.objects.filter(session=periods[0]).count() == 4
        row = StudentAttendance.objects.get(session=periods[0], student=kids[0])
        assert row.status == "present"
        assert PeriodConfirmation.objects.filter(class_group=klass).count() == 1

    def test_the_record_carries_the_supervisors_source(
        self, school, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 7)

        _confirm(klass, periods[0], {}, supervisor)

        assert set(StudentAttendance.objects.values_list("source", flat=True)) == {"supervisor"}

    def test_an_elective_pair_is_one_period_written_to_both_sessions(
        self, school, klass, kids, teacher, other_teacher, supervisor
    ):
        _periods(school, klass, teacher, 7)
        twin = _elective_twin(school, klass, other_teacher)

        assert len(periods_of(klass, SUNDAY)) == 7
        _confirm(klass, twin, {kids[0]: "absent"}, supervisor)

        assert StudentAttendance.objects.filter(student=kids[0], status="absent").count() == 2

    def test_an_unconfirmed_period_is_not_filled_from_another(
        self, school, klass, kids, teacher, supervisor
    ):
        """الحصّةُ غيرُ المرصودة تبقى «لم تُرصد» — لا تُسحب إليها حالة."""
        periods = _periods(school, klass, teacher, 3)

        _confirm(klass, periods[0], {kids[0]: "absent"}, supervisor)

        assert not StudentAttendance.objects.filter(session=periods[1]).exists()


class TestPeriodStatus:
    """فائتةٌ بعد نهايتها بخمس دقائق — لا بعد بدايتها."""

    @pytest.mark.parametrize(
        "moment,status",
        [
            ((7, 0), "upcoming"),
            ((7, 10), "current"),
            ((7, 55), "current"),
            ((8, 0), "current"),
            ((8, 1), "missed"),
        ],
    )
    def test_the_window_ends_five_minutes_after_the_period(
        self, school, klass, teacher, moment, status
    ):
        _periods(school, klass, teacher, 1)
        (period,) = periods_of(klass, SUNDAY)

        assert period.status(SUNDAY, at(*moment)) == status

    def test_a_period_confirmed_in_its_window_is_confirmed_whatever_the_time(
        self, school, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 1)
        _confirm(klass, periods[0], {}, supervisor, now=at(7, 30))
        (period,) = periods_of(klass, SUNDAY)

        assert period.status(SUNDAY, at(23, 0)) == "confirmed"

    def test_a_period_confirmed_after_its_deadline_stays_marked_late(
        self, school, klass, kids, teacher, supervisor
    ):
        """التثبيتُ بعد المهلة «ثُبّتت متأخّرة» — والتثبيتُ ثانيةً لا يمحو الوسم."""
        periods = _periods(school, klass, teacher, 1)
        _confirm(klass, periods[0], {}, supervisor, now=at(8, 6))

        _confirm(klass, periods[0], {kids[0]: "absent"}, supervisor, now=at(9, 0))

        (period,) = periods_of(klass, SUNDAY)
        assert period.status(SUNDAY, at(23, 0)) == "confirmed_late"
        assert period.confirmation.absent_count == 1

    def test_the_first_confirmation_time_is_kept(self, school, klass, kids, teacher, supervisor):
        periods = _periods(school, klass, teacher, 1)
        _confirm(klass, periods[0], {}, supervisor, now=at(7, 20))

        _confirm(klass, periods[0], {kids[0]: "absent"}, supervisor, now=at(7, 40))

        confirmation = PeriodConfirmation.objects.get(class_group=klass, date=SUNDAY)
        assert confirmation.first_confirmed_at == at(7, 20)
        assert not confirmation.confirmed_late


# ══════════════════════════════════════════════════════════════════
# التأخّر
# ══════════════════════════════════════════════════════════════════


class TestLateness:
    def test_minutes_are_measured_when_confirmed_during_the_period(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 1)

        _confirm(klass, periods[0], {kids[0]: "late"}, supervisor, now=at(7, 22))

        row = StudentAttendance.objects.get(session=periods[0], student=kids[0])
        assert row.late_minutes == 12

    def test_minutes_are_measured_from_the_tap_not_the_confirmation(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """نُقر «متأخّر» في 07:20 وثُبّتت الحصّةُ في 07:30: عشرُ دقائق لا عشرون."""
        periods = _periods(school, klass, teacher, 1)
        tapped = int(at(7, 20).timestamp())

        _confirm(
            klass,
            periods[0],
            {kids[0]: {"status": "late", "tapped_at": str(tapped)}},
            supervisor,
            now=at(7, 30),
        )

        assert StudentAttendance.objects.get(session=periods[0], student=kids[0]).late_minutes == 10

    @pytest.mark.parametrize("moment", [(7, 0), (7, 45), "garbage"])
    def test_a_tap_outside_the_period_or_unreadable_falls_back_to_the_confirmation(
        self, school, seeded_calendar, klass, kids, teacher, supervisor, moment
    ):
        periods = _periods(school, klass, teacher, 1)
        raw = moment if isinstance(moment, str) else str(int(at(*moment).timestamp()))

        _confirm(
            klass,
            periods[0],
            {kids[0]: {"status": "late", "tapped_at": raw}},
            supervisor,
            now=at(7, 30),
        )

        assert StudentAttendance.objects.get(session=periods[0], student=kids[0]).late_minutes == 20

    def test_confirming_again_does_not_grow_the_minutes(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 1)
        _confirm(klass, periods[0], {kids[0]: "late"}, supervisor, now=at(7, 18))

        _confirm(klass, periods[0], {kids[0]: "late", kids[1]: "absent"}, supervisor, now=at(7, 40))

        assert StudentAttendance.objects.get(session=periods[0], student=kids[0]).late_minutes == 8

    def test_outside_the_window_the_supervisor_writes_the_minutes(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """الحسابُ من لحظة التثبيت بعد الحصّة يعطي مدّتَها كلَّها — فالرقمُ باليد."""
        periods = _periods(school, klass, teacher, 1)

        _confirm(
            klass,
            periods[0],
            {kids[0]: {"status": "late", "late_minutes": "8"}},
            supervisor,
            now=at(13, 0),
        )

        row = StudentAttendance.objects.get(session=periods[0], student=kids[0])
        assert row.late_minutes == 8

    def test_five_minutes_is_not_a_tardiness_infraction(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 1)

        _confirm(klass, periods[0], {kids[0]: "late"}, supervisor, now=at(7, 15))

        assert not _auto(kids[0], "period_tardy").exists()

    def test_six_minutes_makes_the_infraction_at_once(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 1)

        result = _confirm(klass, periods[0], {kids[0]: "late"}, supervisor, now=at(7, 16))

        (infraction,) = _auto(kids[0], "period_tardy")
        assert infraction.violation_category.code == "1-01"
        assert infraction.session_id == periods[0].id
        assert infraction.escalation_step == 1
        assert result.tardy_infractions == 1

    def test_correcting_to_present_removes_the_infraction(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 1)
        _confirm(klass, periods[0], {kids[0]: "late"}, supervisor, now=at(7, 30))

        _confirm(klass, periods[0], {kids[0]: "present"}, supervisor, now=at(7, 31))

        assert not _auto(kids[0], "period_tardy").exists()

    def test_confirming_twice_does_not_double_the_infraction(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 1)
        _confirm(klass, periods[0], {kids[0]: "late"}, supervisor, now=at(7, 30))

        _confirm(klass, periods[0], {kids[0]: "late"}, supervisor, now=at(7, 40))

        assert _auto(kids[0], "period_tardy").count() == 1

    def test_a_hand_written_infraction_is_never_touched(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        from behavior.models import ViolationCategory
        from behavior.services import BehaviorService

        periods = _periods(school, klass, teacher, 1)
        BehaviorService.create_infraction(
            school=school,
            student=kids[0],
            reporter=supervisor,
            level=1,
            description="كتبها المشرفُ بيده",
            violation_category=ViolationCategory.objects.get(code="1-01"),
            session=periods[0],
        )

        _confirm(klass, periods[0], {kids[0]: "present"}, supervisor, now=at(7, 20))

        assert BehaviorInfraction.objects.filter(student=kids[0], auto_rule="").count() == 1


# ══════════════════════════════════════════════════════════════════
# الهروب
# ══════════════════════════════════════════════════════════════════


class TestEscape:
    """الغيابُ بعد حضور: بين حضورين هروبٌ من الحصّة، وحتى آخر اليوم هروبٌ من المدرسة."""

    def test_absent_between_two_attended_periods_escaped_the_class(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 3)
        _confirm(klass, periods[0], {}, supervisor)
        _confirm(klass, periods[1], {kids[0]: "absent"}, supervisor)

        _confirm(klass, periods[2], {}, supervisor)

        (infraction,) = _auto(kids[0], "class_escape")
        assert infraction.violation_category.code == "2-02"
        assert infraction.session_id == periods[1].id
        assert not _auto(kids[0], "school_escape").exists()

    def test_absent_until_the_end_of_the_day_escaped_the_school_once(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """حضر الأولى ثمّ غاب الستَّ الباقية: مخالفةٌ واحدةٌ 3-10 — لا ستُّ 2-02."""
        periods = _periods(school, klass, teacher, 7)
        _confirm(klass, periods[0], {}, supervisor)

        for session in periods[1:]:
            _confirm(klass, session, {kids[0]: "absent"}, supervisor)

        (infraction,) = _auto(kids[0], "school_escape")
        assert infraction.violation_category.code == "3-10"
        assert infraction.session_id == periods[1].id
        assert not _auto(kids[0], "class_escape").exists()

    def test_nothing_is_decided_while_later_periods_are_unconfirmed(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """غاب في الثانية والثالثةُ لم تُرصد: قد يعود — فلا مخالفةَ بعد."""
        periods = _periods(school, klass, teacher, 3)
        _confirm(klass, periods[0], {}, supervisor)

        _confirm(klass, periods[1], {kids[0]: "absent"}, supervisor)

        assert not BehaviorInfraction.objects.filter(student=kids[0]).exists()

    def test_returning_later_turns_the_school_escape_into_a_class_escape(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 3)
        _confirm(klass, periods[0], {}, supervisor)
        _confirm(klass, periods[1], {kids[0]: "absent"}, supervisor)
        _confirm(klass, periods[2], {kids[0]: "absent"}, supervisor)
        assert _auto(kids[0], "school_escape").count() == 1

        _confirm(klass, periods[2], {kids[0]: "present"}, supervisor)

        assert not _auto(kids[0], "school_escape").exists()
        assert _auto(kids[0], "class_escape").count() == 1

    def test_who_never_came_is_absent_not_escaped(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 3)

        for session in periods:
            _confirm(klass, session, {kids[0]: "absent"}, supervisor)

        assert not BehaviorInfraction.objects.filter(student=kids[0]).exists()

    @pytest.mark.parametrize("where", ["clinic", "activity", "out_permit", "left_early"])
    def test_leave_with_permission_is_not_an_escape(
        self, school, seeded_calendar, klass, kids, teacher, supervisor, where
    ):
        periods = _periods(school, klass, teacher, 3)
        _confirm(klass, periods[0], {}, supervisor)
        _confirm(
            klass, periods[1], {kids[0]: {"status": "absent", "whereabouts": where}}, supervisor
        )

        _confirm(klass, periods[2], {}, supervisor)

        assert not BehaviorInfraction.objects.filter(student=kids[0]).exists()

    def test_leaving_without_permission_until_the_end_is_a_school_escape(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 2)
        _confirm(klass, periods[0], {}, supervisor)

        _confirm(
            klass,
            periods[1],
            {kids[0]: {"status": "absent", "whereabouts": "out_no_permit"}},
            supervisor,
        )

        assert _auto(kids[0], "school_escape").count() == 1

    def test_class_escape_is_counted_per_subject(
        self, school, seeded_calendar, klass, kids, teacher, supervisor, subjects
    ):
        """الهروبُ من الرياضيّات مرّتين خطوتان، ومن العلوم بعدها خطوةٌ أولى (ص91)."""
        math, science = subjects
        periods = _periods(school, klass, teacher, 7)
        for session, subject in zip(
            periods, (None, math, None, math, None, science, None), strict=True
        ):
            if subject:
                session.subject = subject
                session.save(update_fields=["subject"])

        for index, session in enumerate(periods):
            _confirm(klass, session, {kids[0]: "absent"} if index in (1, 3, 5) else {}, supervisor)

        steps = dict(
            _auto(kids[0], "class_escape").values_list("session__start_time", "escalation_step")
        )
        assert steps == {
            periods[1].start_time: 1,
            periods[3].start_time: 2,
            periods[5].start_time: 1,
        }

    def test_a_full_day_from_the_register_counts_in_the_standing(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 7)

        for session in periods:
            _confirm(klass, session, {kids[0]: "absent"}, supervisor)

        assert standing_for(kids[0], school, grade="G7", on=SUNDAY).unexcused_days == 1


# ══════════════════════════════════════════════════════════════════
# إنذاراتُ عتبات الغياب
# ══════════════════════════════════════════════════════════════════


class TestAbsenceAlerts:
    """الكشفُ يُنذر بعتبات الغياب كما كان يفعل رصدُ المعلّم — لا صمتَ بعد الانتقال."""

    def _absent_days(self, school, klass, kids, teacher, supervisor, count):
        for offset in range(count):
            day = SUNDAY + dt.timedelta(days=offset)
            for session in _periods(school, klass, teacher, 7, day=day):
                _confirm(klass, session, {kids[0]: "absent"}, supervisor, day=day)

    def test_three_absent_days_raise_the_first_gate_warning(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """عتبةُ السابع الأولى خمسةُ أيّام، والإنذارُ قبلها بيومين — فالثالثُ يُنذر."""
        from operations.models import AbsenceAlert

        self._absent_days(school, klass, kids, teacher, supervisor, 3)

        assert AbsenceAlert.objects.filter(student=kids[0]).exists()
        assert not AbsenceAlert.objects.filter(student=kids[1]).exists()

    def test_the_same_gate_is_not_raised_again_on_the_next_period(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        from operations.models import AbsenceAlert

        self._absent_days(school, klass, kids, teacher, supervisor, 3)
        before = AbsenceAlert.objects.filter(student=kids[0]).count()

        day = SUNDAY + dt.timedelta(days=3)
        (period,) = _periods(school, klass, teacher, 1, day=day)
        _confirm(klass, period, {kids[0]: "absent"}, supervisor, day=day)

        assert AbsenceAlert.objects.filter(student=kids[0]).count() == before

    def test_a_single_absent_period_is_not_an_absent_day(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        from operations.models import AbsenceAlert

        for offset in range(3):
            day = SUNDAY + dt.timedelta(days=offset)
            periods = _periods(school, klass, teacher, 7, day=day)
            for index, session in enumerate(periods):
                marks = {kids[0]: "absent"} if index == 0 else {}
                _confirm(klass, session, marks, supervisor, day=day)

        assert not AbsenceAlert.objects.filter(student=kids[0]).exists()


# ══════════════════════════════════════════════════════════════════
# نقرةُ المعلّم «دخل متأخّراً»
# ══════════════════════════════════════════════════════════════════


class TestTheTeacherTapsLate:
    """المعلّمُ لا يرصد الغياب، لكنّه ينقر «دخل الآن» لمن دخل متأخّراً — النظامُ يسجّل
    الوقت، والمشرفُ يجدها في كشفه (قرارُ 2026-09-13)."""

    def test_the_tap_records_the_moment_not_a_typed_number(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        from operations.period_register import tap_late

        (period,) = _periods(school, klass, teacher, 1)

        assert tap_late(period, kids[0], by=teacher, now=at(7, 22)) == 12

        row = StudentAttendance.objects.get(session=period, student=kids[0])
        assert (row.status, row.source, row.late_minutes) == ("late", "teacher_late", 12)

    def test_a_second_tap_keeps_the_first_moment(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        from operations.period_register import tap_late

        (period,) = _periods(school, klass, teacher, 1)
        tap_late(period, kids[0], by=teacher, now=at(7, 18))

        assert tap_late(period, kids[0], by=teacher, now=at(7, 40)) == 8

    def test_the_tap_never_overwrites_the_supervisor(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        from operations.period_register import tap_late

        (period,) = _periods(school, klass, teacher, 1)
        _confirm(klass, period, {kids[0]: "absent"}, supervisor)

        tap_late(period, kids[0], by=teacher, now=at(7, 30))

        row = StudentAttendance.objects.get(session=period, student=kids[0])
        assert (row.status, row.source) == ("absent", "supervisor")

    def test_the_supervisor_finds_the_tap_prefilled_and_confirms_its_minutes(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        from operations.period_register import tap_late

        (period,) = _periods(school, klass, teacher, 1)
        tap_late(period, kids[0], by=teacher, now=at(7, 22))

        body = (
            client_as(supervisor)
            .get(reverse("wings:record_section", args=[klass.id]) + f"?date={SUNDAY.isoformat()}")
            .content.decode()
        )
        assert "12 د" in body, "خانةُ الطالب «متأخّر» بدقائق المعلّم"

        # التثبيتُ بعد عشرين دقيقةً يأخذ لحظةَ الدخول عند المعلّم لا لحظةَ التثبيت.
        _confirm(klass, period, {kids[0]: "late"}, supervisor, now=at(7, 42))
        row = StudentAttendance.objects.get(session=period, student=kids[0])
        assert (row.source, row.late_minutes) == ("supervisor", 12)
        assert _auto(kids[0], "period_tardy").count() == 1

    def test_the_teacher_sees_the_button_and_the_supervisor_page_does_not_count_the_tap_as_recorded(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)

        body = client_as(teacher).get(reverse("attendance", args=[period.id])).content.decode()
        assert reverse("mark_late_tap", args=[period.id]) in body
        assert reverse("mark_single", args=[period.id]) not in body, "لا يرصد"

        response = client_as(teacher).post(
            reverse("mark_late_tap", args=[period.id]), {"student_id": str(kids[1].id)}
        )
        assert response.status_code == 200
        assert "دخل متأخّراً" in response.content.decode()
        assert not PeriodConfirmation.objects.exists(), "النقرةُ ليست تثبيتاً"

    def test_another_teacher_may_not_tap(
        self, client_as, school, seeded_calendar, klass, kids, teacher, other_teacher, supervisor
    ):
        (period,) = _periods(school, klass, teacher, 1)

        response = client_as(other_teacher).post(
            reverse("mark_late_tap", args=[period.id]), {"student_id": str(kids[0].id)}
        )

        assert response.status_code == 403
        assert not StudentAttendance.objects.exists()


# ══════════════════════════════════════════════════════════════════
# المعلّم
# ══════════════════════════════════════════════════════════════════


class TestTheTeacherDoesNotRecord:
    """الرصدُ لمشرف الجناح وحدَه — والسجلُّ واحدٌ لكلّ طالبٍ في كلّ حصّة."""

    def test_a_teacher_cannot_overwrite_what_the_supervisor_recorded(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 7)
        _confirm(klass, periods[0], {kids[0]: "absent"}, supervisor)

        response = client_as(teacher).post(
            reverse("mark_single", args=[periods[0].id]),
            {"student_id": str(kids[0].id), "status": "present"},
        )

        assert response.status_code == 403
        row = StudentAttendance.objects.get(session=periods[0], student=kids[0])
        assert (row.status, row.source) == ("absent", "supervisor")

    def test_a_teacher_cannot_record_even_before_the_supervisor(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 7)

        response = client_as(teacher).post(
            reverse("mark_single", args=[periods[0].id]),
            {"student_id": str(kids[0].id), "status": "absent"},
        )

        assert response.status_code == 403
        assert not StudentAttendance.objects.exists()

    def test_a_teacher_cannot_mark_all_present(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 7)

        response = client_as(teacher).post(reverse("mark_all_present", args=[periods[0].id]))

        assert response.status_code == 403
        assert not StudentAttendance.objects.exists()

    def test_the_supervisor_still_corrects_his_own_record(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 7)
        _confirm(klass, periods[0], {kids[0]: "absent"}, supervisor)

        response = client_as(supervisor).post(
            reverse("mark_single", args=[periods[0].id]),
            {"student_id": str(kids[0].id), "status": "late"},
        )

        assert response.status_code == 200

    def test_the_teacher_sees_the_session_without_buttons(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 7)
        _confirm(klass, periods[0], {kids[0]: "absent"}, supervisor)

        response = client_as(teacher).get(reverse("attendance", args=[periods[0].id]))
        body = response.content.decode()

        assert response.status_code == 200
        assert "لمشرف الجناح" in body
        assert reverse("mark_single", args=[periods[0].id]) not in body

    def test_the_teachers_schedule_does_not_invite_him_to_record(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 7)

        body = (
            client_as(teacher)
            .get(reverse("teacher_schedule") + f"?date={SUNDAY.isoformat()}")
            .content.decode()
        )

        assert reverse("attendance", args=[periods[0].id]) in body
        assert "تسجيل حضور" not in body

    def test_a_section_outside_the_wings_keeps_its_teacher_recording(
        self, client_as, school, year, teacher
    ):
        """التربيةُ الخاصّة خارجَ الأجنحة، ويرصدها معلّموها."""
        ese = ClassGroupFactory(
            school=school, grade="G7", section="9", level_type="prep", academic_year=year
        )
        student = UserFactory(full_name="طالب خاصّ", national_id="29300000099")
        StudentEnrollmentFactory(student=student, class_group=ese)
        (session,) = _periods(school, ese, teacher, 1)

        response = client_as(teacher).post(
            reverse("mark_single", args=[session.id]),
            {"student_id": str(student.id), "status": "absent"},
        )

        assert response.status_code == 200


# ══════════════════════════════════════════════════════════════════
# الشاشة
# ══════════════════════════════════════════════════════════════════


class TestTheScreen:
    def test_the_supervisor_sees_his_sections_with_period_dots(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        _periods(school, klass, teacher, 7)

        body = (
            client_as(supervisor)
            .get(reverse("wings:record_index") + f"?date={SUNDAY.isoformat()}")
            .content.decode()
        )

        assert klass.short_code in body
        assert body.count('class="per-dot') == 7

    def test_the_screen_is_reachable_from_the_menu(self, client_as, school, supervisor):
        """شاشةٌ لا رابطَ إليها شاشةٌ غيرُ موجودة — والرابطُ يُكتب بيدٍ في `base.html`."""
        body = client_as(supervisor).get(reverse("dashboard")).content.decode()

        assert reverse("wings:record_index") in body

    def test_the_supervisors_home_page_shows_his_sections_to_record(
        self, client_as, school, klass, kids, teacher, supervisor, monkeypatch
    ):
        # يومُ دوام: يومَ الجمعة لا تُعرض الشُّعب، فالساعةُ الحقيقيّة تُسقطه آخرَ الأسبوع.
        monkeypatch.setattr("django.utils.timezone.now", lambda: at(9, 0))

        body = client_as(supervisor).get(reverse("dashboard")).content.decode()

        assert klass.short_code in body
        assert reverse("wings:record_section", args=[klass.id]) in body

    def test_a_teacher_is_turned_away(self, client_as, school, klass, teacher):
        response = client_as(teacher).get(reverse("wings:record_index"))

        assert response.status_code in (302, 403)

    def test_the_sheet_shows_the_period_strip_and_the_flags(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        previous = SUNDAY - dt.timedelta(days=3)
        (old,) = _periods(school, klass, teacher, 1, day=previous)
        _confirm(klass, old, {kids[0]: "absent"}, supervisor, day=previous)
        _periods(school, klass, teacher, 7)

        body = (
            client_as(supervisor)
            .get(reverse("wings:record_section", args=[klass.id]) + f"?date={SUNDAY.isoformat()}")
            .content.decode()
        )

        assert body.count('class="per-col is-') == 7, "عمودٌ لكلّ حصّةٍ من حصص اليوم"
        assert body.count('class="per-cell is-none"') == 7 * 4 - 4, "الحصصُ غيرُ المفتوحة حرفُ حال"
        assert "غاب أمس" in body
        assert "غيابُ الكلّ" in body

    def test_posting_a_period_confirms_it(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 7)

        client_as(supervisor).post(
            reverse("wings:record_period", args=[klass.id]),
            {
                "date": SUNDAY.isoformat(),
                "start": "07:10",
                f"s-{kids[0].id}": "absent",
                f"s-{kids[1].id}": "late",
                f"m-{kids[1].id}": "9",
                f"s-{kids[2].id}": "absent",
                f"w-{kids[2].id}": "clinic",
                # «حاضر» ومكانٌ خفيٌّ بقي في النموذج: الحاضرُ في فصله لا في العيادة.
                f"w-{kids[3].id}": "clinic",
            },
        )

        c = PeriodConfirmation.objects.get(class_group=klass, date=SUNDAY)
        assert (c.absent_count, c.late_count) == (2, 1)
        row = StudentAttendance.objects.get(session=periods[0], student=kids[2])
        assert row.whereabouts == "clinic"
        row = StudentAttendance.objects.get(session=periods[0], student=kids[3])
        assert (row.status, row.whereabouts) == ("present", "")

    def test_confirm_and_move_on_goes_to_the_next_section_awaiting_the_same_period(
        self, client_as, school, seeded_calendar, year, klass, kids, teacher, supervisor
    ):
        """المشرفُ يمرّ على شُعبه في الحصّة نفسِها: بعد التثبيت يُنقل إلى التي تليها
        ولم تُثبَّت — وتُفتح على الحصّة ذاتِها لا على ما يختاره الخادم."""
        _periods(school, klass, teacher, 7)
        second = ClassGroupFactory(
            school=school, grade="G7", section="2", level_type="prep", academic_year=year
        )
        third = ClassGroupFactory(
            school=school, grade="G7", section="3", level_type="prep", academic_year=year
        )
        for i, other in enumerate((second, third)):
            other.wing = klass.wing
            other.save(update_fields=["wing"])
            # معلّمٌ لكلّ شعبة: قيدُ `no_teacher_time_overlap` لا يقبل معلّماً في شعبتين معاً.
            colleague = UserFactory(full_name=f"معلّم {i}", national_id=f"2930000009{i + 5}")
            MembershipFactory(
                user=colleague, school=school, role=RoleFactory(school=school, name="teacher")
            )
            _periods(school, other, colleague, 7)
        # الثانيةُ ثُبّتت حصّتُها الأولى سلفاً — فالنقلُ يتخطّاها إلى الثالثة.
        (first_of_second,) = Session.objects.filter(
            class_group=second, date=SUNDAY, start_time=dt.time(7, 10)
        )
        _confirm(second, first_of_second, {}, supervisor)

        page = (
            client_as(supervisor)
            .get(reverse("wings:record_section", args=[klass.id]) + f"?date={SUNDAY.isoformat()}")
            .content.decode()
        )
        assert f"ثبّت وانتقل إلى {third.short_code}" in page

        response = client_as(supervisor).post(
            reverse("wings:record_period", args=[klass.id]),
            {"date": SUNDAY.isoformat(), "start": "07:10", "next": "1"},
        )

        assert PeriodConfirmation.objects.filter(class_group=klass, date=SUNDAY).exists()
        assert response.status_code == 302
        assert response.url == (
            reverse("wings:record_section", args=[third.id]) + f"?date={SUNDAY.isoformat()}&p=07:10"
        )

    def test_confirm_and_move_on_returns_to_the_index_when_the_wing_is_done(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """شعبةٌ وحيدةٌ في الجناح: لا زرَّ انتقالٍ في الصفحة، والطلبُ به يعود إلى الفهرس."""
        _periods(school, klass, teacher, 7)

        page = (
            client_as(supervisor)
            .get(reverse("wings:record_section", args=[klass.id]) + f"?date={SUNDAY.isoformat()}")
            .content.decode()
        )
        assert "ثبّت وانتقل" not in page

        response = client_as(supervisor).post(
            reverse("wings:record_period", args=[klass.id]),
            {"date": SUNDAY.isoformat(), "start": "07:10", "next": "1"},
        )

        assert response.status_code == 302
        assert response.url == reverse("wings:record_index") + f"?date={SUNDAY.isoformat()}"

    def test_a_confirmed_column_keeps_its_confirmation_time(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """العمودُ غيرُ المثبَّت ساعتُه حيّة، والمثبَّتُ وقتُ تثبيته محفوظاً لا يتحرّك."""
        periods = _periods(school, klass, teacher, 3)
        _confirm(klass, periods[0], {}, supervisor)
        saved = timezone.localtime(
            PeriodConfirmation.objects.get(class_group=klass, date=SUNDAY).first_confirmed_at
        )

        body = (
            client_as(supervisor)
            .get(reverse("wings:record_section", args=[klass.id]) + f"?date={SUNDAY.isoformat()}")
            .content.decode()
        )

        assert body.count('class="per-col__clock is-fixed"') == 1
        assert f">{saved:%H:%M:%S}</time>" in body
        assert body.count("data-clock") == 2, "الحصّتان الباقيتان ساعتُهما حيّة"

    def test_there_is_no_copy_button(self, client_as, school, klass, kids, teacher, supervisor):
        """قرارُ 2026-09-13: كلُّ حصّةٍ دخولٌ إلى الفصل — لا نسخَ من حصّةٍ إلى أخرى."""
        periods = _periods(school, klass, teacher, 3)
        _confirm(klass, periods[0], {}, supervisor)
        url = reverse("wings:record_section", args=[klass.id]) + f"?date={SUNDAY.isoformat()}"

        assert "انسخ" not in client_as(supervisor).get(url).content.decode()

    def test_a_supervisor_sees_only_his_own_wing(
        self, client_as, school, year, klass, kids, teacher, supervisor
    ):
        """المشرفُ لجناحه فقط — وشعبةُ جناحٍ آخر برابطها المباشر لا تُفتح."""
        other = UserFactory(full_name="مشرف جناح آخر", national_id="29300000093")
        MembershipFactory(
            user=other, school=school, role=RoleFactory(school=school, name="admin_supervisor")
        )
        Wing.objects.create(
            school=school, code="w2", name="جناح 2", academic_year=year, supervisor=other
        )
        _periods(school, klass, teacher, 1)
        url = reverse("wings:record_section", args=[klass.id]) + f"?date={SUNDAY.isoformat()}"

        assert client_as(other).get(url).status_code == 404
        response = client_as(other).post(
            reverse("wings:record_period", args=[klass.id]),
            {"date": SUNDAY.isoformat(), "start": "07:10"},
        )
        assert response.status_code == 404
        assert not StudentAttendance.objects.exists()

    def test_the_wave_screen_is_gone(self, client_as, school, klass, kids, teacher, supervisor):
        """شاشةُ «الموجة الواحدة» أُزيلت — والكشفُ لا يكتب شيئاً بـPOST عليه."""
        _periods(school, klass, teacher, 7)

        client_as(supervisor).post(
            reverse("wings:record_section", args=[klass.id]),
            {"date": SUNDAY.isoformat(), f"s-{kids[0].id}": "absent"},
        )

        assert not StudentAttendance.objects.exists()
