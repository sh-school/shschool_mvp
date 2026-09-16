"""[LEGAL] عيوبُ المراجعة العدائيّة لموجة تقييم الأداء (جولة الإصلاح 2، 2026-09-15).

كلُّ اختبارٍ هنا سقط على الفرع قبل إصلاحه. والمراجع مقروءةٌ من صورة الصفحة:

  - «02- النظام الوظيفي لموظفي المدارس.pdf» (قرار مجلس الوزراء 32/2019) صفحة الملفّ 10
    (المطبوعة 24): «مادة (15) ... تضع المدرسة تقارير تقييم الأداء للموظفين سنوياً، وفقاً
    للنماذج المعتمدة من الوزير. وتتولى لجنة شؤون المدارس، تقييم أداء مديري المدارس سنوياً»،
    ثمّ «مادة (16) يضع الرئيس المباشر تقييم أداء الموظف ويعتمد من مدير المدرسة». ونقلُهما
    في `02_staff_affairs.md:199-200`.
  - صفحة الملفّ 12 (المطبوعة 26)، المادة 20: «ويجوز للموظف أن يتظلم منه ... خلال خمسة عشر
    يوماً من تاريخ علمه».
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from quality.evaluation_services import (
    PRINCIPAL_NOT_EVALUATED,
    EvaluationRejectedError,
    approve_evaluation,
    record_receipt_on_refusal,
)
from quality.models import EmployeeEvaluation, EvaluationScore, RoleEvaluationTemplate
from tests.test_evaluation_review_round1 import YEAR, _seed, _staff, _url

ROOT = Path(__file__).resolve().parent.parent


# ── 1. المادة 15 لا 16: لجنةُ شؤون المدارس والنماذجُ المعتمدة من الوزير ──────────

#: ما نصُّه في المادة 15 (صفحة الملفّ 10). فسطرٌ يقتبسه ويُسنده إلى المادة 16 خطأُ إسناد.
ARTICLE_15_PHRASES = ("لجنة شؤون المدارس", "النماذج المعتمدة من الوزير", "للنماذج ")
CITING_FILES = (
    *sorted((ROOT / "quality").glob("*.py")),
    *sorted((ROOT / "templates" / "quality").glob("*.html")),
    ROOT / "docs" / "adr" / "0002-unified-staff-appraisal.md",
    ROOT / "tests" / "test_evaluation_review_round1.py",
    ROOT / "tests" / "test_evaluation_write_paths.py",
)


def _lines(paths, predicate):
    return [
        f"{path.relative_to(ROOT)}:{n}"
        for path in paths
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if predicate(line)
    ]


def test_article_15_text_is_not_attributed_to_article_16():
    misattributed = _lines(
        CITING_FILES,
        lambda line: "المادة 16" in line and any(p in line for p in ARTICLE_15_PHRASES),
    )
    assert misattributed == []
    assert "المادة 15" in PRINCIPAL_NOT_EVALUATED and "المادة 16" not in PRINCIPAL_NOT_EVALUATED


def test_article_16_is_quoted_verbatim():
    """الأصل «ويعتمد من مدير المدرسة» — لا «ويعتمده مدير المدرسة»."""
    assert _lines(CITING_FILES, lambda line: "ويعتمده مدير المدرسة" in line) == []


@pytest.mark.django_db
def test_annual_report_rejection_cites_article_15(school, principal_user, teacher_user):
    evaluation = EmployeeEvaluation.objects.create(
        school=school, employee=teacher_user, evaluator=_staff(school, "vice_academic"),
        academic_year=YEAR, period="S2", status="submitted",
    )  # fmt: skip
    with pytest.raises(EvaluationRejectedError, match="المادة 15"):
        approve_evaluation(evaluation=evaluation, approver=principal_user)


# ── 2. «تاريخ علمه» أسبقُ التاريخين: الإقرارُ اللاحق لا يعيد فتح المهلة ──────────


def _approved(school, employee, evaluator, **fields):
    return EmployeeEvaluation.objects.create(
        school=school, employee=employee, evaluator=evaluator,
        academic_year=YEAR, period="S2", status="approved", **fields,
    )  # fmt: skip


@pytest.mark.django_db
def test_late_acknowledgement_does_not_postpone_the_date_of_knowledge(
    client, school, principal_user, teacher_user
):
    """المادة 20: «خلال خمسة عشر يوماً من تاريخ علمه» — وقد علم يومَ دُوِّن استلامُه."""
    received = timezone.localdate() - timedelta(days=60)
    evaluation = _approved(school, teacher_user, principal_user, received_on=received)
    client.force_login(teacher_user)
    client.post(reverse("acknowledge_evaluation", kwargs={"eval_id": evaluation.pk}))
    evaluation.refresh_from_db()
    assert evaluation.acknowledged_at is not None
    assert evaluation.known_on() == received
    assert evaluation.grievance_deadline() == received + timedelta(days=15)
    assert evaluation.is_final() is True


# ── 3. تظلّمٌ بعد فوات ميعاده لا يُسقط النهائيّة ─────────────────────────────────


@pytest.mark.django_db
def test_grievance_after_the_fifteen_days_does_not_reopen_a_final_report(
    school, principal_user, teacher_user
):
    evaluation = _approved(school, teacher_user, principal_user)
    evaluation.status = "acknowledged"
    evaluation.acknowledged_at = timezone.make_aware(datetime.combine(date(2026, 6, 20), time(10)))
    evaluation.grievance_submitted_on = date(2026, 8, 1)
    assert evaluation.is_final(today=date(2026, 8, 15)) is True
    evaluation.grievance_decided_on = date(2026, 8, 20)
    assert evaluation.is_final(today=date(2026, 9, 1)) is True
    with pytest.raises(ValidationError, match="المادة 20"):
        evaluation.full_clean()
    # وفي آخر يومٍ من الميعاد مقبول، ويُنتظر البتّ.
    evaluation.grievance_submitted_on = date(2026, 7, 5)
    evaluation.grievance_decided_on = None
    evaluation.full_clean()
    assert evaluation.is_final(today=date(2026, 7, 20)) is False


# ── 4. صفٌّ قديمٌ ربطه GET القديم بقالبٍ ودرجاتُه في المحاور الافتراضيّة ─────────


@pytest.mark.django_db
def test_legacy_row_bound_to_a_template_keeps_its_default_axis_scores(
    client, school, principal_user, teacher_user
):
    form = _seed(school)
    template = RoleEvaluationTemplate.objects.get(
        school=school, role_name="teacher", academic_year=YEAR
    )
    vice = _staff(school, "vice_academic")
    evaluation = EmployeeEvaluation.objects.create(
        school=school, employee=teacher_user, evaluator=vice, academic_year=YEAR, period="S2",
        axis_professional=20, axis_commitment=22, axis_teamwork=21, axis_development=22,
        status="submitted",
    )  # fmt: skip
    EmployeeEvaluation.objects.filter(pk=evaluation.pk).update(template=template)
    evaluation.refresh_from_db()
    assert evaluation.total_score == 85
    assert not EvaluationScore.objects.filter(evaluation=evaluation).exists()

    client.force_login(vice)
    page = client.get(_url(teacher_user))
    rows = {key: value for key, _label, _max, value in page.context["axis_rows"]}
    assert rows == {
        "axis_professional": 20, "axis_commitment": 22, "axis_teamwork": 21, "axis_development": 22,
    }  # fmt: skip
    client.post(_url(teacher_user), {a.key: "0" for a in form.axes} | {"action": "submitted"})
    evaluation.refresh_from_db()
    assert (evaluation.total_score, evaluation.status) == (85, "submitted")

    with pytest.raises(EvaluationRejectedError, match="استمارة"):
        approve_evaluation(evaluation=evaluation, approver=principal_user)


# ── 5. تاريخُ الاستلام لا يسبق الاعتماد ─────────────────────────────────────────


@pytest.mark.django_db
def test_receipt_date_cannot_precede_the_approval(school, principal_user, teacher_user):
    """المادة 20: المهلةُ «من تاريخ علمه» بالتقرير — ولا يُعلم بتقريرٍ قبل اعتماده."""
    form = _seed(school)
    template = RoleEvaluationTemplate.objects.get(
        school=school, role_name="teacher", academic_year=YEAR
    )
    vice = _staff(school, "vice_academic")
    evaluation = EmployeeEvaluation.objects.create(
        school=school, employee=teacher_user, evaluator=vice, academic_year=YEAR, period="S2",
        template=template, status="submitted",
    )  # fmt: skip
    # درجاتٌ على مفاتيح محاور الاستمارة — وإلّا رُفض الاعتماد (جولة الإصلاح 3).
    EvaluationScore.objects.create(
        evaluation=evaluation,
        evaluator=vice,
        weight=100,
        custom_axes={axis.key: axis.weight for axis in form.axes},
    )
    approve_evaluation(evaluation=evaluation, approver=principal_user)
    evaluation.refresh_from_db()

    today = timezone.localdate()
    with pytest.raises(EvaluationRejectedError, match="اعتماد"):
        record_receipt_on_refusal(
            evaluation=evaluation, recorder=principal_user, received_on=today - timedelta(days=30)
        )
    record_receipt_on_refusal(evaluation=evaluation, recorder=principal_user, received_on=today)
    evaluation.refresh_from_db()
    assert evaluation.received_on == today
