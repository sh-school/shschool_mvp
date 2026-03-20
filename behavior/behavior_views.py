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


# ── [مهمة 18] إشعار تلقائي لولي الأمر عند تسجيل مخالفة ─────────
def _notify_parents_behavior(infraction, school, reporter):
    """
    يُرسَل إشعار بريد إلكتروني + SMS لولي الأمر فور تسجيل المخالفة.
    - الدرجة 1: بريد فقط (تنبيه خفيف)
    - الدرجة 2+: بريد + SMS
    - الدرجة 3-4: بريد + SMS + تنبيه إضافي بالإحالة للجنة
    """
    LEVEL_DISPLAY = {
        1: "الدرجة الأولى (بسيطة)",
        2: "الدرجة الثانية (متوسطة)",
        3: "الدرجة الثالثة (جسيمة)",
        4: "الدرجة الرابعة (شديدة الخطورة)",
    }
    LEVEL_DESC = {
        1: "مخالفة بسيطة تستوجب التنبيه والتوجيه",
        2: "مخالفة متوسطة تستوجب التدخل والمتابعة",
        3: "مخالفة جسيمة أُحيلت للجنة الضبط السلوكي",
        4: "مخالفة شديدة الخطورة تستوجب التدخل الفوري",
    }

    try:
        from notifications.services import NotificationService
        from core.models import ParentStudentLink
        from django.template.loader import render_to_string

        links = ParentStudentLink.objects.filter(
            student=infraction.student, school=school
        ).select_related("parent")

        if not links.exists():
            return  # لا يوجد أولياء أمور مرتبطون

        ctx = {
            "school_name":     school.name,
            "student_name":    infraction.student.full_name,
            "level":           infraction.level,
            "level_display":   LEVEL_DISPLAY.get(infraction.level, ""),
            "level_description": LEVEL_DESC.get(infraction.level, ""),
            "infraction_date": infraction.date.strftime("%Y/%m/%d") if infraction.date else "",
            "points_deducted": infraction.points_deducted,
            "description":     infraction.description,
            "action_taken":    infraction.action_taken,
            "reported_by":     reporter.full_name,
        }

        for link in links:
            parent = link.parent
            ctx["parent_name"] = parent.full_name

            subject = (
                f"⚠️ مخالفة سلوكية — {infraction.student.full_name} "
                f"({LEVEL_DISPLAY.get(infraction.level, '')})"
            )

            # ── بريد إلكتروني ─────────────────────────────────────────
            if parent.email:
                try:
                    body_html = render_to_string(
                        "notifications/email/behavior_html.html", ctx
                    )
                    body_text = render_to_string(
                        "notifications/email/behavior_text.txt", ctx
                    )
                    NotificationService.send_email(
                        school         = school,
                        recipient_email= parent.email,
                        subject        = subject,
                        body_text      = body_text,
                        body_html      = body_html,
                        student        = infraction.student,
                        notif_type     = "behavior",
                        sent_by        = reporter,
                    )
                except Exception:
                    pass  # لا نوقف التسجيل إذا فشل الإرسال

            # ── SMS — للدرجة 2 فأكثر فقط ─────────────────────────────
            if infraction.level >= 2 and parent.phone:
                sms_body = (
                    f"مدرسة الشحانية: تم تسجيل {LEVEL_DISPLAY.get(infraction.level, 'مخالفة')} "
                    f"لابنكم {infraction.student.full_name}. "
                    f"يُرجى التواصل مع المدرسة."
                )
                try:
                    NotificationService.send_sms(
                        school      = school,
                        phone_number= parent.phone,
                        message     = sms_body,
                        student     = infraction.student,
                        notif_type  = "behavior",
                        sent_by     = reporter,
                    )
                except Exception:
                    pass

    except Exception:
        pass  # الإشعار لا يوقف عملية التسجيل أبداً


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

            # ── [مهمة 18] إشعار تلقائي لولي الأمر ───────────────────────
            # يُرسَل دائماً من الدرجة 2 فأكثر — الدرجة 1 اختيارية
            _notify_parents_behavior(infraction, school, request.user)

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



