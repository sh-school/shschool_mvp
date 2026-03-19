# behavior/views.py — النسخة الكاملة مع لجنة الضبط السلوكي
"""
وحدة السلوك الطلابي — SchoolOS V2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يشمل:
  - لوحة التحكم العامة
  - تسجيل المخالفات (4 درجات)
  - الملف السلوكي للطالب
  - استعادة النقاط (التعزيز الإيجابي)
  - لجنة الضبط السلوكي (جديد — للمخالفات من الدرجة 3-4)
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Sum, Count, Q
from django.utils import timezone

from core.models import (
    BehaviorInfraction, BehaviorPointRecovery,
    CustomUser, School, Membership
)


def _can_report(user):
    """معلم / منسق / أخصائي / إدارة يمكنهم تسجيل مخالفة"""
    role = user.get_role()
    return role in ["principal", "vice_admin", "vice_academic",
                    "coordinator", "teacher", "specialist", "admin"]


def _is_committee(user):
    """أعضاء لجنة الضبط السلوكي: المدير + النواب + الأخصائي"""
    role = user.get_role()
    return role in ["principal", "vice_admin", "vice_academic", "specialist"] \
           or user.is_superuser


# ── لوحة التحكم ──────────────────────────────────────────────
@login_required
def behavior_dashboard(request):
    role = request.user.get_role()
    if role in ("parent", "student"):
        return HttpResponseForbidden("ليس لديك صلاحية الوصول إلى هذه الصفحة.")

    school = request.user.get_school()
    if not school:
        messages.error(request, "لم يتم العثور على مدرسة مرتبطة بحسابك.")
        return redirect("dashboard")

    today = timezone.now().date()

    stats = BehaviorInfraction.objects.filter(school=school).values("level").annotate(
        count=Count("id")
    )

    total_deducted = BehaviorInfraction.objects.filter(school=school).aggregate(
        Sum("points_deducted")
    )["points_deducted__sum"] or 0

    total_restored = BehaviorPointRecovery.objects.filter(
        infraction__school=school
    ).aggregate(Sum("points_restored"))["points_restored__sum"] or 0

    recent_infractions = (
        BehaviorInfraction.objects
        .filter(school=school)
        .select_related("student", "reported_by")
        .order_by("-date")[:15]
    )

    # المخالفات الجسيمة غير المحلولة
    critical_unresolved = BehaviorInfraction.objects.filter(
        school=school, level__in=[3, 4], is_resolved=False
    ).select_related("student")

    context = {
        "stats":               stats,
        "total_deducted":      total_deducted,
        "total_restored":      total_restored,
        "net_deducted":        total_deducted - total_restored,
        "recent_infractions":  recent_infractions,
        "critical_unresolved": critical_unresolved,
        "can_report":          _can_report(request.user),
        "is_committee":        _is_committee(request.user),
    }
    return render(request, "behavior/dashboard.html", context)


# ── تسجيل مخالفة جديدة ───────────────────────────────────────
@login_required
def report_infraction(request):
    if not _can_report(request.user):
        messages.error(request, "ليس لديك صلاحية تسجيل المخالفات.")
        return redirect("behavior:dashboard")

    school = request.user.get_school()

    if request.method == "POST":
        student_id  = request.POST.get("student_id")
        level       = int(request.POST.get("level", 1))
        description = request.POST.get("description", "").strip()
        points      = int(request.POST.get("points_deducted", 0))
        action      = request.POST.get("action_taken", "").strip()

        if not student_id or not description:
            messages.error(request, "يرجى تعبئة جميع الحقول الإلزامية.")
        else:
            student = get_object_or_404(CustomUser, id=student_id)
            infraction = BehaviorInfraction.objects.create(
                school=school,
                student=student,
                reported_by=request.user,
                level=level,
                description=description,
                action_taken=action,
                points_deducted=points,
            )
            messages.success(
                request,
                f"✅ تم تسجيل مخالفة من الدرجة {level} للطالب {student.full_name}"
            )
            # توجيه المخالفات الجسيمة تلقائياً للجنة
            if level >= 3:
                messages.warning(
                    request,
                    f"⚠️ تم إحالة المخالفة للجنة الضبط السلوكي لكونها من الدرجة {level}"
                )
                return redirect("behavior:committee")
            return redirect("behavior:student_profile", student_id=student.id)

    # قائمة الطلاب
    students = (
        CustomUser.objects
        .filter(
            memberships__school=school,
            memberships__role__name="student",
            memberships__is_active=True,
        )
        .order_by("full_name")
        .distinct()
    )

    POINTS_BY_LEVEL = {1: 5, 2: 15, 3: 25, 4: 40}

    return render(request, "behavior/report_form.html", {
        "students":        students,
        "POINTS_BY_LEVEL": POINTS_BY_LEVEL,
        "levels":          BehaviorInfraction.LEVELS,
    })


# ── الملف السلوكي للطالب ─────────────────────────────────────
@login_required
def student_behavior_profile(request, student_id):
    student     = get_object_or_404(CustomUser, id=student_id)
    infractions = BehaviorInfraction.objects.filter(student=student).select_related(
        "reported_by", "recovery"
    ).order_by("-date")

    total_deducted = infractions.aggregate(Sum("points_deducted"))["points_deducted__sum"] or 0
    total_restored = BehaviorPointRecovery.objects.filter(
        infraction__student=student
    ).aggregate(Sum("points_restored"))["points_restored__sum"] or 0

    net_score     = 100 - total_deducted + total_restored  # من 100 درجة
    status_color  = "green" if net_score >= 80 else ("yellow" if net_score >= 60 else "red")

    by_level = {1: 0, 2: 0, 3: 0, 4: 0}
    for inf in infractions:
        by_level[inf.level] = by_level.get(inf.level, 0) + 1

    return render(request, "behavior/student_profile.html", {
        "student":        student,
        "infractions":    infractions,
        "total_deducted": total_deducted,
        "total_restored": total_restored,
        "net_score":      net_score,
        "status_color":   status_color,
        "by_level":       by_level,
        "can_report":     _can_report(request.user),
        "is_committee":   _is_committee(request.user),
    })


# ── استعادة النقاط (التعزيز الإيجابي) ────────────────────────
@login_required
def point_recovery_request(request, infraction_id):
    if not _is_committee(request.user):
        messages.error(request, "استعادة النقاط مقتصرة على أعضاء لجنة الضبط السلوكي.")
        return redirect("behavior:dashboard")

    infraction = get_object_or_404(BehaviorInfraction, id=infraction_id)

    if hasattr(infraction, "recovery"):
        messages.warning(request, "تم معالجة هذه المخالفة مسبقاً.")
        return redirect("behavior:student_profile", student_id=infraction.student.id)

    if request.method == "POST":
        reason  = request.POST.get("reason", "").strip()
        points  = int(request.POST.get("points_restored", 0))

        if not reason:
            messages.error(request, "يرجى تحديد سبب استعادة النقاط.")
        elif points <= 0 or points > infraction.points_deducted:
            messages.error(request, f"النقاط يجب أن تكون بين 1 و {infraction.points_deducted}.")
        else:
            BehaviorPointRecovery.objects.create(
                infraction=infraction,
                reason=reason,
                points_restored=points,
                approved_by=request.user,
            )
            infraction.is_resolved = True
            infraction.save()
            messages.success(
                request,
                f"✅ تمت استعادة {points} نقطة للطالب {infraction.student.full_name}"
            )
            return redirect("behavior:student_profile", student_id=infraction.student.id)

    return render(request, "behavior/recovery_form.html", {"infraction": infraction})


# ── لجنة الضبط السلوكي ───────────────────────────────────────
@login_required
def committee_dashboard(request):
    """
    لوحة لجنة الضبط السلوكي — للمخالفات من الدرجة 3 و4
    مقتصرة على: المدير + النوابَين + الأخصائي الاجتماعي
    """
    if not _is_committee(request.user):
        return HttpResponseForbidden("ليس لديك صلاحية الوصول إلى هذه الصفحة.")

    school = request.user.get_school()

    # المخالفات الجسيمة غير المحلولة
    open_cases = (
        BehaviorInfraction.objects
        .filter(school=school, level__in=[3, 4], is_resolved=False)
        .select_related("student", "reported_by")
        .order_by("-date")
    )

    # المخالفات الجسيمة المحلولة
    resolved_cases = (
        BehaviorInfraction.objects
        .filter(school=school, level__in=[3, 4], is_resolved=True)
        .select_related("student", "reported_by", "recovery", "recovery__approved_by")
        .order_by("-date")[:20]
    )

    # إحصائيات
    stats = {
        "open_count":     open_cases.count(),
        "resolved_count": BehaviorInfraction.objects.filter(
            school=school, level__in=[3, 4], is_resolved=True
        ).count(),
        "level3":         open_cases.filter(level=3).count(),
        "level4":         open_cases.filter(level=4).count(),
    }

    return render(request, "behavior/committee.html", {
        "open_cases":     open_cases,
        "resolved_cases": resolved_cases,
        "stats":          stats,
    })


# ── اتخاذ قرار اللجنة ────────────────────────────────────────
@login_required
def committee_decision(request, infraction_id):
    """تسجيل قرار اللجنة في المخالفة الجسيمة"""
    if not _is_committee(request.user):
        messages.error(request, "غير مسموح.")
        return redirect("behavior:committee")

    infraction = get_object_or_404(BehaviorInfraction, id=infraction_id, level__in=[3, 4])

    if request.method == "POST":
        decision    = request.POST.get("decision")
        action      = request.POST.get("action_taken", "").strip()
        restore_pts = int(request.POST.get("points_restored", 0))
        reason      = request.POST.get("recovery_reason", "").strip()

        # تسجيل الإجراء المتخذ
        if action:
            infraction.action_taken = (infraction.action_taken + "\n" + action).strip()

        if decision == "resolve":
            # حل المخالفة
            infraction.is_resolved = True
            if restore_pts > 0 and not hasattr(infraction, "recovery"):
                BehaviorPointRecovery.objects.create(
                    infraction=infraction,
                    reason=reason or "قرار لجنة الضبط السلوكي",
                    points_restored=restore_pts,
                    approved_by=request.user,
                )
            infraction.save()
            messages.success(request, f"✅ تم حل المخالفة للطالب {infraction.student.full_name}")

        elif decision == "escalate":
            # تصعيد — رفع درجة المخالفة (إذا كانت 3 تصبح 4)
            if infraction.level < 4:
                infraction.level = 4
                infraction.save()
            messages.warning(request, f"⬆️ تم تصعيد المخالفة إلى الدرجة الرابعة")

        elif decision == "suspend":
            # إيقاف مؤقت
            infraction.action_taken = (
                infraction.action_taken + "\n[قرار اللجنة: إيقاف مؤقت]"
            ).strip()
            infraction.save()
            messages.info(request, "📋 تم تسجيل قرار الإيقاف المؤقت")

        return redirect("behavior:committee")

    return render(request, "behavior/committee_decision.html", {"infraction": infraction})
