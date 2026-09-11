"""التبديلُ مؤقّتٌ بالبناء، ويُوقّعه منسّقا المادّتين، ويُعرَف بلونه.

أربعةُ قراراتٍ للمستخدم 2026-09-11:

1. التبديلُ لا يمسّ قالبَ الأسبوع — ينقضي بانتهاء الحصّة الأبعد ويعود الجدولُ
   من نفسه، بلا إجراءٍ ولا مهمّةٍ مجدولة.
2. يوقّعه منسّقا المادّتين، والنائبُ بديلٌ عن الغائب منهما لا متجاوزٌ عليهما.
3. الحصّةُ المبدَّلةُ تُعرف بلونها، ويُعرَف صاحبُها الأوّل.
4. يجوز في الأسبوع الجاري أو الذي يليه — فتاريخٌ لكلّ حصّة.
"""

from datetime import date, time, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models.department import Department
from operations.models import ScheduleSlot, Session, TeacherSwap
from operations.services import SwapService
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db


def _teacher(school, name, department=None, role="teacher"):
    user = UserFactory(full_name=name)
    MembershipFactory(
        user=user,
        school=school,
        role=RoleFactory(school=school, name=role),
        department_obj=department,
    )
    return user


def _department(school, name, code, head=None):
    return Department.objects.create(school=school, name=name, code=code, head=head)


def _slot(school, teacher, klass, day, period, subject=None):
    return ScheduleSlot.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        subject=subject,
        day_of_week=day,
        period_number=period,
        start_time=time(8 + period, 0),
        end_time=time(8 + period, 45),
        academic_year=klass.academic_year,
    )


#: ترقيمُ يوم القالب (الأحدُ صفرٌ) من ترقيم بايثون (الاثنينُ صفر) — وهو
#: عكسُ `_slot_weekday` في العرض. والجمعةُ والسبتُ خارجَ الأسبوع الدراسيّ.
SCHOOL_DAY = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4}


def _slot_day(day):
    return SCHOOL_DAY[day.weekday()]


@pytest.fixture
def week(school):
    """يومان دراسيّان داخلَ المدى — ولا يقعان جمعةً ولا سبتاً."""
    today = timezone.localdate()
    days = [
        today + timedelta(days=n)
        for n in range(1, 15)
        if (today + timedelta(days=n)).weekday() in SCHOOL_DAY
    ]
    return days[0], days[5]


@pytest.fixture
def pair(school, week):
    """معلّمان في قسمين، لكلٍّ حصّةٌ في يومٍ مختلف."""
    maths = _department(school, "الرياضيات", "math")
    arabic = _department(school, "اللغة العربية", "arabic")
    a = _teacher(school, "معلّم الرياضيات", maths)
    b = _teacher(school, "معلّم العربية", arabic)
    maths.head = _teacher(school, "منسّق الرياضيات", maths, role="coordinator")
    arabic.head = _teacher(school, "منسّق العربية", arabic, role="coordinator")
    maths.save(update_fields=["head"])
    arabic.save(update_fields=["head"])
    klass = ClassGroupFactory(school=school)
    day_a, day_b = week
    return {
        "a": a,
        "b": b,
        "maths": maths,
        "arabic": arabic,
        "slot_a": _slot(school, a, klass, _slot_day(day_a), 2),
        "slot_b": _slot(school, b, klass, _slot_day(day_b), 3),
        "date_a": day_a,
        "date_b": day_b,
    }


def _swap(school, pair, status="pending_coordinator"):
    return TeacherSwap.objects.create(
        school=school,
        teacher_a=pair["a"],
        teacher_b=pair["b"],
        slot_a=pair["slot_a"],
        slot_b=pair["slot_b"],
        swap_date_a=pair["date_a"],
        swap_date_b=pair["date_b"],
        status=status,
    )


