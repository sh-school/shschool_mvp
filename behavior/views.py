# behavior/views.py — Thin views using BehaviorService
"""
وحدة السلوك الطلابي — SchoolOS V2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Views نحيفة — كل Business Logic في behavior/services.py
"""

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone as _tz
from django.utils.http import url_has_allowed_host_and_scheme

from core.permissions import (
    BEHAVIOR_COMMITTEE,
    BEHAVIOR_MANAGE,
    BEHAVIOR_STATS_TEACHING,
    BEHAVIOR_VIEW_ALL,
    forbidden_page,
    get_teacher_student_ids,
    teacher_can_access_student,
)

logger = logging.getLogger(__name__)

_VALID_LEVELS = {1, 2, 3, 4}
_MAX_POINTS = 100
_MAX_DESC_LEN = 2000


def _behavior_report_redirect(
    request,
    student_id,
    year,
    period,
):
    """Return only a same-host behavior-report redirect."""
    query = urlencode(
        {
            "year": year,
            "period": period,
        }
    )
    target = f"{reverse('behavior:behavior_report', kwargs={'student_id': student_id})}" f"?{query}"

    if url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(target)

    return redirect(
        "behavior:behavior_report",
        student_id=student_id,
    )


from behavior.forms import InfractionForm
from behavior.models import BehaviorInfraction, ViolationCategory
from core.capabilities import capability_required, has_capability
from core.domain.tones import SHARE_KPI, tone_for
from core.models import CustomUser
from core.navigation import can_open
from wings.scope import student_scope_for

# ── نطاقُ الطلبة ─────────────────────────────────────────────
# المشرفُ الإداريُّ لجناحه (قرارا 2026-09-14/15): يرى طلبةَ شُعب أجنحته ومخالفاتِهم أيّاً كان
# راصدُها، ويرصد عليهم، ولا يبلغ غيرَهم — فمعرّفُ طالبٍ خارج جناحه في الرابط أو الاستعلام
# أو النموذج يعود 404 لا صفحةَ منع، إذ وجودُه في جناحٍ آخر ليس شأنَه. والسؤالُ يُسأل مرّةً
# للطلب في `student_scope_for`؛ وغيرُ المقيَّد لا يُنفَّذ له استعلامٌ واحدٌ زائد، وتبقى قاعدتُه
# كما كانت: القيادةُ للمدرسة، والمعلّمُ والمنسّقُ لطلبة جدولهما.


def _visible_student_ids(request):
    """طلبةُ صاحب الطلب — `None` للمدرسة كلِّها، ومجموعةٌ للمقيَّد بجدولٍ أو جناح."""
    return get_teacher_student_ids(request.user, scope=student_scope_for(request))


def _require_in_wing(request, student_id):
    """404 لطالبٍ خارج جناح المقيَّد — ولا شيءَ لغيره (قاعدتُه في موضعها لم تتغيّر)."""
    if student_id:
        student_scope_for(request).require_student(student_id)


def _deny_unreachable(request, student_id, message):
    """المقيَّدُ بجناحه: 404 خارجَه. وغيرُه على «طلابُك فقط» بصفحة المنع كما كان."""
    scope = student_scope_for(request)
    if scope.is_wing_bound:
        scope.require_student(student_id)
        return None
    if not teacher_can_access_student(request.user, student_id):
        return forbidden_page(request, message)
    return None


def _get_scoped_students(request, school):
    """
    يُعيد QuerySet طلاب مرئيّ حسب دور المستخدم:
    - القيادة/الأخصائيون → كل طلاب المدرسة
    - المشرف الإداري → طلبة جناحه
    - المعلم/المنسق → طلاب فصوله فقط
    """
    student_ids = _visible_student_ids(request)
    if student_ids is None:
        # admin/leadership — all students
        return (
            CustomUser.objects.filter(
                memberships__school=school,
                memberships__role__name="student",
                memberships__is_active=True,
            )
            .order_by("full_name")
            .distinct()
        )
    return CustomUser.objects.filter(id__in=student_ids).order_by("full_name")


from core.academic_calendar import academic_year_for

from .notify import notify_behavior_after_commit
from .services import (
    PERIOD_CHOICES,
    BehaviorPermissions,
    BehaviorService,
)

# [B4-PRE3] المساعدُ المؤجَّل — انتقل إلى `behavior/notify.py` ليستدعيه كشفُ الحصص
# أيضاً بلا أن تستورد خدمةٌ شاشة، وبقي اسمُه هنا لشاشتَي المخالفة.
_notify_behavior_after_commit = notify_behavior_after_commit


# ── لوحة التحكم ──────────────────────────────────────────────
def _behaviour_year_window(school):
    """نافذة العام الدراسي — وترتدّ إلى السنة الميلادية إن لم يُبذر تقويم."""
    from datetime import date

    from core.academic_calendar import academic_year_window

    window = academic_year_window(school)
    if window is not None:
        return window
    today = _tz.localdate()
    return date(today.year, 1, 1), date(today.year, 12, 31)


