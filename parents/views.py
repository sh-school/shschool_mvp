"""
parents/views.py — thin views (Phase 4)
بوابة ولي الأمر — درجات + غياب
"""

import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import ConsentRecord, CustomUser, Membership, ParentStudentLink, StudentEnrollment
from behavior.models import BehaviorInfraction, BehaviorPointRecovery
from operations.models import AbsenceAlert

from .services import ParentService


def _get_parent_school(request):
    """يُعيد school لولي الأمر أو None"""
    if request.user.is_superuser:
        return request.user.get_school()
    m = request.user.get_parent_membership()
    return m.school if m else None


# ── لوحة تحكم ولي الأمر ─────────────────────────────────────


@login_required
def parent_dashboard(request):
    """لوحة تحكم ولي الأمر — بيانات أبنائه من درجات وغياب."""
    school = _get_parent_school(request)
    if not school:
        return HttpResponse("هذه الصفحة لأولياء الأمور فقط", status=403)

    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)
    children = ParentService.get_children_data(request.user, school, year)

    return render(
        request,
        "parents/dashboard.html",
        {
            "children": children,
            "year": year,
            "school": school,
        },
    )


# ── درجات الطالب ────────────────────────────────────────────


@login_required
def student_grades(request, student_id):
    """درجات الطالب — لولي الأمر بعد التحقق من صلاحية العرض."""
    school = _get_parent_school(request) or request.user.get_school()
    student = get_object_or_404(CustomUser, id=student_id)
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)

    link = ParentStudentLink.objects.filter(
        parent=request.user, student=student, school=school
    ).first()
    if not link and not request.user.is_superuser:
        return HttpResponse("غير مسموح", status=403)
    if link and not link.can_view_grades:
        return HttpResponse("ليس لديك صلاحية عرض الدرجات", status=403)

    data = ParentService.get_student_grades(student, school, year)
    enrollment = (
        StudentEnrollment.objects.filter(student=student, is_active=True)
        .select_related("class_group")
        .first()
    )

    return render(
        request,
        "parents/student_grades.html",
        {
            "student": student,
            "link": link,
            "year": year,
            "enrollment": enrollment,
            **data,
        },
    )


# ── غياب الطالب ─────────────────────────────────────────────


@login_required
def student_attendance(request, student_id):
    """سجل غياب الطالب — لولي الأمر مع تنبيهات الغياب المتكرر."""
    school = _get_parent_school(request) or request.user.get_school()
    student = get_object_or_404(CustomUser, id=student_id)
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)

    link = ParentStudentLink.objects.filter(
        parent=request.user, student=student, school=school
    ).first()
    if not link and not request.user.is_superuser:
        return HttpResponse("غير مسموح", status=403)
    if link and not link.can_view_attendance:
        return HttpResponse("ليس لديك صلاحية عرض الغياب", status=403)

    period = request.GET.get("period", "30")
    try:
        days = int(period)
    except ValueError:
        days = 30

    data = ParentService.get_student_attendance(student, school, days)
    enrollment = (
        StudentEnrollment.objects.filter(student=student, is_active=True)
        .select_related("class_group")
        .first()
    )
    alerts = AbsenceAlert.objects.filter(student=student, school=school).order_by("-created_at")[:5]

    return render(
        request,
        "parents/student_attendance.html",
        {
            "student": student,
            "link": link,
            "enrollment": enrollment,
            "alerts": alerts,
            "period": period,
            "year": year,
            "period_choices": ["7", "14", "30", "60"],
            **data,
        },
    )


# ── سلوك الأبناء ──────────────────────────────────────────────


@login_required
def parent_behavior(request):
    """ملخص السلوك لأبناء ولي الأمر."""
    school = _get_parent_school(request)
    if not school:
        return HttpResponse("هذه الصفحة لأولياء الأمور فقط", status=403)

    links = ParentStudentLink.objects.filter(
        parent=request.user, school=school
    ).select_related("student")

    children_behavior = []
    for link in links:
        infractions = BehaviorInfraction.objects.filter(
            school=school, student=link.student
        ).select_related("violation_category").order_by("-date")

        total_points = sum(i.points_deducted for i in infractions)
        recovered = BehaviorPointRecovery.objects.filter(
            infraction__school=school, infraction__student=link.student
        ).count()
        recovered_points = sum(
            r.points_restored
            for r in BehaviorPointRecovery.objects.filter(
                infraction__school=school, infraction__student=link.student
            )
        )

        behavior_score = max(0, 100 - total_points + recovered_points)

        children_behavior.append({
            "student": link.student,
            "infractions": infractions[:10],
            "total_infractions": infractions.count(),
            "total_points_deducted": total_points,
            "recovered_points": recovered_points,
            "behavior_score": min(100, behavior_score),
            "unresolved": infractions.filter(is_resolved=False).count(),
        })

    return render(request, "parents/behavior.html", {
        "children_behavior": children_behavior,
        "school": school,
    })


