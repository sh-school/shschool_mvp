"""[QUALITY] إصلاح ب.2 — لا يُربط تقييمٌ محفوظٌ بقالبٍ جديد تلقائياً.

كان `create_evaluation` يربط أيّ تقييمٍ (حتى المعتمَد) بأوّل قالبٍ يجده لدور
الموظّف الحاليّ إن لم يكن `template` مضبوطاً من قبل، ويعرض محاوره على مفاتيح
القالب الجديد — فتظهر درجاتُه صفراً رغم وجود درجاتٍ محفوظة فعلاً على المحاور
الافتراضية الأربعة أو على `EvaluationScore`.

وبالمثل، كان أمر البذر `seed_quality_templates.py` يُحدّث وزن/تسمية محاور
قالبٍ حتى لو عليه تقييماتٌ مُقدَّمة أو معتمَدة أو ذاتُ درجاتٍ من مقيِّمين
متعدّدين.
"""

import pytest
from django.urls import reverse

from core.academic_calendar import default_academic_year
from quality.models import EvaluationAxis, EvaluationScore, RoleEvaluationTemplate
from tests.test_quality_models import make_admin, make_evaluation, make_teacher


@pytest.mark.django_db
def test_opening_an_approved_evaluation_does_not_relink_its_template(client, school):
    """تقييمٌ معتمَدٌ على المحاور الافتراضية — فتحه بعد بذر قالبٍ جديد لدوره
    يجب ألّا يربطه بالقالب ولا يُظهر محاوره صفراً."""
    admin = make_admin(school)
    teacher = make_teacher(school)
    ev = make_evaluation(
        school,
        teacher,
        admin,
        status="approved",
        axis_professional=22,
        axis_commitment=20,
        axis_teamwork=19,
        axis_development=21,
    )
    assert ev.template is None

    # يُبذر قالبٌ جديد لدور "teacher" بعد إنشاء التقييم
    template = RoleEvaluationTemplate.objects.create(
        school=school, role_name="teacher", academic_year=ev.academic_year
    )
    EvaluationAxis.objects.create(template=template, key="planning", label="التخطيط", weight=100)

    client.force_login(admin)
    resp = client.get(
        reverse("create_evaluation", args=[teacher.id])
        + f"?year={ev.academic_year}&period={ev.period}"
    )
    assert resp.status_code == 200

    ev.refresh_from_db()
    assert ev.template is None, "تقييمٌ معتمَدٌ رُبط بقالبٍ جديد تلقائياً"

    axis_rows = resp.context["axis_rows"]
    displayed_total = sum(v for _k, _l, _w, v in axis_rows)
    assert displayed_total == 82, "محاورُ التقييم المعتمَد ظهرت صفراً بعد الربط الخاطئ"


@pytest.mark.django_db
def test_fresh_draft_still_gets_linked_to_new_template(client, school):
    """تقييمٌ جديدٌ فارغٌ (مسودّة بلا درجات) يُربط بالقالب الجديد كالمعتاد."""
    admin = make_admin(school)
    teacher = make_teacher(school)
    template = RoleEvaluationTemplate.objects.create(
        school=school, role_name="teacher", academic_year="2025-2026"
    )
    EvaluationAxis.objects.create(template=template, key="planning", label="التخطيط", weight=100)

    client.force_login(admin)
    resp = client.get(reverse("create_evaluation", args=[teacher.id]) + "?year=2025-2026&period=S1")
    assert resp.status_code == 200
    assert resp.context["template"] == template


@pytest.mark.django_db
def test_seed_command_does_not_overwrite_axis_of_locked_template(school):
    from django.core.management import call_command

    admin = make_admin(school)
    teacher = make_teacher(school)
    template = RoleEvaluationTemplate.objects.create(
        school=school, role_name="teacher", academic_year=default_academic_year()
    )
    axis = EvaluationAxis.objects.create(
        template=template, key="planning_development", label="عنوانٌ قديم", weight=99, order=1
    )
    ev = make_evaluation(
        school, teacher, admin, template=template, academic_year=template.academic_year
    )
    EvaluationScore.objects.create(evaluation=ev, evaluator=admin, weight=100, axis_professional=25)

    call_command("seed_quality_templates", "--apply")

    axis.refresh_from_db()
    assert axis.weight == 99, "عُدِّل وزنُ محورٍ عليه تقييمٌ مقفلٌ (له درجاتٌ محفوظة)"
    assert axis.label == "عنوانٌ قديم"
