"""tests/test_clinic_metrics.py — مؤشرات قياس العيادة الخمسة (W-20261020-035).

الصيغ، وأن المخرجات أعدادٌ ونسبٌ بلا أسماء ولا نصٍّ صحيّ، وأن الوحدة لا تقرأ الحقول المشفَّرة ولا الفرد.
"""

import datetime as dt
import pathlib

import pytest
from django.utils import timezone

from clinic import metrics
from clinic.models import ClinicVisit
from clinic.services import ClinicService

ROOT = pathlib.Path(__file__).resolve().parent.parent

# تثبيتُ الساعة على أربعاءِ دوام: القياسُ يقرأ «اليوم» وشهرَه (حارس الساعة).
pytestmark = pytest.mark.pin_clock


def _visit(school, student, nurse, **kw):
    return ClinicVisit.objects.create(school=school, student=student, nurse=nurse, reason="ص", **kw)


@pytest.mark.django_db
class TestRegistrationTime:
    def test_p50_and_p90_use_nearest_rank_on_visits_with_a_draft(
        self, school, student_user, nurse_user
    ):
        for secs in (10, 20, 30, 40, 100):
            v = _visit(school, student_user, nurse_user)
            ClinicVisit.objects.filter(pk=v.pk).update(
                draft_started_at=v.visit_date - dt.timedelta(seconds=secs)
            )
        _visit(school, student_user, nurse_user)  # بلا مسودة: خارج القياس
        out = metrics.registration_time(ClinicVisit.objects.filter(school=school))
        assert out == {"n": 5, "p50": 30, "p90": 100}

    def test_the_service_stores_the_draft_start_without_any_health_text(
        self, school, student_user, nurse_user
    ):
        started = timezone.now() - dt.timedelta(seconds=15)
        visit = ClinicService.record_visit(
            school, student_user, nurse_user, reason="x", draft_started_at=started
        )
        assert visit.draft_started_at == started

    def test_no_visits_gives_none_not_zero(self, school):
        assert metrics.registration_time(ClinicVisit.objects.filter(school=school))["p50"] is None


@pytest.mark.django_db
class TestCodingCoverage:
    def test_a_closed_visit_needs_an_outcome_too(self, school, student_user, nurse_user):
        _visit(school, student_user, nurse_user, service_code="bandage", complaint_code="injury")
        _visit(school, student_user, nurse_user, service_code="bandage")  # بلا شكوى
        _visit(
            school,
            student_user,
            nurse_user,
            service_code="bandage",
            complaint_code="injury",
            closed_at=timezone.now(),
        )  # أُغلقت بلا حالة خروج
        out = metrics.coding_coverage(ClinicVisit.objects.filter(school=school))
        assert out == {"visits": 3, "coded": 1, "rate": 1 / 3}

    def test_empty_month_has_no_rate(self, school):
        assert metrics.coding_coverage(ClinicVisit.objects.filter(school=school))["rate"] is None


@pytest.mark.django_db
class TestAuditAndReconciliation:
    def test_every_created_visit_has_an_audit_row(self, school, student_user, nurse_user):
        _visit(school, student_user, nurse_user)
        _visit(school, student_user, nurse_user)
        out = metrics.audit_coverage(ClinicVisit.objects.filter(school=school))
        assert (out["visits"], out["audited"], out["rate"]) == (2, 2, 1.0)

    def test_reconciliation_is_total_when_every_dimension_sums_to_the_visits(
        self, school, student_user, nurse_user
    ):
        _visit(school, student_user, nurse_user, service_code="bandage", service_group="first_aid")
        _visit(school, student_user, nurse_user)
        out = metrics.monthly_reconciliation(ClinicVisit.objects.filter(school=school))
        assert out["rate"] == 1.0
        assert all(out["dimensions"].values())


@pytest.mark.django_db
class TestExitLink:
    def test_a_medical_permit_is_linked_by_a_same_day_earlier_visit(
        self, school, student_user, nurse_user, class_group
    ):
        from operations.models import ExitPermit

        group = class_group
        visit = _visit(school, student_user, nurse_user)
        base = {
            "school": school,
            "student": student_user,
            "reason": "medical",
            "class_group": group,
        }
        ExitPermit.objects.create(
            sequence=1, exit_at=visit.visit_date + dt.timedelta(minutes=5), **base
        )
        ExitPermit.objects.create(
            sequence=2, exit_at=visit.visit_date - dt.timedelta(hours=2), **base
        )
        start, end = metrics.month_bounds(visit.visit_date.year, visit.visit_date.month)
        out = metrics.exit_link(school, start, end)
        assert (out["permits"], out["linked"], out["rate"]) == (2, 1, 0.5)


@pytest.mark.django_db
class TestPrivacyAndPage:
    def test_the_indicators_carry_only_numbers(self, school, student_user, nurse_user):
        _visit(school, student_user, nurse_user, service_code="bandage")
        today = timezone.localdate()
        text = repr(metrics.clinic_indicators(school, today.year, today.month))
        assert student_user.full_name not in text
        assert nurse_user.full_name not in text

    def test_the_module_never_reads_encrypted_text_or_the_nurse(self):
        import ast

        tree = ast.parse((ROOT / "clinic" / "metrics.py").read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
            n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
        }
        strings = {
            n.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
        for forbidden in ("symptoms", "treatment", "nurse", "nurse_id", "full_name"):
            assert forbidden not in names | strings, forbidden

    def test_the_page_renders_five_cards_for_the_nurse(self, client_as, nurse_user, school):
        response = client_as(nurse_user).get("/clinic/metrics/")
        assert response.status_code == 200
        assert len(response.context["cards"]) == 5

    def test_a_bad_month_falls_back_to_this_month(self, client_as, nurse_user, school):
        response = client_as(nurse_user).get("/clinic/metrics/", {"month": "xx"})
        assert response.status_code == 200
        today = timezone.localdate()
        assert response.context["month_value"] == f"{today.year:04d}-{today.month:02d}"
