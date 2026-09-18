"""operations/views_schedule.py — views إدارة الجداول والغياب والبدلاء."""

import logging
import uuid
from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from core.academic_calendar import academic_year_for, academic_year_for_school
from core.audit_export import log_export
from core.capabilities import capability_required, has_capability
from core.dashboard_presentation import chunk_for_grid
from core.domain.tones import tone_for
from core.models import CustomUser, Membership
from core.models.academic import grade_order
from core.models.access import EXEMPTABLE_ROLES

from .models import (
    ScheduleBaseline,
    ScheduleGeneration,
    ScheduleSlot,
    Subject,
    SubjectClassAssignment,
    SubstituteAssignment,
    TeacherAbsence,
    TeacherExemption,
    TeacherPreference,
)
from .schedule_paper import paper_geometry
from .schedule_selectors import DEFAULT_ORIENTATION, ORIENTATIONS, PAPERS
from .schedule_selectors import browse_lists as _browse_lists
from .schedule_selectors import export_filename as _export_filename
from .schedule_selectors import schedule_print_payload as _schedule_print_payload_core
from .schedule_selectors import schedule_print_selection as _schedule_print_selection_core
from .services import ScheduleService, SubstituteService

logger = logging.getLogger(__name__)

#: بعدها يُعدّ التوليدُ المعلّقُ ميّتاً. والحدُّ أكبرُ من `soft_time_limit`
#: للمهمّة (خمس عشرة دقيقة) بهامشِ انتظارٍ في الطابور — فما تجاوزه لم يعد
#: ينتظر عاملاً، بل يحجب الزرَّ عمّن يريد إعادةَ المحاولة.
_GENERATION_STALE_AFTER = timedelta(minutes=20)


def _reap_stale_generations(school, year):
    """يُنهي التوليداتِ المعلّقةَ التي لا عاملَ لها — ويعيد ما بقي حيّاً.

    فالعاملُ قد يكون مطفأً أو ساقطاً، و`delay()` تنجح لأنّ الوسيطَ قَبِل
    الرسالة ولا أحدَ يقرؤها. وصفٌّ «في الانتظار» إلى الأبد يقفل الزرَّ ويقول
    للمستخدم إنّ شيئاً يجري — وليس شيءٌ يجري.
    """
    cutoff = timezone.now() - _GENERATION_STALE_AFTER
    pending = ScheduleGeneration.objects.filter(
        school=school,
        academic_year=year,
        status__in=ScheduleGeneration.PENDING_STATUSES,
    )
    pending.filter(generated_at__lt=cutoff).update(
        status="failed",
        finished_at=timezone.now(),
        error_message=(
            "لم يلتقط عاملُ الخلفيّة هذه المهمّة خلال عشرين دقيقة — "
            "غالباً لأنّ Celery متوقّف. راجع تشغيلَه ثمّ أعد المحاولة."
        ),
    )
    return pending.filter(generated_at__gte=cutoff).first()


