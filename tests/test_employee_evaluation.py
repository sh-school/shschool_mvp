"""
tests/test_employee_evaluation.py
اختبارات تقييم أداء الموظفين — quality/employee_evaluation.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يغطي:
  - EmployeeEvaluation : calculate_total, rating levels, acknowledge, __str__
  - EvaluationCycle   : completion_rate, __str__, constraints
"""
import pytest
from datetime import date, timedelta
from django.utils import timezone

from quality.models import EmployeeEvaluation, EvaluationCycle
from tests.conftest import (
    SchoolFactory, UserFactory, RoleFactory, MembershipFactory,
)


# ══════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════

def make_principal(school):
    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name="مدير المدرسة")
    MembershipFactory(user=user, school=school, role=role)
    return user


def make_teacher(school):
    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(full_name="معلم")
    MembershipFactory(user=user, school=school, role=role)
    return user


def make_evaluation(school, employee, evaluator,
                    professional=20, commitment=20, teamwork=20, development=20,
                    period="S1", status="draft"):
    return EmployeeEvaluation.objects.create(
        school=school,
        employee=employee,
        evaluator=evaluator,
        academic_year="2025-2026",
        period=period,
        status=status,
        axis_professional=professional,
        axis_commitment=commitment,
        axis_teamwork=teamwork,
        axis_development=development,
    )


# ══════════════════════════════════════════════════════════════
#  EmployeeEvaluation — calculate_total
# ══════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestCalculateTotal:

    def test_excellent_rating_90_plus(self, school):
        principal = make_principal(school)
        teacher   = make_teacher(school)
        # 23+23+23+23 = 92 → ممتاز
        ev = make_evaluation(school, teacher, principal,
                             professional=23, commitment=23, teamwork=23, development=23)
        assert ev.total_score == 92
        assert ev.rating == "excellent"

    def test_very_good_rating_75_to_89(self, school):
        principal = make_principal(school)
        teacher   = make_teacher(school)
        # 20+20+20+20 = 80 → جيد جداً
        ev = make_evaluation(school, teacher, principal,
                             professional=20, commitment=20, teamwork=20, development=20)
        assert ev.total_score == 80
        assert ev.rating == "very_good"

    def test_good_rating_60_to_74(self, school):
        principal = make_principal(school)
        teacher   = make_teacher(school)
        # 16+16+16+17 = 65 → جيد
        ev = make_evaluation(school, teacher, principal,
                             professional=16, commitment=16, teamwork=16, development=17)
        assert ev.total_score == 65
        assert ev.rating == "good"

    def test_needs_dev_below_60(self, school):
        principal = make_principal(school)
        teacher   = make_teacher(school)
        # 10+10+10+10 = 40 → يحتاج تطوير
        ev = make_evaluation(school, teacher, principal,
                             professional=10, commitment=10, teamwork=10, development=10)
        assert ev.total_score == 40
        assert ev.rating == "needs_dev"

    def test_boundary_exactly_90_is_excellent(self, school):
        principal = make_principal(school)
        teacher   = make_teacher(school)
        ev = make_evaluation(school, teacher, principal,
                             professional=23, commitment=23, teamwork=22, development=22)
        assert ev.total_score == 90
        assert ev.rating == "excellent"

    def test_boundary_exactly_75_is_very_good(self, school):
        principal = make_principal(school)
        teacher   = make_teacher(school)
        ev = make_evaluation(school, teacher, principal,
                             professional=19, commitment=19, teamwork=19, development=18)
        assert ev.total_score == 75
        assert ev.rating == "very_good"

    def test_boundary_exactly_60_is_good(self, school):
        principal = make_principal(school)
        teacher   = make_teacher(school)
        ev = make_evaluation(school, teacher, principal,
                             professional=15, commitment=15, teamwork=15, development=15)
        assert ev.total_score == 60
        assert ev.rating == "good"

    def test_total_saved_automatically(self, school):
        """calculate_total يُستدعى في save()"""
        principal = make_principal(school)
        teacher   = make_teacher(school)
        ev = make_evaluation(school, teacher, principal,
                             professional=25, commitment=25, teamwork=25, development=25)
        refreshed = EmployeeEvaluation.objects.get(id=ev.id)
        assert refreshed.total_score == 100
        assert refreshed.rating == "excellent"


