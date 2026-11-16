import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse

logger = logging.getLogger(__name__)
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from clinic.export import VISITS_PDF_KIND, VISITS_TABLE
from clinic.health_access import OPEN_REASONS, clean_reason, log_full_open
from clinic.models import ClinicVisit, HealthRecord
from clinic.needs_care_services import import_from_request
from clinic.selectors import (
    class_options,
    recent_visitors,
    student_choice,
    visit_range,
    visits_for,
)
from clinic.services import ClinicService
from core.audit_repr import masked_repr
from core.capabilities import capability_required, has_capability
from core.exports.services import respond_export
from core.models import AuditLog, CustomUser


def _audit_health_screen(request, screen, *, model_name, object_id="", rows=None):
    """يكتب سطرَ تدقيقٍ لفتح شاشةٍ تعرض بياناً صحيّاً (PDPPL م.11 وم.13: سجلُّ الوصول).

    معرّفاتٌ فقط: نوعُ الشاشة وعددُ الصفوف ومعرّفُ السجلّ — لا اسمَ طالبٍ ولا نصَّ صحّيّاً
    (reason/treatment/تشخيص)؛ فسجلُّ التدقيق ملحقٌ لا يُعدَّل ويبقى بعد محو صاحبه.
    كلُّ شاشةٍ صحّيّةٍ جديدةٍ في العيادة تستدعيه، ويفرض ذلك tests/test_clinic_audit_every_screen.py.
    """
    changes = {"screen": screen}
    if rows is not None:
        # قائمة الاستعلام تُعدّ هنا لا في العرض فلا يزيد عدّ الطبقات فيه
        changes["rows"] = rows if isinstance(rows, int) else rows.count()
    AuditLog.log(
        user=request.user,
        action="view",
        model_name=model_name,
        object_id=object_id,
        object_repr=f"عرض شاشة صحية — {screen}",
        changes=changes,
        request=request,
    )


@login_required
@capability_required("clinic.access")
def clinic_dashboard(request):
    """لوحة تحكم العيادة المدرسية"""
    school = request.user.get_school()

    today = timezone.now().date()
    # ✅ v5.4: ClinicService.get_dashboard_stats — 7 استعلامات في service layer
    context = ClinicService.get_dashboard_stats(school, today=today)
    context.update(
        today_label=f"{today:%d/%m/%Y} · متابعةُ الزيارات والسجلات الصحّيّة",
        # اللونُ يحمل التنبيه — لا سطرَ «تنبيه» تحت الرقم ولا شريطَ يكرّره.
        sent_home_tone="red" if context.get("sent_home_today") else "green",
        frequent_tone="amber" if context.get("frequent") else "green",
    )
    # اللوحةُ تعرض أسماءَ الطلاب وسببَ الزيارة: وصولٌ إلى بيانٍ صحّيّ يُدقَّق.
    _audit_health_screen(request, "لوحة العيادة", model_name="ClinicVisit")
    return render(request, "clinic/dashboard.html", context)


@login_required
@capability_required("clinic.counts")
def clinic_counts(request):
    """اللوحةُ العدديّةُ للعيادة: أعدادٌ بلا أسماء وبقمع الخلايا الأقلّ من 5 (W-20261020-031)."""
    school = request.school
    today = timezone.now().date()
    context = ClinicService.get_counts_board(school, today=today)
    context["today_label"] = f"{today:%d/%m/%Y} · أعدادٌ مجمَّعةٌ بلا أسماء"
    return render(request, "clinic/dashboard_counts.html", context)


def _load_health_record(student, can_write):
    """سجلُّ الطالب الصحّيّ؛ والقارئُ لا يُنشئ سجلاًّ فارغاً بفتح الصفحة (حكم 0104)."""
    try:
        return student.health_record
    except HealthRecord.DoesNotExist:
        return (
            HealthRecord.objects.create(student=student)
            if can_write
            else HealthRecord(student=student)
        )


def _save_health_record(health_record, post):
    # لا تشفيرَ هنا: الحقولُ الطبّيّةُ `EncryptedTextField`، والنموذجُ يتولّاه (تدقيقُ التعديل
    # بـpost_save signal). والعلامةُ صريحةٌ من الممرّض وحدَه: خانةٌ غيرُ مؤشَّرةٍ تعني «لا» (W-045).
    health_record.blood_type_encrypted = post.get("blood_type", "")
    health_record.emergency_contact_name = post.get("emergency_contact_name", "")
    health_record.emergency_contact_phone = post.get("emergency_contact_phone", "")
    health_record.allergies = post.get("allergies", "")
    health_record.chronic_diseases = post.get("chronic_diseases", "")
    health_record.medications = post.get("medications", "")
    health_record.needs_care = post.get("needs_care") == "1"
    health_record.save()


def _record_context(student, health_record, *, full, can_write):
    return {
        "student": student,
        "health_record": health_record,
        "visits": ClinicVisit.objects.filter(student=student).order_by("-visit_date"),
        "can_write": can_write,
        "full": full,
        "open_reasons": OPEN_REASONS,
    }


