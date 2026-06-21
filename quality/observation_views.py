"""
quality/observation_views.py — الإشراف على أداء المعلّم (الملاحظة الصفّية).
Skinny Views — المنطق في ObservationService.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from core.models import AuditLog, CustomUser
from core.pdf_utils import render_pdf
from core.permissions import OBSERVATION_CREATE, role_required

from .observation_models import (
    FOLLOW_UP_MODE,
    FOLLOW_UP_SCOPE,
    OBSERVATION_DOMAINS,
    RATING_CHOICES,
    ClassroomObservation,
)
from .observation_services import ObservationService

_TEACHER_ROLES = ["teacher", "ese_teacher", "coordinator", "activities_coordinator"]


def _grouped_criteria(school, scores_map=None):
    """يُعيد [(domain_label, [criterion, ...])] مرتّبة حسب المجال ثم الترتيب."""
    crits = list(ObservationService.criteria_for(school))
    labels = dict(OBSERVATION_DOMAINS)
    groups = []
    for domain, label in OBSERVATION_DOMAINS:
        items = [c for c in crits if c.domain == domain]
        if items:
            groups.append((label, items))
    return groups


@login_required
@role_required(OBSERVATION_CREATE)
def observation_create(request):
    """إنشاء/تعبئة استمارة إشراف."""
    school = request.user.get_school()
    if request.method == "POST":
        teacher = get_object_or_404(
            CustomUser.objects.filter(memberships__school=school).distinct(),
            id=request.POST.get("teacher"),
        )
        obs = ClassroomObservation.objects.create(
            school=school,
            teacher=teacher,
            observer=request.user,
            subject_id=request.POST.get("subject") or None,
            class_group_id=request.POST.get("class_group") or None,
            observation_date=request.POST.get("observation_date") or None,
            period=request.POST.get("period") or None,
            topic=request.POST.get("topic", "").strip(),
            follow_up_mode=request.POST.get("follow_up_mode", ""),
            follow_up_scope=request.POST.get("follow_up_scope", ""),
            broadcast_note=request.POST.get("broadcast_note", "").strip(),
            general_notes=request.POST.get("general_notes", "").strip(),
            created_by=request.user,
        )
        crit_ids = [str(c.id) for grp in _grouped_criteria(school) for c in grp[1]]
        ratings = {cid: request.POST.get(f"rating_{cid}", "") for cid in crit_ids}
        recs = {cid: request.POST.get(f"rec_{cid}", "") for cid in crit_ids}
        ObservationService.save_scores(obs, ratings, recs)

        if request.POST.get("action") == "submit":
            ObservationService.submit(obs, request.user)
            messages.success(request, "تم إرسال الملاحظة للمعلّم وإشعاره.")
        else:
            messages.success(request, "حُفظت كمسودة.")

        AuditLog.log(
            user=request.user,
            action="create",
            model_name="other",
            object_id=obs.pk,
            object_repr=f"إشراف صفّي — {teacher.full_name}",
            request=request,
        )
        return redirect("observation_detail", obs_id=obs.pk)

    from operations.models import Subject

    context = {
        "teachers": CustomUser.objects.filter(
            memberships__school=school,
            memberships__role__name__in=_TEACHER_ROLES,
            memberships__is_active=True,
        ).distinct().order_by("full_name"),
        "subjects": Subject.objects.filter(school=school).order_by("name_ar"),
        "class_groups": school.classgroup_set.all() if hasattr(school, "classgroup_set") else [],
        "grouped_criteria": _grouped_criteria(school),
        "rating_choices": RATING_CHOICES,
        "follow_up_modes": FOLLOW_UP_MODE,
        "follow_up_scopes": FOLLOW_UP_SCOPE,
    }
    # class_groups عبر العلاقة الصحيحة
    from core.models.academic import ClassGroup

    context["class_groups"] = ClassGroup.objects.filter(school=school).order_by("grade", "section")
    return render(request, "quality/observation_form.html", context)


@login_required
def observation_list(request):
    """قائمة الملاحظات المرئيّة للمستخدم."""
    school = request.user.get_school()
    qs = ObservationService.visible_to(request.user, school).order_by("-observation_date")
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    can_create = request.user.get_role() in OBSERVATION_CREATE or request.user.is_superuser
    return render(
        request,
        "quality/observation_list.html",
        {"observations": page, "page_obj": page, "can_create": can_create},
    )


def _get_observation(request, obs_id):
    school = request.user.get_school()
    obs = get_object_or_404(
        ClassroomObservation.objects.select_related("teacher", "observer", "subject", "class_group"),
        id=obs_id,
        school=school,
    )
    # تحكّم بالوصول: الزائر/المعلّم/القيادة فقط
    from core.permissions import OBSERVATION_VIEW_ALL

    role = request.user.get_role()
    allowed = (
        request.user.is_superuser
        or role in OBSERVATION_VIEW_ALL
        or obs.observer_id == request.user.id
        or obs.teacher_id == request.user.id
    )
    return obs, allowed


@login_required
def observation_detail(request, obs_id):
    obs, allowed = _get_observation(request, obs_id)
    if not allowed:
        return render(request, "403.html", status=403)
    scores = {str(s.criterion_id): s for s in obs.scores.select_related("criterion")}
    groups = []
    for label, items in _grouped_criteria(obs.school):
        groups.append((label, [(c, scores.get(str(c.id))) for c in items]))
    is_teacher = obs.teacher_id == request.user.id
    return render(
        request,
        "quality/observation_detail.html",
        {"obs": obs, "grouped": groups, "is_teacher": is_teacher},
    )


@login_required
@require_POST
def observation_acknowledge(request, obs_id):
    obs, _ = _get_observation(request, obs_id)
    if obs.teacher_id != request.user.id:
        return render(request, "403.html", status=403)
    if obs.status == "submitted":
        ObservationService.acknowledge(obs, request.POST.get("teacher_comment", ""))
        messages.success(request, "تم تسجيل إقرارك بالاطّلاع.")
    return redirect("observation_detail", obs_id=obs.pk)


@login_required
def observation_pdf(request, obs_id):
    obs, allowed = _get_observation(request, obs_id)
    if not allowed:
        return render(request, "403.html", status=403)
    scores = {str(s.criterion_id): s for s in obs.scores.select_related("criterion")}
    groups = []
    for label, items in _grouped_criteria(obs.school):
        groups.append((label, [(c, scores.get(str(c.id))) for c in items]))
    html = render_to_string(
        "quality/observation_pdf.html",
        {"obs": obs, "grouped": groups, "rating_choices": RATING_CHOICES},
    )
    return render_pdf(html, f"observation_{obs.teacher.full_name}_{obs.observation_date}.pdf")