@login_required
@capability_required("behavior.view")
def behavior_dashboard(request):
    """لوحة تحكم السلوك — إحصائيات المخالفات والحالات الحرجة للمدرسة."""
    role = request.user.get_role()
    if role in ("parent", "student"):
        return HttpResponseForbidden("ليس لديك صلاحية الوصول إلى هذه الصفحة.")

    school = request.school
    if not school:
        messages.error(request, "لم يتم العثور على مدرسة مرتبطة بحسابك.")
        return redirect("dashboard")

    # المعلم/المنسق يرى سلوك طلابه فقط، والمشرفُ سلوكَ طلبة جناحه — قبل كلّ عدٍّ ورسم
    student_ids = _visible_student_ids(request)
    context = BehaviorService.get_dashboard_stats(school, student_ids=student_ids)
    context["can_report"] = BehaviorPermissions.can_report(request.user)
    context["is_committee"] = BehaviorPermissions.is_committee(request.user)
    context["can_summon"] = BehaviorPermissions.can_summon(request.user)
    context["can_stats"] = BehaviorPermissions.can_view_stats(request.user)

    # ── Chart data ──
    from datetime import timedelta

    from django.db.models import Count
    from django.db.models.functions import TruncDate, TruncMonth

    today = _tz.localdate()

    # Monthly trend (last 6 months)
    six_months_ago = today - timedelta(days=180)
    base_qs = BehaviorInfraction.objects.filter(school=school)
    if student_ids is not None:
        base_qs = base_qs.filter(student_id__in=student_ids)

    monthly_trend = (
        base_qs.filter(created_at__date__gte=six_months_ago)
        .values(month=TruncMonth("created_at"))
        .annotate(count=Count("id"))
        .order_by("month")
    )

    # توزيع المستويات — على العام الدراسي لا السنة الميلادية.
    #
    # سجلّ الطالب السلوكيّ يدور مع العام الدراسي (أغسطس–يونيو). والترشيح
    # بالسنة الميلادية يخلط شطرَ العام الماضي بشطر الحالي في سبتمبر، ثم
    # يُسقط الفصل الأول كلّه في يناير — واللوحة تقول «السنة الحالية».
    year_start, year_end = _behaviour_year_window(school)
    level_dist = (
        base_qs.filter(created_at__date__gte=year_start, created_at__date__lte=year_end)
        .values("level")
        .annotate(count=Count("id"))
        .order_by("level")
    )

    # Weekly trend (last 7 days)
    week_ago = today - timedelta(days=7)
    daily_trend = (
        base_qs.filter(created_at__date__gte=week_ago)
        .values(day=TruncDate("created_at"))
        .annotate(count=Count("id"))
        .order_by("day")
    )

    # أعلى فئات المخالفات — على العام الدراسي كذلك.
    top_violations = (
        base_qs.filter(created_at__date__gte=year_start, created_at__date__lte=year_end)
        .values("violation_category__name_ar")
        .annotate(count=Count("id"))
        .order_by("-count")[:5]
    )

    context["monthly_trend"] = monthly_trend
    context["level_dist"] = list(level_dist)
    context["daily_trend"] = list(daily_trend)
    context["top_violations"] = top_violations
    context.update(_dashboard_presentation(context, today))

    return render(request, "behavior/dashboard.html", context)


def _dashboard_presentation(context: dict, today) -> dict:
    """أرقامُ رأس لوحة السلوك وألوانُها — الحكمُ هنا مرّةً لا شرطاً في القالب.

    كان عددُ الجسيمة المعلّقة يُقال ثلاثاً: بطاقةٌ وشريطُ تنبيهٍ وعنوانُ قائمةٍ
    مطويّة. فصار يُقال في البطاقة وحدَها، ولونُها يحمل التنبيه: أحمرُ متى وُجدت
    جسيمةٌ بلا قرار لجنة (العتبةُ التي كانت في القالب: وجودُ واحدة).
    """
    critical = len(context.get("critical_unresolved") or [])
    return {
        "today_label": f"{today:%d/%m/%Y}",
        "year_total": sum(row["count"] for row in context.get("level_dist", [])),
        "week_total": sum(row["count"] for row in context.get("daily_trend", [])),
        "critical_count": critical,
        "critical_tone": "red" if critical else "green",
    }