@login_required
@capability_required("clinic.access")
@require_http_methods(["GET", "POST"])
def student_health_record(request, student_id):
    """السجلُّ الصحّيّ: كاملٌ للممرّض، ومختصرٌ لغيره يُفتح كاملُه بسببٍ مغلقٍ مسجَّل (W-20261020-033)."""
    student = get_object_or_404(
        CustomUser, id=student_id, memberships__school=request.user.get_school()
    )
    can_write = has_capability(request.user, "clinic.write")
    full = has_capability(request.user, "clinic.health_full")
    health_record = _load_health_record(student, can_write)
    if request.method == "POST":
        if request.POST.get("open_full") == "1":
            return _open_full(request, student, health_record)
        if not (can_write and full):
            raise PermissionDenied
        _save_health_record(health_record, request.POST)
        messages.success(request, "✅ تم حفظ السجل الصحي بنجاح.")
        return redirect("clinic:health_record", student_id=student_id)
    context = _record_context(student, health_record, full=full, can_write=can_write and full)
    if not full:
        # المختصرُ لا يفكّ تشفيراً ولا يعرض تشخيصاً: سطرُ تدقيقٍ للشاشة وحدَها.
        _audit_health_screen(
            request, "السجل الصحي (مختصر)", model_name="HealthRecord", object_id=health_record.pk
        )
        return render(request, "clinic/health_record.html", context)
    # PDPPL م.11 وم.13: تدقيق الوصول للسجل الصحي الحساس (يُفكّ تشفير الحساسية/الأمراض/الأدوية)
    AuditLog.log(
        user=request.user,
        action="view",
        model_name="HealthRecord",
        object_id=health_record.pk,
        object_repr=f"عرض السجل الصحي — {masked_repr(student)}",
        request=request,
    )
    return render(request, "clinic/health_record.html", context)


def _open_full(request, student, health_record):
    """فتحُ الكامل لغير الممرّض: سببٌ من القائمة المغلقة إلزاميّ، والرفضُ يُسجَّل ولا يكشف شيئاً."""
    reason = clean_reason(request.POST.get("reason"))
    if reason is None:
        AuditLog.log(
            user=request.user,
            action="view",
            model_name="HealthRecord",
            object_id=health_record.pk,
            object_repr=f"رُفض فتح السجل الصحي الكامل بلا سبب — {masked_repr(student)}",
            changes={"screen": "السجل الصحي الكامل", "denied": "no_reason"},
            request=request,
        )
        messages.error(request, "اختر سبباً من القائمة لفتح السجل الصحي الكامل.")
        context = _record_context(student, health_record, full=False, can_write=False)
        return render(request, "clinic/health_record.html", context, status=400)
    log_full_open(request, health_record, student, reason, request.POST.get("note", ""))
    # الكاملُ المفتوحُ بسببٍ للقراءة؛ التعديلُ للممرّض.
    context = _record_context(student, health_record, full=True, can_write=False)
    return render(request, "clinic/health_record.html", context)


@login_required
@capability_required("clinic.write")
@require_http_methods(["GET", "POST"])
def record_visit(request, student_id=None):
    """تسجيل زيارة جديدة للعيادة"""
    school = request.user.get_school()
    nurse = request.user

    if request.method == "POST":
        student_id = request.POST.get("student_id")
        student = get_object_or_404(
            CustomUser,
            id=student_id,
            memberships__school=school,
            memberships__role__name="student",
            memberships__is_active=True,
        )

        # ✅ v5.4: ClinicService.record_visit — atomic + notification منفصلة عن الإنشاء
        # يُحلّ مشكلة double save() وإشعار مدمج في الـ view
        try:
            visit = ClinicService.record_visit(
                school=school,
                student=student,
                nurse=nurse,
                reason=request.POST.get("reason", ""),
                symptoms=request.POST.get("symptoms", ""),
                temperature=request.POST.get("temperature") or None,
                treatment=request.POST.get("treatment", ""),
                is_sent_home=request.POST.get("is_sent_home") == "on",
                service_code=request.POST.get("service_code", ""),
                complaint_code=request.POST.get("complaint_code", ""),
            )
        except ValueError:
            return HttpResponse("رمزٌ غير معتمد في الطلب", status=400)
        # ملاحظة: تدقيق إنشاء الزيارة يتم تلقائياً عبر post_save signal (core/signals.py)

        if request.headers.get("HX-Request"):
            return render(request, "clinic/visit_card.html", {"visit": visit})

        return redirect("clinic:health_record", student_id=student_id)

    # اختيارُ الطالب بمكوّنٍ واحدٍ مع الإدخال السريع — لا قائمةَ بكلّ الطلبة (W-20261102-001).
    chosen = student_choice(school, student_id) if student_id else None
    context = {
        "student_id": student_id,
        "chosen": chosen,
        "classes": class_options(school),
        "recent": recent_visitors(school, timezone.localdate()),
        "mode": "form",
    }
    return render(request, "clinic/record_visit.html", context)


