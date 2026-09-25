"""التبديلُ بسبب غياب المعلّم — قراراتُ المالك 2026-09-23 و2026-09-24.

- مع معلّمي الشعبة نفسها وحدَهم: يأخذ الآخرُ حصّةَ الغائب يومَ غيابه، ويردّها له الغائبُ
  حصّةً من حصص الآخر في الشعبة يومَ عودته.
- يبدأه المنسّق: يوافق المعلّمُ الآخر، ثمّ يوقّع المنسّقان، ثمّ يعتمد النائبُ أو من كُلِّف عنه.
- تبدأه القيادة: يُنفَّذ فوراً.
"""

import datetime as dt

import pytest
from django.urls import reverse

from core.academic_calendar import academic_year_for_school
from core.models import Department
from notifications.models import InAppNotification
from operations.models import ScheduleSlot, Session, Subject, TeacherAbsence, TeacherSwap
from operations.services import AbsenceSwapService, SubstituteService, SwapService
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

SUNDAY = dt.date(2026, 9, 20)
MONDAY = SUNDAY + dt.timedelta(days=1)
DAY_A = SubstituteService._date_to_day(SUNDAY)
DAY_B = SubstituteService._date_to_day(MONDAY)


@pytest.fixture(autouse=True)
def _calendar(seeded_calendar):
    return seeded_calendar


def _member(school, role, name, department=None):
    user = UserFactory(full_name=name)
    MembershipFactory(
        user=user,
        school=school,
        role=RoleFactory(school=school, name=role),
        department_obj=department,
    )
    return user


def _slot(school, teacher, class_group, day, period, subject=None):
    return ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=class_group,
        subject=subject,
        day_of_week=day,
        period_number=period,
        start_time=dt.time(6 + period, 0),
        end_time=dt.time(6 + period, 45),
        academic_year=academic_year_for_school(school),
    )


@pytest.fixture
def world(school, class_group):
    math = Department.objects.create(school=school, name="الرياضيات", code="math")
    science = Department.objects.create(school=school, name="العلوم", code="science")
    coord_math = _member(school, "coordinator", "منسّق الرياضيات", math)
    coord_science = _member(school, "coordinator", "منسّق العلوم", science)
    math.head, science.head = coord_math, coord_science
    math.save(update_fields=["head"])
    science.save(update_fields=["head"])
    absent = _member(school, "teacher", "الغائب", math)
    partner = _member(school, "teacher", "معلّم العلوم في الشعبة", science)
    busy = _member(school, "teacher", "معلّمٌ مشغول", science)
    outsider = _member(school, "teacher", "من شعبةٍ أخرى", science)
    vice = _member(school, "vice_academic", "النائب الأكاديمي")
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")
    sci = Subject.objects.create(school=school, name_ar="العلوم", code="SCI")
    other_class = ClassGroupFactory(school=school)

    lesson = _slot(school, absent, class_group, DAY_A, 3, maths)
    payback = _slot(school, partner, class_group, DAY_B, 2, sci)
    _slot(school, busy, class_group, DAY_B, 4, sci)
    _slot(school, busy, other_class, DAY_A, 3, sci)  # مشغولٌ وقتَ حصّة الغائب
    _slot(school, outsider, other_class, DAY_B, 1, sci)
    absence = TeacherAbsence.objects.create(school=school, teacher=absent, date=SUNDAY)
    return {
        "absent": absent,
        "partner": partner,
        "busy": busy,
        "outsider": outsider,
        "coord_math": coord_math,
        "coord_science": coord_science,
        "vice": vice,
        "lesson": lesson,
        "payback": payback,
        "absence": absence,
    }


def _session(slot, day):
    return Session.objects.get(class_group=slot.class_group, date=day, start_time=slot.start_time)


class TestWhoCanBeSwappedWith:
    def test_only_free_teachers_of_the_same_class_with_a_payback_day(self, world):
        options = AbsenceSwapService.options(world["absence"], world["lesson"])

        assert [(o["teacher"], o["slot"], o["date"]) for o in options] == [
            (world["partner"], world["payback"], MONDAY)
        ]

    def test_a_choice_outside_the_options_is_refused(self, world):
        with pytest.raises(ValueError):
            AbsenceSwapService.request(
                world["absence"], world["lesson"], world["payback"], SUNDAY, world["coord_math"]
            )