# ── تسجيل مخالفة جديدة ───────────────────────────────────────
@login_required
@capability_required("behavior.record")
def report_infraction(request):
    """تسجيل مخالفة سلوكية جديدة مع إشعار ولي الأمر تلقائياً."""
    if not BehaviorPermissions.can_report(request.user):
        messages.error(request, "ليس لديك صلاحية تسجيل المخالفات.")
        return redirect("behavior:dashboard")

    school = request.school

    # فئات المخالفات النشطة — 40 مخالفة رسمية حسب لائحة الشحانية
    # الفلتر code__regex يستبعد ABCD القديمة حتى لو بقيت is_active=True
    all_violations = ViolationCategory.objects.filter(
        is_active=True, code__regex=r"^\d+-\d+$"
    ).order_by("code")
    violations_by_degree = {str(d): list(all_violations.filter(degree=d)) for d in range(1, 5)}

    if request.method == "POST":
        # معرّفُ الطالب يُسأل عنه قبل صحّة النموذج: طالبٌ خارج الجناح 404 مهما كان باقيه.
        _require_in_wing(request, request.POST.get("student_id", "").strip())
        form = InfractionForm(request.POST)
        if not form.is_valid():
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, err)
        else:
            student_id = form.cleaned_data["student_id"]
            violation_cat_id = form.cleaned_data.get("violation_category")
            description = form.cleaned_data["description"]
            # REQ-SH-001: structured disciplinary action + conditional textarea
            disciplinary_action_type = form.cleaned_data.get("disciplinary_action_type", "")
            violation_description = form.cleaned_data.get("violation_description", "")
            # Legacy free-text (kept for backward compat). Mirror the selected label
            # from the dropdown so legacy readers still see a human-friendly value.
            _choices_map = dict(form.fields["disciplinary_action_type"].choices)
            action = _choices_map.get(disciplinary_action_type, "") or form.cleaned_data.get(
                "action_taken", ""
            )
            level = form.cleaned_data["level"]

            # جلب فئة المخالفة إن وُجدت
            violation_cat = None
            if violation_cat_id:
                try:
                    violation_cat = ViolationCategory.objects.get(id=violation_cat_id)
                    level = violation_cat.degree
                except ViolationCategory.DoesNotExist:
                    messages.error(request, "فئة المخالفة غير موجودة.")
                    violation_cat = "INVALID"

            if violation_cat != "INVALID":
                student = get_object_or_404(CustomUser, id=student_id)

                try:
                    # [B4-PRE3] المخالفة ونيّة إشعارها في حدٍّ واحد.
                    #
                    # `create_infraction` مزيَّنة بـ`@transaction.atomic`، فتصير
                    # هنا نقطةَ حفظ داخلية؛ والالتزام الذي يُطلق الـcallback هو
                    # نهاية المعاملة الخارجية. فإن تراجعت، لا مخالفة ولا إشعار.
                    with transaction.atomic():
                        # ✅ v5.4: BehaviorService.create_infraction — atomic + escalation حسابي
                        # نظام النقاط ملغى — نُمرر 0 لتوافق DB (الحقل NOT NULL)
                        infraction = BehaviorService.create_infraction(
                            school=school,
                            student=student,
                            reporter=request.user,
                            level=level,
                            description=description,
                            action_taken=action,
                            points_deducted=0,
                            violation_category=violation_cat if violation_cat else None,
                            disciplinary_action_type=disciplinary_action_type,
                            violation_description=violation_description,
                        )

                        # [B4-7A.3] `robust=True` شرطٌ لا زينة: استثناءٌ في
                        # callback عاديّ يُرفع من `run_and_clear_commit_hooks`
                        # **بعد** الالتزام — فتُحفظ المخالفة ويرى المستخدم 500،
                        # فيُعيد التسجيل ويُنشئ ثانية. وكان الارتدادُ المحذوف
                        # هو ما يبتلع ذلك بالمصادفة.
                        transaction.on_commit(
                            lambda infraction=infraction,
                            school=school,
                            reporter=request.user: _notify_behavior_after_commit(
                                infraction, school, reporter
                            ),
                            robust=True,
                        )
                except ValueError as e:
                    messages.error(request, str(e))
                    return redirect("behavior:dashboard")

                messages.success(
                    request, f"تم تسجيل مخالفة من الدرجة {level} للطالب {student.full_name}"
                )

                if level >= 3:
                    messages.warning(
                        request, f"تم إحالة المخالفة للجنة الضبط السلوكي لكونها من الدرجة {level}"
                    )
                return redirect(_after_record_url(request.user, student.id, level))

    students = _get_scoped_students(request, school)
    return render(
        request,
        "behavior/report_form.html",
        {
            "students": students,
            "levels": BehaviorInfraction.LEVELS,
            "violations_by_degree": violations_by_degree,
            "degree_panels": _degree_panels(violations_by_degree),
        },
    )


#: لوحاتُ الدرجات الأربع — الاسمُ ولونُ الرمز. و`color` قيمةُ `data-color` القديمة تبقى للشيفرة.
_DEGREE_PANELS = (
    ("1", "الدرجة 1 — بسيطة", "green", "green"),
    ("2", "الدرجة 2 — متوسطة", "amber", "yellow"),
    ("3", "الدرجة 3 — خطيرة", "orange", "orange"),
    ("4", "الدرجة 4 — جسيمة", "red", "red"),
)


def _degree_panels(violations_by_degree: dict) -> list[dict]:
    """لوحةٌ لكلّ درجة بمخالفاتها — كانت أربعَ نسخٍ متطابقةً في القالب لا يفرّقها إلّا اللون."""
    return [
        {
            "degree": degree,
            "label": label,
            "tone": tone,
            "color": color,
            "items": violations_by_degree.get(degree, []),
        }
        for degree, label, tone, color in _DEGREE_PANELS
    ]


