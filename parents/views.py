"""
parents/views.py — thin views (Phase 4)
بوابة ولي الأمر — درجات + غياب
"""

import json
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import CharField, Exists, F, Func, OuterRef, Q, Subquery, Value
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from behavior.models import BehaviorInfraction
from core.models import (
    ConsentRecord,
    CustomUser,
    Membership,
    ParentStudentLink,
    Role,
    StudentEnrollment,
)
from core.permissions import PARENT_PORTAL, PARENT_PORTAL_ADMIN, role_required
from core.sorting import apply_sort, arabic_key
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
@role_required(PARENT_PORTAL)
def parent_dashboard(request):
    """لوحة تحكم ولي الأمر — بيانات أبنائه من درجات وغياب."""
    school = _get_parent_school(request)
    if not school:
        return HttpResponse("هذه الصفحة لأولياء الأمور فقط", status=403)

    year = request.GET.get("year") or academic_year_for(request)
    today = timezone.now().date()
    children = ParentService.get_children_data(request.user, school, year)

    # ✅ v5.4: ParentService.enrich_children_dashboard — 4 batch queries في service layer
    children = ParentService.enrich_children_dashboard(children, school, today=today)

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
@role_required(PARENT_PORTAL)
def student_grades(request, student_id):
    """درجات الطالب — لولي الأمر بعد التحقق من صلاحية العرض."""
    school = _get_parent_school(request) or request.user.get_school()
    student = get_object_or_404(
        CustomUser,
        id=student_id,
        memberships__school=school,
        memberships__is_active=True,
    )
    year = request.GET.get("year") or academic_year_for(request)

    link = ParentStudentLink.objects.filter(
        parent=request.user, student=student, school=school
    ).first()
    if not link and not request.user.is_superuser:
        return HttpResponse("غير مسموح", status=403)
    if link and not link.can_view_grades:
        return HttpResponse("ليس لديك صلاحية عرض الدرجات", status=403)

    data = ParentService.get_student_grades(student, school, year)
    enrollment = StudentEnrollment.objects.current_of(student)

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
@role_required(PARENT_PORTAL)
def student_attendance(request, student_id):
    """سجل غياب الطالب — لولي الأمر مع تنبيهات الغياب المتكرر."""
    school = _get_parent_school(request) or request.user.get_school()
    student = get_object_or_404(
        CustomUser,
        id=student_id,
        memberships__school=school,
        memberships__is_active=True,
    )
    year = request.GET.get("year") or academic_year_for(request)

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
    enrollment = StudentEnrollment.objects.current_of(student)
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


# ── درجات كل الأبناء ─────────────────────────────────────────


@login_required
@role_required(PARENT_PORTAL)
def parent_all_grades(request):
    """ملخص درجات كل أبناء ولي الأمر."""
    school = _get_parent_school(request)
    if not school:
        return HttpResponse("هذه الصفحة لأولياء الأمور فقط", status=403)

    year = request.GET.get("year") or academic_year_for(request)
    links = ParentStudentLink.objects.filter(parent=request.user, school=school).select_related(
        "student"
    )

    children_grades = []
    for link in links:
        if not link.can_view_grades:
            continue
        enrollment = StudentEnrollment.objects.current_of(link.student)
        data = ParentService.get_student_grades(link.student, school, year)
        children_grades.append(
            {
                "student": link.student,
                "enrollment": enrollment,
                **data,
            }
        )

    return render(
        request,
        "parents/all_grades.html",
        {
            "children_grades": children_grades,
            "school": school,
            "year": year,
        },
    )


# ── حضور كل الأبناء ─────────────────────────────────────────


