"""[LEGAL] قوالبُ تقييم الأداء هي الاستماراتُ الوزاريّةُ السبع — حرفاً ورقماً.

المرجع: `AAdocs/ministry_data/2026_2027/06_attendance_performance_review.md`
(الملفّاتُ المصدر: `data/2026-2027/06- تقييم أداء الموظفين/*.pdf`)

    §2.3  استمارة تقييم الفئة العمالية        20 عنصراً مسطَّحاً      سطر 127–157
    §2.4  استمارة تقييم المعلم                 7 مجالات               سطر 163–207
    §2.5  استمارة تقييم النائب الإداري         6 مجالات               سطر 215–240
    §2.6  استمارة تقييم النائب الأكاديمي       5 مجالات               سطر 254–281
    §2.7  استمارة تقييم الوظائف الإدارية 1     6 مجالات               سطر 289–314
    §2.8  استمارة تقييم الوظائف الإدارية 2     8 مجالات               سطر 320–345
    §2.9  استمارة تقييم الوظائف الإدارية 3     6 مجالات               سطر 351–376

والملخّصُ المقارن في §3 (سطر 384–392) مصدرٌ ثانٍ للأوزان: الاختبارُ يقرأ الجداولَ
التفصيليّة ويقارنها بملفّ البيانات، ويقارن الاثنين بأوزان الملخّص المنسوخة هنا
يدويّاً — فخطأُ محلِّلٍ واحدٍ لا يمرّ.

وكانت الجولةُ الأولى تبذر هذه الأوزانَ صحيحةً بأسماء أدوارٍ لا وجودَ لها
(`worker`، `admin_role_1`…) فلا تقرؤها شاشةُ التقييم، التي تطلب القالبَ بـ`Role.name`
للموظّف. ولهذا يُختبر هنا البذرُ من طرف القراءة لا من طرف الكتابة.
"""

from __future__ import annotations

import re
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command

from core.models import Role
from quality.appraisal_forms import forms_by_role, load_forms
from quality.evaluation_views import _get_axes_for_employee
from quality.models import (
    _EVALUABLE_ROLES,
    EmployeeEvaluation,
    EvaluationAxis,
    RoleEvaluationTemplate,
)

REFERENCE = Path("AAdocs/ministry_data/2026_2027/06_attendance_performance_review.md")
YEAR = "2026-2027"

#: §3 «ملخص مقارن سريع» — منسوخٌ يدويّاً، والفئةُ العمالية من §2.3 مباشرةً.
SUMMARY_WEIGHTS = {
    "2.3": [8, 4, 5, 4, 4, 4, 8, 4, 5, 6, 4, 4, 4, 6, 4, 4, 5, 6, 5, 6],
    "2.4": [15, 25, 10, 15, 10, 10, 15],
    "2.5": [10, 20, 20, 25, 10, 15],
    "2.6": [20, 35, 25, 10, 10],
    "2.7": [12, 23, 20, 20, 10, 15],
    "2.8": [10, 20, 10, 25, 10, 10, 10, 5],
    "2.9": [10, 22, 24, 14, 10, 20],
}


def _reference_section(section: str) -> list[str]:
    lines = REFERENCE.read_text(encoding="utf-8").split("\n")
    start = next(i for i, line in enumerate(lines) if line.startswith(f"### {section} "))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith(("### ", "## ")))
    return lines[start:end]


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _reference_axes(section: str) -> list[tuple[str, int, list[tuple[str, str, int]]]]:
    """(اسم المجال، وزنه، [(رمز المؤشّر، نصّه، درجته)]) كما في جدول القسم."""
    rows = [
        _cells(line)
        for line in _reference_section(section)
        if line.startswith("|") and not line.startswith("|---")
    ][1:]
    axes: list[tuple[str, int, list[tuple[str, str, int]]]] = []
    for c in rows:
        if "المجموع" in "".join(c):
            continue
        if section == "2.3":
            axes.append((c[1], int(c[2]), []))
        elif c[0]:
            name = re.sub(r"^\d+-\s*", "", c[0].replace("**", "").strip())
            axes.append((name, int(c[1].rstrip("%")), [(c[2], c[3], int(c[4]))]))
        else:
            axes[-1][2].append((c[2], c[3], int(c[4])))
    return axes