# ── تسجيل مخالفة سريعة (HTMX Modal) ────────────────────────
@login_required
@capability_required("behavior.record")
def quick_log(request):
    """
    تسجيل مخالفة سريعة عبر HTMX Modal.

    GET  → نموذج HTML (partial) لعرضه داخل modal
    POST → إنشاء المخالفة + HX-Trigger showToast + HX-Redirect للملف السلوكي
    """
    from core.htmx_utils import htmx_redirect, htmx_toast

    if not BehaviorPermissions.can_report(request.user):
        from django.http import HttpResponse

        return HttpResponse("ليس لديك صلاحية", status=403)

    school = request.school

    if request.method == "POST":
        student_id = request.POST.get("student_id", "").strip()
        _require_in_wing(request, student_id)
        violation_cat_id = request.POST.get("violation_category", "").strip()
        description = request.POST.get("description", "").strip()
        action = request.POST.get("action_taken", "").strip()

        try:
            level = int(request.POST.get("level", 1))
        except (ValueError, TypeError):
            level = 1

        # جلب فئة المخالفة
        violation_cat = None
        if violation_cat_id:
            try:
                violation_cat = ViolationCategory.objects.get(id=violation_cat_id)
                level = violation_cat.degree
            except ViolationCategory.DoesNotExist:
                pass

        # Validation
        errors = []
        if not student_id:
            errors.append("يرجى اختيار الطالب.")
        if not description:
            errors.append("يرجى كتابة وصف المخالفة.")
        elif len(description) > _MAX_DESC_LEN:
            errors.append(f"الوصف لا يتجاوز {_MAX_DESC_LEN} حرف.")
        if level not in _VALID_LEVELS:
            errors.append("درجة المخالفة يجب أن تكون بين 1 و 4.")

        if errors:
            return htmx_toast(
                render(
                    request,
                    "behavior/partials/quick_log_form.html",
                    _quick_log_context(request, school, student_id),
                ),
                msg=" | ".join(errors),
                msg_type="danger",
            )

        student = get_object_or_404(CustomUser, id=student_id)

        # [B4-PRE3] المخالفة ونيّة إشعارها في حدٍّ واحد — انظر report_infraction.
        with transaction.atomic():
            # ✅ v5.4: BehaviorService.create_infraction — atomic + escalation حسابي
            # نظام النقاط ملغى — points_deducted=0 للحفاظ على توافق DB
            infraction = BehaviorService.create_infraction(
                school=school,
                student=student,
                reporter=request.user,
                level=level,
                description=description,
                action_taken=action,
                points_deducted=0,
                violation_category=violation_cat,
            )

            transaction.on_commit(
                lambda infraction=infraction,
                school=school,
                reporter=request.user: _notify_behavior_after_commit(infraction, school, reporter),
                robust=True,
            )

        redirect_url = _after_record_url(request.user, student.id, level)
        msg = f"تم تسجيل مخالفة درجة {level} للطالب {student.full_name}"
        if level >= 3:
            msg += " — تم إحالتها للجنة الضبط"
        return htmx_redirect(redirect_url, msg=msg, msg_type="success")

    # GET — نموذج فارغ
    student_id_hint = request.GET.get("student_id", "")
    _require_in_wing(request, student_id_hint)
    return render(
        request,
        "behavior/partials/quick_log_form.html",
        _quick_log_context(request, school, student_id_hint),
    )


def _after_record_url(user, student_id, level: int) -> str:
    """وجهةُ ما بعد التسجيل: الجسيمةُ إلى اللجنة لمن يفتحها، وإلّا ملفُّ الطالب.

    المشرفُ الإداريّ يسجّل الدرجتين الثالثة والرابعة ولا يدخل صفحةَ اللجنة،
    فتحويلُه إليها كان يُريه «غير مصرّح» بعد حفظٍ ناجح. والإحالةُ نفسُها
    تتمّ في `create_infraction` أيّاً كانت الوجهة.
    """
    if level >= 3 and can_open(user, "behavior:committee"):
        return reverse("behavior:committee")
    return reverse("behavior:student_profile", kwargs={"student_id": student_id})


def _quick_log_context(request, school, preselected_student_id=""):
    """Context مشترك لنموذج التسجيل السريع — يُظهر طلاب المعلم فقط، وطلبةَ جناح المشرف."""
    students = _get_scoped_students(request, school)
    return {
        "students": students,
        "levels": BehaviorInfraction.LEVELS,
        "violation_categories": ViolationCategory.objects.filter(
            is_active=True, code__regex=r"^\d+-\d+$"
        ).order_by("degree", "code"),
        "preselected_student_id": str(preselected_student_id),
    }


# ── الملف السلوكي للطالب ─────────────────────────────────────
@login_required
@capability_required("behavior.view")
def student_behavior_profile(request, student_id):
    """الملف السلوكي للطالب — جميع مخالفاته ونقاطه المخصومة والمستعادة."""
    school = request.school
    student = get_object_or_404(
        CustomUser,
        id=student_id,
        memberships__school=school,
        memberships__is_active=True,
    )

    # ── تقييد الوصول: المعلم/المنسق يرى طلابه فقط، والمشرفُ طلبةَ جناحه ──
    denied = _deny_unreachable(
        request, student.id, "هذا الطالب ليس من طلابك — لا يمكنك عرض ملفه السلوكي."
    )
    if denied:
        return denied

    context = BehaviorService.get_student_profile(student)
    context["student"] = student
    context["can_report"] = BehaviorPermissions.can_report(request.user)
    context["is_committee"] = BehaviorPermissions.is_committee(request.user)
    context["can_summon"] = BehaviorPermissions.can_summon(request.user)
    # نماذجُ الإنذار والتعهّد لإدارة المخالفات — رابطٌ لا يُفتح لصاحبه لا يُعرض له.
    context["can_print_forms"] = has_capability(request.user, "behavior.manage")
    return render(request, "behavior/student_profile.html", context)


# ── لجنة الضبط السلوكي ───────────────────────────────────────
@login_required
@capability_required("behavior.committee")
def committee_dashboard(request):
    """لوحة لجنة الضبط السلوكي — المخالفات الجسيمة من الدرجة 3 و4."""
    if not BehaviorPermissions.is_committee(request.user):
        return HttpResponseForbidden("ليس لديك صلاحية الوصول إلى هذه الصفحة.")
    school = request.school
    context = BehaviorService.get_committee_data(school)
    # القضايا المفتوحة حمراءُ متى وُجدت واحدة، وخضراءُ حين تُحلّ كلُّها.
    context["open_tone"] = "red" if context["stats"]["open_count"] else "green"
    return render(request, "behavior/committee.html", context)