# ── تقرير سلوكي دوري للطالب ──────────────────────────────────
@login_required
def behavior_report(request, student_id):
    """
    التقرير السلوكي الدوري — لائحة السلوك المدرسي MOEHE
    يُرسَل لولي الأمر + يُحفظ كدليل QNSA
    """
    if not _can_report(request.user) and not request.user.is_superuser:
        return HttpResponseForbidden("ليس لديك صلاحية.")

    school  = request.user.get_school()
    student = get_object_or_404(CustomUser, id=student_id)
    year    = request.GET.get("year", "2025-2026")
    period  = request.GET.get("period", "full")  # full | S1 | S2

    from django.utils import timezone
    from datetime import date

    # نطاق الفترة
    if period == "S1":
        date_from, date_to = date(2025, 9, 1),  date(2026, 1, 31)
        period_label = "الفصل الأول"
    elif period == "S2":
        date_from, date_to = date(2026, 2, 1),  date(2026, 6, 30)
        period_label = "الفصل الثاني"
    else:
        date_from, date_to = date(2025, 9, 1),  date(2026, 6, 30)
        period_label = "العام الدراسي كاملاً"

    infractions = BehaviorInfraction.objects.filter(
        student=student, school=school,
        date__gte=date_from, date__lte=date_to,
    ).select_related("reported_by", "recovery").order_by("date")

    total_deducted = infractions.aggregate(Sum("points_deducted"))["points_deducted__sum"] or 0
    total_restored = BehaviorPointRecovery.objects.filter(
        infraction__student=student,
        infraction__date__gte=date_from,
        infraction__date__lte=date_to,
    ).aggregate(Sum("points_restored"))["points_restored__sum"] or 0

    net_score = 100 - total_deducted + total_restored
    net_score = max(0, min(100, net_score))

    if net_score >= 90:   rating, rating_color = "ممتاز",      "green"
    elif net_score >= 75: rating, rating_color = "جيد جداً",   "blue"
    elif net_score >= 60: rating, rating_color = "جيد",        "amber"
    else:                 rating, rating_color = "يحتاج تطوير","red"

    by_level = {1: [], 2: [], 3: [], 4: []}
    for inf in infractions:
        by_level[inf.level].append(inf)

    # ولي الأمر
    from core.models import ParentStudentLink
    parent_links = ParentStudentLink.objects.filter(
        student=student, school=school
    ).select_related("parent")

    # إرسال للأولياء
    sent_to = []
    if request.method == "POST" and request.POST.get("action") == "send":
        from notifications.services import NotificationService
        for link in parent_links:
            parent = link.parent
            if parent.email:
                body = (
                    f"ولي أمر الطالب: {parent.full_name}\n\n"
                    f"التقرير السلوكي للطالب: {student.full_name}\n"
                    f"الفترة: {period_label} — {year}\n\n"
                    f"نقاط السلوك: {net_score}/100 ({rating})\n"
                    f"المخالفات المسجَّلة: {infractions.count()}\n"
                    f"النقاط المخصومة: {total_deducted}\n"
                    f"النقاط المستعادة: {total_restored}\n\n"
                    f"للاطلاع على التفاصيل الكاملة يرجى زيارة البوابة الإلكترونية.\n\n"
                    f"مدرسة الشحانية الإعدادية الثانوية للبنين"
                )
                try:
                    NotificationService.send_email(
                        school=school,
                        recipient_email=parent.email,
                        subject=f"التقرير السلوكي — {student.full_name} — {period_label}",
                        body_text=body,
                        student=student,
                        notif_type="behavior",
                        sent_by=request.user,
                    )
                    sent_to.append(parent.full_name)
                except Exception:
                    pass

        if sent_to:
            messages.success(request, f"تم إرسال التقرير لـ: {', '.join(sent_to)}")
        else:
            messages.warning(request, "لا يوجد بريد إلكتروني مسجَّل لأولياء الأمور.")
        return redirect(request.path + f"?year={year}&period={period}")

    period_choices = [
        ("full", "العام كاملاً"),
        ("S1",   "الفصل الأول"),
        ("S2",   "الفصل الثاني"),
    ]

    return render(request, "behavior/behavior_report.html", {
        "student":        student,
        "infractions":    infractions,
        "by_level":       by_level,
        "total_deducted": total_deducted,
        "total_restored": total_restored,
        "net_score":      net_score,
        "rating":         rating,
        "rating_color":   rating_color,
        "period":         period,
        "period_label":   period_label,
        "year":           year,
        "parent_links":   parent_links,
        "sent_to":        sent_to,
        "date_from":      date_from,
        "date_to":        date_to,
        "period_choices": period_choices,
    })


# ── تقرير إحصائي للمدير ──────────────────────────────────────
@login_required
def behavior_statistics(request):
    """
    تقرير إحصائي شامل للمدير — QNSA المعيار 2
    """
    if not _is_committee(request.user):
        return HttpResponseForbidden("للمدير ونائبيه فقط.")

    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")
    from datetime import date
    date_from = date(2025, 9, 1)
    date_to   = date(2026, 6, 30)

    # إحصائيات عامة
    all_inf = BehaviorInfraction.objects.filter(
        school=school, date__gte=date_from, date__lte=date_to
    )

    by_level = {
        lvl: all_inf.filter(level=lvl).count()
        for lvl in [1, 2, 3, 4]
    }
    total = all_inf.count()

    # أكثر الطلاب مخالفة
    top_students = (
        all_inf.values("student__full_name", "student__id")
        .annotate(count=Count("id"), pts=Sum("points_deducted"))
        .order_by("-count")[:10]
    )

    # توزيع شهري
    from django.db.models.functions import TruncMonth
    monthly = (
        all_inf.annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(count=Count("id"))
        .order_by("month")
    )

    # الفصول الأكثر مخالفات
    from core.models import StudentEnrollment
    top_classes = (
        all_inf.values(
            "student__enrollments__class_group__grade",
            "student__enrollments__class_group__section",
        )
        .annotate(count=Count("id"))
        .order_by("-count")[:5]
    )

    return render(request, "behavior/statistics.html", {
        "by_level":    by_level,
        "total":       total,
        "top_students": top_students,
        "monthly":     monthly,
        "top_classes": top_classes,
        "year":        year,
        "resolved_pct": round(
            all_inf.filter(is_resolved=True).count() / total * 100
        ) if total else 0,
    })
