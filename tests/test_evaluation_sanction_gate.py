"""[LEGAL] قيودُ المستوى في المواد 17 و18 و19 — بعتباتها، وفي مسار الحفظ الذي يستعمله العرض.

المرجع: النظام الوظيفي لموظفي المدارس (قرار مجلس الوزراء 32/2019)،
`data/2026-2027/02- شؤون الموظفين/02- النظام الوظيفي لموظفي المدارس.pdf`
(صفحتا الملفّ 11 و12، المطبوعتان 25 و26)، ونقلُه في `02_staff_affairs.md:208-210`:

    المادة (17) لا «ممتاز»: جزاءٌ بالخصم أو الوقف «لمدة تزيد على خمسة أيام»، أو جزاءاتٌ
                «تجاوز مجموعها … لمدة تزيد على عشرة أيام»، أو «أي جزاء آخر أشد»؛
                انقطاعٌ بلا عذرٍ «مدة تزيد على خمسة أيام»؛ تدريبٌ «لم يجتزه بنجاح».
    المادة (18) لا «ممتاز» ولا «جيد جداً»: جزاءٌ «لمدة تزيد على عشرة أيام»، أو جزاءاتٌ
                «يجاوز مجموعها … خمسة عشر يوماً»، أو «أي جزاء آخر أشد»؛ انقطاعٌ «مدة تزيد
                على عشرة أيام»؛ تدريبٌ «تخلف عنه دون عذر مقبول».
    المادة (19) «ضعيف» لمن لم يجدّد رخصتَه المهنيّة.

وكان المرجعُ المستخرج (`06_attendance_performance_review.md:110`) يقول «خمسة وعشرين»
لمجموع المادة 18 — خطأَ نسخٍ صُحّح من القرار ومن مربّع المادة في الاستمارات الخمس.

والسجلّاتُ (الجزاءات 2.1، التدريب، الرخص) لم تُبنَ، فـ`year_facts` تُرجع None. وهذه
الحرّاسُ تحقن الوقائع وتثبت الرفضَ في `save_evaluation` نفسِه — لا في دالّةٍ معزولة.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.urls import reverse

from quality import evaluation_services
from quality.appraisal_forms import forms_by_role
from quality.evaluation_selectors import DEFAULT_AXES as _DEFAULT_AXES
from quality.evaluation_services import (
    AppraisalYearFacts,
    EvaluationRejectedError,
    ratings_barred_by,
    save_evaluation,
)
from quality.models import EmployeeEvaluation, EvaluationScore, RoleEvaluationTemplate

YEAR = "2026-2027"
NONE: frozenset[str] = frozenset()
EXCELLENT = frozenset({"excellent"})
TOP_TWO = frozenset({"excellent", "very_good"})
ALL_BUT_WEAK = frozenset({"excellent", "very_good", "good", "acceptable"})


def _inject(monkeypatch, facts):
    monkeypatch.setattr(evaluation_services, "year_facts", lambda staff, year: facts)


def _evaluation(school, employee, evaluator, period="S2"):
    """
    كما يربطه العرضُ قبل الحفظ (`create_evaluation`): التقريرُ السنويّ على قالب دوره إن بُذر.
    وبلا الربط لا تكون درجاتُه درجاتِ استمارة (`has_form_scores`) فلا مستوى له.
    """
    template = None
    if period == EmployeeEvaluation.MINISTRY_PERIOD:
        template = RoleEvaluationTemplate.objects.filter(
            school=school, role_name="teacher", academic_year=YEAR
        ).first()
    return EmployeeEvaluation.objects.create(
        school=school, employee=employee, evaluator=evaluator, academic_year=YEAR,
        period=period, template=template,
    )  # fmt: skip


def _default_post(total_each, action="submitted"):
    data = {field: str(total_each) for field, _label, _max in _DEFAULT_AXES}
    data["action"] = action
    return data


def _teacher_axes(school):
    """
    محاورُ استمارة المعلم مبذورةً. التقريرُ السنويّ (S2) لا يُحفظ على المحاور الافتراضيّة
    (جولة الإصلاح 1: «وفقاً للنماذج المعتمدة من الوزير»، 02_staff_affairs.md:199).
    """
    _seed_teacher_template(school)
    return [(a.key, a.label, a.weight) for a in forms_by_role()["teacher"].axes]


def _form_post(axes, total, action="submitted"):
    """درجاتُ المحاور مجموعُها `total` — تُنقص من المحاور بالترتيب."""
    missing = 100 - total
    data = {}
    for key, _label, weight in axes:
        cut = min(missing, weight)
        data[key] = str(weight - cut)
        missing -= cut
    data["action"] = action
    return data


# ── القاعدة: عتباتُ المواد بلا قاعدة بيانات ──────────────────────────────


@pytest.mark.parametrize(
    ("facts", "barred"),
    [
        # الجزاءُ المفرد — المادة 17 فوق 5، والمادة 18 فوق 10.
        (AppraisalYearFacts(longest_sanction_days=5, sanction_days_total=5), NONE),
        (AppraisalYearFacts(longest_sanction_days=6, sanction_days_total=6), EXCELLENT),
        (AppraisalYearFacts(longest_sanction_days=10, sanction_days_total=10), EXCELLENT),
        (AppraisalYearFacts(longest_sanction_days=11, sanction_days_total=11), TOP_TWO),
        # المجموع — المادة 17 فوق 10، والمادة 18 «يجاوز … خمسة عشر يوماً».
        (AppraisalYearFacts(longest_sanction_days=3, sanction_days_total=10), NONE),
        (AppraisalYearFacts(longest_sanction_days=3, sanction_days_total=11), EXCELLENT),
        (AppraisalYearFacts(longest_sanction_days=3, sanction_days_total=15), EXCELLENT),
        (AppraisalYearFacts(longest_sanction_days=3, sanction_days_total=16), TOP_TWO),
        (AppraisalYearFacts(longest_sanction_days=3, sanction_days_total=25), TOP_TWO),
        # «أي جزاء آخر أشد».
        (AppraisalYearFacts(harsher_sanction=True), TOP_TWO),
        # الانقطاع بلا عذر — فوق 5 وفوق 10.
        (AppraisalYearFacts(unexcused_absence_days=5), NONE),
        (AppraisalYearFacts(unexcused_absence_days=6), EXCELLENT),
        (AppraisalYearFacts(unexcused_absence_days=10), EXCELLENT),
        (AppraisalYearFacts(unexcused_absence_days=11), TOP_TWO),
        # التدريب — لم يجتزه (17)، تخلّف عنه بلا عذر (18).
        (AppraisalYearFacts(training_not_passed=True), EXCELLENT),
        (AppraisalYearFacts(training_skipped_without_excuse=True), TOP_TWO),
        # المادة 19 — «ضعيف».
        (AppraisalYearFacts(license_expired_not_renewed=True), ALL_BUT_WEAK),
        # سياسة الرخص ص10 — معلّمٌ لم تُمنح له الرخصة واستمرّ أداؤه متدنّياً.
        (AppraisalYearFacts(teacher_license_denied_persistent_low=True), TOP_TWO),
    ],
)
def test_articles_17_18_19_thresholds(facts, barred):
    assert ratings_barred_by(facts) == barred


def test_warning_and_reprimand_bar_nothing():
    """الإنذار واللوم ليسا خصماً ولا وقفاً ولا تذكرهما المادتان — فلا حقلَ لهما ولا منع."""
    assert ratings_barred_by(AppraisalYearFacts()) == NONE


@pytest.mark.django_db
def test_hook_returns_nothing_until_the_registers_exist(teacher_user):
    assert evaluation_services.year_facts(teacher_user, YEAR) is None
    assert evaluation_services.barred_ratings(teacher_user, YEAR) == NONE


# ── الخدمة ───────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("facts", "total", "article"),
    [
        (AppraisalYearFacts(longest_sanction_days=6, sanction_days_total=6), 96, "المادة 17"),
        (AppraisalYearFacts(longest_sanction_days=11, sanction_days_total=11), 80, "المادة 18"),
        (AppraisalYearFacts(unexcused_absence_days=11), 80, "المادة 18"),
        (AppraisalYearFacts(license_expired_not_renewed=True), 52, "المادة 19"),
    ],
)
def test_barred_rating_is_rejected_before_any_write(
    monkeypatch, school, principal_user, teacher_user, facts, total, article
):
    _inject(monkeypatch, facts)
    axes = _teacher_axes(school)
    evaluation = _evaluation(school, teacher_user, principal_user)
    with pytest.raises(EvaluationRejectedError, match=article):
        save_evaluation(
            evaluation=evaluation,
            evaluator=principal_user,
            axes=axes,
            data=_form_post(axes, total),
        )
    evaluation.refresh_from_db()
    assert (evaluation.total_score, evaluation.status, evaluation.axis_professional) == (
        0,
        "draft",
        0,
    )
    assert not EvaluationScore.objects.filter(evaluation=evaluation).exists()


@pytest.mark.django_db
def test_article_17_leaves_very_good_open(monkeypatch, school, principal_user, teacher_user):
    """جزاءُ ستّة أيام يحجب «ممتاز» وحده — فالثمانون «جيد جداً» تُحفظ."""
    _inject(monkeypatch, AppraisalYearFacts(longest_sanction_days=6, sanction_days_total=6))
    axes = _teacher_axes(school)
    evaluation = _evaluation(school, teacher_user, principal_user)
    save_evaluation(
        evaluation=evaluation, evaluator=principal_user, axes=axes, data=_form_post(axes, 80)
    )
    evaluation.refresh_from_db()
    assert (evaluation.total_score, evaluation.rating) == (80, "very_good")


@pytest.mark.django_db
def test_article_18_leaves_good_open(monkeypatch, school, principal_user, teacher_user):
    _inject(monkeypatch, AppraisalYearFacts(harsher_sanction=True))
    axes = _teacher_axes(school)
    evaluation = _evaluation(school, teacher_user, principal_user)
    save_evaluation(
        evaluation=evaluation, evaluator=principal_user, axes=axes, data=_form_post(axes, 68)
    )
    evaluation.refresh_from_db()
    assert (evaluation.total_score, evaluation.rating) == (68, "good")


@pytest.mark.django_db
def test_internal_s1_follow_up_is_not_a_ministry_report(
    monkeypatch, school, principal_user, teacher_user
):
    """المواد تقيّد «تقرير تقييم الأداء» السنويّ؛ والمتابعةُ الداخليّة S1 ليست إيّاه."""
    _inject(monkeypatch, AppraisalYearFacts(harsher_sanction=True))
    evaluation = _evaluation(school, teacher_user, principal_user, period="S1")
    save_evaluation(
        evaluation=evaluation, evaluator=principal_user, axes=_DEFAULT_AXES, data=_default_post(24)
    )
    evaluation.refresh_from_db()
    assert evaluation.rating == "excellent"


@pytest.mark.django_db
def test_without_facts_excellent_is_saved(school, principal_user, teacher_user):
    axes = _teacher_axes(school)
    evaluation = _evaluation(school, teacher_user, principal_user)
    save_evaluation(
        evaluation=evaluation, evaluator=principal_user, axes=axes, data=_form_post(axes, 96)
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
        (lambda key, weight: {key: str(weight + 1)}, "بين 0 و{weight}"),
        (lambda key, weight: {key: "x"}, "عددٌ صحيح"),
        (lambda key, weight: {"action": "approved"}, "حالةُ"),
    ],
)
def test_invalid_input_is_rejected_before_any_write(
    school, principal_user, teacher_user, override, message
):
    axes = _teacher_axes(school)
    key, _label, weight = axes[0]
    evaluation = _evaluation(school, teacher_user, principal_user)
    with pytest.raises(EvaluationRejectedError, match=message.format(weight=weight)):
        save_evaluation(
            evaluation=evaluation,
            evaluator=principal_user,
            axes=axes,
            data={**_form_post(axes, 40), **override(key, weight)},
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


def _url(employee, period="S2"):
    return (
        reverse("create_evaluation", kwargs={"employee_id": employee.pk})
        + f"?year={YEAR}&period={period}"
    )


def _ministry_post(form, share, action="submitted"):
    """درجةُ كلّ مجالٍ نسبةٌ من وزنه — فالمجموعُ ≈ share × 100."""
    data = {a.key: str(round(a.weight * share)) for a in form.axes}
    data["action"] = action
    return data


@pytest.mark.django_db
def test_view_rejects_excellent_for_sanctioned_teacher(
    monkeypatch, client, school, principal_user, teacher_user
):
    _inject(monkeypatch, AppraisalYearFacts(longest_sanction_days=11, sanction_days_total=11))
    form = _seed_teacher_template(school)
    client.force_login(principal_user)
    url = _url(teacher_user)
    response = client.post(url, _ministry_post(form, 1.0))

    assert response.status_code == 302
    assert response.url == url  # يعود إلى النموذج لا إلى اللوحة
    # والرفضُ لا يترك سجلّاً: الإنشاءُ والحفظُ في معاملةٍ واحدة.
    assert not EmployeeEvaluation.objects.filter(school=school, employee=teacher_user).exists()
    assert not EvaluationScore.objects.exists()


@pytest.mark.django_db
def test_view_saves_ministry_axes_instead_of_dropping_them(
    client, school, principal_user, teacher_user
):
    """كان الحفظُ يقرأ المحاورَ الأربعةَ الافتراضيّة وحدها، فتقييمٌ على قالب الوزارة يُحفظ صفراً."""
    form = _seed_teacher_template(school)
    client.force_login(principal_user)
    data = _ministry_post(form, 1.0)
    data[form.axes[0].key] = str(form.axes[0].weight - 5)  # 95
    response = client.post(_url(teacher_user), data)

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

    page = client.get(_url(teacher_user))
    rows = {key: value for key, _label, _max, value in page.context["axis_rows"]}
    assert rows == score.custom_axes