@login_required
@capability_required("behavior.committee")
def committee_decision(request, infraction_id):
    """تسجيل قرار لجنة الضبط السلوكي في مخالفة جسيمة."""
    if not BehaviorPermissions.is_committee(request.user):
        messages.error(request, "غير مسموح.")
        return redirect("behavior:committee")

    school = request.school
    infraction = get_object_or_404(
        BehaviorInfraction, id=infraction_id, level__in=[3, 4], school=school
    )
    if request.method == "POST":
        # نظام النقاط ملغى — restore_pts=0 دائماً
        msg, level = BehaviorService.apply_committee_decision(
            infraction=infraction,
            decision=request.POST.get("decision"),
            action=request.POST.get("action_taken", "").strip(),
            restore_pts=0,
            reason="",
            approved_by=request.user,
            suspension_type=request.POST.get("suspension_type", "internal"),
            suspension_days=int(request.POST.get("suspension_days", 1) or 1),
        )
        getattr(messages, level)(request, msg)
        return redirect("behavior:committee")

    return render(
        request,
        "behavior/committee_decision.html",
        {
            "infraction": infraction,
            "escalation_steps": infraction.get_escalation_steps(),
        },
    )


# ── تقرير سلوكي دوري ─────────────────────────────────────────
def _report_year(request):
    """عامُ التقرير: `?year=` لغير المقيَّد كما كان، والمقيَّدُ على العام الجاري دائماً —
    فجناحُه يُحسب على العام الجاري، ولا يوسّع عامٌ مضى نطاقَه."""
    requested = request.GET.get("year")
    return student_scope_for(request).year_for(requested, "") or academic_year_for(request)


@login_required
@capability_required("behavior.record")
def behavior_report(request, student_id):
    """التقرير السلوكي الدوري للطالب — مع إمكانية الإرسال لولي الأمر."""
    if not BehaviorPermissions.can_report(request.user) and not request.user.is_superuser:
        return HttpResponseForbidden("ليس لديك صلاحية.")

    school = request.school
    student = get_object_or_404(
        CustomUser,
        id=student_id,
        memberships__school=school,
        memberships__is_active=True,
    )

    # ── تقييد الوصول: المعلم/المنسق يرى طلابه فقط، والمشرفُ طلبةَ جناحه ──
    denied = _deny_unreachable(request, student.id, "هذا الطالب ليس من طلابك.")
    if denied:
        return denied
    year = _report_year(request)
    period = request.GET.get("period", "full")

    report = BehaviorService.get_student_report_data(student, school, period, year)

    sent_to = []
    if request.method == "POST" and request.POST.get("action") == "send":
        from notifications.services import NotificationService

        for link in report["parent_links"]:
            parent = link.parent
            if parent.email:
                body = (
                    f"ولي أمر الطالب: {parent.full_name}\n\n"
                    f"التقرير السلوكي للطالب: {student.full_name}\n"
                    f"الفترة: {report['period_label']} — {year}\n\n"
                    f"نقاط السلوك: {report['net_score']}/100 ({report['rating']})\n"
                    f"المخالفات: {report['infractions'].count()}\n\n"
                    f"{school.name}"
                )
                try:
                    NotificationService.deliver_email(
                        user=parent,
                        school=school,
                        subject=f"التقرير السلوكي — {student.full_name} — {report['period_label']}",
                        body_text=body,
                        student=student,
                        notif_type="behavior",
                        sent_by=request.user,
                    )
                    sent_to.append(parent.full_name)
                except Exception as e:
                    # [PII-11] سجّل معرّف ولي الأمر لا بريده
                    logger.error("behavior_report: email failed for parent id=%s: %s", parent.id, e)
        if sent_to:
            messages.success(request, f"تم إرسال التقرير لـ: {', '.join(sent_to)}")
        else:
            messages.warning(request, "لا يوجد بريد إلكتروني مسجَّل لأولياء الأمور.")
        return _behavior_report_redirect(request, student.id, year, period)

    return render(
        request,
        "behavior/behavior_report.html",
        {
            "student": student,
            "year": year,
            "period": period,
            "sent_to": sent_to,
            "period_choices": PERIOD_CHOICES,
            "report_subtitle": f"{student.full_name} · {report['period_label']} · {year}",
            **report,
        },
    )


# ── تقرير إحصائي ─────────────────────────────────────────────
_STATS_ALLOWED_ROLES = BEHAVIOR_COMMITTEE | BEHAVIOR_VIEW_ALL | BEHAVIOR_STATS_TEACHING


@login_required
@capability_required("behavior.statistics")
def behavior_statistics(request):
    """التقرير الإحصائي السلوكي — القيادة/اللجنة ترى الكل، المعلم/المنسق يرى طلابه فقط."""
    role = request.user.get_role()
    school = request.school
    year = request.GET.get("year") or academic_year_for(request)

    # المعلم/المنسق/معلم ESE → إحصائيات مقيّدة بطلابهم فقط
    if role in BEHAVIOR_STATS_TEACHING:
        student_ids = get_teacher_student_ids(request.user)
        stats = BehaviorService.get_statistics_scoped(school, student_ids=student_ids)
        stats["is_scoped"] = True
    else:
        # القيادة ولجنة الضبط والأخصائيون → كل طلاب المدرسة
        _full_access = BEHAVIOR_MANAGE | BEHAVIOR_VIEW_ALL | BEHAVIOR_COMMITTEE
        if role not in _full_access and not request.user.is_superuser:
            return HttpResponseForbidden("للمدير ونائبيه واللجنة فقط.")
        stats = BehaviorService.get_statistics(school)
        stats["is_scoped"] = False

    stats["year"] = year
    stats.update(_statistics_presentation(stats))
    return render(request, "behavior/statistics.html", stats)


