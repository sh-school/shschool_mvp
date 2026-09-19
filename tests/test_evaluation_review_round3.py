"""[LEGAL] عيوبُ المراجعة العدائيّة لموجة تقييم الأداء (جولة الإصلاح 3، 2026-09-16).

كلُّ اختبارٍ هنا سقط على الفرع قبل إصلاحه. والمراجع مقروءةٌ من صورة الصفحة:

  - «02- النظام الوظيفي لموظفي المدارس.pdf» (قرار مجلس الوزراء 32/2019): المادة 16 صفحة
    الملفّ 10 (المطبوعة 24) — «يضع الرئيس المباشر تقييم أداء الموظف ويعتمد من مدير
    المدرسة»؛ والمادتان 19 و20 صفحة الملفّ 12 (المطبوعة 26) — «أو لم يقم بتجديدها، بمستوى
    ضعيف»، و«يُعلن الموظف بنسخة من تقرير تقييم الأداء، ويجوز للموظف أن يتظلم منه».
  - «الدليل التنظيمي لسياسة إدارة سلوك الطلبة 2026.pdf» صفحة الملفّ 105 (المطبوعة 96):
    «ملاحظ الحافلة» و«المشرف الإداري (مسؤول الحافلات)».
  - «02- شؤون الموظفين/05- الوصف الوظيفي/ملاحظ طلبة.pdf» ص1 (مهامُّه تبدأ بمرافقة الطلاب في
    الباصات)، و«مشرف اداري.pdf» ص1 («الأشراف على أمن وسلامة الطلبة مستخدمي الحافلات
    المدرسية»، و«الباصات» فيما يُكلَّف به).
  - «05- سياسة الرخص المهنية للمعلمين و قادة المدارس.pdf» ص22–23.
"""

from __future__ import annotations

import inspect
from datetime import timedelta
from pathlib import Path

import pytest
from django.apps import apps as django_apps
from django.urls import reverse
from django.utils import timezone

from quality.appraisal_forms import forms_by_role, load_forms
from quality.evaluation_selectors import DEFAULT_AXES as _DEFAULT_AXES
from quality.evaluation_services import (
    AppraisalYearFacts,
    EvaluationRejectedError,
    approve_evaluation,
    save_evaluation,
)
from quality.models import (
    EmployeeEvaluation,
    EvaluationCycle,
    EvaluationScore,
    RoleEvaluationTemplate,
)
from tests.test_evaluation_review_round1 import (
    YEAR,
    _migration_0018_forward,
    _post_total,
    _seed,
    _staff,
    _url,
)

ROOT = Path(__file__).resolve().parent.parent


# ── 1. إقرارُ الموظّف يحفظ تعليقه ─────────────────────────────────────────────


@pytest.mark.django_db
def test_acknowledgement_keeps_the_employee_comment(client, school, principal_user, teacher_user):
    """المادة 20: «يُعلن الموظف بنسخة ... ويجوز للموظف أن يتظلم منه» — وتعليقُه يُحفظ."""
    evaluation = EmployeeEvaluation.objects.create(
        school=school, employee=teacher_user, evaluator=principal_user,
        academic_year=YEAR, period="S2", status="approved",
    )  # fmt: skip
    client.force_login(teacher_user)
    client.post(
        reverse("acknowledge_evaluation", kwargs={"eval_id": evaluation.pk}),
        {"comment": "أعترض على درجة المجال الثاني"},
    )
    evaluation.refresh_from_db()
    assert evaluation.status == "acknowledged"
    assert evaluation.employee_comment == "أعترض على درجة المجال الثاني"


# ── 2. لا يضع الموظّفُ تقريرَه عن نفسه ────────────────────────────────────────


