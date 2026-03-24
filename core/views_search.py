"""Global search endpoint for the Command Palette (Ctrl+K)."""

import re

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse

# ✅ v5.1.1: regex للتحقق من صحة استعلامات البحث (عربي + لاتيني + أرقام + مسافات)
_SEARCH_RE = re.compile(r"^[\w\s\u0600-\u06FF\u0750-\u077F\-_.@]+$")


@login_required
def global_search(request):
    q = request.GET.get("q", "").strip()[:80]
    if len(q) < 2:
        return JsonResponse({"results": []})
    if not _SEARCH_RE.match(q):
        return JsonResponse({"results": []})

    school = request.user.get_school()
    if not school:
        return JsonResponse({"results": []})

    results = []

    # بحث في الطلاب (عبر StudentEnrollment → CustomUser)
    from core.models import StudentEnrollment

    student_enrollments = (
        StudentEnrollment.objects.filter(
            class_group__school=school, is_active=True,
        )
        .filter(
            Q(student__full_name__icontains=q) | Q(student__national_id__icontains=q)
        )
        .select_related("student")
        .values("student__id", "student__full_name", "student__national_id")
        .distinct()[:6]
    )
    students = [
        {"id": s["student__id"], "full_name": s["student__full_name"], "national_id": s["student__national_id"]}
        for s in student_enrollments
    ]
    for s in students:
        results.append(
            {
                "type": "student",
                "icon": "🎓",
                "title": s["full_name"],
                "sub": s["national_id"] or "",
                "url": f"/behavior/student/{s['id']}/",
            }
        )

    # بحث في المعلمين/الموظفين (فقط للمدير)
    if request.user.is_admin:
        from core.models import CustomUser, Membership

        staff_ids = Membership.objects.filter(
            school=school, is_active=True
        ).exclude(role__name__in=["student", "parent"]).values_list("user_id", flat=True)

        staff = (
            CustomUser.objects.filter(id__in=staff_ids, is_active=True)
            .filter(Q(full_name__icontains=q) | Q(email__icontains=q))
            .values("id", "full_name", "email")[:4]
        )
        for t in staff:
            results.append(
                {
                    "type": "teacher",
                    "icon": "👨‍🏫",
                    "title": t["full_name"],
                    "sub": t["email"] or "",
                    "url": f"/admin/core/customuser/{t['id']}/change/",
                }
            )

    # صفحات سريعة (static)
    pages = [
        {"title": "لوحة التحكم", "url": "/dashboard/", "icon": "🏠"},
        {"title": "الجدول الأسبوعي", "url": "/schedule/weekly/", "icon": "📅"},
        {"title": "التقييمات", "url": "/assessments/", "icon": "📝"},
        {"title": "تسجيل الحضور", "url": "/teacher/schedule/", "icon": "📋"},
        {"title": "الإشعارات", "url": "/notifications/inbox/", "icon": "🔔"},
        {"title": "التقارير", "url": "/reports/", "icon": "📄"},
        {"title": "العيادة", "url": "/clinic/", "icon": "🏥"},
        {"title": "المكتبة", "url": "/library/", "icon": "📚"},
        {"title": "السلوك", "url": "/behavior/", "icon": "⚖️"},
        {"title": "الجودة", "url": "/quality/", "icon": "📊"},
        {"title": "التحليلات", "url": "/analytics/", "icon": "📈"},
    ]
    for p in pages:
        if q in p["title"]:
            results.append(
                {
                    "type": "page",
                    "icon": p["icon"],
                    "title": p["title"],
                    "sub": "صفحة",
                    "url": p["url"],
                }
            )

    return JsonResponse({"results": results[:12]})
