"""
quality/observation_views.py — الإشراف على أداء المعلّم (الزيارات الصفية).
Skinny Views — المنطق في ObservationService. الصلاحيات في _obs_perms (مصدر واحد).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from core.models import AuditLog, CustomUser
from core.pdf_utils import render_pdf
from core.permissions import (
    OBSERVATION_CREATE,
    OBSERVATION_SELF_CREATE,
    OBSERVATION_VIEW_ALL,
    role_required,
)

from .observation_models import (
    FOLLOW_UP_MODE,
    FOLLOW_UP_SCOPE,
    OBSERVATION_DOMAINS,
    OBSERVATION_KIND,
    OBSERVATION_STATUS,
    RATING_CHOICES,
    ClassroomObservation,
)
from .observation_services import ObservationService

_TEACHER_ROLES = ["teacher", "ese_teacher", "coordinator", "activities_coordinator"]
_SORT_MAP = {"date": "-observation_date", "score": "-score_percent", "status": "status"}


# ══════════════════════════ مساعدات ══════════════════════════════════
def _is_leadership(user):
    return user.is_superuser or user.get_role() in OBSERVATION_VIEW_ALL


def _grouped_criteria(school):
    """[(domain_label, [criterion, ...])] مرتّبة حسب المجال ثم الترتيب."""
    crits = list(ObservationService.criteria_for(school))
    groups = []
    for domain, label in OBSERVATION_DOMAINS:
        items = [c for c in crits if c.domain == domain]
        if items:
            groups.append((label, items))
    return groups


def _form_lists(school):
    from core.models.academic import ClassGroup
    from operations.models import Subject

    return {
        "teachers": CustomUser.objects.filter(
            memberships__school=school,
            memberships__role__name__in=_TEACHER_ROLES,
            memberships__is_active=True,
        )
        .distinct()
        .order_by("full_name"),
        "subjects": Subject.objects.filter(school=school).order_by("name_ar"),
        "class_groups": ClassGroup.objects.filter(school=school).order_by("grade", "section"),
    }


def _collect_post(request, school):
    """يستخرج (header, ratings, recommendations) من POST."""
    header = {
        "subject_id": request.POST.get("subject") or None,
        "class_group_id": request.POST.get("class_group") or None,
        "period": request.POST.get("period") or None,
        "topic": request.POST.get("topic", "").strip(),
        "follow_up_mode": request.POST.get("follow_up_mode", ""),
        "follow_up_scope": request.POST.get("follow_up_scope", ""),
        "broadcast_note": request.POST.get("broadcast_note", "").strip(),
        "general_notes": request.POST.get("general_notes", "").strip(),
    }
    date = request.POST.get("observation_date")
    if date:  # فارغ → لا نكتبه (إنشاء: يُطبَّق الافتراضي؛ تعديل: يبقى القديم)
        header["observation_date"] = date
    crit_ids = [str(c.id) for grp in _grouped_criteria(school) for c in grp[1]]
    ratings = {cid: request.POST.get(f"rating_{cid}", "") for cid in crit_ids}
    recs = {cid: request.POST.get(f"rec_{cid}", "") for cid in crit_ids}
    return header, ratings, recs


def _obs_perms(user, obs):
    """صلاحيات الإجراءات على زيارة بعينها — مصدر واحد للقوالب والتحقّق الخادمي."""
    role = user.get_role()
    lead = user.is_superuser or role in OBSERVATION_VIEW_ALL
    is_observer = obs.observer_id == user.id
    is_teacher = obs.teacher_id == user.id
    status = obs.status
    can_edit = (is_observer or user.is_superuser) and status != "acknowledged"
    if status == "draft":
        can_delete = is_observer or user.is_superuser
    elif status == "submitted":
        can_delete = lead
    else:  # acknowledged
        can_delete = user.is_superuser or role == "principal"
    return {
        "is_teacher": is_teacher,
        "is_observer": is_observer,
        "is_leadership": lead,
        "can_edit": can_edit,
        "can_submit": can_edit and status == "draft",
        "can_withdraw": (is_observer or lead) and status == "submitted",
        "can_reopen": lead and status == "acknowledged",
        "can_ack": is_teacher and status == "submitted" and obs.kind == "supervision",
        "can_delete": can_delete,
    }


def _form_context(school, *, obs=None, scores_map=None, is_self=False):
    """grouped_criteria = [(domain_label, [(criterion, score|None)])] — score للتعبئة عند التعديل."""
    scores_map = scores_map or {}
    grouped = [
        (label, [(c, scores_map.get(str(c.id))) for c in items])
        for label, items in _grouped_criteria(school)
    ]
    ctx = _form_lists(school)
    ctx.update(
        {
            "grouped_criteria": grouped,
            "rating_choices": RATING_CHOICES,
            "follow_up_modes": FOLLOW_UP_MODE,
            "follow_up_scopes": FOLLOW_UP_SCOPE,
            "mode": "edit" if obs else "create",
            "obs": obs,
            "is_self": is_self or bool(obs and obs.kind == "self"),
        }
    )
    return ctx


def _get_observation(request, obs_id):
    """يجلب الزيارة (غير المؤرشَفة) + علم الوصول (زائر/معلّم/قيادة)."""
    school = request.user.get_school()
    obs = get_object_or_404(
        ClassroomObservation.objects.select_related(
            "teacher", "observer", "subject", "class_group"
        ),
        id=obs_id,
        school=school,
    )
    allowed = (
        _is_leadership(request.user)
        or obs.observer_id == request.user.id
        or obs.teacher_id == request.user.id
    )
    return obs, allowed


def _groups_with_scores(obs):
    scores = {str(s.criterion_id): s for s in obs.scores.select_related("criterion")}
    return [
        (label, [(c, scores.get(str(c.id))) for c in items])
        for label, items in _grouped_criteria(obs.school)
    ]


# ══════════════════════════ إنشاء / تعديل ════════════════════════════
@login_required
@role_required(OBSERVATION_CREATE)
def observation_create(request):
    school = request.user.get_school()
    if request.method == "POST":
        teacher = get_object_or_404(
            CustomUser.objects.filter(memberships__school=school).distinct(),
            id=request.POST.get("teacher"),
        )
        if teacher.id == request.user.id:
            messages.error(request, "لا يمكن للمشرف أن يزور نفسه — استخدم «تقييم ذاتي».")
            return redirect("observation_create")
        header, ratings, recs = _collect_post(request, school)
        obs = ClassroomObservation.objects.create(
            school=school,
            teacher=teacher,
            observer=request.user,
            kind="supervision",
            created_by=request.user,
            **header,
        )
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
    return render(request, "quality/observation_form.html", _form_context(school))


@login_required
@role_required(OBSERVATION_SELF_CREATE)
def observation_self_create(request):
    """تقييم ذاتي — المعلّم يقيّم نفسه (هو المعلّم والمُقيِّم معاً)."""
    school = request.user.get_school()
    if request.method == "POST":
        header, ratings, recs = _collect_post(request, school)
        obs = ClassroomObservation.objects.create(
            school=school,
            teacher=request.user,
            observer=request.user,
            kind="self",
            created_by=request.user,
            **header,
        )
        ObservationService.save_scores(obs, ratings, recs)
        if request.POST.get("action") == "submit":
            ObservationService.submit(obs, request.user)
            messages.success(request, "تم اعتماد تقييمك الذاتي.")
        else:
            messages.success(request, "حُفظ كمسودة.")
        AuditLog.log(
            user=request.user,
            action="create",
            model_name="other",
            object_id=obs.pk,
            object_repr=f"تقييم ذاتي — {request.user.full_name}",
            request=request,
        )
        return redirect("observation_detail", obs_id=obs.pk)
    return render(request, "quality/observation_form.html", _form_context(school, is_self=True))


@login_required
def observation_edit(request, obs_id):
    obs, allowed = _get_observation(request, obs_id)
    if not allowed:
        return render(request, "403.html", status=403)
    perms = _obs_perms(request.user, obs)
    if not perms["can_edit"]:
        if obs.status == "acknowledged":
            messages.error(request, "لا يمكن تعديل ملاحظة مُقَرّة — أعد فتحها أولاً.")
            return redirect("observation_detail", obs_id=obs.pk)
        return render(request, "403.html", status=403)
    school = obs.school
    if request.method == "POST":
        header, ratings, recs = _collect_post(request, school)
        if obs.kind != "self":  # التقييم الذاتي: المعلّم ثابت (هو المستخدم) — لا حقل اختيار
            teacher = get_object_or_404(
                CustomUser.objects.filter(memberships__school=school).distinct(),
                id=request.POST.get("teacher"),
            )
            if teacher.id == request.user.id:
                messages.error(request, "لا يمكن للمشرف أن يزور نفسه — استخدم «تقييم ذاتي».")
                return redirect("observation_edit", obs_id=obs.pk)
            header["teacher"] = teacher
        ObservationService.update_observation(
            obs, header=header, ratings=ratings, recommendations=recs, by_user=request.user
        )
        if request.POST.get("action") == "submit" and obs.status == "draft":
            ObservationService.submit(obs, request.user)
            messages.success(request, "حُفظت التعديلات وأُرسلت الملاحظة للمعلّم.")
        else:
            messages.success(request, "حُفظت التعديلات.")
        AuditLog.log(
            user=request.user,
            action="update",
            model_name="other",
            object_id=obs.pk,
            object_repr=f"إشراف صفّي — {obs.teacher.full_name}",
            request=request,
        )
        return redirect("observation_detail", obs_id=obs.pk)
    scores_map = {str(s.criterion_id): s for s in obs.scores.all()}
    return render(
        request,
        "quality/observation_form.html",
        _form_context(school, obs=obs, scores_map=scores_map),
    )


# ══════════════════════════ قائمة + تفصيل ════════════════════════════
@login_required
def observation_list(request):
    school = request.user.get_school()
    qs = ObservationService.visible_to(request.user, school)
    g = request.GET
    lead = _is_leadership(request.user)

    if g.get("status") in dict(OBSERVATION_STATUS):
        qs = qs.filter(status=g["status"])
    if g.get("kind") in dict(OBSERVATION_KIND):
        qs = qs.filter(kind=g["kind"])
    if g.get("teacher"):
        qs = qs.filter(teacher_id=g["teacher"])
    if lead and g.get("observer"):
        qs = qs.filter(observer_id=g["observer"])
    if g.get("date_from"):
        qs = qs.filter(observation_date__gte=g["date_from"])
    if g.get("date_to"):
        qs = qs.filter(observation_date__lte=g["date_to"])
    q = g.get("q", "").strip()
    if q:
        qs = qs.filter(Q(topic__icontains=q) | Q(teacher__full_name__icontains=q))
    qs = qs.order_by(_SORT_MAP.get(g.get("sort"), "-observation_date"))

    page = Paginator(qs, 25).get_page(g.get("page"))
    rows = [(o, _obs_perms(request.user, o)) for o in page]

    params = g.copy()
    params.pop("page", None)

    visible = ObservationService.visible_to(request.user, school)
    teachers = CustomUser.objects.filter(
        id__in=visible.values_list("teacher_id", flat=True)
    ).order_by("full_name")
    observers = (
        CustomUser.objects.filter(id__in=visible.values_list("observer_id", flat=True)).order_by(
            "full_name"
        )
        if lead
        else []
    )
    return render(
        request,
        "quality/observation_list.html",
        {
            "rows": rows,
            "page_obj": page,
            "can_create": request.user.get_role() in OBSERVATION_CREATE
            or request.user.is_superuser,
            "can_self": request.user.get_role() in OBSERVATION_SELF_CREATE,
            "is_leadership": lead,
            "status_choices": OBSERVATION_STATUS,
            "kind_choices": OBSERVATION_KIND,
            "sort_choices": [("date", "التاريخ"), ("score", "النسبة"), ("status", "الحالة")],
            "teachers": teachers,
            "observers": observers,
            "f": g,
            "querystring": params.urlencode(),
        },
    )


@login_required
def observation_detail(request, obs_id):
    obs, allowed = _get_observation(request, obs_id)
    if not allowed:
        return render(request, "403.html", status=403)
    ctx = {"obs": obs, "grouped": _groups_with_scores(obs)}
    ctx.update(_obs_perms(request.user, obs))
    return render(request, "quality/observation_detail.html", ctx)


# ══════════════════════════ سير الحالة ═══════════════════════════════
@login_required
@require_POST
def observation_acknowledge(request, obs_id):
    obs, _allowed = _get_observation(request, obs_id)
    if obs.teacher_id != request.user.id:
        return render(request, "403.html", status=403)
    if obs.status == "submitted":
        ObservationService.acknowledge(obs, request.POST.get("teacher_comment", ""))
        messages.success(request, "تم تسجيل إقرارك بالاطّلاع.")
    return redirect("observation_detail", obs_id=obs.pk)


@login_required
@require_POST
def observation_submit(request, obs_id):
    """إرسال مسودة قائمة للمعلّم (من صفحة التفصيل) دون المساس بالتقييمات."""
    obs, allowed = _get_observation(request, obs_id)
    if not allowed or not _obs_perms(request.user, obs)["can_submit"]:
        return render(request, "403.html", status=403)
    ObservationService.submit(obs, request.user)
    AuditLog.log(
        user=request.user,
        action="update",
        model_name="other",
        object_id=obs.pk,
        object_repr=f"إشراف صفّي — {obs.teacher.full_name}",
        changes={"transition": "submit"},
        request=request,
    )
    messages.success(request, "تم إرسال الملاحظة للمعلّم وإشعاره.")
    return redirect("observation_detail", obs_id=obs.pk)


@login_required
@require_POST
def observation_withdraw(request, obs_id):
    obs, allowed = _get_observation(request, obs_id)
    if not allowed or not _obs_perms(request.user, obs)["can_withdraw"]:
        return render(request, "403.html", status=403)
    ObservationService.withdraw(obs, request.user)
    AuditLog.log(
        user=request.user,
        action="update",
        model_name="other",
        object_id=obs.pk,
        object_repr=f"إشراف صفّي — {obs.teacher.full_name}",
        changes={"transition": "withdraw"},
        request=request,
    )
    messages.success(request, "سُحبت الملاحظة وعادت إلى مسودة.")
    return redirect("observation_detail", obs_id=obs.pk)


@login_required
@require_POST
def observation_reopen(request, obs_id):
    obs, allowed = _get_observation(request, obs_id)
    if not allowed or not _obs_perms(request.user, obs)["can_reopen"]:
        return render(request, "403.html", status=403)
    reason = request.POST.get("reason", "").strip()
    ObservationService.reopen(obs, request.user, reason=reason)
    AuditLog.log(
        user=request.user,
        action="update",
        model_name="other",
        object_id=obs.pk,
        object_repr=f"إشراف صفّي — {obs.teacher.full_name}",
        changes={"transition": "reopen", "reason": reason},
        request=request,
    )
    messages.success(request, "أُعيد فتح الملاحظة — سيُعاد إشعار المعلّم بالإقرار.")
    return redirect("observation_detail", obs_id=obs.pk)


@login_required
@require_POST
def observation_delete(request, obs_id):
    obs, allowed = _get_observation(request, obs_id)
    if not allowed or not _obs_perms(request.user, obs)["can_delete"]:
        return render(request, "403.html", status=403)
    reason = request.POST.get("reason", "").strip()
    if obs.status in ("submitted", "acknowledged") and not reason:
        messages.error(request, "يجب ذكر سبب حذف ملاحظة مُرسَلة/مُقَرّة.")
        return redirect("observation_detail", obs_id=obs.pk)
    prev_status = obs.status
    ObservationService.archive(obs, request.user, reason=reason)
    AuditLog.log(
        user=request.user,
        action="delete",
        model_name="other",
        object_id=obs.pk,
        object_repr=f"إشراف صفّي — {obs.teacher.full_name} — {prev_status}",
        changes={"reason": reason, "prev_status": prev_status},
        request=request,
    )
    messages.success(request, "حُذفت الملاحظة (محفوظة في الأرشيف ويمكن استرجاعها).")
    return redirect("observation_list")


# ══════════════════════════ PDF ══════════════════════════════════════
@login_required
def observation_pdf(request, obs_id):
    obs, allowed = _get_observation(request, obs_id)
    if not allowed:
        return render(request, "403.html", status=403)
    html = render_to_string(
        "quality/observation_pdf.html",
        {"obs": obs, "grouped": _groups_with_scores(obs), "rating_choices": RATING_CHOICES},
    )
    return render_pdf(html, f"observation_{obs.teacher.full_name}_{obs.observation_date}.pdf")