def _statistics_presentation(stats: dict) -> dict:
    """ألوانُ صفحة الإحصاءات ونصوصُها المركّبة.

    نسبةُ الحلّ خضراءُ من 80% وكهرمانيّةٌ من 50% وحمراءُ دونها — العتباتُ التي
    كانت في القالب. وهي محسوبةٌ على **كلّ** مخالفات العام لا الجسيمة وحدها
    (`resolved_pct` في الخدمة)، فالاسمُ يقول ذلك.

    وشريطُ الشهر كان يُقاس على عشرين ثابتة فيفيض فوق 100% في شهرٍ مزدحم؛
    فصار يُقاس على أكثر الشهور.
    """
    pct = stats.get("resolved_pct") or 0
    by_level = stats.get("by_level") or {}
    monthly = list(stats.get("monthly") or [])
    peak = max((row["count"] for row in monthly), default=0)
    # تنبيهُ «طلابك فقط» كان شريطاً بألوانٍ ثابتةٍ بين العنوان والأرقام — وهو وصفٌ للصفحة.
    scope = " · طلابُك وحدَهم وفق جدولك الدراسي" if stats.get("is_scoped") else ""
    return {
        "subtitle": f"{stats.get('year')} · QNSA المعيار 2{scope}",
        "severe_count": by_level.get(3, 0) + by_level.get(4, 0),
        "resolved_label": f"{pct}%",
        "resolved_tone": tone_for(pct, SHARE_KPI),
        "monthly_rows": [
            {**row, "share": round(row["count"] * 100 / peak) if peak else 0} for row in monthly
        ],
    }


# ── تصعيد إجراء ──────────────────────────────────────────────
@login_required
@capability_required("behavior.committee")
def escalate_infraction(request, infraction_id):
    """تصعيد المخالفة إلى الخطوة التالية."""
    if not BehaviorPermissions.is_committee(request.user):
        return HttpResponseForbidden("غير مسموح.")
    school = request.school
    infraction = get_object_or_404(BehaviorInfraction, id=infraction_id, school=school)
    if request.method == "POST":
        notes = request.POST.get("notes", "").strip()
        success, msg = BehaviorService.escalate_infraction(
            infraction,
            escalated_by=request.user,
            notes=notes,
        )
        if success:
            messages.success(request, f"⬆️ {msg}")
        else:
            messages.warning(request, msg)
        return redirect("behavior:student_profile", student_id=infraction.student.id)
    return redirect("behavior:committee")


# ── تسجيل إحالة أمنية ────────────────────────────────────────
@login_required
@capability_required("behavior.committee")
def security_referral(request, infraction_id):
    """تسجيل إحالة أمنية لمخالفة من الدرجة الرابعة."""
    if not BehaviorPermissions.is_committee(request.user):
        return HttpResponseForbidden("غير مسموح.")
    school = request.school
    infraction = get_object_or_404(BehaviorInfraction, id=infraction_id, level=4, school=school)

    if request.method == "POST":
        agency = request.POST.get("security_agency", "")
        ref_num = request.POST.get("reference_number", "").strip()
        notes = request.POST.get("security_notes", "").strip()
        success, msg = BehaviorService.record_security_referral(
            infraction,
            agency=agency,
            reference_number=ref_num,
            notes=notes,
            referred_by=request.user,
        )
        if success:
            messages.success(request, f"🔒 {msg}")
        else:
            messages.error(request, msg)
        return redirect("behavior:student_profile", student_id=infraction.student.id)

    from .constants import SECURITY_AGENCIES

    return render(
        request,
        "behavior/security_referral.html",
        {
            "infraction": infraction,
            "agencies": SECURITY_AGENCIES,
        },
    )


# ════════════════════════════════════════════════════════════════
# PDF النماذج
# ════════════════════════════════════════════════════════════════


def _render_behavior_pdf(request, template_name, context, filename, *, kind, student=None):
    """يولّد نموذجَ السلوك ويسجّل توليدَه.

    النماذجُ الفرديّةُ (إنذار، تعهّد، تقرير) تحمل الرقمَ الشخصيَّ كاملاً لأنّها
    تُسلَّم لصاحبها — والتدقيقُ ثمنُ الكمال (`core/privacy.py`). واللائحةُ
    وثيقةُ مدرسةٍ بلا طالب فتُسجَّل بلا رقم.
    """
    from django.template.loader import render_to_string

    from core.audit_export import log_export
    from core.pdf_utils import render_pdf

    log_export(
        request,
        kind,
        rows=1 if student else None,
        full_national_id=student is not None,
        object_id=student.pk if student else "",
        object_repr=f"{kind} — {student.full_name}" if student else kind,
    )
    return render_pdf(render_to_string(template_name, context), filename)


# [PII-08] أسماءُ النماذج الثلاثة تحمل معرّفَ الطالب لا رقمَه الشخصيّ: اسمُ
# الملفّ يبقى في سجلّ تنزيلات المتصفّح وفي مجلّد التنزيلات وفي سجلّات الوكيل —
# مواضعُ لا يبلغها سترُ الشاشة ولا تدقيقُ التصدير. والتقريرُ الشامل على هذا من قبل.