@login_required
@capability_required("clinic.write")
@require_http_methods(["POST"])
def confirm_referral_notice(request, visit_id):
    """تأكيدُ الممرّض إحالةَ الطالب للمنزل فيُشعَر وليُّ الأمر بالحدث (بلا السبب) — W-20261020-034."""
    school = request.school
    visit = get_object_or_404(ClinicVisit, id=visit_id, school=school)
    notified = ClinicService.confirm_referral_notice(visit, school, request.user)
    if request.headers.get("HX-Request"):
        return render(
            request, "clinic/visit_card.html", {"visit": visit, "confirm_attempted": True}
        )
    if notified:
        messages.success(request, "أُشعر وليُّ الأمر بالحدث.")
    else:
        messages.warning(
            request, "لم يُرسَل الإشعار: لا بريدَ لوليّ الأمر أو التواصل مجمَّد. تواصل معه مباشرةً."
        )
    return redirect("clinic:health_record", student_id=visit.student_id)


@login_required
@capability_required("clinic.access")
def visits_list(request):
    """قائمة الزيارات بالعيادة: مدًى «من/إلى» واسمُ الطالب — والمحدِّدُ في `selectors.visits_for` (يشاركه التصدير)."""
    visits = visits_for(request.school, request.GET)
    start, end = visit_range(request.GET)

    context = {
        "visits": visits,
        "date_from": start.isoformat() if start else "",
        "date_to": end.isoformat() if end else "",
        "student_filter": request.GET.get("student", ""),
    }

    is_htmx = bool(getattr(request, "htmx", None) or request.headers.get("HX-Request"))
    # القائمةُ تعرض اسمَ الطالب وreason وtreatment: تُدقَّق (أعدادٌ فقط، لا نصوص ولا ترشيح بحث).
    # البحثُ الحيّ (HTMX) يُطلق طلباً لكلّ ضغطة مفتاح: سطرٌ واحد لكلّ مستخدمٍ في الدقيقة (قرار 0101)،
    # أمّا فتحُ الصفحة الكاملة فيُدقَّق دائماً.
    if not is_htmx or cache.add(f"clinic_audit_live:{request.user.pk}:visits_list", 1, 60):
        _audit_health_screen(request, "قائمة الزيارات", model_name="ClinicVisit", rows=visits)

    # HTMX: أعد الجزء فقط (بحث حي + ترشيح)
    if is_htmx:
        return render(request, "clinic/partials/visit_rows.html", context)

    return render(request, "clinic/visits_list.html", context)


@login_required
def visits_export_xlsx(request):
    """سجلُّ الزيارات Excel بالفلاتر نفسها — القدرةُ `clinic.access` يفحصها `respond_export` من السجلّ."""
    return respond_export(request, VISITS_TABLE.kind, params=request.GET.copy())


@login_required
def visits_export_pdf(request):
    """سجلُّ الزيارات PDF بالفلاتر نفسها — النوعُ المسجَّلُ `clinic.visits_pdf`."""
    return respond_export(request, VISITS_PDF_KIND, params=request.GET.copy())


@login_required
@capability_required("clinic.access")
def health_statistics(request):
    """إحصائيات صحية للمدرسة"""
    school = request.user.get_school()

    # ✅ v5.4: ClinicService.get_health_statistics — 4 استعلامات في service layer
    context = ClinicService.get_health_statistics(school)
    return render(request, "clinic/statistics.html", context)


@login_required
@capability_required("clinic.access")
def api_clinic_charts(request):
    """API: بيانات الرسوم البيانية للعيادة — آخر 30 يوم"""
    school = request.user.get_school()
    today = timezone.now().date()

    # ✅ v5.4: ClinicService.get_chart_data — استعلام واحد بدل 60 (N+1 → O(1))
    data = ClinicService.get_chart_data(school, days=30)
    return JsonResponse(data)


@login_required
@capability_required("clinic.write")
@require_http_methods(["GET", "POST"])
def needs_care_import(request):
    """استيرادُ علامة «يحتاج مراعاةً» من ملف (رقمٌ وطنيّ + صفّ) — للممرّض بـ`clinic.write` (W-045).

    الملفُّ يُقرأ في الذاكرة ولا يُحفظ، والتقريرُ أعدادٌ فقط؛ ولا يمرّ الرقمُ في رسالةٍ ولا سجلّ.
    والمنطقُ كلُّه في `clinic.needs_care_services.import_from_request`.
    """
    report, error = import_from_request(request) if request.method == "POST" else (None, "")
    return render(
        request,
        "clinic/needs_care_import.html",
        {"report": report, "error": error},
    )


@login_required
@capability_required("clinic.access")
def clinic_metrics(request):
    """مؤشرات قياس العيادة الخمسة لشهرٍ واحد (W-20261020-035) — مجمَّعةٌ على مستوى العيادة بلا أسماء."""
    from clinic.metrics import cards, clinic_indicators

    school = request.school
    today = timezone.localdate()
    try:
        year, month = (int(part) for part in request.GET.get("month", "").split("-"))
        if not (2000 <= year <= 2100 and 1 <= month <= 12):
            raise ValueError
    except ValueError:
        year, month = today.year, today.month
    context = {
        "cards": cards(clinic_indicators(school, year, month)),
        "month_value": f"{year:04d}-{month:02d}",
    }
    return render(request, "clinic/metrics.html", context)