class TestLeadershipSwapsAtOnce:
    def test_the_vice_principal_executes_it_and_everyone_is_told(
        self, world, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            swap = AbsenceSwapService.request(
                world["absence"], world["lesson"], world["payback"], MONDAY, world["vice"]
            )

        assert swap.status == "executed"
        assert _session(world["lesson"], SUNDAY).teacher == world["partner"]
        assert _session(world["payback"], MONDAY).teacher == world["absent"]
        world["absence"].refresh_from_db()
        assert world["absence"].status == "covered"
        told = set(InAppNotification.objects.values_list("user__full_name", flat=True))
        assert {"الغائب", "معلّم العلوم في الشعبة", "منسّق الرياضيات", "منسّق العلوم"} <= told


class TestTheCoordinatorsPath:
    def test_teacher_then_both_coordinators_then_the_vice_principal(self, world):
        swap = AbsenceSwapService.request(
            world["absence"], world["lesson"], world["payback"], MONDAY, world["coord_math"]
        )
        assert swap.status == "pending_b"
        assert swap.approved_a_by == world["coord_math"], "من بدأه وقّع عن جهته"

        SwapService.respond_to_swap(swap, accepted=True)
        swap.refresh_from_db()
        assert swap.status == "pending_coordinator", "ينتظر منسّقَ العلوم"

        SwapService.approve_swap(swap, approved_by=world["coord_science"])
        swap.refresh_from_db()
        assert swap.status == "pending_vp", "التوقيعان لا ينفّذانه — ينتظر النائب"
        assert _session_missing_or_unmoved(world["lesson"])

        with pytest.raises(ValueError):
            SwapService.approve_swap(swap, approved_by=world["coord_math"])

        SwapService.approve_swap(swap, approved_by=world["vice"])
        swap.refresh_from_db()
        assert swap.status == "executed"
        assert _session(world["lesson"], SUNDAY).teacher == world["partner"]

    def test_the_acting_vice_principal_may_approve(self, school, world, principal_user):
        from django.utils import timezone

        from staff_affairs.models import StaffAssignment

        stand_in = _member(school, "coordinator", "المكلَّف عن النائب")
        StaffAssignment.objects.create(
            school=school,
            assignee=stand_in,
            assigned_by=world["vice"],
            acting_role="vice_academic",
            start_date=timezone.localdate(),
            end_date=timezone.localdate(),
            reason="غياب النائب",
        )
        swap = TeacherSwap.objects.create(
            school=school,
            teacher_a=world["absent"],
            teacher_b=world["partner"],
            slot_a=world["lesson"],
            slot_b=world["payback"],
            swap_date_a=SUNDAY,
            swap_date_b=MONDAY,
            status="pending_vp",
            absence=world["absence"],
        )

        assert AbsenceSwapService.can_final_approve(swap, stand_in)
        assert not AbsenceSwapService.can_final_approve(swap, world["coord_math"])


def _session_missing_or_unmoved(slot):
    session = Session.objects.filter(
        class_group=slot.class_group, date=SUNDAY, start_time=slot.start_time
    ).first()
    return session is None or session.original_teacher_id is None


class TestTheSlotCardShowsTheSwap:
    def test_a_pending_swap_is_named_on_the_absence_page(self, client_as, world, principal_user):
        AbsenceSwapService.request(
            world["absence"], world["lesson"], world["payback"], MONDAY, world["coord_math"]
        )

        body = client_as(principal_user).get(reverse("absence_detail", args=[world["absence"].id]))

        assert "تبديل مع معلّم العلوم في الشعبة" in body.content.decode()

    def test_the_options_fragment_lists_the_class_teacher(self, client_as, world):
        body = client_as(world["coord_math"]).get(
            reverse("absence_swap_options", args=[world["absence"].id, world["lesson"].id])
        )

        assert "معلّم العلوم في الشعبة" in body.content.decode()
        assert "أرسل للموافقة" in body.content.decode()