@pytest.mark.django_db
def test_evaluator_cannot_place_their_own_report(client, school):
    """المادة 16: «يضع الرئيس المباشر تقييم أداء الموظف» — وليس الموظّفُ رئيسَ نفسه."""
    _seed(school)
    form = forms_by_role()["vice_academic"]
    vice = _staff(school, "vice_academic")
    client.force_login(vice)
    assert client.get(_url(vice)).status_code == 403
    assert client.post(_url(vice), _post_total(form, 100)).status_code == 403
    assert client.get(_url(vice, "S1")).status_code == 403
    assert not EmployeeEvaluation.objects.filter(employee=vice).exists()

    evaluation = EmployeeEvaluation(
        school=school, employee=vice, evaluator=vice, academic_year=YEAR, period="S1"
    )
    data = {key: "25" for key, _label, _max in _DEFAULT_AXES} | {"action": "submitted"}
    with pytest.raises(EvaluationRejectedError, match="المادة 16"):
        save_evaluation(evaluation=evaluation, evaluator=vice, axes=_DEFAULT_AXES, data=data)
    assert not EmployeeEvaluation.objects.filter(employee=vice).exists()


# ── 3. تقريرٌ سنويٌّ مربوطٌ بقالبٍ بلا درجاتِ واضعٍ لا يُعتمد ─────────────────────


@pytest.mark.django_db
def test_template_bound_annual_report_without_placed_scores_is_not_approved(
    school, principal_user, teacher_user
):
    """صفٌّ كتبه المسارُ القديم: قالبٌ مربوط، ومحاورُ صفر، ولا `EvaluationScore` — مجموعُه 0."""
    _seed(school)
    template = RoleEvaluationTemplate.objects.get(
        school=school, role_name="teacher", academic_year=YEAR
    )
    evaluation = EmployeeEvaluation.objects.create(
        school=school, employee=teacher_user, evaluator=_staff(school, "vice_academic"),
        academic_year=YEAR, period="S2", template=template, status="submitted",
    )  # fmt: skip
    assert evaluation.total_score == 0
    assert not EvaluationScore.objects.filter(evaluation=evaluation).exists()
    with pytest.raises(EvaluationRejectedError, match="استمارة"):
        approve_evaluation(evaluation=evaluation, approver=principal_user)
    evaluation.refresh_from_db()
    assert evaluation.status == "submitted"


# ── 4. مشرفُ الحافلة ومسؤولُ النقل: تكليفٌ على مسمّىً تثبته الوثائق ────────────


@pytest.mark.parametrize(
    ("role_name", "section", "category"),
    [
        # دليل السلوك ص105: «ملاحظ الحافلة»؛ وبطاقةُ «ملاحظ طلبة» مهامُّها الباصات.
        ("bus_supervisor", "2.3", "ملاحظ طلبة"),
        # دليل السلوك ص105: «المشرف الإداري (مسؤول الحافلات)»؛ وبطاقةُ «مشرف اداري» تذكر
        # الحافلات والباصات.
        ("transport_officer", "2.7", "مشرف إداري"),
    ],
)
def test_transport_roles_are_appraised_on_the_documented_category(role_name, section, category):
    form = forms_by_role()[role_name]
    assert form.section == section
    assert dict(form.assignments)[role_name] == category


def test_every_form_assignment_names_a_header_category():
    """التكليفُ على خانةٍ مطبوعةٍ في رأس الاستمارة نفسها (منسوخةٍ حرفيّاً في `roles`)."""
    assignments = [(f, c) for f in load_forms() for _role, c in f.assignments]
    assert assignments
    for form, category in assignments:
        assert category in dict(form.roles).values(), (form.code, category)


@pytest.mark.django_db
@pytest.mark.parametrize("role_name", ["bus_supervisor", "transport_officer"])
def test_transport_roles_get_an_annual_report(client, school, role_name):
    _seed(school)
    employee = _staff(school, role_name)
    client.force_login(_staff(school, "vice_admin"))
    assert client.get(_url(employee)).status_code == 200
    form = forms_by_role()[role_name]
    assert client.post(_url(employee), _post_total(form, 80)).status_code == 302
    evaluation = EmployeeEvaluation.objects.get(employee=employee, period="S2")
    assert (evaluation.total_score, evaluation.template.role_name) == (80, role_name)


# ── 5. المادة 19 كما نصُّها: «أو لم يقم بتجديدها» ────────────────────────────────