# ══════════════════════════════════════════════════════════════
# إدارة الربط (للمدير فقط)
# ══════════════════════════════════════════════════════════════


@login_required
def manage_parent_links(request):
    """صفحة المدير: ربط أولياء الأمور بأبنائهم"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)
    search = request.GET.get("q", "").strip()
    rel_filter = request.GET.get("rel", "").strip()

    # جميع ارتباطات المدرسة
    links = (
        ParentStudentLink.objects.filter(school=school)
        .select_related("parent", "student")
        .order_by("student__full_name", "parent__full_name")
    )

    total_count = links.count()

    # فلترة بالبحث
    if search:
        links = links.filter(
            Q(parent__full_name__icontains=search)
            | Q(student__full_name__icontains=search)
            | Q(parent__national_id__icontains=search)
            | Q(student__national_id__icontains=search)
        )

    # فلترة بصلة القرابة
    if rel_filter:
        links = links.filter(relationship=rel_filter)

    # إحصائيات
    parent_count = links.values("parent").distinct().count()
    student_count = links.values("student").distinct().count()

    # Pagination
    paginator = Paginator(links, 25)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    ctx = {
        "page_obj": page_obj,
        "total_count": total_count,
        "parent_count": parent_count,
        "student_count": student_count,
        "search": search,
        "rel_filter": rel_filter,
        "year": year,
        "RELATIONSHIP": ParentStudentLink.RELATIONSHIP,
    }

    # HTMX → partial فقط
    if request.headers.get("HX-Request"):
        return render(request, "parents/partials/links_table.html", ctx)

    # قائمة الطلاب للـ dropdown
    student_ids = StudentEnrollment.objects.filter(
        class_group__school=school,
        class_group__academic_year=year,
        is_active=True,
    ).values_list("student_id", flat=True)
    ctx["students"] = CustomUser.objects.filter(id__in=student_ids).order_by("full_name")

    # قائمة أولياء الأمور
    parent_ids = Membership.objects.filter(
        school=school, is_active=True, role__name="parent"
    ).values_list("user_id", flat=True)
    ctx["parents"] = CustomUser.objects.filter(id__in=parent_ids).order_by("full_name")

    return render(request, "parents/manage_links.html", ctx)


@login_required
def add_parent_link(request):
    """إضافة ربط جديد بين ولي أمر وطالب — للمدير فقط."""
    if request.method != "POST" or not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    parent_id = request.POST.get("parent_id")
    student_id = request.POST.get("student_id")
    rel = request.POST.get("relationship", "father")

    parent = get_object_or_404(CustomUser, id=parent_id)
    student = get_object_or_404(CustomUser, id=student_id)

    link, created = ParentStudentLink.objects.get_or_create(
        school=school,
        parent=parent,
        student=student,
        defaults={
            "relationship": rel,
            "can_view_grades": True,
            "can_view_attendance": True,
        },
    )
    if created:
        messages.success(request, f"✓ تم ربط {parent.full_name} بـ {student.full_name}")
    else:
        messages.warning(request, f"الربط موجود مسبقاً: {parent.full_name} ← {student.full_name}")

    return redirect("manage_parent_links")


@login_required
def remove_parent_link(request, link_id):
    """حذف ربط ولي الأمر بالطالب — للمدير فقط."""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    link = get_object_or_404(ParentStudentLink, id=link_id, school=school)
    name = f"{link.parent.full_name} ← {link.student.full_name}"
    link.delete()
    messages.success(request, f"تم حذف الربط: {name}")
    return redirect("manage_parent_links")


# ── صفحة الموافقة على معالجة البيانات (PDPPL) ────────────────

DATA_TYPES = [
    ("health", "البيانات الصحية"),
    ("behavior", "بيانات السلوك"),
    ("grades", "الدرجات والتقييمات"),
    ("attendance", "الحضور والغياب"),
    ("transport", "بيانات النقل"),
]


@login_required
def consent_view(request):
    """ولي الأمر يمنح / يسحب الموافقة على أنواع البيانات"""
    if not request.user.has_role("parent") and not request.user.is_superuser:
        return HttpResponse("هذه الصفحة لأولياء الأمور فقط.", status=403)

    school = request.user.get_school()
    links = ParentStudentLink.objects.filter(parent=request.user, school=school).select_related(
        "student"
    )

    if request.method == "POST":
        for link in links:
            for dt, _ in DATA_TYPES:
                is_given = request.POST.get(f"consent_{link.student_id}_{dt}") == "1"
                obj, created = ConsentRecord.objects.get_or_create(
                    parent=request.user,
                    student=link.student,
                    school=school,
                    data_type=dt,
                    defaults={
                        "is_given": is_given,
                        "method": "digital",
                        "recorded_by": request.user,
                    },
                )
                if not created and obj.is_given != is_given:
                    obj.is_given = is_given
                    obj.withdrawn_at = None if is_given else timezone.now()
                    obj.save(update_fields=["is_given", "withdrawn_at"])

        if not request.user.consent_given_at:
            request.user.consent_given_at = timezone.now()
            request.user.save(update_fields=["consent_given_at"])

        messages.success(request, "تم حفظ إعدادات الموافقة بنجاح.")
        return redirect("parent_dashboard")

    # Batch load all consent records (avoid N+1)
    student_ids = [link.student_id for link in links]
    all_consents = ConsentRecord.objects.filter(
        parent=request.user, student_id__in=student_ids
    ).values_list("student_id", "data_type", "is_given")
    consent_map = {(str(sid), dt): given for sid, dt, given in all_consents}
    consent_data = {
        str(link.student_id): {
            dt: consent_map.get((str(link.student_id), dt), True) for dt, _ in DATA_TYPES
        }
        for link in links
    }

    import json as _json

    return render(
        request,
        "parents/consent.html",
        {
            "links": links,
            "data_types": DATA_TYPES,
            "consent_data_json": _json.dumps(consent_data),
            "school": school,
        },
    )


# ── Push Subscription endpoints (VAPID) ─────────────────────

from notifications.models import PushSubscription


@login_required
@require_POST
def push_subscribe(request):
    """تسجيل اشتراك Push Notification للمستخدم على متصفحه."""
    try:
        data = json.loads(request.body)
        endpoint = data.get("endpoint", "").strip()
        p256dh = data.get("keys", {}).get("p256dh", "").strip()
        auth = data.get("keys", {}).get("auth", "").strip()
        if not all([endpoint, p256dh, auth]):
            return JsonResponse({"error": "بيانات ناقصة"}, status=400)
        school = _get_parent_school(request) or request.user.get_school()
        if not school:
            return JsonResponse({"error": "مدرسة غير معروفة"}, status=400)
        _, created = PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={
                "user": request.user,
                "school": school,
                "p256dh": p256dh,
                "auth": auth,
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:300],
                "is_active": True,
            },
        )
        return JsonResponse({"status": "subscribed", "new": created})
    except (KeyError, ValueError, TypeError, OSError) as e:
        logger.exception("فشل تسجيل اشتراك Push لولي الأمر: %s", e)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def push_unsubscribe(request):
    """إلغاء اشتراك Push Notification للمستخدم من متصفحه."""
    try:
        endpoint = json.loads(request.body).get("endpoint", "")
        PushSubscription.objects.filter(endpoint=endpoint, user=request.user).update(
            is_active=False
        )
        return JsonResponse({"status": "unsubscribed"})
    except (KeyError, ValueError, TypeError, OSError) as e:
        logger.exception("فشل إلغاء اشتراك Push لولي الأمر: %s", e)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def push_vapid_key(request):
    """يُعيد المفتاح العام VAPID لتفعيل Push Notifications في المتصفح."""
    return JsonResponse({"publicKey": getattr(settings, "VAPID_PUBLIC_KEY_B64", "")})
