import logging
from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.db.models.functions import ExtractHour, TruncDate
from django.http import JsonResponse

logger = logging.getLogger(__name__)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from clinic.services import ClinicService
from core.models import ClinicVisit, CustomUser, HealthRecord
from core.permissions import nurse_required


@login_required
@nurse_required
def clinic_dashboard(request):
    """لوحة تحكم العيادة المدرسية"""
    school = request.user.get_school()

    today = timezone.now().date()
    visits_today = ClinicVisit.objects.filter(school=school, visit_date__date=today).count()
    sent_home_today = ClinicVisit.objects.filter(
        school=school, visit_date__date=today, is_sent_home=True
    ).count()

    recent_visits = (
        ClinicVisit.objects.filter(school=school)
        .select_related("student")
        .order_by("-visit_date")[:10]
    )

    follow_up_visits = ClinicVisit.objects.filter(
        school=school, is_sent_home=True, visit_date__date=today
    ).select_related("student")

    # ── Weekly trend (last 7 days) ──
    week_ago = today - timedelta(days=7)
    weekly_visits = (
        ClinicVisit.objects.filter(school=school, visit_date__date__gte=week_ago)
        .values(day=TruncDate("visit_date"))
        .annotate(total=Count("id"), sent_home=Count("id", filter=Q(is_sent_home=True)))
        .order_by("day")
    )

    # ── Peak hours ──
    peak_hours = (
        ClinicVisit.objects.filter(school=school, visit_date__date__gte=week_ago)
        .values(hour=ExtractHour("visit_date"))
        .annotate(count=Count("id"))
        .order_by("-count")[:5]
    )

    # ── Frequent visitors (3+ visits this month) ──
    frequent = (
        ClinicVisit.objects.filter(
            school=school, visit_date__month=today.month, visit_date__year=today.year
        )
        .values("student__id", "student__full_name")
        .annotate(visit_count=Count("id"))
        .filter(visit_count__gte=3)
        .order_by("-visit_count")[:10]
    )

    # ── Monthly total ──
    month_total = ClinicVisit.objects.filter(
        school=school, visit_date__month=today.month, visit_date__year=today.year
    ).count()

    context = {
        "visits_today": visits_today,
        "sent_home_today": sent_home_today,
        "recent_visits": recent_visits,
        "follow_up_visits": follow_up_visits,
        "weekly_visits": weekly_visits,
        "peak_hours": peak_hours,
        "frequent": frequent,
        "month_total": month_total,
    }
    return render(request, "clinic/dashboard.html", context)


@login_required
@nurse_required
@require_http_methods(["GET", "POST"])
def student_health_record(request, student_id):
    """عرض وتعديل السجل الصحي للطالب — مع فك تشفير البيانات الحساسة"""
    school = request.user.get_school()
    student = get_object_or_404(CustomUser, id=student_id, memberships__school=school)

    try:
        health_record = student.health_record
    except HealthRecord.DoesNotExist:
        health_record = HealthRecord.objects.create(student=student)

    # ── [مهمة 5] حفظ الحقول الحساسة مشفّرة ──────────────────────────
    if request.method == "POST":
        # استخدام save_encrypted() الموجودة في models.py
        # تُشفّر الحقول الثلاثة بـ Fernet قبل الحفظ
        health_record.blood_type = request.POST.get("blood_type", "")
        health_record.emergency_contact_name = request.POST.get("emergency_contact_name", "")
        health_record.emergency_contact_phone = request.POST.get("emergency_contact_phone", "")
        health_record.save_encrypted(
            allergies=request.POST.get("allergies", ""),
            chronic_diseases=request.POST.get("chronic_diseases", ""),
            medications=request.POST.get("medications", ""),
        )
        from django.contrib import messages

        messages.success(request, "✅ تم حفظ السجل الصحي بنجاح.")
        return redirect("clinic:health_record", student_id=student_id)

    visits = ClinicVisit.objects.filter(student=student).order_by("-visit_date")

    # ── [مهمة 5] فك التشفير عند العرض ───────────────────────────────
    # نمرّر القيم المفكوكة للقالب بدلاً من الحقول الخام المشفّرة
    context = {
        "student": student,
        "health_record": health_record,
        "visits": visits,
        # قيم مفكوكة التشفير للعرض في النموذج
        "allergies": health_record.get_allergies(),
        "chronic_diseases": health_record.get_chronic_diseases(),
        "medications": health_record.get_medications(),
    }
    return render(request, "clinic/health_record.html", context)