@login_required
@role_required(PARENT_PORTAL)
def parent_all_attendance(request):
    """ملخص حضور كل أبناء ولي الأمر."""
    school = _get_parent_school(request)
    if not school:
        return HttpResponse("هذه الصفحة لأولياء الأمور فقط", status=403)

    period = request.GET.get("period", "30")
    try:
        days = int(period)
    except ValueError:
        days = 30

    links = ParentStudentLink.objects.filter(parent=request.user, school=school).select_related(
        "student"
    )

    children_attendance = []
    for link in links:
        if not link.can_view_attendance:
            continue
        enrollment = StudentEnrollment.objects.current_of(link.student)
        data = ParentService.get_student_attendance(link.student, school, days)
        alerts = AbsenceAlert.objects.filter(student=link.student, school=school).order_by(
            "-created_at"
        )[:3]
        children_attendance.append(
            {
                "student": link.student,
                "enrollment": enrollment,
                "alerts": alerts,
                **data,
            }
        )

    return render(
        request,
        "parents/all_attendance.html",
        {
            "children_attendance": children_attendance,
            "school": school,
            "period": period,
            "period_choices": ["7", "14", "30", "60"],
        },
    )


# ── سلوك الأبناء ──────────────────────────────────────────────


@login_required
@role_required(PARENT_PORTAL)
def parent_behavior(request):
    """ملخص السلوك لأبناء ولي الأمر."""
    school = _get_parent_school(request)
    if not school:
        return HttpResponse("هذه الصفحة لأولياء الأمور فقط", status=403)

    # يُقصَر على الأبناء المسموح لولي الأمر برؤية سلوكهم (اتساقاً مع الدرجات/الحضور — PDPPL)
    links = ParentStudentLink.objects.filter(
        parent=request.user, school=school, can_view_behavior=True
    ).select_related("student")

    # نظام النقاط ملغى — نعرض عدد المخالفات فقط
    children_behavior = []
    for link in links:
        infractions = (
            BehaviorInfraction.objects.filter(school=school, student=link.student)
            .select_related("violation_category")
            .order_by("-date")
        )
        children_behavior.append(
            {
                "student": link.student,
                "infractions": infractions[:10],
                "total_infractions": infractions.count(),
                "unresolved": infractions.filter(is_resolved=False).count(),
            }
        )

    return render(
        request,
        "parents/behavior.html",
        {
            "children_behavior": children_behavior,
            "school": school,
        },
    )


# ══════════════════════════════════════════════════════════════
# إدارة الربط (للمدير فقط)
# ══════════════════════════════════════════════════════════════


# حقولُ الفرز المسموحة — `?sort=` نصٌّ من المستخدم لا يبلغ ORM إلّا مصفّى.
LINK_SORTS = {
    "student": ("student_key", "parent_key"),
    "parent": ("parent_key", "student_key"),
    "relationship": ("relationship", "student_key"),
    "klass": ("grade_key", "section_key", "student_key"),
}