def _reference_categories(section: str) -> list[str]:
    line = next(x for x in _reference_section(section) if x.startswith("**الفئ"))
    text = re.sub(r"\s*\([^)]*\)", "", line.split(":**", 1)[1].strip().rstrip("."))
    return [c.strip() for c in text.split("،")]


FORMS = {f.section: f for f in load_forms()}


def test_seven_forms_in_reference_order():
    assert list(FORMS) == ["2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9"]


@pytest.mark.parametrize("section", sorted(SUMMARY_WEIGHTS))
def test_axes_match_reference_verbatim(section):
    """اسمُ كلّ مجالٍ ووزنُه ومؤشّراتُه = جدولُ القسم في المرجع، خانةً بخانة."""
    form = FORMS[section]
    expected = _reference_axes(section)
    actual = [
        (a.label, a.weight, [(i.code, i.label, i.score) for i in a.indicators]) for a in form.axes
    ]
    assert actual == expected
    assert form.title == _reference_section(section)[0][len(f"### {section} ") :].strip()


@pytest.mark.parametrize("section", sorted(SUMMARY_WEIGHTS))
def test_weights_sum_to_100_and_match_summary(section):
    form = FORMS[section]
    assert [a.weight for a in form.axes] == SUMMARY_WEIGHTS[section]
    assert len(form.axes) == len(SUMMARY_WEIGHTS[section])
    assert form.total_weight == 100


@pytest.mark.parametrize("section", ["2.4", "2.5", "2.6", "2.7", "2.8", "2.9"])
def test_indicators_sum_to_domain_weight(section):
    """مجموعُ مؤشّرات كلّ مجالٍ = وزنُه، في الاستمارات السّت ذوات المؤشّرات (2.3 مسطّحةٌ بلا مؤشّرات).

    واستمارةُ المعلّم منها: كان المرجعُ يحمل خمسَ درجاتٍ منسوخةً خطأً (2.5=4، 4.2=4،
    5.4=1، 5.5=1، 6.2=2) ويسمّي ما نتج عنها «تعارضاً مطبوعاً في نموذج الوزارة»، وكان
    اختبارٌ هنا يُلزم بحفظه. والمطبوعُ 3 و2 و2 و2 و3 — «استمارة تقييم المعلم والدليل
    التفسيري.pdf» ص1–2، ومجموعُ بنود كلّ مؤشّرٍ في الدليل ص3–6 يساوي درجتَه — فصُحّح
    المرجعُ نفسُه (06_attendance_performance_review.md §2.4، 2026-09-15) وصار كلُّ مجالٍ
    يطابق وزنه.
    """
    for axis in FORMS[section].axes:
        assert sum(i.score for i in axis.indicators) == axis.weight, axis.label


@pytest.mark.parametrize("section", sorted(SUMMARY_WEIGHTS))
def test_role_categories_are_quoted_from_form_header(section):
    """كلُّ خانةِ فئةٍ في رأس الاستمارة: إمّا دورٌ مربوطٌ بنصّها، وإمّا مذكورةٌ بلا دور."""
    form = FORMS[section]
    quoted = [text for _role, text in form.roles] + list(form.unmapped_categories)
    assert sorted(quoted) == sorted(_reference_categories(section))


def test_every_mapped_role_exists_is_evaluable_and_unique():
    known = {name for name, _label in Role.ROLES}
    mapping = forms_by_role()  # يرفع ValueError إن تكرّر دور
    assert set(mapping) <= known
    assert set(mapping) <= _EVALUABLE_ROLES, set(mapping) - _EVALUABLE_ROLES
    assert len(mapping) == 21


def test_axis_keys_unique_per_form():
    for form in load_forms():
        keys = [a.key for a in form.axes]
        assert len(keys) == len(set(keys)), form.code


# ── البذر ────────────────────────────────────────────────────────────


def _seed(school, *flags):
    out = StringIO()
    call_command(
        "seed_quality_templates", "--school", school.code, "--year", YEAR, *flags, stdout=out
    )
    return out.getvalue()


def _counts(school):
    return (
        RoleEvaluationTemplate.objects.filter(school=school).count(),
        EvaluationAxis.objects.filter(template__school=school).count(),
    )


@pytest.mark.django_db
def test_dry_run_writes_nothing(school):
    output = _seed(school)
    assert _counts(school) == (0, 0)
    assert "[جديد] teacher" in output
    assert "لم يُكتب شيء" in output