@login_required
@nurse_required
@require_http_methods(["GET", "POST"])
def record_visit(request, student_id=None):
    """تسجيل زيارة جديدة للعيادة"""
    school = request.user.get_school()
    nurse = request.user

    if request.method == "POST":
        student_id = request.POST.get("student_id")
        student = get_object_or_404(CustomUser, id=student_id, memberships__school=school)

        # ✅ v5.4: ClinicService.record_visit — atomic + notification منفصلة عن الإنشاء
        # يُحلّ مشكلة double save() وإشعار مدمج في الـ view
        visit = ClinicService.record_visit(
            school=school,
            student=student,
            nurse=nurse,
            reason=request.POST.get("reason", ""),
            symptoms=request.POST.get("symptoms", ""),
            temperature=request.POST.get("temperature") or None,
            treatment=request.POST.get("treatment", ""),
            is_sent_home=request.POST.get("is_sent_home") == "on",
        )

        if request.headers.get("HX-Request"):
            return render(request, "clinic/visit_card.html", {"visit": visit})

        return redirect("clinic:health_record", student_id=student_id)

    students = CustomUser.objects.filter(
        memberships__school=school, memberships__role__name="student", memberships__is_active=True
    ).distinct()

    context = {
        "students": students,
        "student_id": student_id,
    }
    return render(request, "clinic/record_visit.html", context)


@login_required
@nurse_required
def visits_list(request):
    """قائمة الزيارات بالعيادة"""
    school = request.user.get_school()
    visits = (
        ClinicVisit.objects.filter(school=school).select_related("student").order_by("-visit_date")
    )

    date_filter = request.GET.get("date")
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
            visits = visits.filter(visit_date__date=filter_date)
        except ValueError:
            pass

    student_filter = request.GET.get("student")
    if student_filter:
        visits = visits.filter(student__full_name__icontains=student_filter)

    context = {
        "visits": visits,
        "date_filter": date_filter,
        "student_filter": student_filter,
    }

    # HTMX: أعد الجزء فقط (بحث حي + ترشيح)
    if getattr(request, "htmx", None) or request.headers.get("HX-Request"):
        return render(request, "clinic/partials/visit_rows.html", context)

    return render(request, "clinic/visits_list.html", context)


@login_required
@nurse_required
def health_statistics(request):
    """إحصائيات صحية للمدرسة"""
    school = request.user.get_school()

    health_records = (
        HealthRecord.objects.filter(student__memberships__school=school)
        .filter(chronic_diseases__isnull=False)
        .exclude(chronic_diseases="")
    )

    allergies = (
        HealthRecord.objects.filter(student__memberships__school=school)
        .filter(allergies__isnull=False)
        .exclude(allergies="")
    )

    visits_count = ClinicVisit.objects.filter(school=school).count()
    visits_this_month = ClinicVisit.objects.filter(
        school=school, visit_date__month=timezone.now().month, visit_date__year=timezone.now().year
    ).count()

    context = {
        "health_records_count": health_records.count(),
        "allergies_count": allergies.count(),
        "visits_count": visits_count,
        "visits_this_month": visits_this_month,
    }
    return render(request, "clinic/statistics.html", context)


@login_required
@nurse_required
def api_clinic_charts(request):
    """API: بيانات الرسوم البيانية للعيادة — آخر 30 يوم"""
    school = request.user.get_school()
    today = timezone.now().date()

    days = []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        count = ClinicVisit.objects.filter(school=school, visit_date__date=d).count()
        sent = ClinicVisit.objects.filter(school=school, visit_date__date=d, is_sent_home=True).count()
        days.append({"date": d.strftime("%d/%m"), "visits": count, "sent_home": sent})

    return JsonResponse(
        {
            "labels": [d["date"] for d in days],
            "visits": [d["visits"] for d in days],
            "sent_home": [d["sent_home"] for d in days],
        }
    )
