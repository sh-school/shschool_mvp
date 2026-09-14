"""[LEGAL] من عليه جزاءٌ تأديبيٌّ لا يُحفظ له «ممتاز» ولا «جيد جداً».

المرجع: `AAdocs/ministry_data/2026_2027/06_attendance_performance_review.md` §2.1
(سطر 103–111)، والنصّ مكرّرٌ حرفيّاً في الاستمارات السبع:

    المادة (17): «لا يجوز تقييم أداء الموظفين من الفئات المبيّنة فيما يلي بمستوى
                  ممتاز: 1. الموظف الذي وقع عليه جزاء تأديبي بالخصم من راتبه أو
                  الوقف عن العمل لمدة تزيد عن خمسة أيام …»
    المادة (18): «… بمستوى ممتاز أو جيد جداً: 1. الموظف الذي وقع عليه جزاء تأديبي
                  بالخصم من راتبه أو الوقف عن العمل لمدة تزيد على عشرة أيام …»

سجلُّ الجزاءات (بند 2.1، `StaffDisciplinaryAction`) لم يُبنَ، فـ`has_active_sanction`
تُرجع False. وهذه الحرّاسُ تستبدلها بـTrue وتثبت أنّ الرفض **في مسار الحفظ الذي
يستعمله العرض** — لا في دالّةٍ معزولةٍ لا يستدعيها أحد. وحين يُبنى السجلُّ تبقى
كما هي.

وقرارُ الموجة (2026-09-14): أيُّ جزاءٍ نشطٍ يحجب الدرجتين معاً إلى أن يميّز
السجلُّ بين عتبة المادة 17 (ممتاز وحده) وعتبة المادة 18 (الاثنان).
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.urls import reverse

from quality import evaluation_services
from quality.appraisal_forms import forms_by_role
from quality.evaluation_services import EvaluationRejectedError, save_evaluation
from quality.evaluation_views import _DEFAULT_AXES
from quality.models import EmployeeEvaluation, EvaluationScore

YEAR = "2026-2027"


@pytest.fixture
def sanctioned(monkeypatch):
    monkeypatch.setattr(evaluation_services, "has_active_sanction", lambda staff, year: True)


def _evaluation(school, employee, evaluator):
    return EmployeeEvaluation.objects.create(
        school=school, employee=employee, evaluator=evaluator, academic_year=YEAR, period="S1"
    )


def _default_post(total_each, action="submitted"):
    data = {field: str(total_each) for field, _label, _max in _DEFAULT_AXES}
    data["action"] = action
    return data


# ── الخدمة ───────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_hook_returns_false_until_the_sanctions_register_exists(teacher_user):
    assert evaluation_services.has_active_sanction(teacher_user, YEAR) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("each", "rating"), [(25, "excellent"), (23, "excellent"), (20, "very_good")]
)
def test_sanctioned_staff_cannot_be_saved_excellent_or_very_good(
    school, principal_user, teacher_user, sanctioned, each, rating
):
    evaluation = _evaluation(school, teacher_user, principal_user)
    assert EmployeeEvaluation.rating_for(each * 4) == rating
    with pytest.raises(EvaluationRejectedError, match="المادتان 17 و18"):
        save_evaluation(
            evaluation=evaluation,
            evaluator=principal_user,
            axes=_DEFAULT_AXES,
            data=_default_post(each),
        )
    evaluation.refresh_from_db()
    assert (evaluation.total_score, evaluation.status, evaluation.axis_professional) == (
        0,
        "draft",
        0,
    )


@pytest.mark.django_db
def test_sanctioned_staff_can_still_be_saved_good(school, principal_user, teacher_user, sanctioned):
    evaluation = _evaluation(school, teacher_user, principal_user)
    save_evaluation(
        evaluation=evaluation, evaluator=principal_user, axes=_DEFAULT_AXES, data=_default_post(17)
    )
    evaluation.refresh_from_db()
    assert (evaluation.total_score, evaluation.rating) == (68, "good")


@pytest.mark.django_db
def test_without_sanction_excellent_is_saved(school, principal_user, teacher_user):
    evaluation = _evaluation(school, teacher_user, principal_user)
    save_evaluation(
        evaluation=evaluation, evaluator=principal_user, axes=_DEFAULT_AXES, data=_default_post(24)
    )
    evaluation.refresh_from_db()
    assert (evaluation.total_score, evaluation.rating, evaluation.status) == (
        96,
        "excellent",
        "submitted",
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"axis_professional": "26"}, "بين 0 و25"),
        ({"axis_commitment": "x"}, "عددٌ صحيح"),
        ({"action": "approved"}, "حالةُ"),
    ],
)
def test_invalid_input_is_rejected_before_any_write(
    school, principal_user, teacher_user, override, message
):
    evaluation = _evaluation(school, teacher_user, principal_user)
    with pytest.raises(EvaluationRejectedError, match=message):
        save_evaluation(
            evaluation=evaluation,
            evaluator=principal_user,
            axes=_DEFAULT_AXES,
            data={**_default_post(10), **override},
        )


# ── العرض: المسارُ الذي يستعمله المقيِّم فعلاً ─────────────────────────


def _seed_teacher_template(school):
    call_command(
        "seed_quality_templates",
        "--apply",
        "--school",
        school.code,
        "--year",
        YEAR,
        stdout=StringIO(),
    )
    return forms_by_role()["teacher"]


def _post_form(client, employee, data):
    url = (
        reverse("create_evaluation", kwargs={"employee_id": employee.pk})
        + f"?year={YEAR}&period=S1"
    )
    return url, client.post(url, data)


def _ministry_post(form, share, action="submitted"):
    """درجةُ كلّ مجالٍ نسبةٌ من وزنه — فالمجموعُ ≈ share × 100."""
    data = {a.key: str(round(a.weight * share)) for a in form.axes}
    data["action"] = action
    return data


@pytest.mark.django_db
def test_view_rejects_excellent_for_sanctioned_teacher(
    client, school, principal_user, teacher_user, sanctioned
):
    form = _seed_teacher_template(school)
    client.force_login(principal_user)
    url, response = _post_form(client, teacher_user, _ministry_post(form, 1.0))

    assert response.status_code == 302
    assert response.url == url  # يعود إلى النموذج لا إلى اللوحة
    evaluation = EmployeeEvaluation.objects.get(
        school=school, employee=teacher_user, academic_year=YEAR
    )
    assert (evaluation.total_score, evaluation.status) == (0, "draft")
    assert not EvaluationScore.objects.filter(evaluation=evaluation).exists()


@pytest.mark.django_db
def test_view_saves_ministry_axes_instead_of_dropping_them(
    client, school, principal_user, teacher_user
):
    """كان الحفظُ يقرأ المحاورَ الأربعةَ الافتراضيّة وحدها، فتقييمٌ على قالب الوزارة يُحفظ صفراً."""
    form = _seed_teacher_template(school)
    client.force_login(principal_user)
    data = _ministry_post(form, 1.0)
    data[form.axes[0].key] = str(form.axes[0].weight - 5)  # 95
    _url, response = _post_form(client, teacher_user, data)

    assert response.status_code == 302
    evaluation = EmployeeEvaluation.objects.get(
        school=school, employee=teacher_user, academic_year=YEAR
    )
    assert (evaluation.total_score, evaluation.rating, evaluation.status) == (
        95,
        "excellent",
        "submitted",
    )
    score = EvaluationScore.objects.get(evaluation=evaluation, evaluator=principal_user)
    assert score.custom_axes[form.axes[0].key] == form.axes[0].weight - 5
    assert set(score.custom_axes) == {a.key for a in form.axes}

    page = client.get(
        reverse("create_evaluation", kwargs={"employee_id": teacher_user.pk})
        + f"?year={YEAR}&period=S1"
    )
    rows = {key: value for key, _label, _max, value in page.context["axis_rows"]}
    assert rows == score.custom_axes
