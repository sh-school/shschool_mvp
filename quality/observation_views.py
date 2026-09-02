"""
quality/observation_views.py — الإشراف على أداء المعلّم (الزيارات الصفية).
Skinny Views — المنطق في ObservationService. الصلاحيات في _obs_perms (مصدر واحد).
"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from core.academic_calendar import academic_year_for_school
from core.models import AuditLog, CustomUser
from core.pdf_utils import render_pdf
from core.permissions import (
    OBSERVATION_CREATE,
    OBSERVATION_PEER_CREATE,
    OBSERVATION_SELF_CREATE,
    OBSERVATION_SEND,
    OBSERVATION_VIEW_ALL,
    role_required,
)
from core.sorting import apply_sort

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

logger = logging.getLogger(__name__)

_TEACHER_ROLES = ["teacher", "ese_teacher", "coordinator", "activities_coordinator"]
# حقولُ الفرز المسموحة: `?sort=` نصٌّ من المستخدم لا يبلغ ORM إلّا مصفّى،
# ولكلٍّ حقلٌ ثانٍ يقطع التساوي فلا يتأرجح ترتيبُ الصفحات بين طلبين.
OBSERVATION_SORTS = {
    "teacher": ("teacher__full_name", "-observation_date"),
    "observer": ("observer__full_name", "-observation_date"),
    "subject": ("subject__name", "-observation_date"),
    "date": ("observation_date", "-created_at"),
    "kind": ("kind", "-observation_date"),
    "score": ("score_percent", "-observation_date"),
    "status": ("status", "-observation_date"),
}
# التاريخُ والنسبةُ يبدآن تنازليّاً: الأحدثُ والأعلى هو المقصودُ أوّلاً.
OBSERVATION_DESC_FIRST = ("date", "score")

ARCHIVE_SORTS = {
    "teacher": ("teacher__full_name", "-observation_date"),
    "observer": ("observer__full_name", "-observation_date"),
    "subject": ("subject__name", "-observation_date"),
    "date": ("observation_date", "-created_at"),
    "kind": ("kind", "-observation_date"),
    "score": ("score_percent", "-observation_date"),
    "archived": ("deleted_at", "-observation_date"),
}
ARCHIVE_DESC_FIRST = ("date", "score", "archived")


# ══════════════════════════ مساعدات ══════════════════════════════════
def _is_leadership(user):
    return user.is_superuser or user.get_role() in OBSERVATION_VIEW_ALL


def _can_send(user):
    return user.is_superuser or user.get_role() in OBSERVATION_SEND


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
        "class_groups": ClassGroup.objects.filter(
            school=school, academic_year=academic_year_for_school(school)
        ).in_school_order(),
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
        # الزيارة الإشرافية وزيارة الزميل يُقرّهما المزور — والتقييم
        # الذاتيّ لا إقرارَ فيه، فصاحبُه هو كاتبُه.
        "can_ack": is_teacher and status == "submitted" and obs.kind != "self",
        "can_delete": can_delete,
    }


def _form_context(school, *, obs=None, scores_map=None, is_self=False, is_peer=False):
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
            "is_peer": is_peer or bool(obs and obs.kind == "peer"),
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


def _as_data_uri(image_field):
    """صورة المدرسة مضمَّنةً في الصفحة لا مُشاراً إليها برابط.

    الملفّات المرفوعة تُخزَّن في القاعدة لا على قرص (Railway بلا قرصٍ
    دائم)، فرابطها `/dbmedia/...` يُخدَم بعرضٍ يتطلّب جلسة. وWeasyPrint
    يحلّ الروابط النسبية على **القرص** من `BASE_DIR`، فيبحث عن ملفٍّ لا
    وجود له ويطبع الصفحة بلا ترويسة — بلا خطأٍ ولا شكوى.

    فتُقرأ الصورة وتُضمَّن. وحجمُها عشراتُ الكيلوبايتات، والوثيقة تُولَّد
    مرّةً عند الطلب.
    """
    if not image_field:
        return ""
    import base64
    import mimetypes

    kind = mimetypes.guess_type(image_field.name)[0] or "image/png"
    try:
        with image_field.open("rb") as fh:
            payload = base64.b64encode(fh.read()).decode("ascii")
    except (OSError, ValueError):
        logger.warning("تعذّرت قراءة %s — تُطبع الوثيقة بعنوانٍ نصّيّ", image_field.name)
        return ""
    return f"data:{kind};base64,{payload}"


def _pdf_context(obs):
    """سياق الاستمارة المطبوعة — طبق الأصل من نموذج المدرسة.

    والأصل صفحتان، وطلبت المدرسة صفحةً واحدة — فالمجالات الأربعة تُعرض في
    جدولٍ واحد بلا قسمة.
    """
    grouped = [
        (label, [{"criterion": c, "score": s} for c, s in rows])
        for label, rows in _groups_with_scores(obs)
    ]
    return {
        "obs": obs,
        "letterhead": _as_data_uri(obs.school.letterhead),
        "letterfoot": _as_data_uri(obs.school.letterfoot),
        "domains": grouped,
        "ratings": RATING_CHOICES,
        "academic_year": academic_year_for_school(obs.school).replace("-", "/"),
        "form_subject": {
            "self": "التقييم الذاتي للمعلّم",
            "peer": "تبادل الزيارات بين المعلّمين",
        }.get(obs.kind, "الإشراف على أداء المعلّم"),
    }


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
@role_required(OBSERVATION_PEER_CREATE)
def observation_peer_create(request):
    """تبادل الزيارات — معلّمٌ يزور زميله.

    الزائرُ هو صاحبُ الحساب دائماً ولا يُقرأ من النموذج: زيارةٌ تُنسب إلى
    غير من كتبها ليست تبادلاً بل انتحال. والمزور يُختار من زملائه.

    ولا يزور المرءُ نفسه هنا — لذلك التقييم الذاتي.
    """
    school = request.user.get_school()
    if request.method == "POST":
        header, ratings, recs = _collect_post(request, school)
        teacher_id = request.POST.get("teacher")
        colleague = _colleague(request, school, teacher_id)
        if colleague is None:
            messages.error(request, "اختر زميلاً من المدرسة غيرَك.")
            return render(
                request,
                "quality/observation_form.html",
                _form_context(school, is_peer=True),
            )
        obs = ClassroomObservation.objects.create(
            school=school,
            teacher=colleague,
            observer=request.user,
            kind="peer",
            created_by=request.user,
            **header,
        )
        ObservationService.save_scores(obs, ratings, recs)
        if request.POST.get("action") == "submit":
            ObservationService.submit(obs, request.user)
            messages.success(request, "أُرسلت زيارة الزميل إليه.")
        else:
            messages.success(request, "حُفظت كمسودة.")
        AuditLog.log(
            user=request.user,
            action="create",
            model_name="other",
            object_id=obs.pk,
            object_repr=f"زيارة زميل — {colleague.full_name}",
            request=request,
        )
        return redirect("observation_detail", obs_id=obs.pk)
    return render(request, "quality/observation_form.html", _form_context(school, is_peer=True))


def _colleague(request, school, teacher_id):
    """الزميل المزور — من المدرسة نفسها، وليس صاحب الحساب."""
    if not teacher_id or str(teacher_id) == str(request.user.id):
        return None
    return CustomUser.objects.filter(
        id=teacher_id,
        memberships__school=school,
        memberships__is_active=True,
        memberships__role__name__in=_TEACHER_ROLES,
    ).first()


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
    # الفرزُ على الاستعلام كلِّه قبل التقسيم — لا على الصفحة الظاهرة وحدَها.
    qs, sort = apply_sort(
        qs,
        request,
        OBSERVATION_SORTS,
        "date",
        default_desc=True,
        desc_first=OBSERVATION_DESC_FIRST,
    )

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
            "sort": sort,
            "can_create": request.user.get_role() in OBSERVATION_CREATE
            or request.user.is_superuser,
            "can_self": request.user.get_role() in OBSERVATION_SELF_CREATE,
            "can_peer": request.user.get_role() in OBSERVATION_PEER_CREATE,
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


# ══════════════════════════ الأرشيف ══════════════════════════════════
@login_required
def observation_archive(request):
    """المؤرشَف بنفس نطاق رؤية المستخدم للحيّ.

    الحذف ناعمٌ منذ البداية، لكن لم يكن ثمّة ما يعرضه — فرسالة «محفوظة في
    الأرشيف ويمكن استرجاعها» صادقةٌ في القاعدة وغير قابلة للتحقّق من الواجهة.
    """
    school = request.user.active_membership.school
    rows = ObservationService.archived_for(request.user, school)
    rows, sort = apply_sort(
        rows,
        request,
        ARCHIVE_SORTS,
        "archived",
        default_desc=True,
        desc_first=ARCHIVE_DESC_FIRST,
    )

    page = Paginator(rows, 25).get_page(request.GET.get("page"))
    for obs in page:
        obs.perms = _obs_perms(request.user, obs)

    return render(
        request,
        "quality/observation_archive.html",
        {"page_obj": page, "sort": sort, "total": page.paginator.count},
    )


@login_required
@require_POST
def observation_restore(request, obs_id):
    """الاستعادة لمن كان يملك الحذف — من أرشفها يُرجعها.

    ولا تُشتقّ من صلاحية القراءة: المعلّم يرى ملاحظته ولا يحذفها، فلا يُعقل
    أن يُرجع ما أرشفته القيادة.
    """
    school = request.user.active_membership.school
    obs = get_object_or_404(ObservationService.archived_for(request.user, school), pk=obs_id)
    if not _obs_perms(request.user, obs)["can_delete"]:
        return render(request, "403.html", status=403)

    ObservationService.restore(obs, request.user)
    AuditLog.log(
        user=request.user,
        action="update",
        model_name="other",
        object_id=obs.pk,
        object_repr=f"إشراف صفّي — {obs.teacher.full_name}",
        changes={"action": "restore"},
        request=request,
    )
    messages.success(request, "أُعيدت الملاحظة من الأرشيف.")
    return redirect("observation_detail", obs_id=obs.pk)


# ══════════════════════════ PDF ══════════════════════════════════════
@login_required
@xframe_options_sameorigin
def observation_pdf(request, obs_id):
    """`X_FRAME_OPTIONS = "DENY"` عامٌّ على المشروع، فيمنع عرض هذا الملفّ داخل
    إطار صفحته العارضة — والمتصفّح يُظهر «refused to connect» مكانه.

    والاستثناء `sameorigin` لهذه الاستجابة وحدها لا تخفيفٌ عامّ: الصفحة
    المُضمِّنة من الأصل نفسه، وكلّ ما عداها يبقى على `DENY`.
    """
    obs, allowed = _get_observation(request, obs_id)
    if not allowed:
        return render(request, "403.html", status=403)
    html = render_to_string("quality/observation_pdf.html", _pdf_context(obs))
    return render_pdf(html, f"observation_{obs.teacher.full_name}_{obs.observation_date}.pdf")


@login_required
def observation_pdf_view(request, obs_id):
    """صفحةٌ عارضة حول ملفّ الـPDF — شريط أدوات فوقه.

    الـPDF يُعاد بـ`Content-Disposition: inline`، فيفتحه المتصفّح بعارضه الخاصّ
    ويحلّ محلّ الصفحة كاملةً: لا رجوع ولا إجراء. وحقنُ زرٍّ داخل الملفّ نفسه
    غير ممكن، فالحلّ أن يُعرض الملفّ داخل هذه الصفحة ويبقى شريط الأدوات لنا.
    """
    obs, allowed = _get_observation(request, obs_id)
    if not allowed:
        return render(request, "403.html", status=403)
    return render(
        request,
        "quality/observation_pdf_view.html",
        {
            "obs": obs,
            "can_send": _can_send(request.user),
            "recipients": ObservationService.recipient_options(obs),
        },
    )


@login_required
@require_POST
def observation_send(request, obs_id):
    """إرسال نسخةٍ إلى من اختاره المُرسِل — بلا مساسٍ بحالة الزيارة."""
    obs, allowed = _get_observation(request, obs_id)
    if not allowed or not _can_send(request.user):
        return render(request, "403.html", status=403)

    keys = request.POST.getlist("recipients")
    if not keys:
        messages.warning(request, "اختر مستلماً واحداً على الأقلّ.")
        return redirect("observation_pdf_view", obs_id=obs.pk)

    sent = ObservationService.send_copy(obs, request.user, keys)
    if sent:
        AuditLog.log(
            user=request.user,
            action="update",
            model_name="other",
            object_id=obs.pk,
            object_repr=f"إشراف صفّي — {obs.teacher.full_name}",
            changes={"action": "send_copy", "recipients": len(sent)},
            request=request,
        )
        messages.success(request, "أُرسلت نسخة إلى: " + "، ".join(sent) + ".")
    else:
        messages.warning(request, "لم يصل الإشعار إلى أحد — تحقّق من شاغلي الأدوار المختارة.")
    return redirect("observation_pdf_view", obs_id=obs.pk)
