"""
parents/views.py — thin views (Phase 4)
بوابة ولي الأمر — درجات + غياب
"""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from core.models import ConsentRecord, CustomUser, Membership, ParentStudentLink, StudentEnrollment
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
    school = _get_parent_school(request)
    if not school:
        return HttpResponse("هذه الصفحة لأولياء الأمور فقط", status=403)

    year = request.GET.get("year", "2025-2026")
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
    school = _get_parent_school(request) or request.user.get_school()
    student = get_object_or_404(CustomUser, id=student_id)
    year = request.GET.get("year", "2025-2026")

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
    school = _get_parent_school(request) or request.user.get_school()
    student = get_object_or_404(CustomUser, id=student_id)
    year = request.GET.get("year", "2025-2026")

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


# ══════════════════════════════════════════════════════════════
# إدارة الربط (للمدير فقط)
# ══════════════════════════════════════════════════════════════


@login_required
def manage_parent_links(request):
    """صفحة المدير: ربط أولياء الأمور بأبنائهم"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year = request.GET.get("year", "2025-2026")
    search = request.GET.get("q", "").strip()

    # أولياء الأمور الحاليون
    links = (
        ParentStudentLink.objects.filter(school=school)
        .select_related("parent", "student")
        .order_by("student__full_name", "parent__full_name")
    )

    if search:
        links = links.filter(
            Q(parent__full_name__icontains=search)
            | Q(student__full_name__icontains=search)
            | Q(parent__national_id__icontains=search)
            | Q(student__national_id__icontains=search)
        )

    # قائمة الطلاب للـ dropdown
    student_ids = StudentEnrollment.objects.filter(
        class_group__school=school,
        class_group__academic_year=year,
        is_active=True,
    ).values_list("student_id", flat=True)
    students = CustomUser.objects.filter(id__in=student_ids).order_by("full_name")

    # قائمة أولياء الأمور
    parent_ids = Membership.objects.filter(
        school=school, is_active=True, role__name="parent"
    ).values_list("user_id", flat=True)
    parents = CustomUser.objects.filter(id__in=parent_ids).order_by("full_name")

    return render(
        request,
        "parents/manage_links.html",
        {
            "links": links,
            "students": students,
            "parents": parents,
            "search": search,
            "year": year,
            "RELATIONSHIP": ParentStudentLink.RELATIONSHIP,
        },
    )


@login_required
def add_parent_link(request):
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

    return render(
        request,
        "parents/consent.html",
        {
            "links": links,
            "data_types": DATA_TYPES,
            "consent_data": consent_data,
            "school": school,
        },
    )


# ── Push Subscription endpoints (VAPID) ─────────────────────

from django.conf import settings

from notifications.models import PushSubscription


@login_required
@csrf_exempt
def push_subscribe(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
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
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@csrf_exempt
def push_unsubscribe(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    try:
        endpoint = json.loads(request.body).get("endpoint", "")
        PushSubscription.objects.filter(endpoint=endpoint, user=request.user).update(
            is_active=False
        )
        return JsonResponse({"status": "unsubscribed"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def push_vapid_key(request):
    return JsonResponse({"publicKey": getattr(settings, "VAPID_PUBLIC_KEY_B64", "")})