def test_article_19_flag_is_defined_by_the_text_not_by_an_application():
    source = inspect.getsource(AppraisalYearFacts)
    adr = (ROOT / "docs" / "adr" / "0002-unified-staff-appraisal.md").read_text(encoding="utf-8")
    assert "لم يقم بتجديدها" in source
    for text in (source, adr):
        assert "لم يتقدّم لتجديدها" not in text


# ── 6. نسبةُ إنجاز S2 وزرُّ التقييم لأدوارٍ بلا استمارة ─────────────────────────


@pytest.mark.django_db
def test_s2_cycle_completes_when_every_role_with_a_form_is_reported(
    client, school, principal_user, teacher_user
):
    """
    الأدوارُ بلا استمارةٍ لا يُفتح لها S2 حتى يقرّر المالك (ADR-0002 §6.6 بند 12)، فلا تدخل
    مقامَ النسبة ولا يُعرض لها زرٌّ يُفضي إلى 409.
    """
    form = _seed(school)
    nurse = _staff(school, "nurse", "الممرّض")
    vice_academic = _staff(school, "vice_academic", "النائب الأكاديمي")
    vice_admin = _staff(school, "vice_admin", "النائب الإداري")
    client.force_login(vice_academic)
    assert client.post(_url(teacher_user), _post_total(form, 80)).status_code == 302
    assert (
        client.post(_url(vice_admin), _post_total(forms_by_role()["vice_admin"], 80)).status_code
        == 302
    )
    client.force_login(vice_admin)
    vice_form = forms_by_role()["vice_academic"]
    assert client.post(_url(vice_academic), _post_total(vice_form, 80)).status_code == 302
    assert EmployeeEvaluation.objects.filter(period="S2", status="submitted").count() == 3

    cycle = EvaluationCycle.objects.create(
        school=school,
        academic_year=YEAR,
        period="S2",
        deadline=timezone.localdate() + timedelta(days=30),
    )
    assert cycle.completion_rate == 100

    client.force_login(principal_user)
    page = client.get(reverse("evaluation_dashboard") + f"?year={YEAR}").content.decode()
    page = page.replace("&amp;", "&")
    link = reverse("create_evaluation", kwargs={"employee_id": nurse.pk})
    assert f"{link}?period=S1" in page
    assert f"{link}?period=S2" not in page


def _adr_owner_item(number: int) -> str:
    adr = (ROOT / "docs" / "adr" / "0002-unified-staff-appraisal.md").read_text(encoding="utf-8")
    section = adr.split("### 6.6", 1)[1]
    start = section.index(f"\n{number}. **")
    end = section.index(f"\n{number + 1}. **", start)
    return " ".join(section[start:end].split())


def test_article_19_exempts_no_one_the_licence_policy_obliges_to_renew():
    """
    «05- سياسة الرخص المهنية للمعلمين و قادة المدارس.pdf» ص22 بند 4: من تقدّم لمستوىً أعلى ولم
    يُمنحه «لن يفقدوا رخصهم ... ويتعين عليهم تجديد رخصهم بنفس المستوى في نهاية السنة الخامسة» —
    إلزامٌ بالتجديد لا إعفاءٌ منه. وص23 بند 1 (نائبٌ تقدّم ولم يستوفِ «لن يفقد» رخصته) صامتٌ عن
    أثره في التقييم، فهو سؤالٌ للمالك لا مُقرَّر.
    """
    source = inspect.getsource(AppraisalYearFacts)
    assert "ولا يُعدّ هنا" not in source
    assert "ص22 بند 4 «لن يفقدوا رخصهم ... ويتعين عليهم" in source
    item = _adr_owner_item(4)
    assert "ولا يُعدّ من نصّت" not in item
    assert "ص23 بند 1" in item.split("ويبقى للمالك", 1)[1]


# ── 7. درجةُ الاستمارة: مفاتيحُ محاورها، لا وجودُ `EvaluationScore` ─────────────────

#: مفاتيحُ صفٍّ أُدخل من لوحة الإدارة قبل الموجة — ليست محاورَ أيّ استمارة.
_FOREIGN_KEYS = {"professional": 25, "commitment": 25, "teamwork": 20, "development": 20}