@pytest.mark.django_db
def test_apply_is_idempotent(school):
    _seed(school, "--apply")
    first = _counts(school)
    # 21 دوراً؛ ومحاورُها: 4×20 + 7 + 6 + 5 + 5×6 + 4×8 + 5×6 = 190
    assert first == (21, 190)
    output = _seed(school, "--apply")
    assert _counts(school) == first
    assert "'created': 0, 'updated': 0, 'same': 21" in output


@pytest.mark.django_db
def test_dry_run_shows_drift_and_apply_repairs_it(school):
    _seed(school, "--apply")
    axis = EvaluationAxis.objects.get(
        template__school=school, template__role_name="teacher", key="assessment"
    )
    axis.weight = 20
    axis.save()
    EvaluationAxis.objects.create(template=axis.template, key="legacy", label="قديم", weight=5)

    output = _seed(school)
    assert "[يختلف] teacher" in output
    assert "~ assessment: الوزن 20 ← 15" in output
    assert "- legacy" in output
    axis.refresh_from_db()
    assert axis.weight == 20  # العرضُ لم يكتب

    _seed(school, "--apply")
    template = RoleEvaluationTemplate.objects.get(
        school=school, role_name="teacher", academic_year=YEAR
    )
    assert template.total_weight == 100
    assert not template.axes.filter(key="legacy").exists()


@pytest.mark.django_db
def test_template_with_evaluations_is_never_rewritten(school, principal_user, teacher_user):
    _seed(school, "--apply")
    template = RoleEvaluationTemplate.objects.get(
        school=school, role_name="teacher", academic_year=YEAR
    )
    EmployeeEvaluation.objects.create(
        school=school,
        employee=teacher_user,
        evaluator=principal_user,
        template=template,
        academic_year=YEAR,
        period="S1",
    )
    template.axes.filter(key="assessment").update(weight=20)

    output = _seed(school, "--apply")
    assert "مقفل" in output
    assert template.axes.get(key="assessment").weight == 20


@pytest.mark.django_db
def test_orphan_templates_from_first_round_are_reported_and_pruned(school):
    """قوالبُ الجولة الأولى بأسماءٍ ليست أدواراً: تُعرض يتيمة، وتُحذف بطلبٍ صريح."""
    RoleEvaluationTemplate.objects.create(
        school=school, role_name="admin_role_1", academic_year=YEAR
    )
    assert "[يتيم] admin_role_1" in _seed(school)
    _seed(school, "--apply")
    assert RoleEvaluationTemplate.objects.filter(role_name="admin_role_1").exists()
    _seed(school, "--apply", "--prune-orphans")
    assert not RoleEvaluationTemplate.objects.filter(role_name="admin_role_1").exists()


@pytest.mark.django_db
def test_evaluation_screen_reads_the_seeded_axes(school, teacher_user, it_technician_user):
    """طرفُ القراءة: ما يبذره الأمرُ هو ما يعرضه نموذجُ التقييم لهذا الدور."""
    _seed(school, "--apply")
    for user, section in ((teacher_user, "2.4"), (it_technician_user, "2.8")):
        axes, template = _get_axes_for_employee(school, user, YEAR)
        assert template is not None
        assert axes == [(a.key, a.label, a.weight) for a in FORMS[section].axes]


# ── البذرُ لا يمسّ تقييماً محفوظاً ─────────────────────────────────────
# مراجعة 2026-09-15: القفلُ كان يعدّ التقييماتِ المربوطةَ بالقالب وحدها. فتقييمٌ حُفظ على
# المحاور الافتراضيّة (template=None)، أو على قالب دورٍ سابق، كان يُربط عند مجرّد فتحه بعد
# البذر بالقالب الجديد فتُعرض محاورُه صفراً — حتى المعتمَد — ثمّ يمحو الحفظُ درجاتِه.


def _form_page(client, user, period="S2"):
    from django.urls import reverse

    return client.get(
        reverse("create_evaluation", kwargs={"employee_id": user.pk})
        + f"?year={YEAR}&period={period}"
    )


def _default_axes_evaluation(school, employee, evaluator, **extra):
    return EmployeeEvaluation.objects.create(
        school=school,
        employee=employee,
        evaluator=evaluator,
        academic_year=YEAR,
        period="S2",
        axis_professional=22,
        axis_commitment=22,
        axis_teamwork=22,
        axis_development=22,
        **extra,
    )


