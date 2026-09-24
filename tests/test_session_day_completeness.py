"""اليومُ المبتور، وواجهةُ المصالحة لمدى (2026-09-24).

كان التوليدُ يعدّ اليومَ مكتملاً إن وُجدت فيه حصّةٌ واحدة. فتبديلٌ أو إشغالٌ أو
تعويضٌ لتاريخٍ في أسبوعٍ لم يُولَّد يُنشئ حصّتَه وحدها، فيبقى ذلك اليومُ للمدرسة
كلّها بحصّةٍ واحدة ولا يُكمَل أبداً (ثبت بالتجربة: 1 بدل 176). والإصلاح:

- التوليدُ يقيس اليومَ بعدد حصصه أمام خطّته، ويُكمل الناقص بلا تكرار.
- نقلُ الحصّة (إشغالٌ وتبديل) والتعويضُ يولّدان يومهما كاملاً قبل الكتابة فيه.
- `resync_sessions_for_range` تصالح الأيّامَ المولَّدةَ مع الخطّة بعد تعديلها
  مباشرةً (جلسة الجدولة، البند SCH-08).
"""

import datetime as dt

import pytest

from core.models import ClassGroup
from operations.models import (
    CompensatorySession,
    ScheduleSlot,
    Session,
    StudentAttendance,
    Subject,
    TeacherAbsence,
    TimeSlotConfig,
)
from operations.services import CompensatoryService, ScheduleService, SubstituteService
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"
#: أحدٌ من أيّام الدراسة في التقويم المبذور، في أسبوعٍ لا يولّده شيءٌ غير الاختبار.
SUNDAY = dt.date(2026, 10, 11)
NEXT_SUNDAY = SUNDAY + dt.timedelta(days=7)


def _teacher(school, name):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


@pytest.fixture
def plan(school):
    """ثلاثُ شعبٍ في الحصّة الأولى يومَ الأحد، لكلٍّ معلّمُها."""
    subject = Subject.objects.create(school=school, name_ar="الرياضيات")
    slots = []
    for i in range(3):
        cg = ClassGroup.objects.create(
            school=school, grade="G8", section=str(i + 1), academic_year=YEAR
        )
        slots.append(
            ScheduleSlot.objects.create(
                school=school,
                teacher=_teacher(school, f"معلّم {i + 1}"),
                class_group=cg,
                subject=subject,
                day_of_week=0,
                period_number=1,
                start_time=dt.time(7, 10),
                end_time=dt.time(7, 55),
                academic_year=YEAR,
            )
        )
    return {"slots": slots, "subject": subject, "free": _teacher(school, "متفرّغ")}


def _day(school, day=SUNDAY):
    return Session.objects.filter(school=school, date=day)


class TestADayIsCompleteByItsCountNotByOneRow:
    def test_a_lone_row_does_not_stop_the_rest_of_the_day(self, school, plan):
        lone = plan["slots"][0]
        Session.objects.create(
            school=school,
            teacher=plan["free"],
            original_teacher=lone.teacher,
            class_group=lone.class_group,
            subject=lone.subject,
            date=SUNDAY,
            start_time=lone.start_time,
            end_time=lone.end_time,
        )

        created = ScheduleService.ensure_sessions_for_date(school, SUNDAY, academic_year=YEAR)

        assert created == 2, "الناقصُ وحده يُنشأ، والموجودُ لا يتكرّر"
        assert _day(school).count() == 3
        assert _day(school).get(class_group=lone.class_group).teacher == plan["free"]

    def test_a_complete_week_is_left_alone_cheaply(
        self, school, plan, django_assert_max_num_queries
    ):
        ScheduleService.ensure_sessions_for_date(school, SUNDAY, academic_year=YEAR)

        with django_assert_max_num_queries(2):
            assert ScheduleService.ensure_sessions_for_date(school, SUNDAY, academic_year=YEAR) == 0


class TestWritersGenerateTheirDayFirst:
    def test_handing_over_a_lesson_in_an_ungenerated_week(self, school, plan, seeded_calendar):
        slot = plan["slots"][0]

        SubstituteService.hand_over_session(school, slot, SUNDAY, plan["free"])

        assert _day(school).count() == 3, "كان اليومُ يبقى بحصّةٍ واحدة"
        moved = _day(school).get(class_group=slot.class_group)
        assert (moved.teacher, moved.original_teacher) == (plan["free"], slot.teacher)

    def test_approving_a_compensatory_lesson_in_an_ungenerated_week(
        self, school, plan, principal_user, seeded_calendar
    ):
        slot = plan["slots"][0]
        TimeSlotConfig.objects.create(
            school=school, period_number=6, start_time=dt.time(11, 0), end_time=dt.time(11, 45)
        )
        absence = TeacherAbsence.objects.create(
            school=school, teacher=slot.teacher, date=SUNDAY - dt.timedelta(days=7)
        )
        comp = CompensatorySession.objects.create(
            school=school,
            teacher=slot.teacher,
            original_slot=slot,
            absence=absence,
            compensatory_date=SUNDAY,
            compensatory_period=6,
            class_group=slot.class_group,
            subject=slot.subject,
        )

        CompensatoryService.approve_compensatory(comp, approved_by=principal_user)

        assert _day(school).count() == 4, "حصصُ الخطّة الثلاث والتعويضُ معها"


class TestResyncForARange:
    def test_a_permanent_change_in_the_plan_reaches_generated_days_only(
        self, school, plan, seeded_calendar
    ):
        ScheduleService.ensure_sessions_for_date(school, SUNDAY, academic_year=YEAR)
        slot = plan["slots"][1]
        slot.teacher = plan["free"]  # تبديلٌ دائمٌ في الخطّة نفسها
        slot.save(update_fields=["teacher"])

        totals = ScheduleService.resync_sessions_for_range(
            school, SUNDAY, NEXT_SUNDAY, academic_year=YEAR
        )

        assert totals == {"deleted": 1, "created": 1, "kept": 0}
        assert _day(school).get(class_group=slot.class_group).teacher == plan["free"]
        assert not _day(school, NEXT_SUNDAY).exists(), "يومٌ لم يُولَّد لا يُولَّد هنا"

    def test_a_lesson_with_attendance_is_kept(self, school, plan, student_user, seeded_calendar):
        ScheduleService.ensure_sessions_for_date(school, SUNDAY, academic_year=YEAR)
        slot = plan["slots"][2]
        session = _day(school).get(class_group=slot.class_group)
        StudentAttendance.objects.create(session=session, student=student_user, school=school)
        slot.teacher = plan["free"]
        slot.save(update_fields=["teacher"])

        totals = ScheduleService.resync_sessions_for_range(
            school, SUNDAY, SUNDAY, academic_year=YEAR
        )

        assert totals["kept"] == 1
        assert Session.objects.filter(pk=session.pk).exists()

    def test_an_inverted_range_is_refused(self, school):
        with pytest.raises(ValueError):
            ScheduleService.resync_sessions_for_range(school, NEXT_SUNDAY, SUNDAY)