def _submitted_on_foreign_keys(school, employee, custom_axes=None):
    _seed(school)
    template = RoleEvaluationTemplate.objects.get(
        school=school, role_name="teacher", academic_year=YEAR
    )
    vice = _staff(school, "vice_academic")
    evaluation = EmployeeEvaluation.objects.create(
        school=school, employee=employee, evaluator=vice, academic_year=YEAR,
        period="S2", template=template, status="submitted",
    )  # fmt: skip
    EvaluationScore.objects.create(
        evaluation=evaluation,
        evaluator=vice,
        custom_axes=_FOREIGN_KEYS if custom_axes is None else custom_axes,
    )
    return evaluation


@pytest.mark.django_db
@pytest.mark.parametrize("custom_axes", [_FOREIGN_KEYS, {}], ids=["foreign-keys", "empty"])
def test_annual_report_scored_on_keys_outside_the_form_is_not_approved(
    school, principal_user, teacher_user, custom_axes
):
    """
    المادة 15: «وفقاً للنماذج المعتمدة من الوزير» — المجموعُ من محاور الاستمارة وحدها.
    و`{}` صفُّ لوحة الإدارة القديمة بالمحاور الأربعة الافتراضيّة (custom_axes فارغ).
    """
    evaluation = _submitted_on_foreign_keys(school, teacher_user, custom_axes)
    with pytest.raises(EvaluationRejectedError, match="استمارة"):
        approve_evaluation(evaluation=evaluation, approver=principal_user)
    evaluation.refresh_from_db()
    assert evaluation.status == "submitted"
    assert evaluation.rating == ""  # 90 من غير الاستمارة ليس «ممتاز» المادة 16


# ── 8. تقريرٌ سنويٌّ ليس على الاستمارة لا يحمل اسمَ مستوى المادة 16 ──────────────────


@pytest.mark.django_db
def test_annual_rows_off_the_form_get_no_article_16_level(
    client, school, principal_user, teacher_user
):
    """
    المادة 16 تسمّي مستوياتِ التقرير الذي يوضع «وفقاً للنماذج المعتمدة من الوزير» (المادة 15)؛
    والمستوى تترتّب عليه آثارُ المادتين 21 و22. فصفُّ S2 على المحاور الأربعة (قبل الموجة) أو على
    مفاتيحَ غريبة لا يأخذ اسمَه في الهجرة 0018 ولا في الحفظ، ولا يُعدّ في توزيع اللوحة. والمتابعةُ
    الداخليّة S1 تبقى على السُّلَّم الواحد (ADR-0002 §6.3).
    """
    foreign = _submitted_on_foreign_keys(school, teacher_user)
    other = _staff(school, "it_technician")
    common = {"school": school, "evaluator": principal_user, "academic_year": YEAR}
    legacy = EmployeeEvaluation.objects.create(
        employee=other, period="S2", status="approved", axis_professional=20,
        axis_commitment=20, axis_teamwork=11, axis_development=11, **common,
    )  # fmt: skip
    internal = EmployeeEvaluation.objects.create(
        employee=other, period="S1", status="approved", axis_professional=20,
        axis_commitment=20, axis_teamwork=11, axis_development=11, **common,
    )  # fmt: skip
    assert (legacy.total_score, legacy.rating) == (62, "")
    for row in (foreign, legacy):
        EmployeeEvaluation.objects.filter(pk=row.pk).update(rating="good")

    _migration_0018_forward()(django_apps, None)
    for row in (foreign, legacy, internal):
        row.refresh_from_db()
    assert (foreign.rating, legacy.rating, internal.rating) == ("", "", "acceptable")

    legacy.save()  # حفظٌ عامّ (لوحةُ الإدارة) لا يعيد إليه المستوى
    legacy.refresh_from_db()
    assert legacy.rating == ""

    EmployeeEvaluation.objects.filter(pk=legacy.pk).update(rating="acceptable")
    client.force_login(principal_user)
    dist = client.get(reverse("evaluation_dashboard") + f"?year={YEAR}").context["rating_dist"]
    assert sum(dist.values()) == 0