def _safe_schedule_settings_redirect(request, fallback_year=None):
    """Use a same-host Referer or a safe year-aware fallback."""
    referer = request.META.get("HTTP_REFERER", "")

    if referer and url_has_allowed_host_and_scheme(
        referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(referer)

    if fallback_year:
        query = urlencode({"year": fallback_year})
        target = f"{reverse('schedule_settings')}?{query}"

        if url_has_allowed_host_and_scheme(
            target,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(target)

    return redirect("schedule_settings")


# ── الجدول الأسبوعي ──────────────────────────────────────────────


@login_required
@capability_required("schedule.weekly")
def weekly_schedule(request):
    """صفحةُ الجدول الأسبوعيّ — عرضٌ في المنصّة، والطباعةُ ورقتُها الخاصّة.

    قرارُ 2026-09-06 وحّد العرضَ والطباعةَ في ورقةٍ واحدة داخل إطار، فصار
    جدول المعلم يُقاس بالملّيمتر على الشاشة كما على الورق، وصار يحتاج تصغيراً
    شاشيّاً وحيلَ ارتفاعٍ ليَسَعَ النافذةَ بلا تمرير — والتصغيرُ يُصغّر خطَّه
    معه. فقرارُ 2026-09-18: العرضُ جدولٌ عاديٌّ برموز المنصّة (`week_grid.html`
    نفسُ جزئيّة البيانات، بلا الملّيمتر)، والطباعةُ إطارٌ مخفيٌّ بورقتها
    الحقيقيّة كما كانت — مستقلّان، ولا يُصغَّر أحدُهما ليشبه الآخر. والجدولُ
    العامّ (كلّ المعلّمين) يبقى ورقةً في إطارٍ ظاهر: مصفوفةٌ عريضةٌ لا تصلح
    جدولاً عاديّاً، وفيها بحثٌ ولوحُ تحليلٍ يتّصلان بالورقة مباشرةً.

    وما كان في الشبكة القديمة ولم يكن في الورقة انتقل إليها لا سقط: لافتةُ
    معاينة المسودّة (`?generation=`) والتعارضاتُ للإدارة.
    """
    ctx = _schedule_print_payload(request)
    ctx["departments"] = (
        ScheduleService.department_options(ctx["school"], ctx["year"]) if ctx["may_browse"] else []
    )
    ctx["conflicts"] = (
        ScheduleService.detect_conflicts(ctx["school"], ctx["year"])
        if request.user.is_admin() and not ctx["preview"]
        else []
    )
    return render(request, "schedule/print_view.html", ctx)


def _schedule_print_selection(request):
    """ما يُطبع ولمن — يشترك فيه الورقُ وصفحةُ العرض التي تحتضنه.

    الجوهرُ في `operations/schedule_selectors.py` (طبقةُ قراءةٍ لا عرض) —
    البند 5: عاملُ Celery الخلفيّ يستدعيه أيضاً بلا `request` حقيقيّ.
    """
    return _schedule_print_selection_core(request.school, request.user, request.GET)


def _schedule_print_payload(request) -> dict:
    """سياقُ الورقة كاملاً: الاختيارُ وبياناته.

    ثلاثةُ مخارجَ تقرأ هذه الورقة — صفحةٌ في المتصفّح، وPDF، وExcel — فبناؤها
    في موضعٍ واحد يمنع أن يختلف المطبوعُ عن المعروض بعد تعديلٍ في أحدهما.
    الجوهرُ في `operations/schedule_selectors.py` للسبب نفسه أعلاه.
    """
    return _schedule_print_payload_core(request.school, request.user, request.GET)


# `X_FRAME_OPTIONS = "DENY"` عامٌّ على المشروع، فيمنع عرض الورقة داخل إطار
# صفحة العرض في المنصّة — والمصدرُ هو الموقع نفسه، فـ sameorigin يكفي.
@xframe_options_sameorigin
@login_required
@capability_required("schedule.print")
def schedule_print(request):
    """ورقةُ الطباعة نفسها — A4/A3، بلا هيدر المنصّة ولا فوترها."""
    return render(request, "schedule/print_schedule.html", _schedule_print_payload(request))


@login_required
@capability_required("schedule.print")
def schedule_export_pdf(request):
    """يُنشئ صفَّ تصديرٍ خلفيّاً ويُرجع فوراً — لا توليدَ PDF متزامناً.

    WeasyPrint بطيءٌ بما يكفي ليُخالف معيار المشروع (>300ms → Background
    Job، راجع `operations/tasks.py::render_schedule_export_task`). صفحةُ
    المتابعة تتحدَّث تلقائياً وتُنزّل الناتجَ حين يجهز.
    """
    from core.models import ExportJob
    from operations.tasks import render_schedule_export_task

    query = request.GET.urlencode()
    log_export(request, "schedule.pdf", object_repr=f"schedule.pdf?{query}")
    job = ExportJob.objects.create(
        school=request.school,
        requested_by=request.user,
        kind="schedule.pdf",
        query_string=query,
    )
    render_schedule_export_task.delay(str(job.id), "pdf")
    return redirect("export_job_status", job_id=job.id)


@login_required
@capability_required("schedule.print")
def schedule_export_excel(request):
    """صفُّ تصديرٍ خلفيّ أيضاً — الشرحُ في `schedule_export_pdf`."""
    from core.models import ExportJob
    from operations.tasks import render_schedule_export_task

    query = request.GET.urlencode()
    log_export(request, "schedule.xlsx", object_repr=f"schedule.xlsx?{query}")
    job = ExportJob.objects.create(
        school=request.school,
        requested_by=request.user,
        kind="schedule.xlsx",
        query_string=query,
    )
    render_schedule_export_task.delay(str(job.id), "xlsx")
    return redirect("export_job_status", job_id=job.id)


@login_required
def export_job_status(request, job_id):
    """متابعة/تنزيل صفّ تصديرٍ خلفيّ — تتحدَّث تلقائياً حتى يجهز الناتج."""
    from urllib.parse import quote

    from core.models import ExportJob

    job = get_object_or_404(ExportJob, id=job_id, school=request.school, requested_by=request.user)
    if job.status == "done":
        response = HttpResponse(bytes(job.content), content_type=job.content_type)
        response["Content-Disposition"] = (
            f"attachment; filename=export; filename*=UTF-8''{quote(job.filename)}"
        )
        return response
    return render(request, "operations/export_job_status.html", {"job": job})


@login_required
@capability_required("schedule.print")
def schedule_print_view(request):
    """الرابطُ القديم لصفحة الطباعة — صارت هي صفحةَ الجدول، فيُحال إليها.

    يبقى الاسمُ لأنّ روابطَ قديمةً ومحفوظاتٍ تقصده؛ والاختيارُ في الرابط يُحمل
    كما هو.
    """
    from django.urls import reverse

    query = request.META.get("QUERY_STRING", "")
    return redirect(reverse("weekly_schedule") + (f"?{query}" if query else ""))


# ── نظام البديل ──────────────────────────────────────────────────

#: لونُ الغياب بحاله — كان شرطاً في القالبين: مغطّى أخضر، وغيرُ مغطّى أحمر،
#: وما سواهما (بانتظار البديل) كهرمانيّ.
_ABSENCE_TONES = {"covered": ("green", "success"), "uncovered": ("red", "danger")}
_ABSENCE_TONE_DEFAULT = ("amber", "warning")

#: لونُ درجة التوليد المنسوبة إلى الأساس: 98 فأعلى نجاح، و90 فأعلى تنبيه، ودونها خطر.
LAB_RELATIVE_TONES = ((98, "success"), (90, "warning"), (None, "danger"))

#: حالُ التعيين: قبِل أخضر، ورفض أحمر، ومُعيَّنٌ لم يُجِب بعدُ أزرق.
_ASSIGNMENT_TONES = {"confirmed": "success", "declined": "danger"}


def _assignment_tone(assignment) -> str:
    return _ASSIGNMENT_TONES.get(assignment.status, "info")


def _absence_presentation(absence) -> None:
    """يلصق بالغياب لونَ بطاقته ولونَ سطر حاله — الحكمُ هنا لا في القالب."""
    absence.tone, absence.status_tone = _ABSENCE_TONES.get(absence.status, _ABSENCE_TONE_DEFAULT)


def _slot_presentation(slot, assignment, available) -> dict:
    """حصّةُ الغائب في بطاقة كيان: الحصّة · البديل · الحالة.

    المغطّاةُ خضراء وسطرُ حالها حالُ التعيين (قبِل/رفض/مُعيَّن)؛ وغيرُ المغطّاة
    حمراء وسطرُها عددُ المتاحين — أو «لا معلمين متاحين» حين لا يُوجد أحد.
    """
    if assignment:
        status_tone = _assignment_tone(assignment)
        tone, status_label = "green", f"مُغطّاة · {assignment.get_status_display()}"
    elif available:
        tone, status_tone = "red", "danger"
        status_label = f"بحاجة بديل · {len(available)} متاح"
    else:
        tone, status_tone = "red", "danger"
        status_label = "بحاجة بديل · لا معلمين متاحين في هذا الوقت"
    return {
        "slot": slot,
        "assignment": assignment,
        "available": available,
        "title": f"الحصّة {slot.period_number}",
        "who": f"{slot.subject or '—'} · {slot.class_group}",
        "time_label": f"{slot.start_time:%H:%M}–{slot.end_time:%H:%M}"
        if slot.start_time and slot.end_time
        else "",
        "tone": tone,
        "status_tone": status_tone,
        "status_label": status_label,
    }


@login_required
@capability_required("operations.reports")
def teacher_absence_list(request):
    """قائمة غيابات المعلمين — للمدير والمنسق"""
    from core.permissions import get_department_teacher_ids

    school = request.school
    selected = request.GET.get("date", timezone.now().date().isoformat())
    try:
        abs_date = date.fromisoformat(selected)
    except ValueError:
        abs_date = timezone.now().date()

    absences = (
        TeacherAbsence.objects.filter(school=school, date=abs_date)
        .select_related("teacher", "reported_by")
        .prefetch_related("assignments__substitute")
    )
    dept_ids = get_department_teacher_ids(request.user)
    if dept_ids is not None:
        absences = absences.filter(teacher_id__in=dept_ids)
    absences = list(absences)
    for absence in absences:
        _absence_presentation(absence)

    return render(
        request, "substitute/absence_list.html", {"absences": absences, "abs_date": abs_date}
    )


@login_required
@capability_required("operations.substitutes_manage")
def register_teacher_absence(request):
    """تسجيل غياب معلم — للمدير والمنسق، ومشرفُ الجناح يقرأ ولا يكتب هنا."""
    from core.permissions import get_department_teacher_ids

    school = request.school

    if request.method == "POST":
        teacher = get_object_or_404(
            CustomUser.objects.in_school(school), id=request.POST["teacher"]
        )
        raw_date = request.POST.get("date", timezone.now().date().isoformat())
        try:
            abs_date = date.fromisoformat(raw_date)
        except ValueError:
            abs_date = timezone.now().date()

        reason = request.POST.get("reason", "other")
        reason_notes = request.POST.get("reason_notes", "")
        absence = SubstituteService.register_absence(
            school, teacher, abs_date, reason, reason_notes, reported_by=request.user
        )
        messages.success(request, f"تم تسجيل غياب {teacher.full_name} بتاريخ {abs_date}")
        return redirect("absence_detail", absence_id=absence.id)

    dept_ids = get_department_teacher_ids(request.user)
    if dept_ids is not None:
        teachers = CustomUser.objects.filter(id__in=dept_ids).order_by("full_name")
    else:
        teacher_ids = Membership.objects.filter(
            school=school,
            is_active=True,
            role__name__in=("teacher", "coordinator", "ese_teacher", "e_projects_coordinator"),
        ).values_list("user_id", flat=True)
        teachers = CustomUser.objects.filter(id__in=teacher_ids).order_by("full_name")

    return render(
        request,
        "substitute/register_absence.html",
        {
            "teachers": teachers,
            "reasons": TeacherAbsence.REASON,
            "today": timezone.now().date(),
        },
    )


@login_required
@capability_required("operations.reports")
def absence_detail(request, absence_id):
    """تفاصيل الغياب + تعيين البدلاء"""
    from core.permissions import get_department_teacher_ids

    school = request.school
    absence = get_object_or_404(TeacherAbsence, id=absence_id, school=school)

    dept_ids = get_department_teacher_ids(request.user)
    if dept_ids is not None and absence.teacher_id not in dept_ids:
        return HttpResponse("هذا المعلم ليس من قسمك", status=403)

    our_day = SubstituteService._date_to_day(absence.date)
    slots = (
        ScheduleSlot.objects.live(school)
        .filter(teacher=absence.teacher, day_of_week=our_day)
        .select_related("class_group", "subject")
    )

    assignments = {
        a.slot_id: a
        for a in SubstituteAssignment.objects.filter(absence=absence).select_related("substitute")
    }
    slots_data = []
    for slot in slots:
        available = SubstituteService.get_available_teachers(
            school,
            absence.date,
            slot.day_of_week,
            slot.period_number,
            exclude_teacher=absence.teacher,
            subject_id=slot.subject_id,
        )
        slots_data.append(_slot_presentation(slot, assignments.get(slot.id), available))

    # عددٌ لا سلسلةُ آحاد: القالبُ كان يطبع «1» لكلّ حصّةٍ مغطّاة، فثلاثٌ تُقرأ «111».
    covered_count = sum(1 for row in slots_data if row["assignment"])
    _absence_presentation(absence)
    return render(
        request,
        "substitute/absence_detail.html",
        {
            "absence": absence,
            "slots_data": slots_data,
            "subtitle": f"{absence.teacher.full_name} — {date_format(absence.date)}",
            "covered_count": covered_count,
            "covered_label": f"من {len(slots_data)}",
            # حصّةٌ بلا بديلٍ واحدةٌ تكفي للأحمر؛ ولا حصصَ = لا شيءَ ينتظر.
            "covered_tone": "green" if covered_count == len(slots_data) else "red",
            # مشرفُ الجناح يفتح هذه الصفحةَ (`operations.reports`) ولا يعيّن
            # (`operations.substitutes_manage`) — فالنموذجُ يظهر لمن يكتب وحدَه.
            "can_assign": has_capability(request.user, "operations.substitutes_manage"),
        },
    )


@login_required
@capability_required("operations.substitutes_manage")
@require_POST
def assign_substitute(request, absence_id, slot_id):
    """HTMX: تعيين بديل لحصة — مشرفُ الجناح يرى المعيَّن ولا يعيّنه."""
    from core.permissions import get_department_teacher_ids

    school = request.school
    absence = get_object_or_404(TeacherAbsence, id=absence_id, school=school)
    slot = get_object_or_404(ScheduleSlot, id=slot_id, school=school)

    dept_ids = get_department_teacher_ids(request.user)
    if dept_ids is not None and absence.teacher_id not in dept_ids:
        return HttpResponse("هذا المعلم ليس من قسمك", status=403)

    substitute = get_object_or_404(CustomUser, id=request.POST["substitute"])
    assignment = SubstituteService.assign_substitute(
        absence,
        slot,
        substitute,
        assigned_by=request.user,
        notes=request.POST.get("notes", ""),
    )
    available = SubstituteService.get_available_teachers(
        school,
        absence.date,
        slot.day_of_week,
        slot.period_number,
        exclude_teacher=absence.teacher,
        subject_id=slot.subject_id,
    )
    return render(
        request,
        "substitute/partials/slot_card.html",
        # مسارُ هذا الردّ دائماً وراء `operations.substitutes_manage` (الديكوريتور
        # أعلاه) — لكن `can_assign` صريحةٌ هنا احتراساً لا اتّكالاً على أنّ
        # `item.assignment` يبقى صحيحاً أبداً.
        {
            "item": _slot_presentation(slot, assignment, available),
            "absence": absence,
            "can_assign": True,
        },
    )


@login_required
@capability_required("operations.reports")
def substitute_report(request):
    """تقرير الحصص البديلة"""
    from core.permissions import get_department_teacher_ids

    school = request.school
    today = timezone.now().date()
    date_from = date.fromisoformat(request.GET.get("from", (today - timedelta(days=7)).isoformat()))
    date_to = date.fromisoformat(request.GET.get("to", today.isoformat()))

    assignments = SubstituteService.get_substitute_report(school, date_from, date_to)
    dept_ids = get_department_teacher_ids(request.user)
    if dept_ids is not None:
        assignments = [a for a in assignments if a.absence.teacher_id in dept_ids]

    summary = {}
    assignments = list(assignments)
    for a in assignments:
        a.status_tone = _assignment_tone(a)
        name = a.substitute.full_name
        summary[name] = summary.get(name, 0) + 1

    return render(
        request,
        "substitute/report.html",
        {
            "assignments": assignments,
            "summary": sorted(summary.items(), key=lambda x: -x[1]),
            "date_from": date_from,
            "date_to": date_to,
        },
    )


# ── الجدولة الذكية ────────────────────────────────────────────────


def _quality_gate_kpis(by_key: dict) -> list[dict]:
    """بوّابةُ الصلاحية: ثلاثةُ أرقامٍ لا تقبل النقاش — بطاقةُ رقمٍ لكلٍّ منها.

    كانت ثلاثَ لوحاتٍ مصمَتةٍ بنظام بطاقاتٍ خاصٍّ بالصفحة (`gate-tile`)، وحكمُ
    النجاح شرطٌ في القالب. والعتباتُ هي نفسُها: التعارضاتُ صفر، والاكتمالُ 100،
    والأيّامُ الفارغةُ بلا تفريغٍ صفر — وما خالفها أحمر.
    """

    def metric(key):
        row = by_key.get(key) or {}
        return row.get("value"), row.get("detail") or {}

    conflicts, conflicts_detail = metric("validity.hard_conflicts")
    conflicts_sub = " ".join(f"{k}: {v}" for k, v in conflicts_detail.items() if v)
    completeness, completeness_detail = metric("validity.completeness")
    uncovered, uncovered_detail = metric("validity.uncovered_days")
    names = " · ".join(str(name) for name in uncovered_detail)
    return [
        {
            "label": "تعارضات صلبة",
            "value": "—" if conflicts is None else conflicts,
            "sub": conflicts_sub,
            "title": conflicts_sub,
            "tone": "green" if conflicts == 0 else "red",
        },
        {
            "label": "اكتمال النصاب",
            "value": "—" if completeness is None else f"{completeness}%",
            "sub": (
                f"{completeness_detail.get('placed')} من {completeness_detail.get('required')} حصّة"
                if completeness_detail
                else ""
            ),
            "title": "",
            "tone": "green" if completeness == 100 else "red",
        },
        {
            "label": "معلّمون بيومٍ فارغ",
            "value": "—" if uncovered is None else uncovered,
            "sub": names,
            "title": f"معلّمون لهم يومٌ فارغٌ بلا تفريغ: {names}" if names else "",
            "tone": "green" if uncovered == 0 else "red",
        },
    ]


@login_required
@capability_required("schedule.admin")
def schedule_quality_lab(request):
    """مختبرُ جودة الجدول بصريّاً: بوّابةُ الصلاحية، ورادارُ المجموعات، وبطاقاتُ
    المؤشرات بفرقها عن المرجع، وأشدُّ المعلّمين ضغطاً، والموارد.

    الجدولُ المقيس: الحيُّ أو توليدٌ بعينه (`?schedule=`). والمرجعُ: آخرُ أساسٍ
    محفوظ، أو الحيُّ، أو توليدٌ آخر (`?ref=`). و`POST save_baseline` يحفظ
    القياسَ الحاليَّ أساساً باسم.
    """

    from operations.schedule_lab import (
        SECTIONS,
        ScheduleLab,
        grouped_rows,
        latest_baseline,
        section_scores,
    )

    school = request.school
    year = request.GET.get("year") or academic_year_for(request)
    generations = list(
        ScheduleGeneration.objects.filter(school=school, academic_year=year)
        .exclude(status__in=("failed", "queued", "running"))
        .select_related("generated_by")[:12]
    )

    def _pick(param, default):
        ident = request.GET.get(param, default) or default
        if ident == "live":
            return "live", None
        gen = next((g for g in generations if str(g.id) == ident), None)
        return ("gen", gen) if gen else ("live", None)

    kind, target = _pick("schedule", "live")
    if kind == "gen":
        metrics = target.metrics or ScheduleLab.for_generation(target).compute()
        title = f"التوليد {target.generated_at:%Y-%m-%d %H:%M} ({target.get_status_display()})"
    else:
        metrics = ScheduleLab.for_live(school, year).compute()
        title = "الجدول الحيّ"

    if request.method == "POST" and request.POST.get("save_baseline"):
        label = (request.POST.get("label") or "").strip()[:60] or f"أساس {timezone.now():%Y-%m-%d}"
        ScheduleBaseline.objects.update_or_create(
            school=school,
            academic_year=year,
            label=label,
            defaults={"metrics": metrics, "created_by": request.user},
        )
        messages.success(request, f"حُفظ «{title}» أساساً باسم «{label}».")
        query = urlencode({"year": year, "schedule": request.GET.get("schedule", "live")})
        return redirect(f"{reverse('schedule_quality_lab')}?{query}")

    ref = request.GET.get("ref", "baseline") or "baseline"
    baseline = latest_baseline(school, year)
    if ref == "baseline" and baseline is not None:
        ref_metrics, ref_title = baseline.metrics, f"الأساس «{baseline.label}»"
    elif ref == "live":
        ref_metrics, ref_title = ScheduleLab.for_live(school, year).compute(), "الجدول الحيّ"
    else:
        rkind, rtarget = _pick("ref", "live")
        if rkind == "gen":
            ref_metrics = rtarget.metrics or ScheduleLab.for_generation(rtarget).compute()
            ref_title = f"التوليد {rtarget.generated_at:%Y-%m-%d %H:%M}"
        else:
            ref_metrics, ref_title = None, ""

    groups = grouped_rows(metrics, ref_metrics)
    scores = section_scores(metrics)
    ref_scores = section_scores(ref_metrics) if ref_metrics else {}
    by_key = {r["key"]: r for g in groups for r in g["rows"]}
    shown = [c for c in SECTIONS if scores.get(c) is not None]
    radar = {
        "labels": [SECTIONS[c] for c in shown],
        "current": [scores[c] for c in shown],
        "reference": [ref_scores.get(c) for c in shown],
    }
    shown_groups = [g for g in groups if g["code"] != "validity"]
    for g in shown_groups:
        score = scores.get(g["code"])
        g["score_label"] = f"درجة {score}" if score is not None else "درجة —"
    return render(
        request,
        "schedule/quality_lab.html",
        {
            "lab_subtitle": " — ".join(
                part for part in (title, f"مقابل {ref_title}" if ref_title else "", year) if part
            ),
            "gate_kpis": _quality_gate_kpis(by_key),
            "year": year,
            "title": title,
            "ref_title": ref_title,
            "schedule_param": request.GET.get("schedule", "live"),
            "ref_param": ref,
            "generations": generations,
            "baseline": baseline,
            "groups": shown_groups,
            "gate": by_key,
            "by_key": by_key,
            "scores": scores,
            "radar_json": radar,
            "stress_top": by_key.get("fairness.stress", {}).get("detail", {}),
            "resources": by_key.get("resources.utilization", {}).get("detail", {}),
            "missed_prefs": by_key.get("fairness.preference_satisfaction", {}).get("detail", {}),
            "can_save": request.user.is_superuser
            or request.user.get_role() in ("principal", "vice_academic"),
        },
    )


@login_required
@capability_required("schedule.admin")
def smart_schedule_view(request):
    """صفحة إدارة الجدولة الذكية"""
    school = request.school
    year = request.GET.get("year") or academic_year_for(request)

    assignments = (
        SubjectClassAssignment.objects.filter(school=school, academic_year=year, is_active=True)
        .select_related("class_group", "subject", "teacher")
        .order_by(grade_order("class_group__grade"), "class_group__section", "subject__name_ar")
    )
    # التوليدُ الجاري — الصفحةُ تُخفي الزرَّ وتستطلع الحالةَ ما دام قائماً.
    # والقتلُ يسبق القراءة: صفٌّ متقادمٌ يُوسَم فاشلاً قبل أن يُعرض «جارياً».
    pending_generation = _reap_stale_generations(school, year)
    from django.db.models import Count

    # حصصُ التوليد تُعَدّ من صفوفها لا من رقمٍ خُزّن يومَ التوليد: الرقمُ المخزَّن
    # كان يَعُدّ خانات الشبكة (839) والتوزيعاتُ تُعَدّ بالحصص (870) — فالتاريخُ
    # كلُّه كان يقول «96.4%» عن جداولَ كاملة.
    generations = list(
        ScheduleGeneration.objects.filter(school=school, academic_year=year)
        .select_related("generated_by")
        .annotate(slot_rows=Count("slots"))[:5]
    )
    total_weekly = sum(a.weekly_periods for a in assignments)
    #: التوازي يفرّق الرقمين: حصّتان تُدرَّسان في التوقيت الواحد لمعلّمَي
    #: المادّتين، وخانةٌ واحدةٌ تُشغَل من أسبوع الشعبة.
    #:
    #:     InstructionalPeriods ≠ OccupiedSlots
    #:
    #: وخلطُهما هو ما يجعل «مطلوب 37 والسعة 35» يبدو فائضاً وليس بفائض. فيُقال
    #: الرقمان معاً حيث يُقرأ المجموع، لا رقمٌ واحدٌ يُحمَل على المعنيين.
    from operations.services import CapacityCheckService as _Cap

    occupied_slots = _Cap.slot_demand(assignments)
    shared_periods = total_weekly - occupied_slots
    # ما وُضع فعلاً مقابلَ ما تطلبه التوزيعاتُ اليوم — لا رقمٌ مجرَّدٌ لا يُقاس على شيء.
    # ومسودّةٌ لم تعد تغطّي الطلبَ الحاليَّ هي بالضبط ما يجب أن يلفت النظر.
    # مؤشراتُ المختبر لكلّ توليدٍ بجانب الأساس المرجعيّ: فرقٌ لا رقمٌ مجرَّد.
    from operations.schedule_lab import (
        ScheduleLab,
        compare,
        latest_baseline,
        overall_score,
        relative_score,
    )

    baseline = latest_baseline(school, year)
    for g in generations:
        g.placed = g.slot_rows or g.total_slots_created
        ratio = 100 * g.placed / total_weekly if total_weekly else 0.0
        # المؤشّراتُ تُعاد من الحصص لا تُقرأ من الصفّ: المخزَّنُ كُتب بتعريفاتِ
        # يومه، وقراءتُه بمنحنيات اليوم تخلط مسطرتين في عمودٍ واحد. والحصصُ
        # هي الواقعة، والدرجةُ حكمٌ يُشتقّ منها كلَّما عُرض.
        lab = ScheduleLab.for_generation(g).compute() if g.placed else (g.metrics or {})
        g.lab_rows = compare(lab, baseline.metrics if baseline else None) if lab else []
        g.lab_absolute = overall_score(lab) if lab else None
        g.lab_relative = relative_score(lab, baseline.metrics) if baseline and lab else None
        # نصٌّ لا رقم: `floatformat` يتبع اللغةَ فيكتب «100٫0»، والرقمُ هنا يُقرأ ويُقارَن.
        g.placed_ratio = f"{ratio:.1f}"

    #: الحسابُ بالعدّ يسبق البحثَ بالساعات — طاقةُ الشُّعب والمعلّمين والموارد
    #: وتباعدُ الأيّام. وكان هنا فحصُ الشُّعب وحدَه، وهو اليومَ أحدُ خمسة.
    from operations import constraint_registry, schedule_feasibility

    feasibility = schedule_feasibility.check(school, year)
    #: ما خالف افتراضَ الشيفرة من القيود — يُعرض ليُقاس، فالرتبةُ لا يكشف
    #: أثرَها عدٌّ: الفحصُ يقيس الطاقةَ لا تشابكَ القيود.
    policy = constraint_registry.resolve(school, year)
    overridden = [(code, constraint_registry.REGISTRY[code].title) for code in policy.overridden]

    return render(
        request,
        "schedule/smart_schedule.html",
        {
            **_smart_schedule_presentation(generations, year, occupied_slots, shared_periods),
            # حكمُ الفحص في طرف ترويسته — كان لونَ الشريط كلِّه وحدَّ البطاقة.
            "feasibility_verdict": "عجزٌ يقينيّ" if feasibility.blocking else "لا عجزَ في العدّ",
            "occupied_slots": occupied_slots,
            "shared_periods": shared_periods,
            # جدولُ التوزيعات كان يُعرض هنا كاملاً — وشاشةُ الإسناد تعرضه
            # بأدواتها. فبقي العددُ وحدَه: مؤشّراً في الأعلى، وشرطاً للفراغ.
            "assignments_count": len(assignments),
            "generations": generations,
            "pending_generation": pending_generation,
            # زرُّ الاعتماد لمن يملكه: كان يظهر لكلّ من يرى الصفحةَ، و`admin`
            # يضغطه فيُصدَم بـ403.
            "can_approve": request.user.is_superuser
            or request.user.get_role() in ("principal", "vice_academic"),
            "year": year,
            "baseline": baseline,
            "total_weekly": total_weekly,
            "classes_count": assignments.values("class_group").distinct().count(),
            "teachers_count": assignments.values("teacher").distinct().count(),
            "feasibility": feasibility,
            "constraint_overrides": overridden,
        },
    )


def _smart_schedule_presentation(generations, year, occupied_slots, shared_periods) -> dict:
    """ما يُحكم فيه بشرطٍ في صفحة التوليد — يُحسب هنا لا في القالب.

    * لونُ الدرجة المنسوبة إلى الأساس: 98 فأعلى نجاح، و90 فأعلى تنبيه، وما
      دونها خطر — العتباتُ التي كانت في القالب.
    * مؤشّراتُ المختبر مصفوفةٌ واحدة: صفٌّ لكلّ مؤشّر، وعمودٌ للأساس ثمّ عمودٌ
      لكلّ توليد. كانت جدولاً داخل `details` داخل صفٍّ من سجلّ التوليد، لكلّ
      توليدٍ جدولُه، فلا يُقارَن توليدٌ بتوليدٍ إلّا بفتح اثنين والتنقّل بينهما.
    * وصفوفُها لا تُقصّ (اثنان وعشرون مؤشّراً فأكثر) ومحتوى الصفّ ضيّق — فتُقسَّم
      ثلاثة أعمدةٍ متجاورة (معيار تخطيط الصفحات) بدل عمودٍ واحدٍ يطيل الصفحة.
    """
    for g in generations:
        g.lab_tone = tone_for(g.lab_relative, LAB_RELATIVE_TONES, empty="")
    measured = [g for g in generations if g.lab_rows]
    rows: dict[str, dict] = {}
    for column, g in enumerate(measured):
        for r in g.lab_rows:
            row = rows.setdefault(
                r["key"],
                {
                    "label": r["label"],
                    "unit": r["unit"],
                    "baseline": r["baseline"],
                    "cells": [None] * len(measured),
                },
            )
            row["cells"][column] = r
    return {
        "page_subtitle": f"توليد الجدول الأسبوعي تلقائياً — {year}",
        # الرقمان معاً حيث يُقرأ المجموع: الحصصُ تُدرَّس، والخاناتُ تُشغَل.
        "weekly_sub": f"تشغل {occupied_slots} خانة" if shared_periods else "",
        "weekly_title": (
            f"{shared_periods} حصّةً في خاناتٍ مشتركة (توازٍ) — الحصّتان تُدرَّسان في التوقيت الواحد"
            if shared_periods
            else ""
        ),
        "lab_columns": measured,
        "lab_matrix": list(rows.values()),
        "lab_matrix_cols": chunk_for_grid(list(rows.values()), 3),
    }


def _smart_schedule_redirect(year):
    """العودةُ إلى صفحة الجدولة للعام نفسِه الذي طُلب التوليدُ له.

    كان الردُّ `redirect("smart_schedule")` بلا عام، فتُفتح الصفحةُ على العام
    الافتراضيّ: من ولّد جدولَ العام القادم يرى سجلَّ توليدِ عامٍ آخر — ولا يرى
    مسودّتَه، ولا الرقمَ الذي يقول كم حصّةً وُضعت.
    """
    return redirect(f"{reverse('smart_schedule')}?{urlencode({'year': year})}")


@login_required
@capability_required("schedule.admin")
@require_POST
def smart_generate(request):
    """يضع التوليدَ في الطابور — ولا يُولّد داخل الطلب.

    قِيس زمنُ التوليد في هذه المدرسة على ثلاثةٍ وثلاثين عمليّةً فكان بين
    ٤٢ ثانيةً و٢٧٩، و`gunicorn` يقطع الطلبَ عند مئةٍ وعشرين ثانيةً و`nginx`
    مثلَه. فالزرُّ المتزامنُ كان يَعِد بجدولٍ ويُسلّم «502» بعد دقيقتين،
    والتوليدُ يمضي في عاملٍ لا أحدَ ينتظره.

    والصفُّ يُنشأ هنا قبل الإرسال لا في العامل: هو ما يراه المستخدمُ حالةً،
    وهو ما يمنع توليداً ثانياً فوق جارٍ.
    """
    school = request.school
    year = request.POST.get("year") or academic_year_for(request)

    # حارسُ التزامن — توليدان متوازيان يتنازعان جدولاً واحداً، وآخرُهما يفوز
    # بلا أن يعلم أحدٌ أنّ أوّلَهما كان.
    running = _reap_stale_generations(school, year)
    if running is not None:
        messages.info(
            request,
            "هناك توليدٌ جارٍ لهذا العام — انتظر انتهاءَه قبل أن تبدأ آخر.",
        )
        return _smart_schedule_redirect(year)

    generation = ScheduleGeneration.objects.create(
        school=school,
        academic_year=year,
        generated_by=request.user,
        status="queued",
    )

    from .tasks import generate_smart_schedule_task

    try:
        generate_smart_schedule_task.delay(str(generation.id))
    except Exception as exc:  # وسيطُ الرسائل ساقطٌ أو غيرُ مهيّأ
        # ولا يُترك الصفُّ «في الانتظار» إلى الأبد: انتظارٌ بلا عاملٍ كذبةٌ
        # صامتة. يُقال إنّ العاملَ غيرُ متاح، ويُقال ماذا يفعل المسؤول.
        logger.exception("تعذّر إرسال مهمّة توليد الجدول: %s", exc)
        generation.status = "failed"
        # سببُ السقوط في السجلّ أعلاه؛ والمعروضُ للمستخدم ما يفعله لا ما رآه النظام.
        generation.error_message = "تعذّر إرسال المهمّة إلى عامل الخلفيّة — راجع تشغيل Celery."
        generation.finished_at = timezone.now()
        generation.save(update_fields=["status", "error_message", "finished_at"])
        messages.error(
            request,
            "عاملُ المهامّ الخلفيّة غيرُ متاح، ولم يبدأ التوليد. راجع تشغيل Celery ثمّ أعد المحاولة.",
        )
        return _smart_schedule_redirect(year)

    messages.success(
        request,
        "بدأ توليد الجدول في الخلفيّة — تُحدَّث الحالةُ في هذه الصفحة تلقائيّاً، ويصلك إشعارٌ عند انتهائه.",
    )
    return _smart_schedule_redirect(year)


@login_required
@capability_required("schedule.admin")
def smart_generate_status(request):
    """حالةُ آخر توليدٍ — تسألها الصفحةُ كلَّ بضع ثوانٍ ما دام هناك جارٍ.

    وحدُّ ما تُرجعه مقصود: حالةٌ ونصٌّ مختصر. فصفحةٌ تُعيد تحميلَ نفسها كلَّ
    ثلاثِ ثوانٍ على مئاتِ الصفوف تُثقل الخادمَ لتقول «ما زال يعمل».
    """
    school = request.school
    year = request.GET.get("year") or academic_year_for(request)

    # ما تقادم لا يُقال عنه «جارٍ» — وإلّا استطلعت الصفحةُ إلى الأبد.
    _reap_stale_generations(school, year)

    generation = (
        ScheduleGeneration.objects.filter(school=school, academic_year=year)
        .only(
            "id",
            "status",
            "quality_score",
            "total_slots_created",
            "generation_time_ms",
            "error_message",
        )
        .first()
    )
    if generation is None:
        return JsonResponse({"status": None, "pending": False})

    return JsonResponse(
        {
            "id": str(generation.id),
            "status": generation.status,
            "status_label": generation.get_status_display(),
            "pending": generation.is_pending,
            "quality": round(generation.quality_score),
            "slots": generation.total_slots_created,
            "elapsed_ms": generation.generation_time_ms,
            "error": generation.error_message,
        }
    )


@login_required
@capability_required("operations.reports")
def teacher_load_report(request):
    """تقرير أحمال المعلمين"""
    from core.permissions import get_department_teacher_ids

    school = request.school
    year = request.GET.get("year") or academic_year_for(request)

    dept_ids = get_department_teacher_ids(request.user)
    if dept_ids is not None:
        teachers = CustomUser.objects.filter(id__in=dept_ids).order_by("full_name")
    else:
        teacher_ids = Membership.objects.filter(
            school=school,
            is_active=True,
            role__name__in=("teacher", "coordinator", "ese_teacher", "e_projects_coordinator"),
        ).values_list("user_id", flat=True)
        teachers = CustomUser.objects.filter(id__in=teacher_ids).order_by("full_name")

    # ✅ v5.4: TeacherLoadService.get_teacher_load_data — business logic في service layer
    from operations.services import TeacherLoadService

    data = TeacherLoadService.get_teacher_load_data(school, year, teachers)
    _mark_teacher_loads(data)

    return render(
        request,
        "schedule/teacher_load.html",
        {
            "year": year,
            **data,
        },
    )


#: ما يُعدّ حملاً زائداً أو منخفضاً في تقرير الأعباء — العتباتُ التي كانت في القالب.
LOAD_MARGIN = 3  # حصصٌ أسبوعيّةٌ فوق المتوسّط أو دونه
HEAVY_DAY = 6  # حصصٌ في اليوم الواحد
BUSY_SUBSTITUTE = 3  # حصصُ بديلٍ في الشهر


def _mark_teacher_loads(data: dict) -> None:
    """صنفُ كلّ خليّةٍ في تقرير الأعباء — كان شرطاً بألوان Tailwind في القالب.

    الأسبوعيُّ فوق المتوسّط بثلاثٍ زائد، ودونه بثلاثٍ منخفض؛ واليومُ بستٍّ
    فأكثر زائد، والفارغُ مطفأ؛ وأيّامُ التفريغ خضراء؛ وثلاثُ بدائلَ فأكثر تنبيه.
    """
    avg = data.get("avg_weekly") or 0
    for d in data.get("teacher_data", []):
        weekly = d["weekly"]
        d["weekly_class"] = (
            "load-over"
            if weekly > avg + LOAD_MARGIN
            else "load-under"
            if weekly < avg - LOAD_MARGIN
            else ""
        )
        d["day_cells"] = [
            (count, "load-over" if count >= HEAVY_DAY else "load-zero" if count == 0 else "")
            for count in d["days"]
        ]
        d["max_class"] = "load-over" if d["max_daily"] >= HEAVY_DAY else ""
        d["free_class"] = "load-free" if d["free_days"] > 0 else "load-zero"
        d["subs_class"] = "load-busy" if d["subs"] >= BUSY_SUBSTITUTE else ""
    data["avg_label"] = f"{avg:.1f}"
    data["legend_over"] = f"{avg + LOAD_MARGIN:.1f}"
    data["legend_under"] = f"{avg - LOAD_MARGIN:.1f}"


# ── تفضيلات المعلم ──────────────────────────────────────────────


@login_required
@capability_required("schedule.preferences")
def teacher_preferences(request):
    """صفحة تفضيلات المعلم للجدولة الذكية"""
    school = request.school
    year = request.GET.get("year") or academic_year_for(request)
    pref, _created = TeacherPreference.objects.get_or_create(
        teacher=request.user,
        school=school,
        academic_year=year,
    )

    if request.method == "POST":
        # القيمُ من قائمةٍ مغلقة، و`int()` على نصٍّ حرٍّ يُسقط الصفحةَ بـ500
        # ويقبل ما لا معنى له. فما خرج عن المدى يعود إلى الافتراضيّ.
        pref.max_daily_periods = _one_of(request.POST.get("max_daily_periods"), range(1, 8), 5)
        #: و«حصّةٌ واحدة» سقفٌ مشروع: أي لا حصّتين متجاورتين البتّة — وهو
        #: قيدٌ قائمٌ لمعلّمٍ في المدرسة، والمحرّكُ يقرؤه ولا يرفعه في الاسترخاء.
        pref.max_consecutive = _one_of(request.POST.get("max_consecutive"), range(1, 8), 3)
        #: سقفُ الفراغ اختياريّ: الفراغُ لعامّة الكادر ترجيحٌ مرن، ومن اختار
        #: سقفاً صار في حقّه قيداً صلباً. فالفراغُ نصّاً لا يُقرأ افتراضيّاً
        #: بل يُقرأ عدماً — و«0» قيمةٌ صحيحةٌ تعني «لا فراغَ البتّة».
        max_gap = request.POST.get("max_gap", "")
        pref.max_gap = _one_of(max_gap, range(0, 6), None) if max_gap != "" else None
        free_day = request.POST.get("free_day", "")
        pref.free_day = _one_of(free_day, range(0, 5), None) if free_day else None
        pref.notes = request.POST.get("notes", "")

        # قيودٌ لا تسع النصاب تُردّ بحسابها لا تُحفظ: «متتالية 1» مع «فراغ 0»
        # حصّةٌ واحدةٌ في اليوم — ومن حفظها ونصابُه اثنتا عشرةَ رأى سبعاً بلا
        # موضعٍ في التوليد ولم يعرف لماذا.
        from operations.preference_capacity import explain_shortfall, weekly_capacity

        load = sum(
            SubjectClassAssignment.objects.filter(
                school=school, academic_year=year, teacher=request.user, is_active=True
            ).values_list("weekly_periods", flat=True)
        )
        capacity = weekly_capacity(
            pref.max_daily_periods, pref.max_consecutive, pref.max_gap, pref.free_day
        )
        # وقرارُ 2026-09-06: النصابُ يُقسم على الأيّام بفرقِ حصّةٍ على الأكثر،
        # فسقفٌ يوميٌّ دون حصّة القسمة لا يتماشى مع النصاب ويُردّ بحسابه.
        days = 5 - (1 if pref.free_day is not None else 0)
        needed = -(-load // days) if load else 0
        if pref.max_daily_periods < needed:
            messages.error(
                request,
                f"نصابُك {load} حصّةً على {days} أيّامٍ يحتاج {needed} حصصٍ في بعض الأيّام — "
                f"«أقصى حصص يوميّة {pref.max_daily_periods}» لا يتماشى معه"
                + ("، ويومُ التفريغ يضيّقه أكثر" if pref.free_day is not None else "")
                + ". لم يُحفظ.",
            )
            pref.refresh_from_db()
        elif capacity < load:
            messages.error(
                request,
                explain_shortfall(request.user.full_name, capacity, load, pref) + ". لم يُحفظ.",
            )
            pref.refresh_from_db()
        else:
            pref.save()
            messages.success(request, "تم حفظ تفضيلاتك للجدولة الذكية")
            # العامُ يبقى في الرابط: الرجوعُ بلا عامٍ يفتح تفضيلاتِ عامٍ آخر.
            return redirect(f"{reverse('teacher_preferences')}?year={year}")

    #: نصابُ صاحب الصفحة وأدنى سقفٍ يومّيٍّ يسعه — يُعرضان قبل الاختيار لا
    #: بعده. وكانت الصفحةُ تفتح على قوائمَ بلا سياق، فيختار المعلّمُ سقفاً
    #: لا يسع نصابَه ثمّ يُردّ عند الحفظ برسالةٍ حسنةِ الصياغةِ جاءت متأخّرة.
    load = sum(
        SubjectClassAssignment.objects.filter(
            school=school, academic_year=year, teacher=request.user, is_active=True
        ).values_list("weekly_periods", flat=True)
    )
    open_days = 5 - (1 if pref.free_day is not None else 0)
    needed = -(-load // open_days) if load else 0

    return render(
        request,
        "schedule/teacher_preferences.html",
        {
            "pref": pref,
            "days": ScheduleSlot.DAYS,
            #: المدى كاملاً — وكان القالبُ يعرض «3456» فيحجب الخيارين 1 و2
            #: عن اثنَي عشرَ منسّقاً أنصبتُهم ثلاثٌ إلى ثمانٍ عمداً، وهم
            #: أحوجُ الناس إلى تجميع حصصهم في يومٍ أو يومين.
            "periods": ScheduleSlot.PERIODS,
            "load": load,
            "min_daily": needed,
            "year": year,
        },
    )


# ── اعتماد الجدول ─────────────────────────────────────────────────


@login_required
@capability_required("schedule.settings")
@require_POST
def approve_schedule(request, generation_id):
    """اعتماد الجدول المولّد"""
    school = request.school
    gen = get_object_or_404(ScheduleGeneration, id=generation_id, school=school)

    if gen.status != "draft":
        messages.warning(request, "هذا الجدول ليس مسودة — لا يمكن اعتماده")
        return redirect("smart_schedule")

    # الاعتمادُ كلُّه في الخدمة — الزرُّ وأمرُ النقل يمرّان من الباب نفسِه.
    result = ScheduleService.approve_generation(gen)
    sync = result["sync"]

    messages.success(
        request,
        f"تم اعتماد الجدول وإشعار {result['notified']} معلم — جلساتُ الأسبوع: "
        f"حُذف {sync['deleted']}، أُنشئ {sync['created']}، أُبقي {sync['kept']}",
    )
    return redirect("smart_schedule")


def _one_of(raw, allowed, fallback):
    """رقمٌ من مدىً مغلق — وما خرج عنه يعود إلى الافتراضيّ بلا سقوط."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return fallback
    return value if value in allowed else fallback


# ── إعدادات الجدول — النائب الأكاديمي ───────────────────────────


@login_required
@capability_required("schedule.settings")
def schedule_settings(request):
    """إعدادات الجدول الذكي — تفريغات المعلمين + حصص مزدوجة"""
    school = request.school
    year = request.GET.get("year") or academic_year_for(request)

    # التفريغاتُ كلُّها في جدولٍ واحد: كان قسمان — «تفريغات» و«قيودٌ شخصيّةٌ
    # دائمة» — يُفرَّق بينهما بمطابقة جملةٍ في حقل السبب الحرّ. وقد أثبت
    # القياسُ أنّ صفراً من ثلاثةٍ وتسعين تفريغاً يطابقها، فحُذفت القسمة
    # (2026-09-09): القيدُ الدائمُ يُدخل من الشبكة كسائره ويُلغى منها.
    exemptions = TeacherExemption.objects.filter(
        school=school, academic_year=year, is_active=True
    ).select_related("teacher", "created_by")
    subjects = Subject.objects.filter(school=school).order_by("name_ar")
    teacher_prefs = (
        TeacherPreference.objects.filter(school=school, academic_year=year)
        .select_related("teacher")
        .order_by("teacher__full_name")
    )

    # قائمة المعلمين لإضافة تفريغ
    teacher_ids = Membership.objects.filter(
        school=school,
        is_active=True,
        role__name__in=EXEMPTABLE_ROLES,
    ).values_list("user_id", flat=True)
    teachers = CustomUser.objects.filter(id__in=teacher_ids).order_by("full_name")

    return render(
        request,
        "schedule/schedule_settings.html",
        {
            "exemptions": exemptions,
            "subjects": subjects,
            "teacher_prefs": teacher_prefs,
            "teachers": teachers,
            "days": ScheduleSlot.DAYS,
            "periods": ScheduleSlot.PERIODS,
            "year": year,
        },
    )


@login_required
@capability_required("schedule.settings")
def exemption_grid(request):
    """شبكةُ أسبوعِ معلّمٍ بعينه — جزءٌ يُحمّل عند اختياره من القائمة.

    وبلا معلّمٍ مختارٍ تُعاد شبكةٌ خاوية: المجموعةُ («كلّ المنسّقين») لا جدولَ
    واحدَ لها، فتُظلَّل نمطاً مجرّداً بلا شواغلَ ولا سعة.
    """
    import uuid

    from operations.exemption_grid import DAYS, PERIODS, build_grid

    from .forms import TeacherExemptionForm

    school = request.school
    year = request.GET.get("year") or academic_year_for(request)
    raw = (request.GET.get("teacher") or "").strip()

    # المجموعةُ («كلّ المنسّقين») لا جدولَ واحداً لها، فشبكتُها مجرّدة. وهي
    # اسمٌ معلومٌ لا معرّف — فمن أرسل معرّفَ معلّمٍ ليس من المدرسة لا يُعامَل
    # معاملةَ المجموعة: كان يسقط إلى الشبكة المجرّدة فيرى باباً يُوهمه بأنّ
    # اختيارَه صالح، والنموذجُ يردّه بعد التظليل لا قبله.
    group = raw if raw in TeacherExemptionForm.GROUPS else ""

    teacher = None
    if raw and not group:
        # القيدُ بالمدرسة لا زينة: بلا `in_school` يُقرأ أسبوعُ معلّمٍ في
        # مدرسةٍ أخرى بتغيير معرّفٍ في الرابط.
        try:
            teacher = CustomUser.objects.in_school(school).filter(pk=uuid.UUID(raw)).first()
        except ValueError:
            teacher = None

    grid = build_grid(school, teacher, year) if teacher is not None else None
    return render(
        request,
        "schedule/partials/exemption_grid.html",
        {
            "grid": grid,
            "teacher": teacher,
            "group": group,
            "days": DAYS,
            "periods": PERIODS,
            "year": year,
        },
    )


@login_required
@capability_required("schedule.settings")
@require_POST
def add_exemption(request):
    """إضافة تفريغ معلم — POST.

    المدخلاتُ تمرّ على `TeacherExemptionForm` أوّلاً: هي التي تقيّد المعلّمَ
    بمدرسة المُدخِل، وتحوّل الأرقامَ، وتردّ الناقصَ رسالةً لا صفحةَ خطأ.
    """
    from operations.exemption_grid import build_grid as build_exemption_grid
    from operations.exemption_grid import cells_of as _grid_cells

    from .forms import TeacherExemptionForm

    school = request.school
    year = request.POST.get("year") or academic_year_for(request)

    form = TeacherExemptionForm(request.POST, school=school)
    if not form.is_valid():
        for field, errors in form.errors.items():
            label = form.fields[field].label if field in form.fields else ""
            for error in errors:
                messages.error(request, f"{label}: {error}" if label else error)
        return _safe_schedule_settings_redirect(request, year)

    data = form.cleaned_data
    teachers, days, pairs = data["teacher"], data["day_of_week"], data["pairs"]

    # حارسُ الإمكانيّة: «خاناتُ الأسبوع − النصاب = ما يجوز تفريغُه»، والمفرَّغُ
    # سلفاً مطروحٌ منه. وما تجاوزه يُنتج حصصاً بلا موضعٍ فيقول المولّدُ «تعذّر
    # وضع» بلا سبب. والعدّادُ في الشاشة تنبيهٌ يُتجاوَز بإطفاء السكربت، فالمنعُ
    # هنا. ويُفحص كلُّ معلّمٍ على حدة — فالمجموعةُ تختلف أنصبةُ أعضائها.
    over_allowance = []
    for teacher in teachers:
        grid = build_exemption_grid(school, teacher, year)
        added = sum(
            1
            for day, period in pairs
            for cell in _grid_cells(grid, day, period)
            if not cell.exemption_id and not cell.disabled
        )
        if grid.load and added > grid.remaining:
            over_allowance.append(
                f"{teacher.full_name} (نصابه {grid.load} من {grid.week_slots} خانة، "
                f"فالمسموحُ {grid.remaining} وطُلب {added})"
            )
    if over_allowance:
        messages.error(
            request,
            "لم يُحفظ — التفريغُ يتجاوز المسموح: " + "؛ ".join(over_allowance),
        )
        return _safe_schedule_settings_redirect(request, year)

    # معلّمون × أيّام × حصص في معاملةٍ واحدة: إمّا الكلُّ وإمّا لا شيء. والمكرَّرُ
    # (المعلّمُ نفسُه، اليومُ نفسُه، الحصّةُ نفسُها) يُتخطّى ويُعَدّ — فتفريغُ
    # «كلّ المنسّقين» بعد شهرٍ يضيف من استجدّ منهم ولا يكرّر القدماء.
    created, skipped = 0, 0
    try:
        with transaction.atomic():
            # الموجودُ يُجلب مرّةً واحدةً لا عند كلّ (معلّم × يوم × حصّة): كان
            # استعلاماً لكلّ خليّة — «كلُّ المنسّقين» في خمسة أيّامٍ وسبع حصص
            # أربعمئةُ استعلام.
            existing = set(
                TeacherExemption.objects.filter(
                    school=school,
                    academic_year=year,
                    teacher__in=teachers,
                    day_of_week__in=days,
                    is_active=True,
                ).values_list("teacher_id", "day_of_week", "period_number")
            )
            for teacher in teachers:
                for day, period in pairs:
                    if (teacher.id, day, period) in existing:
                        skipped += 1
                        continue
                    existing.add((teacher.id, day, period))
                    ScheduleService.create_exemption(
                        school=school,
                        teacher=teacher,
                        academic_year=year,
                        #: النوعُ من الخانة نفسِها حين تأتي من الشبكة: بلا رقمِ
                        #: حصّةٍ فهو يومٌ كامل. وهو الذي يُنقص مقامَ القسمة.
                        exemption_type=(
                            data["exemption_type"]
                            or ("full_day" if period is None else "specific_period")
                        ),
                        day_of_week=day,
                        period_number=period,
                        reason=data["reason"],
                        created_by=request.user,
                        source=data["source"],
                    )
                    created += 1
    except DjangoValidationError as exc:
        # تفريغُ يومٍ كاملٍ قرارٌ إداريّ — ورفضُه يُقال، ولا يصير 500.
        messages.error(request, "؛ ".join(exc.messages))
        return _safe_schedule_settings_redirect(request, year)

    who = teachers[0].full_name if len(teachers) == 1 else f"{len(teachers)} معلّمين"
    when = "يوم واحد" if len(days) == 1 else f"{len(days)} أيّام"
    note = f" — و{skipped} مكرَّرٌ تُخطّي" if skipped else ""
    if created:
        messages.success(request, f"تم تفريغ {who} في {when}: {created} تفريغاً{note}")
    else:
        messages.info(request, f"لا جديد: التفريغاتُ المطلوبة ({skipped}) مسجَّلةٌ سلفاً")
    return _safe_schedule_settings_redirect(request, year)


@login_required
@capability_required("schedule.settings")
@require_POST
def remove_exemption(request, exemption_id):
    """إلغاء تفريغ"""
    school = request.school
    exemption = get_object_or_404(TeacherExemption, id=exemption_id, school=school)
    exemption.is_active = False
    exemption.save(update_fields=["is_active"])
    messages.success(request, "تم إلغاء التفريغ")
    return _safe_schedule_settings_redirect(
        request,
        exemption.academic_year,
    )


@login_required
@capability_required("schedule.settings")
@require_POST
def remove_exemptions(request):
    """إلغاءُ ما اختير من التفريغات دفعةً واحدة.

    عشرون تفريغاً لمعلّمٍ واحدٍ كانت تُلغى بعشرين نقرةٍ وعشرين تأكيداً — وهي
    فعلٌ واحدٌ في ذهن النائب. فالاختيارُ بمربّعاتٍ والإلغاءُ باستعلامٍ واحد.

    والمعرِّفاتُ تُصفّى قبل الاستعلام: نصٌّ ليس بـUUID يُسقط الاستعلامَ خطأَ
    خادمٍ لا رسالةً، ومدرسةُ المُدخِلِ قيدٌ لا تجميل — فلا يُلغي أحدٌ
    تفريغَ مدرسةٍ غيرِ مدرسته ولو حزر معرِّفَه.
    """
    school = request.school
    year = request.POST.get("year") or None

    ids = []
    for raw in request.POST.getlist("exemption_id"):
        try:
            ids.append(uuid.UUID(raw))
        except (AttributeError, TypeError, ValueError):
            continue

    if not ids:
        messages.info(request, "لم يُحدَّد أيُّ تفريغ.")
        return _safe_schedule_settings_redirect(request, year)

    removed = TeacherExemption.objects.filter(school=school, id__in=ids, is_active=True).update(
        is_active=False
    )

    if removed:
        messages.success(request, f"تمّ إلغاء {removed} تفريغاً")
    else:
        messages.info(request, "لا شيء أُلغي: المحدَّدُ ملغىً سلفاً أو ليس من مدرستك.")
    return _safe_schedule_settings_redirect(request, year)


@login_required
@capability_required("schedule.settings")
@require_POST
def remove_preferences(request):
    """حذفُ ما اختير من تفضيلات المعلّمين — بمربّعاتٍ وزرٍّ واحدٍ كالتفريغات.

    والحذفُ هنا حذفٌ لا إطفاء: للتفضيل قيدُ تفرّدٍ (معلّم × مدرسة × عام)،
    فصفٌّ مطفأٌ باقٍ يمنع صاحبَه أن يسجّل تفضيلاً جديداً. وما يضيع يعيده
    صاحبُه من شاشته.
    """
    school = request.school

    ids = []
    for raw in request.POST.getlist("preference_id"):
        try:
            ids.append(uuid.UUID(raw))
        except (AttributeError, TypeError, ValueError):
            continue

    if not ids:
        messages.info(request, "لم يُحدَّد أيُّ تفضيل.")
        return _safe_schedule_settings_redirect(request, request.POST.get("year") or None)

    removed, _ = TeacherPreference.objects.filter(school=school, id__in=ids).delete()
    if removed:
        messages.success(request, f"تمّ حذف {removed} تفضيلاً")
    else:
        messages.info(request, "لا شيء حُذف: المحدَّدُ محذوفٌ سلفاً أو ليس من مدرستك.")
    return _safe_schedule_settings_redirect(request, request.POST.get("year") or None)


@login_required
@capability_required("schedule.settings")
@require_POST
def save_subject_scheduling(request):
    """ازدواجُ الموادّ في الجدول يُحفظ دفعةً واحدة.

    كان لكلّ سطرٍ زرّاه، فمراجعةُ عشرين مادّةً عشرون رحلةً إلى الخادم. والقرارُ
    في ذهن النائب واحد: هذه الشاشة. فصار زرٌّ واحدٌ في ذيلها يحفظ ما تغيّر
    وحدَه، ويقول كم تغيّر.

    وكان معه «تباعدُ الأيّام» بنطاقه ورسالةِ استحالته. وقد سقط: التباعدُ نتيجةٌ
    تحسبها القسمةُ في HC6 لا قراراً يُتَّخذ، ومادّةُ ستِّ حصصٍ تأخذ يوماً
    بحصّتين — لا استحالةَ فيها حتّى تُقال.
    """
    school = request.school
    doubled = set(request.POST.getlist("double"))
    changed = []
    for subject in Subject.objects.filter(school=school):
        wants_double = str(subject.pk) in doubled
        if wants_double == subject.requires_double_period:
            continue
        subject.requires_double_period = wants_double
        changed.append(subject)

    if changed:
        Subject.objects.bulk_update(changed, ["requires_double_period"], batch_size=100)
        messages.success(request, f"حُفظ تعديلُ {len(changed)} مادّة")
    else:
        messages.info(request, "لا تغييرَ يُحفظ.")
    return _safe_schedule_settings_redirect(request)


# ── جداولُ الصفحات: صفحةٌ لكلّ معلّمٍ أو لكلّ شعبة ─────────────────────

#: اتّجاهُ الورقة — والافتراضُ أفقيّ (قرار الإدارة 2026-09-06)؛ والعموديّ بطلبٍ في الرابط.


def _pages_payload(request) -> dict:
    """ما يُطبع: معلّمون (كلُّهم أو قسمٌ أو واحدٌ) أو شُعب — والاتّجاهُ من الرابط."""
    school = request.school
    year = request.GET.get("year") or academic_year_for_school(school)
    kind = "classes" if request.GET.get("kind") == "classes" else "teachers"
    dept = request.GET.get("dept") or "all"
    teacher_id = request.GET.get("teacher") or ""
    orient = request.GET.get("orient") or DEFAULT_ORIENTATION
    if orient not in ORIENTATIONS:
        orient = DEFAULT_ORIENTATION
    paper = request.GET.get("paper") or "a4"
    if paper not in PAPERS:
        paper = "a4"

    departments = ScheduleService.department_options(school, year)
    if kind == "classes":
        pages = ScheduleService.class_pages(school, year)
        title = "جداول الشُّعب"
    else:
        department = None if dept == "all" or teacher_id else dept
        pages = ScheduleService.teacher_pages(
            school, year, department=department, teacher_id=teacher_id or None
        )
        if teacher_id:
            # الاسمُ من القاعدة لا من الصفحات: من لا حصصَ له صفحاتُه فارغةٌ
            # وعنوانُه كان يصير «جداول معلّمي المدرسة» — عنوانٌ يكذب على قارئه.
            named = CustomUser.objects.filter(id=teacher_id).first()
            title = f"جدول المعلّم: {named.full_name}" if named else "جدول المعلّم"
        elif department:
            name = next((d["name"] for d in departments if d["code"] == department), department)
            title = f"جداول معلّمي قسم {name}"
        else:
            title = "جداول معلّمي المدرسة"

    selection = {"kind": kind, "dept": dept, "orient": orient, "paper": paper, "year": year}
    if teacher_id:
        selection["teacher"] = teacher_id

    teachers, classes = _browse_lists(school)
    return {
        "school": school,
        "year": year,
        "kind": kind,
        "paper": paper,
        "title": title,
        "pages": pages,
        "departments": departments,
        "teachers": teachers,
        "classes": classes,
        "picker_current": "pages:classes" if kind == "classes" else f"pages:teachers:{dept}",
        "selected_dept": dept if not teacher_id else "",
        "orient": orient,
        # السطرُ يومٌ والعمودُ حصّة، واسمُ اليوم مقرونٌ بخاناته في `by_day`.
        "period_numbers": ScheduleSlot.PERIODS,
        # الورقةُ بالملّيمتر: الجدولُ يملأ ما بقي بعد الترويسة والذيل (قرار 2026-09-14).
        "geo": paper_geometry(paper, orient, with_who=True),
        "selection_query": urlencode(selection),
        "embed": request.GET.get("embed") == "1",
    }


@login_required
@capability_required("schedule.browse")
def schedule_pages(request):
    """الصفحةُ داخل المنصّة — هيدرٌ وفوترٌ وأدوات، والورقةُ في إطارٍ يُطبع وحده."""
    return render(request, "schedule/pages_view.html", _pages_payload(request))


@xframe_options_sameorigin
@login_required
@capability_required("schedule.browse")
def schedule_pages_paper(request):
    """الورقةُ وحدها — للإطار وللطباعة."""
    return render(request, "schedule/print_pages.html", _pages_payload(request))


@login_required
@capability_required("schedule.browse")
def schedule_pages_pdf(request):
    """الورقةُ نفسها ملفَّ PDF — قالبٌ واحدٌ للشاشة والورق والملفّ."""
    from django.template.loader import render_to_string

    from core.pdf_utils import render_pdf

    ctx = _pages_payload(request)
    ctx["embed"] = True
    ctx["for_pdf"] = True
    html = render_to_string("schedule/print_pages.html", ctx, request=request)
    log_export(request, "schedule.pages_pdf", object_repr=_export_filename(ctx, "pdf"))
    # الحجمُ المختار لا A4 ثابتاً: WeasyPrint يقرأ @page الورقة، أمّا المسارُ الاحتياطيّ فيقرأ هذا.
    return render_pdf(
        html,
        _export_filename(ctx, "pdf"),
        paper_size="A3" if ctx["paper"] == "a3" else "A4",
        as_attachment=True,
    )