class TestItIsTemporary:
    """كان يبدّل المعلّمَ في `ScheduleSlot` — قالبِ الأسبوع كلِّه."""

    def test_the_weekly_template_is_never_touched(self, school, pair):
        swap = _swap(school, pair)
        before = (pair["slot_a"].teacher_id, pair["slot_b"].teacher_id)

        SwapService.execute_swap(swap)

        pair["slot_a"].refresh_from_db()
        pair["slot_b"].refresh_from_db()
        assert (
            pair["slot_a"].teacher_id,
            pair["slot_b"].teacher_id,
        ) == before, "حصّةُ يومٍ واحدٍ كانت تُبدَّل كلَّ أسبوعٍ إلى الأبد"

    def test_only_the_two_dated_sessions_change_hands(self, school, pair):
        swap = _swap(school, pair)

        SwapService.execute_swap(swap)

        first = Session.objects.get(date=pair["date_a"], start_time=pair["slot_a"].start_time)
        second = Session.objects.get(date=pair["date_b"], start_time=pair["slot_b"].start_time)
        assert first.teacher_id == pair["b"].pk
        assert second.teacher_id == pair["a"].pk

    def test_the_session_is_created_when_the_day_has_none_yet(self, school, pair):
        """القالبُ يقول إنّ الحصّةَ قائمةٌ ذلك اليوم — والتبديلُ يحتاج صفّاً."""
        swap = _swap(school, pair)
        assert not Session.objects.filter(date=pair["date_a"]).exists()

        SwapService.execute_swap(swap)

        assert Session.objects.filter(date=pair["date_a"]).exists()

    def test_the_window_ends_with_the_later_period(self, school, pair):
        swap = _swap(school, pair)

        assert swap.last_period_end.date() == pair["date_b"], "الأبعدُ هو الحدّ"
        assert swap.has_ended is False

    def test_a_swap_whose_periods_have_passed_has_ended(self, school, pair):
        swap = _swap(school, pair)
        swap.swap_date_a = date(2020, 1, 1)
        swap.swap_date_b = date(2020, 1, 2)

        assert swap.has_ended is True


class TestTheColour:
    def test_the_original_teacher_is_remembered(self, school, pair):
        swap = _swap(school, pair)

        SwapService.execute_swap(swap)

        moved = Session.objects.get(date=pair["date_a"], start_time=pair["slot_a"].start_time)
        assert moved.original_teacher_id == pair["a"].pk, "ووجودُه هو ما يُلوّن الخانة"

    def test_a_session_never_swapped_carries_no_trace(self, school, pair):
        Session.objects.create(
            school=school,
            class_group=pair["slot_a"].class_group,
            teacher=pair["a"],
            date=pair["date_a"],
            start_time=pair["slot_a"].start_time,
            end_time=pair["slot_a"].end_time,
        )

        assert Session.objects.get(date=pair["date_a"]).original_teacher_id is None

    def test_the_first_owner_survives_a_second_swap(self, school, pair):
        """حصّةٌ بُدّلت مرّتين صاحبُها الأوّلُ أوّلُها لا أوسطُها."""
        swap = _swap(school, pair)
        SwapService.execute_swap(swap)
        again = _swap(school, pair)

        SwapService.execute_swap(again)

        moved = Session.objects.get(date=pair["date_a"], start_time=pair["slot_a"].start_time)
        assert moved.original_teacher_id == pair["a"].pk


class TestTheTwoSignatures:
    def test_each_coordinator_signs_for_their_own_subject(self, school, pair):
        swap = _swap(school, pair)

        assert SwapService.signable_sides(swap, pair["maths"].head) == ("a",)
        assert SwapService.signable_sides(swap, pair["arabic"].head) == ("b",)

    def test_a_coordinator_of_another_department_signs_for_neither(self, school, pair):
        other = _department(school, "العلوم", "sci")
        stranger = _teacher(school, "منسّق العلوم", other, role="coordinator")
        other.head = stranger
        other.save(update_fields=["head"])

        assert SwapService.signable_sides(_swap(school, pair), stranger) == ()

    def test_one_signature_does_not_execute_it(self, school, pair):
        swap = _swap(school, pair)

        SwapService.approve_swap(swap, approved_by=pair["maths"].head)

        swap.refresh_from_db()
        assert swap.status == "pending_coordinator", "ينتظر الجهةَ الأخرى"
        assert swap.approved_a_by_id == pair["maths"].head.pk
        assert swap.approved_b_by_id is None

    def test_both_signatures_execute_it(self, school, pair):
        swap = _swap(school, pair)

        SwapService.approve_swap(swap, approved_by=pair["maths"].head)
        SwapService.approve_swap(swap, approved_by=pair["arabic"].head)

        swap.refresh_from_db()
        assert swap.status == "executed"

    def test_one_coordinator_for_both_subjects_signs_once(self, school, pair):
        """قسمٌ واحدٌ يجمعهما — فلا يُطلب توقيعُ رجلٍ مرّتين."""
        pair["arabic"].head = pair["maths"].head
        pair["arabic"].save(update_fields=["head"])
        swap = _swap(school, pair)

        SwapService.approve_swap(swap, approved_by=pair["maths"].head)

        swap.refresh_from_db()
        assert swap.status == "executed"

    def test_a_stranger_is_refused_with_a_reason(self, school, pair):
        outsider = _teacher(school, "معلّمٌ آخر", pair["maths"])

        with pytest.raises(ValueError, match="لا تملك التوقيعَ"):
            SwapService.approve_swap(_swap(school, pair), approved_by=outsider)


