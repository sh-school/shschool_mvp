import logging
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

logger = logging.getLogger(__name__)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from clinic.services import ClinicService
from core.models import AuditLog, ClinicVisit, CustomUser, HealthRecord
from core.permissions import nurse_required


@login_required
@nurse_required
def clinic_dashboard(request):
    """لوحة تحكم العيادة المدرسية"""
    school = request.user.get_school()

    today = timezone.now().date()
    # ✅ v5.4: ClinicService.get_dashboard_stats — 7 استعلامات في service layer
    context = ClinicService.get_dashboard_stats(school, today=today)
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

    # ── الحفظ ───────────────────────────────────────────────────────
    # لا تشفيرَ هنا: الحقولُ الطبّيّةُ `EncryptedTextField`، والنموذجُ يتولّاه.
    # وكان المسارُ القديم يشفّر يدوياً بـ`save_encrypted()`، والقالبُ يطبع
    # الحقلَ الخام — فتُعرض الطلاسمُ في المربّع ويُعاد تشفيرُها مع كلّ حفظ.
    if request.method == "POST":
        health_record.blood_type = request.POST.get("blood_type", "")
        health_record.emergency_contact_name = request.POST.get("emergency_contact_name", "")
        health_record.emergency_contact_phone = request.POST.get("emergency_contact_phone", "")
        health_record.allergies = request.POST.get("allergies", "")
        health_record.chronic_diseases = request.POST.get("chronic_diseases", "")
        health_record.medications = request.POST.get("medications", "")
        health_record.save()
        # ملاحظة: تدقيق التعديل يتم تلقائياً عبر post_save signal (core/signals.py)
        from django.contrib import messages

        messages.success(request, "✅ تم حفظ السجل الصحي بنجاح.")
        return redirect("clinic:health_record", student_id=student_id)

    visits = ClinicVisit.objects.filter(student=student).order_by("-visit_date")

    # القراءةُ تفكّ من تلقائها، فلا مفاتيحَ موازيةً في السياق. وكان القالبُ
    # يتجاهل المفكوكةَ ويطبع الخام — والمفتاحان المتوازيان هما ما سمح بذلك.
    context = {
        "student": student,
        "health_record": health_record,
        "visits": visits,
    }

    # PDPPL م.19: تدقيق الوصول للسجل الصحي الحساس (يُفكّ تشفير الحساسية/الأمراض/الأدوية)
    AuditLog.log(
        user=request.user,
        action="view",
        model_name="HealthRecord",
        object_id=health_record.pk,
        object_repr=f"عرض السجل الصحي — {student.full_name}",
        request=request,
    )
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
        # ملاحظة: تدقيق إنشاء الزيارة يتم تلقائياً عبر post_save signal (core/signals.py)

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

    # ✅ v5.4: ClinicService.get_health_statistics — 4 استعلامات في service layer
    context = ClinicService.get_health_statistics(school)
    return render(request, "clinic/statistics.html", context)


@login_required
@nurse_required
def api_clinic_charts(request):
    """API: بيانات الرسوم البيانية للعيادة — آخر 30 يوم"""
    school = request.user.get_school()
    today = timezone.now().date()

    # ✅ v5.4: ClinicService.get_chart_data — استعلام واحد بدل 60 (N+1 → O(1))
    data = ClinicService.get_chart_data(school, days=30)
    return JsonResponse(data)