@login_required
@capability_required("behavior.manage")
def infraction_warning_pdf(request, infraction_id):
    """PDF: نموذج تحذير للطالب بسبب مخالفة سلوكية."""
    inf = get_object_or_404(BehaviorInfraction, id=infraction_id, school=request.school)
    ctx = BehaviorService.get_infraction_context(inf)
    ctx["received_by"] = request.user.full_name
    return _render_behavior_pdf(
        request,
        "behavior/pdf/student_warning.html",
        ctx,
        f"warning_{inf.student_id}_{inf.date}.pdf",
        kind="behavior.warning_pdf",
        student=inf.student,
    )


@login_required
@capability_required("behavior.manage")
def infraction_parent_pdf(request, infraction_id):
    """PDF: تعهد ولي الأمر المتعلق بمخالفة سلوكية."""
    inf = get_object_or_404(BehaviorInfraction, id=infraction_id, school=request.school)
    ctx = BehaviorService.get_infraction_context(inf)
    ctx["received_by"] = request.user.full_name
    return _render_behavior_pdf(
        request,
        "behavior/pdf/parent_undertaking.html",
        ctx,
        f"parent_undertaking_{inf.student_id}.pdf",
        kind="behavior.parent_undertaking_pdf",
        student=inf.student,
    )


@login_required
@capability_required("behavior.manage")
def infraction_student_pdf(request, infraction_id):
    """PDF: تعهد الطالب المتعلق بمخالفة سلوكية."""
    inf = get_object_or_404(BehaviorInfraction, id=infraction_id, school=request.school)
    ctx = BehaviorService.get_infraction_context(inf)
    ctx["received_by"] = request.user.full_name
    return _render_behavior_pdf(
        request,
        "behavior/pdf/student_undertaking.html",
        ctx,
        f"student_undertaking_{inf.student_id}.pdf",
        kind="behavior.student_undertaking_pdf",
        student=inf.student,
    )


@login_required
@capability_required("behavior.summon_parent")
def summon_parent(request, student_id=None):
    """استدعاء ولي أمر طالب — إرسال إشعار رسمي (إداري فقط)."""
    school = request.school
    if not school:
        return HttpResponseForbidden("لم يتم تعيينك في مدرسة")

    from core.models.academic import ParentStudentLink

    SUMMON_CATEGORIES = [
        ("behavior", "سلوكي"),
        ("academic", "أكاديمي"),
        ("attendance", "حضور وغياب"),
        ("general", "عام"),
    ]
    URGENCY_LEVELS = [
        ("normal", "عادي"),
        ("urgent", "مستعجل"),
        ("emergency", "طارئ"),
    ]
    MEETING_PLACES = [
        ("principal_office", "مكتب المدير"),
        ("counseling", "مكتب الإرشاد"),
        ("meeting_room", "غرفة الاجتماعات"),
        ("other", "أخرى"),
    ]

    if request.method == "POST":
        sid = request.POST.get("student_id") or student_id
        reason = request.POST.get("reason", "").strip()
        category = request.POST.get("category", "behavior")
        urgency = request.POST.get("urgency", "normal")
        summon_date = request.POST.get("summon_date", "")
        summon_time = request.POST.get("summon_time", "")
        meeting_place = request.POST.get("meeting_place", "")
        meeting_place_other = request.POST.get("meeting_place_other", "").strip()

        if not sid or not reason:
            messages.error(request, "يجب اختيار الطالب وكتابة السبب")
            return redirect("behavior:summon_parent")

        _require_in_wing(request, sid)
        student = get_object_or_404(CustomUser, pk=sid)

        from notifications.hub import NotificationHub

        # بناء عنوان الإشعار حسب الاستعجال
        urgency_label = dict(URGENCY_LEVELS).get(urgency, "عادي")
        category_label = dict(SUMMON_CATEGORIES).get(category, "عام")
        prefix = "🔴 " if urgency == "emergency" else "🟡 " if urgency == "urgent" else ""
        title = f"{prefix}استدعاء ولي أمر — {student.full_name}"

        # بناء نص الإشعار
        place_label = dict(MEETING_PLACES).get(meeting_place, "")
        if meeting_place == "other" and meeting_place_other:
            place_label = meeting_place_other

        body_parts = [
            f"التصنيف: {category_label}",
            f"درجة الاستعجال: {urgency_label}",
            f"السبب: {reason}",
        ]
        if summon_date:
            date_str = summon_date
            if summon_time:
                date_str += f" الساعة {summon_time}"
            body_parts.append(f"الموعد المطلوب: {date_str}")
        if place_label:
            body_parts.append(f"مكان الاجتماع: {place_label}")
        body_parts.append(f"من: {request.user.full_name}")
        body = "\n".join(body_parts)

        # [B4-PRE3] الاستدعاء نفسه هو الحدث — لا طفرة أعمال سابقة له.
        #
        # فالحدّ يضمّ أثره في القاعدة: إشعارات المنصّة لكل وليّ أمر تُكتب أو
        # لا تُكتب معاً، ولا يخرج شيء خارجيّ إلا بعد أن تلتزم كلّها.
        with transaction.atomic():
            result = NotificationHub.dispatch_to_parents(
                event_type="parent_summon",
                school=school,
                student=student,
                title=title,
                body=body,
                related_url=f"/behavior/student/{student.pk}/",
                sent_by=request.user,
            )

        count = result.get("in_app", 0)
        if count:
            messages.success(request, f"تم إرسال الاستدعاء لـ {count} ولي أمر")
        else:
            messages.warning(request, "لم يُعثر على أولياء أمور مربوطين بهذا الطالب")

        return redirect("behavior:summon_parent")

    # GET — نموذج الاستدعاء (طلاب المعلم/المنسق فقط)
    students = _get_scoped_students(request, school)

    selected_student = None
    student_context = {}
    if student_id:
        _require_in_wing(request, student_id)
        selected_student = CustomUser.objects.filter(pk=student_id).first()
    if selected_student:
        # معلومات سياقية عن الطالب
        score_data = BehaviorService.get_student_score(selected_student)
        parent_links = ParentStudentLink.objects.filter(
            student=selected_student, school=school
        ).select_related("parent")
        active_infractions = BehaviorInfraction.objects.filter(
            student=selected_student, is_resolved=False
        ).count()
        # بيانات أولياء الأمور مع أرقام الهواتف
        parents_info = []
        for link in parent_links:
            parents_info.append(
                {
                    "name": link.parent.full_name,
                    "phone": link.parent.get_phone_decrypted() or "",
                    "relationship": link.get_relationship_display(),
                    "is_primary": link.is_primary,
                }
            )
        # «مؤشرُ السلوك» ليس نقاطاً مخصومة (النظامُ ملغى): يُحسب في
        # `get_student_score` من عدد المخالفات ودرجاتها، فيبقى رقماً حقيقيّاً.
        behavior_score = score_data.get("net_score", 100)
        student_context = {
            "behavior_score": behavior_score,
            # العتباتُ التي كانت في القالب: 80 فأكثر أخضر، 50 فأكثر كهرمانيّ.
            "behavior_score_tone": tone_for(behavior_score, SHARE_KPI),
            "active_infractions": active_infractions,
            "active_infractions_tone": "red" if active_infractions else "green",
            "parents_info": parents_info,
            # لا وليَّ أمرٍ مربوطاً = لا إشعار يصل؛ فالبطاقةُ حمراء.
            "parents_tone": "maroon" if parents_info else "red",
        }

    return render(
        request,
        "behavior/summon_parent.html",
        {
            "students": students,
            "selected_student": selected_student,
            "school": school,
            "categories": SUMMON_CATEGORIES,
            "urgency_levels": URGENCY_LEVELS,
            "meeting_places": MEETING_PLACES,
            "sender": request.user,
            "summon_subtitle": (
                f"{selected_student.full_name} · {school.name}" if selected_student else school.name
            ),
            **student_context,
        },
    )