@login_required
@role_required(PARENT_PORTAL_ADMIN)
def manage_parent_links(request):
    """صفحة المدير: ربط أولياء الأمور بأبنائهم"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)
    search = request.GET.get("q", "").strip()
    rel_filter = request.GET.get("rel", "").strip()

    # ── الارتباطُ يبقى بعد أن يغادر صاحبُه، فالعددُ يكذب ─────────────
    #
    # «742 طالباً مرتبطاً» لمدرسةٍ سجلُّ قيدها 735: مئةٌ واثنان وأربعون منهم
    # غادروا وبقيت ارتباطاتُهم. والرقمُ الذي يُعمَل به غائبٌ عن الشاشة —
    # **من لا وليَّ أمرٍ له** من طلاب هذا العام.
    enrolled = StudentEnrollment.objects.filter(
        student_id=OuterRef("student_id"),
        class_group__school=school,
        class_group__academic_year=year,
        is_active=True,
    )
    section = StudentEnrollment.objects.filter(
        student_id=OuterRef("student_id"),
        class_group__school=school,
        class_group__academic_year=year,
        is_active=True,
    ).order_by("-enrolled_at")

    links = (
        ParentStudentLink.objects.filter(school=school)
        .select_related("parent", "student")
        .annotate(
            is_enrolled=Exists(enrolled),
            grade_code=Subquery(section.values("class_group__grade")[:1]),
            section_code=Subquery(section.values("class_group__section")[:1]),
            student_key=arabic_key(F("student__full_name")),
            parent_key=arabic_key(F("parent__full_name")),
        )
        .annotate(
            grade_key=Func(
                Func(
                    F("grade_code"),
                    Value(r"\D"),
                    Value(""),
                    Value("g"),
                    function="REGEXP_REPLACE",
                    output_field=CharField(),
                ),
                Value(2),
                Value("0"),
                function="LPAD",
                output_field=CharField(),
            ),
            section_key=F("section_code"),
        )
    )

    #: الافتراضُ طلابُ هذا العام، ومن غادر يُرى بترشيحٍ صريحٍ لا يضيع.
    status = request.GET.get("status") or "enrolled"
    if status == "enrolled":
        links = links.filter(is_enrolled=True)
    elif status == "left":
        links = links.filter(is_enrolled=False)

    total_count = links.count()

    if search:
        links = links.filter(
            Q(parent__full_name__icontains=search)
            | Q(student__full_name__icontains=search)
            | Q(parent__national_id__icontains=search)
            | Q(student__national_id__icontains=search)
            | Q(parent__phone__icontains=search)
            | Q(grade_code__icontains=search)
        )

    if rel_filter:
        links = links.filter(relationship=rel_filter)

    parent_count = links.values("parent").distinct().count()
    student_count = links.values("student").distinct().count()

    # ── العددُ الذي يُعمَل به: من بقي بلا وليّ أمر ────────────────────
    current = set(
        StudentEnrollment.objects.filter(
            class_group__school=school, class_group__academic_year=year, is_active=True
        ).values_list("student_id", flat=True)
    )
    linked_now = set(
        ParentStudentLink.objects.filter(school=school, student_id__in=current).values_list(
            "student_id", flat=True
        )
    )
    enrolled_count = len(current)
    unlinked_count = len(current - linked_now)

    # الفرزُ قبل التقسيم: القائمةُ كلُّها تُرتَّب ثمّ تُقتطع صفحةٌ منها.
    links, sort = apply_sort(links, request, LINK_SORTS, "student")

    # Pagination
    paginator = Paginator(links, 25)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    ctx = {
        "page_obj": page_obj,
        "sort": sort,
        "total_count": total_count,
        "parent_count": parent_count,
        "student_count": student_count,
        "enrolled_count": enrolled_count,
        "unlinked_count": unlinked_count,
        "status": status,
        "statuses": (
            ("enrolled", "طلابُ هذا العام"),
            ("left", "غادروا — ارتباطٌ قديم"),
            ("all", "الكلّ"),
        ),
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


def _parent_from_identity(request, school, national_id, full_name, phone, email=""):
    """وليٌّ بالرقم الشخصيّ — يُستعاد إن كان في النظام، وإلّا يُنشأ.

    والحسابُ الجديدُ يُفتح **بلا كلمة مرورٍ صالحة**: كان يُفتح بكلمةٍ هي
    الرقمُ الشخصيُّ نفسُه — وهو رقمٌ في كشوف الوزارة وفي يد المدرسة، فمن
    يعرفه يدخل بحساب الرجل قبل أن يدخل هو. وإلزامُه بالتغيير بعد الدخول لا
    يمنع غيرَه من السبق إليه.

    فتُصدَر له كلمةٌ مؤقّتةٌ بـ`issue_temporary_passwords` حين يُراد تسليمُه.
    """
    if not national_id or not full_name:
        messages.error(request, "اختر وليّاً من القائمة، أو اكتب رقمَه الشخصيَّ واسمَه.")
        return None
    if not re.fullmatch(r"\d{5,20}", national_id):
        messages.error(request, "الرقمُ الشخصيُّ أرقامٌ فقط (5–20 خانة).")
        return None
    if len(full_name) < 4:
        messages.error(request, "الاسمُ قصيرٌ جدّاً.")
        return None

    parent = CustomUser.objects.filter(national_id=national_id).first()
    with transaction.atomic():
        if parent is None:
            parent = CustomUser(
                national_id=national_id, full_name=full_name, phone=phone, email=email
            )
            parent.set_unusable_password()
            parent.save()
            messages.info(
                request,
                f"أُنشئ حسابُ {parent.full_name} بلا كلمة مرور — تُصدَر له بأمر"
                " issue_temporary_passwords.",
            )
        role, _ = Role.objects.get_or_create(school=school, name="parent")
        Membership.objects.get_or_create(
            user=parent, school=school, role=role, defaults={"is_active": True}
        )
    return parent


@login_required
@role_required(PARENT_PORTAL_ADMIN)
def add_parent_link(request):
    """ربطُ وليّ أمرٍ بطالب — قائماً كان أو جديداً.

    كان لهذا الفعل بابان: هذه الاستمارةُ تربط قائماً، وشاشةٌ منفصلةٌ تُنشئ
    وتربط. والمستخدمُ لا يعرف من الشاشة أيَّهما يفتح. فصار باباً واحداً حيث
    يُرى العمل: في الصفحة التي تقول كم طالباً بلا وليّ أمر.

    وثلاثُ حالاتٍ يجمعها:
      اختيارُ وليٍّ من القائمة · رقمٌ شخصيٌّ لمن في النظام ولم يُوسَم وليّاً
      · رقمٌ لا يعرفه النظام فيُنشأ له حساب.
    """
    if request.method != "POST" or not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    parent_id = request.POST.get("parent_id")
    national_id = (request.POST.get("parent_national_id") or "").strip()
    full_name = (request.POST.get("parent_full_name") or "").strip()
    phone = (request.POST.get("parent_phone") or "").strip()
    email = (request.POST.get("parent_email") or "").strip()
    student_id = request.POST.get("student_id")
    rel = request.POST.get("relationship", "father")

    if not student_id:
        messages.error(request, "اختر الطالبَ المراد ربطُه.")
        return redirect("manage_parent_links")
    student = get_object_or_404(CustomUser, id=student_id)

    if parent_id:
        parent = get_object_or_404(CustomUser, id=parent_id)
    else:
        parent = _parent_from_identity(request, school, national_id, full_name, phone, email)
        if parent is None:
            return redirect("manage_parent_links")

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
@role_required(PARENT_PORTAL_ADMIN)
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
@role_required(PARENT_PORTAL)
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

from core.academic_calendar import academic_year_for
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
        # [B4-5] التسجيل يمرّ بمالك السقف لا بـ`update_or_create` مباشرةً:
        # عددُ الاشتراكات الفعّالة هو المُعامل الذي تُحسب به ميزانية زمن Push،
        # فتركُه بلا حدّ يجعل أسوأ حالة غير قابلة للحساب.
        from notifications.push_subscriptions import register_subscription

        _, created, evicted = register_subscription(
            user=request.user,
            school=school,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        return JsonResponse({"status": "subscribed", "new": created, "evicted": evicted})
    except (KeyError, ValueError, TypeError, OSError):
        logger.error("فشل تسجيل اشتراك Push لولي الأمر")
        return JsonResponse({"error": "تعذر تسجيل اشتراك الإشعارات."}, status=500)


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
    except (KeyError, ValueError, TypeError, OSError):
        logger.error("فشل إلغاء اشتراك Push لولي الأمر")
        return JsonResponse({"error": "تعذر إلغاء اشتراك الإشعارات."}, status=500)


@login_required
def push_vapid_key(request):
    """يُعيد المفتاح العام VAPID لتفعيل Push Notifications في المتصفح."""
    return JsonResponse({"publicKey": getattr(settings, "VAPID_PUBLIC_KEY_B64", "")})