@pytest.mark.django_db
def test_seeding_counts_and_spares_evaluations_saved_on_default_axes(
    client, school, principal_user, teacher_user
):
    evaluation = _default_axes_evaluation(school, teacher_user, principal_user, status="approved")
    assert (evaluation.template_id, evaluation.total_score) == (None, 88)

    output = _seed(school)
    assert "خارج القالب: 1" in output
    _seed(school, "--apply")

    client.force_login(principal_user)
    page = _form_page(client, teacher_user)
    rows = {key: value for key, _label, _max, value in page.context["axis_rows"]}
    assert rows == {
        "axis_professional": 22,
        "axis_commitment": 22,
        "axis_teamwork": 22,
        "axis_development": 22,
    }
    evaluation.refresh_from_db()
    assert (evaluation.template_id, evaluation.total_score, evaluation.status) == (
        None,
        88,
        "approved",
    )


@pytest.mark.django_db
def test_evaluation_keeps_its_template_after_the_employee_changes_role(
    client, school, principal_user, teacher_user
):
    from quality.evaluation_services import save_evaluation
    from tests.conftest import RoleFactory

    _seed(school, "--apply")
    teacher_template = RoleEvaluationTemplate.objects.get(
        school=school, role_name="teacher", academic_year=YEAR
    )
    evaluation = EmployeeEvaluation.objects.create(
        school=school,
        employee=teacher_user,
        evaluator=principal_user,
        academic_year=YEAR,
        period="S2",
        template=teacher_template,
    )
    teacher_axes = [(a.key, a.label, a.weight) for a in FORMS["2.4"].axes]
    data = {key: str(weight) for key, _l, weight in teacher_axes} | {"action": "draft"}
    save_evaluation(evaluation=evaluation, evaluator=principal_user, axes=teacher_axes, data=data)

    membership = teacher_user.memberships.get(school=school)
    membership.role = RoleFactory(school=school, name="it_technician")
    membership.save()

    client.force_login(principal_user)
    page = _form_page(client, teacher_user)
    assert [row[0] for row in page.context["axis_rows"]] == [k for k, _l, _w in teacher_axes]
    assert all(row[3] == row[2] for row in page.context["axis_rows"])
    evaluation.refresh_from_db()
    assert (evaluation.template_id, evaluation.total_score) == (teacher_template.pk, 100)


@pytest.mark.django_db
def test_blank_draft_is_still_moved_to_the_role_template(
    client, school, principal_user, teacher_user
):
    EmployeeEvaluation.objects.create(
        school=school,
        employee=teacher_user,
        evaluator=principal_user,
        academic_year=YEAR,
        period="S2",
    )
    _seed(school, "--apply")
    client.force_login(principal_user)
    page = _form_page(client, teacher_user)
    assert [row[0] for row in page.context["axis_rows"]] == [a.key for a in FORMS["2.4"].axes]


@pytest.mark.django_db
def test_lock_is_rechecked_inside_the_write(school, principal_user, teacher_user):
    """تقييمٌ رُبط بالقالب بين بناء الخطّة وتطبيقها يُقفله — فلا تُحذف محاورُه."""
    from quality.appraisal_seed import apply_plan, build_plan

    _seed(school, "--apply")
    template = RoleEvaluationTemplate.objects.get(
        school=school, role_name="teacher", academic_year=YEAR
    )
    template.axes.filter(key="assessment").update(weight=20)
    plan = build_plan(school, YEAR)
    assert next(tp for tp in plan.templates if tp.role_name == "teacher").status == "changed"

    EmployeeEvaluation.objects.create(
        school=school,
        employee=teacher_user,
        evaluator=principal_user,
        template=template,
        academic_year=YEAR,
        period="S2",
    )
    counts = apply_plan(plan)
    assert counts["locked"] == 1
    assert template.axes.get(key="assessment").weight == 20


@pytest.mark.django_db
@pytest.mark.parametrize("year", ["2026/2027", "2026-27", "2026-2028"])
def test_malformed_year_writes_nothing(school, year):
    from django.core.management.base import CommandError

    with pytest.raises(CommandError, match="--year"):
        call_command(
            "seed_quality_templates",
            "--apply",
            "--school",
            school.code,
            "--year",
            year,
            stdout=StringIO(),
        )
    assert _counts(school) == (0, 0)