class TestTheDeputyStandsInForTheAbsent:
    """النائبُ بديلٌ عن الغائب لا متجاوزٌ عليه (قرارُ المستخدم)."""

    def _deputy(self, school):
        return _teacher(school, "النائب الأكاديميّ", None, role="vice_academic")

    def test_the_deputy_signs_where_the_seat_is_vacant(self, school, pair):
        pair["arabic"].head = None
        pair["arabic"].save(update_fields=["head"])

        assert SwapService.signable_sides(_swap(school, pair), self._deputy(school)) == ("b",)

    def test_the_deputy_does_not_sign_where_a_coordinator_is_present(self, school, pair):
        assert SwapService.signable_sides(_swap(school, pair), self._deputy(school)) == ()

    def test_the_deputy_signs_when_the_coordinator_is_absent_today(self, school, pair):
        from operations.models import TeacherAbsence

        TeacherAbsence.objects.create(
            school=school, teacher=pair["maths"].head, date=timezone.localdate()
        )

        assert SwapService.signable_sides(_swap(school, pair), self._deputy(school)) == ("a",)

    def test_the_deputy_signs_when_the_coordinator_is_a_party_to_the_swap(self, school, pair):
        """لا يحكم أحدٌ في أمرِ نفسه."""
        pair["maths"].head = pair["a"]
        pair["maths"].save(update_fields=["head"])

        assert SwapService.signable_sides(_swap(school, pair), self._deputy(school)) == ("a",)

    def test_a_substitute_signature_is_recorded_as_such(self, school, pair):
        pair["arabic"].head = None
        pair["arabic"].save(update_fields=["head"])
        swap = _swap(school, pair)

        SwapService.approve_swap(swap, approved_by=self._deputy(school))

        swap.refresh_from_db()
        assert swap.approved_b_by_substitute is True, "يُقرأ في السجلّ أنّه وقّع بديلاً"


class TestTheRequestWindow:
    def test_a_date_outside_the_two_weeks_is_refused(self, client_as, school, pair):
        from operations.views_swap import _swap_day

        far = timezone.localdate() + timedelta(days=30)
        with pytest.raises(ValueError, match="الأسبوع الجاري"):
            _swap_day(far.isoformat(), pair["slot_a"])

    def test_a_past_date_is_refused(self, school, pair):
        from operations.views_swap import _swap_day

        with pytest.raises(ValueError, match="الأسبوع الجاري"):
            _swap_day("2020-01-01", pair["slot_a"])

    def test_a_date_that_is_not_the_slots_weekday_is_refused(self, school, pair):
        """الحصّةُ في يومٍ بعينه من القالب — وتاريخٌ من يومٍ آخرَ لا حصّةَ فيه."""
        from operations.views_swap import _swap_day

        wrong = pair["date_a"] + timedelta(days=1)
        with pytest.raises(ValueError, match="ليس ذلك اليوم"):
            _swap_day(wrong.isoformat(), pair["slot_a"])

    def test_the_matching_weekday_inside_the_window_is_accepted(self, school, pair):
        from operations.views_swap import _swap_day

        assert _swap_day(pair["date_a"].isoformat(), pair["slot_a"]) == pair["date_a"]

    def test_an_unreadable_date_is_refused_not_replaced_by_today(self, school, pair):
        """كان يُستبدَل بتاريخ اليوم صامتاً — فيقع التبديلُ في يومٍ لم يُطلب."""
        from operations.views_swap import _swap_day

        with pytest.raises(ValueError, match="غيرُ صالح"):
            _swap_day("المرّيخ", pair["slot_a"])

    def test_an_empty_date_is_refused(self, school, pair):
        from operations.views_swap import _swap_day

        with pytest.raises(ValueError, match="تحديد تاريخ"):
            _swap_day("", pair["slot_a"])


class TestTheDeveloperSeesIt:
    """كان `platform_developer` خارجَ `SCHEDULE_VIEW` أصلاً — الشاشةُ محجوبة."""

    def test_the_developer_may_open_the_list(self, client_as, school, pair):
        developer = _teacher(school, "المطوّر", None, role="platform_developer")

        response = client_as(developer).get(reverse("swap_list"))

        assert response.status_code == 200

    def test_the_developer_sees_every_swap_not_only_their_own(self, client_as, school, pair):
        developer = _teacher(school, "المطوّر", None, role="platform_developer")
        _swap(school, pair)

        body = client_as(developer).get(reverse("swap_list")).content.decode()

        assert pair["a"].full_name in body, "يُسأل عن التبديل فيجب أن يجده"