# ══════════════════════════════════════════════════════════════
#  EmployeeEvaluation — acknowledge
# ══════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAcknowledge:

    def test_acknowledge_sets_status(self, school):
        principal = make_principal(school)
        teacher   = make_teacher(school)
        ev = make_evaluation(school, teacher, principal, status="submitted")
        ev.acknowledge()
        refreshed = EmployeeEvaluation.objects.get(id=ev.id)
        assert refreshed.status == "acknowledged"

    def test_acknowledge_sets_timestamp(self, school):
        principal = make_principal(school)
        teacher   = make_teacher(school)
        ev = make_evaluation(school, teacher, principal, status="submitted")
        before = timezone.now()
        ev.acknowledge()
        after = timezone.now()
        refreshed = EmployeeEvaluation.objects.get(id=ev.id)
        assert refreshed.acknowledged_at is not None
        assert before <= refreshed.acknowledged_at <= after

    def test_acknowledge_can_be_called_once(self, school):
        principal = make_principal(school)
        teacher   = make_teacher(school)
        ev = make_evaluation(school, teacher, principal, status="approved")
        ev.acknowledge()
        assert ev.status == "acknowledged"


# ══════════════════════════════════════════════════════════════
#  EmployeeEvaluation — __str__ و Meta
# ══════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestEvaluationMeta:

    def test_str_contains_employee_name(self, school):
        principal = make_principal(school)
        teacher   = make_teacher(school)
        ev = make_evaluation(school, teacher, principal)
        assert teacher.full_name in str(ev)

    def test_str_contains_period(self, school):
        principal = make_principal(school)
        teacher   = make_teacher(school)
        ev = make_evaluation(school, teacher, principal, period="S1")
        assert "نهاية الفصل الأول" in str(ev)

    def test_str_contains_year(self, school):
        principal = make_principal(school)
        teacher   = make_teacher(school)
        ev = make_evaluation(school, teacher, principal)
        assert "2025-2026" in str(ev)

    def test_uuid_primary_key(self, school):
        import uuid
        principal = make_principal(school)
        teacher   = make_teacher(school)
        ev = make_evaluation(school, teacher, principal)
        assert isinstance(ev.id, uuid.UUID)

    def test_unique_constraint_per_period(self, school):
        from django.db import IntegrityError
        principal = make_principal(school)
        teacher   = make_teacher(school)
        make_evaluation(school, teacher, principal, period="S1")
        with pytest.raises(IntegrityError):
            make_evaluation(school, teacher, principal, period="S1")

    def test_ordering_newest_first(self, school):
        principal = make_principal(school)
        t1 = make_teacher(school)
        t2 = make_teacher(school)
        ev1 = make_evaluation(school, t1, principal, period="S1")
        ev2 = make_evaluation(school, t2, principal, period="S1")
        evals = list(EmployeeEvaluation.objects.filter(school=school))
        assert evals[0].id == ev2.id  # الأحدث أولاً


# ══════════════════════════════════════════════════════════════
#  EvaluationCycle
# ══════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestEvaluationCycle:

    def _make_cycle(self, school, created_by, period="S1", is_closed=False):
        return EvaluationCycle.objects.create(
            school=school,
            academic_year="2025-2026",
            period=period,
            deadline=date.today() + timedelta(days=30),
            created_by=created_by,
            is_closed=is_closed,
        )

    def test_str_contains_school_code(self, school):
        principal = make_principal(school)
        cycle = self._make_cycle(school, principal)
        assert school.code in str(cycle)

    def test_str_contains_year(self, school):
        principal = make_principal(school)
        cycle = self._make_cycle(school, principal)
        assert "2025-2026" in str(cycle)

    def test_uuid_primary_key(self, school):
        import uuid
        principal = make_principal(school)
        cycle = self._make_cycle(school, principal)
        assert isinstance(cycle.id, uuid.UUID)

    def test_unique_cycle_per_school_year_period(self, school):
        from django.db import IntegrityError
        principal = make_principal(school)
        self._make_cycle(school, principal, period="S1")
        with pytest.raises(IntegrityError):
            self._make_cycle(school, principal, period="S1")

    def test_completion_rate_zero_when_no_staff(self, school):
        principal = make_principal(school)
        cycle = self._make_cycle(school, principal)
        # لا يوجد موظفون → معدل 0
        assert cycle.completion_rate == 0

    def test_completion_rate_with_staff(self, school):
        principal = make_principal(school)
        teacher   = make_teacher(school)
        cycle = self._make_cycle(school, principal, period="S2")
        # أنشئ تقييم مُقدَّم للمعلم
        EmployeeEvaluation.objects.create(
            school=school,
            employee=teacher,
            evaluator=principal,
            academic_year="2025-2026",
            period="S2",
            status="submitted",
        )
        rate = cycle.completion_rate
        # rate يجب أن يكون > 0 (المعلم مُقيَّم)
        assert rate > 0

    def test_is_closed_default_false(self, school):
        principal = make_principal(school)
        cycle = self._make_cycle(school, principal)
        assert cycle.is_closed is False

    def test_null_on_creator_delete(self, school):
        """حذف المُنشئ → created_by = NULL"""
        principal = make_principal(school)
        cycle = self._make_cycle(school, principal)
        principal.delete()
        refreshed = EvaluationCycle.objects.get(id=cycle.id)
        assert refreshed.created_by is None