@login_required
@capability_required("behavior.view")
def student_behavior_pdf(request, student_id):
    """تقرير سلوكي للطالب — A4 للطباعة (WeasyPrint)"""
    school = request.school
    student = get_object_or_404(
        CustomUser,
        id=student_id,
        memberships__school=school,
        memberships__is_active=True,
    )

    # تقييد الوصول: المعلم/المنسق يرى طلابه فقط، والمشرفُ طلبةَ جناحه
    denied = _deny_unreachable(
        request, student.id, "هذا الطالب ليس من طلابك — لا يمكنك طباعة تقريره السلوكي."
    )
    if denied:
        return denied

    year = _report_year(request)
    period = request.GET.get("period", "full")

    report = BehaviorService.get_student_report_data(student, school, period, year)

    # جلب بيانات الفصل الدراسي
    from core.models import StudentEnrollment

    enrollment = (
        StudentEnrollment.objects.filter(
            student=student, class_group__school=school, is_active=True
        )
        .select_related("class_group")
        .first()
    )
    cg = enrollment.class_group if enrollment else None

    ctx = {
        "student": student,
        "school": school,
        "class_name": str(cg) if cg else None,
        "student_grade": cg.grade.removeprefix("G") if cg else None,
        "student_section": cg.section if cg else None,
        "academic_year": year,
        "generated_at": _tz.now(),
        **report,
    }
    # [PII-08] لا نضع الرقم الشخصي في اسم الملف (يظهر في سجل التنزيلات والوكيل)
    filename = f"behavior_report_{student.id}_{year}.pdf"
    return _render_behavior_pdf(
        request,
        "behavior/pdf/student_report.html",
        ctx,
        filename,
        kind="behavior.student_report_pdf",
        student=student,
    )


@login_required
def behavior_policy_pdf(request):
    """يخدم لائحة السلوك كملف PDF ثابت من static/docs/.

    كان لهذا الاسم تعريفان في الوحدة: واحدٌ يُصيّر `behavior/pdf/policy_doc.html`
    بترويسة المدرسة (أُضيف في #189 ليُعطي القالبَ اليتيمَ مساراً)، وهذا. وبايثون
    يُبقي آخرَ تعريفٍ في الاسم، فكان الأوّلُ ميّتاً منذ كُتب ولا يبلغه مسار —
    حُذف (2026-09-14). والقالبُ `policy_doc.html` حُذف معه (كان يتيماً — لا مسارَ يصله؛ الملفُّ الثابت هو المعتمَد) حتى يقرّر
    المالكُ: يُحذف، أو يحلّ محلَّ هذا الملفّ الثابت.
    """
    import os

    pdf_path = os.path.join(settings.BASE_DIR, "static", "docs", "behavior_policy_2025-2026.pdf")
    if not os.path.exists(pdf_path):
        raise Http404("ملف اللائحة غير موجود")
    return FileResponse(
        open(pdf_path, "rb"),
        content_type="application/pdf",
        as_attachment=False,
        filename="behavior_policy_2025-2026.pdf",
    )
