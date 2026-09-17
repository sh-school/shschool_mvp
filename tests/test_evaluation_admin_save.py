"""[QUALITY] إصلاح ب.1 — لوحةُ الإدارة لا تصفّر تقييماً وزارياً ولا تتجاوز الحالة.

كان `EmployeeEvaluationAdmin.save_model` يستدعي `obj.save()` الافتراضيّ فقط،
وهذا يشغّل `EmployeeEvaluation.calculate_total()` (المحاور الأربعة الافتراضية
axis_professional/commitment/teamwork/development) في كل مرّة يُحفظ فيها
السجلّ من الإدارة — حتى إن كان مجموعه الحقيقيّ محسوباً من `EvaluationScore`
(قالبٌ وزاريّ متعدّد المقيّمين) لا من هذه المحاور الأربعة، فتُصفَّر درجاتُه
بمجرّد تعديل حقلٍ آخر (كالحالة) من شاشة الإدارة.

الإصلاح: `total_score` و`rating` و`status` والمحاور الأربعة للقراءة فقط في
الإدارة، ويُعاد الحساب من `EvaluationScore` بعد كل حفظ إداريّ بدل الرمي إلى
الأصفار. والاعتمادُ الفعليّ يمرّ بمسارٍ مخصّص (`approve_evaluation`) للمدير.
"""

import pytest
from django.contrib.admin.sites import site
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory
from django.urls import reverse

from quality.admin import EmployeeEvaluationAdmin
from quality.models import EmployeeEvaluation, EvaluationScore, RoleEvaluationTemplate
from tests.test_quality_models import make_admin, make_evaluation, make_teacher


def _request(user):
    request = RequestFactory().post("/admin/")
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


@pytest.mark.django_db
def test_the_model_is_registered():
    assert EmployeeEvaluation in site._registry


@pytest.mark.django_db
def test_readonly_fields_block_direct_axis_and_status_edits(school):
    ma = EmployeeEvaluationAdmin(EmployeeEvaluation, site)
    for field in (
        "total_score",
        "rating",
        "status",
        "axis_professional",
        "axis_commitment",
        "axis_teamwork",
        "axis_development",
    ):
        assert field in ma.readonly_fields, f"{field} يجب أن يبقى للقراءة فقط في الإدارة"


@pytest.mark.django_db
def test_admin_save_does_not_zero_a_ministry_template_evaluation(school):
    """
    تقييمٌ محسوبٌ من EvaluationScore (قالبٌ وزاريّ) — محاوره الافتراضية
    الأربعة صفرٌ عمداً. حفظُه من الإدارة (مثلاً بعد تعديل حقلٍ نصّي) يجب ألّا
    يصفّر total_score عبر calculate_total() على المحاور الصفرية.
    """
    admin_user = make_admin(school)
    teacher = make_teacher(school)
    template = RoleEvaluationTemplate.objects.create(
        school=school, role_name="teacher", academic_year="2025-2026"
    )
    ev = make_evaluation(
        school,
        teacher,
        admin_user,
        template=template,
        axis_professional=0,
        axis_commitment=0,
        axis_teamwork=0,
        axis_development=0,
    )
    EvaluationScore.objects.create(
        evaluation=ev,
        evaluator=admin_user,
        weight=100,
        custom_axes={"planning": 15, "engagement": 25, "environment": 10, "assessment": 15},
    )
    ev.recalculate_from_scores()
    ev.refresh_from_db()
    assert ev.total_score == 65  # 15+25+10+15، لا صفر

    ma = EmployeeEvaluationAdmin(EmployeeEvaluation, site)
    ev.employee_comment = "تعديلٌ من شاشة الإدارة لا يمسّ الدرجات"
    ma.save_model(_request(admin_user), ev, form=None, change=True)

    ev.refresh_from_db()
    assert ev.total_score == 65, "لوحة الإدارة صفّرت تقييماً وزارياً محفوظاً"
    assert ev.employee_comment == "تعديلٌ من شاشة الإدارة لا يمسّ الدرجات"


@pytest.mark.django_db
def test_approve_evaluation_view_recalculates_and_sets_approved(client, school):
    """مسارُ الاعتماد الوحيد: المدير يعتمد تقييماً مُقدَّماً فيُعاد حساب
    مجموعه من EvaluationScore ويصير status="approved"."""
    admin_user = make_admin(school)
    teacher = make_teacher(school)
    template = RoleEvaluationTemplate.objects.create(
        school=school, role_name="teacher", academic_year="2025-2026"
    )
    ev = make_evaluation(
        school,
        teacher,
        admin_user,
        template=template,
        status="submitted",
        axis_professional=0,
        axis_commitment=0,
        axis_teamwork=0,
        axis_development=0,
    )
    EvaluationScore.objects.create(
        evaluation=ev, evaluator=admin_user, weight=100, custom_axes={"a": 70}
    )

    client.force_login(admin_user)
    resp = client.post(reverse("approve_evaluation", args=[ev.id]))
    assert resp.status_code == 302

    ev.refresh_from_db()
    assert ev.status == "approved"
    assert ev.total_score == 70


@pytest.mark.django_db
def test_approve_evaluation_forbidden_for_non_admin(client, school):
    teacher = make_teacher(school)
    admin_user = make_admin(school)
    ev = make_evaluation(school, teacher, admin_user, status="submitted")

    client.force_login(teacher)
    resp = client.post(reverse("approve_evaluation", args=[ev.id]))
    assert resp.status_code == 403
    ev.refresh_from_db()
    assert ev.status == "submitted"
