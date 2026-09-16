"""شاشةُ أجنحة المدرسة — طابقان، خمسةُ أجنحة، وجرسٌ يُقرأ بالساعة."""

import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import formats, timezone
from django.views.decorators.http import require_POST

from core.academic_calendar import academic_year_for_school
from core.capabilities import capability_required, has_capability
from core.models import ClassGroup, CustomUser, Wing, WingCoverage
from operations.absence_policy import next_gate
from operations.absence_standing import unexcused_days_for_class
from operations.bells import day_type_for
from operations.day_attendance import enrolled_of
from operations.guardian_contact import awaiting_contact
from operations.models import StudentAttendance
from operations.period_register import (
    absent_yesterday,
    cells_of,
    confirm_period,
    focus_period,
    period_end,
    periods_of,
    prefill_of,
    teacher_outs_of,
    teacher_taps_of,
    track_note,
)
from operations.services import ScheduleService
from wings.scope import student_scope_for

from .services import (
    bell_tables,
    coverage_rows,
    floors_overview,
    next_section_awaiting,
    outside_the_wings,
    record_panels,
    substitute_pool,
    wings_of,
)

DAY_LABEL = {"regular": "الأحد – الأربعاء", "thursday": "الخميس"}


@login_required
@capability_required("wings.floors")
def floors(request):
    school = request.user.get_school()
    now = timezone.localtime()
    year = academic_year_for_school(school)
    day_type = day_type_for(now.date())

    panels = floors_overview(school, year, now)
    outside = outside_the_wings(school, year)
    wing_students = sum(panel.student_count for panel in panels)
    register_count = wing_students + outside.student_count
    wing_count = sum(len(panel.wings) for panel in panels)
    section_count = sum(panel.section_count for panel in panels)
    return render(
        request,
        "wings/floors.html",
        {
            "panels": panels,
            "tables": bell_tables(school),
            "now": now,
            "year": year,
            "subtitle": f"طابقان · {wing_count} أجنحة · {section_count} شعبة · {year}",
            "day_label": DAY_LABEL.get(day_type, "عطلة — لا دوام"),
            "is_school_day": bool(day_type),
            "wing_count": wing_count,
            "section_count": section_count,
            "student_count": wing_students,
            "outside": outside,
            "perms_can_cover": request.user.is_superuser
            or request.user.get_role() in WingCoverage.ASSIGNER_ROLES,
            # سجلُّ المدرسة كلُّه — والفرقُ بينه وبين طلاب الأجنحة معروضٌ لا مطروح.
            "register_count": register_count,
            "kpis": _floors_kpis(outside, register_count, bool(day_type), now),
        },
    )


def _floors_kpis(outside, register_count, is_school_day, now):
    """تفاصيلُ شريط الأرقام نصوصاً جاهزة — كانت سلاسلَ شرطيّةً في القالب."""
    codes = " · ".join(section.short_code for section in outside.sections)
    students_sub = f"من {register_count} في السجلّ"
    if outside.student_count:
        students_sub += f" · و{outside.student_count} في التربية الخاصّة"
    return {
        "sections_sub": (
            f"و{outside.section_count} خارجَها (تربيةٌ خاصّة)"
            if outside.section_count
            else "كلُّ شُعب المدرسة"
        ),
        "sections_title": f"خارجَ الأجنحة بقرار الإدارة: {codes}" if codes else "",
        "students_sub": students_sub,
        # يومُ دوامٍ أخضرُ بساعته، والعطلةُ كهرمانيّةٌ بلا جرس.
        "day_tone": "green" if is_school_day else "amber",
        "day_sub": f"الساعة {now:%H:%M}" if is_school_day else "لا جرسَ يرنّ",
    }


def _day(raw, fallback=None):
    """تاريخٌ من نصّ — وما لا يُقرأ يرتدّ إلى بديلٍ لا يُسقط الطلب."""
    try:
        return dt.date.fromisoformat(raw)
    except (TypeError, ValueError):
        return fallback


@login_required
@capability_required("wings.assign_cover")
def coverage(request):
    """تغطيةُ الأجنحة — من يحمل كلَّ جناحٍ اليوم، ومن يُناب عند الغياب.

    وصلاحيّتُها للمدير والنائبين ومطوّر المنصّة: لوحةُ إدارة جانغو مقصورةٌ على
    المدير والمطوّر بقرار المدرسة، فبلا هذه الشاشة لا يستطيع النائبان تعيينَ
    بديلٍ — وهما اثنان من الأربعة الذين أذن لهم المدير.
    """
    school = request.user.get_school()
    year = academic_year_for_school(school)
    today = timezone.localdate()
    return render(
        request,
        "wings/coverage.html",
        {
            "rows": coverage_rows(school, year, today),
            "pool": substitute_pool(school, on_date=today),
            "today": today,
            "year": year,
            "subtitle": f"من يحمل كلَّ جناحٍ اليوم — والإنابةُ عند الغياب · {year}",
        },
    )


@login_required
@capability_required("wings.assign_cover")
@require_POST
def coverage_assign(request, code):
    school = request.user.get_school()
    year = academic_year_for_school(school)
    wing = get_object_or_404(Wing, school=school, code=code, academic_year=year)
    today = timezone.localdate()

    substitute = CustomUser.objects.filter(id=request.POST.get("substitute") or None).first()
    if substitute is None:
        messages.error(request, "اختر البديل.")
        return redirect("wings:coverage")

    cover = WingCoverage(
        wing=wing,
        substitute=substitute,
        assigned_by=request.user,
        reason=request.POST.get("reason") or "absence",
        start_date=_day(request.POST.get("start_date"), today),
        end_date=_day(request.POST.get("end_date")),
        note=(request.POST.get("note") or "").strip(),
    )
    try:
        cover.full_clean()
    except ValidationError as err:
        for field_errors in err.message_dict.values():
            for text in field_errors:
                messages.error(request, text)
        return redirect("wings:coverage")

    cover.save()
    until = f"حتّى {cover.end_date}" if cover.end_date else "بلا تاريخِ انتهاء"
    messages.success(
        request, f"{substitute.full_name} يغطّي {wing.name} من {cover.start_date} — {until}."
    )
    return redirect("wings:coverage")


@login_required
@capability_required("wings.assign_cover")
@require_POST
def coverage_end(request, pk):
    """إنهاءُ التغطية — بتاريخٍ لا بحذف.

    الحذفُ يمحو من حمل الجناحَ أمسِ، ومن يقرأ غيابَ الأسبوع الماضي يحتاج أن
    يعرف من كان يرصده. فتُغلق المدّةُ ويبقى السجلّ.
    """
    school = request.user.get_school()
    cover = get_object_or_404(WingCoverage, pk=pk, wing__school=school)
    today = timezone.localdate()
    cover.end_date = max(_day(request.POST.get("end_date"), today), cover.start_date)
    cover.ended_by = request.user
    cover.save(update_fields=["end_date", "ended_by"])
    messages.success(
        request,
        f"انتهت تغطيةُ {cover.substitute.full_name} لـ{cover.wing.name} في {cover.end_date}.",
    )
    return redirect("wings:coverage")


@login_required
@capability_required("wings.record_day")
def record_index(request):
    """شُعبي اليومَ وحالُ رصدِها — «شُعبي المتبقّية n/5»."""
    school = request.user.get_school()
    year = academic_year_for_school(school)
    day = _day(request.GET.get("date"), timezone.localdate())

    # الحصصُ تُولَّد إن لم تكن — فشعبةٌ بلا حصصٍ لا تُرصد.
    ScheduleService.ensure_sessions_for_date(school, day)

    # العدُّ في الخدمة لا في القالب: `add` في جانغو لا تطرح، فحسابُ
    # «المتبقّية» هناك كان يُخرج صفراً دائماً.
    panels = record_panels(request.user, school, year, day)
    return render(
        request,
        "wings/record_index.html",
        {
            "panels": panels,
            "day": day,
            "today": timezone.localdate(),
            "day_type": day_type_for(day),
        },
    )


def _time(raw):
    try:
        return dt.time.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def _own_class(request, class_id):
    """شعبةٌ من أجنحة المستخدم وحدَها — والمشرفُ لجناحه فقط (قرارُ 2026-09-13).

    والقيادةُ ترى الأجنحةَ الخمسة (`wings_of`). ومن طلب شعبةَ جناحٍ آخر برابطها
    المباشر يلقى 404 لا 403: وجودُ الشعبة في جناحٍ غيرِه ليس شأنَه.
    """
    school = request.user.get_school()
    klass = get_object_or_404(ClassGroup, id=class_id, school=school)
    year = academic_year_for_school(school)
    if klass.wing_id not in {w.id for w in wings_of(request.user, school, year)}:
        raise Http404("ليست من شُعب جناحك")
    return school, klass


@login_required
@capability_required("wings.record_day")
def record_section(request, class_id):
    """كشفُ الشعبة: الطلابُ صفوفاً، والحصصُ أعمدةً، والحصّةُ المفتوحةُ للرصد.

    تُفتح الحصّةُ الجارية، وإلّا أوّلُ فائتة، وإلّا أوّلُ قادمة — ويُختار غيرُها
    بـ`?p=HH:MM`. وكلُّ طالبٍ بجانبه ما يغيّر قرارَ المشرف في لحظته: «غاب أمس»،
    وأيّامُ غيابه بلا عذرٍ أمام أوّل عتبةٍ لم يتجاوزها.
    """
    school, klass = _own_class(request, class_id)
    day = _day(request.GET.get("date"), timezone.localdate())
    ScheduleService.ensure_sessions_for_date(school, day)

    now = timezone.now()
    periods = periods_of(klass, day)
    wanted = _time(request.GET.get("p"))
    focus = next((p for p in periods if p.start == wanted), None) or focus_period(periods, day, now)
    cells = cells_of(klass, day)
    awaiting = awaiting_contact(klass, day)
    following = next_section_awaiting(klass, day, focus.start) if focus else None
    taps = teacher_taps_of(klass, day)
    outs = teacher_outs_of(klass, day)
    # ما يأتي جاهزاً من المعلّم يُحسب في الخدمة؛ والقالبُ يعرض `row.pick` ولا يحكم.
    prefill = (
        prefill_of(klass, day, focus, now, cells=cells, taps=taps, outs=outs) if focus else None
    )
    ends = {p.start: period_end(day, p) for p in periods}
    yesterday = absent_yesterday(klass, day)
    unexcused = unexcused_days_for_class(klass, school, day)

    rows = []
    for enrollment in enrolled_of(klass):
        sid = enrollment.student_id
        days = unexcused.get(sid, 0)
        gate = next_gate(klass.grade, days)
        own = cells.get(sid, {})
        gone = outs.get(sid, {})
        rows.append(
            {
                "student": enrollment.student,
                # وفي الأعمدة الأخرى شارةُ من خرج ولم يعد — تُفتح حصّتُه برأس عمودها.
                "track": [
                    (p, own.get(p.start), track_note(gone.get(p.start), now, ends[p.start]))
                    for p in periods
                ],
                "cell": own.get(focus.start) if focus else None,
                # حاضر/غائب/متأخّر ومكانُه كما يُفتح — ومعه علامةُ المعلّم وشارتُه.
                "pick": prefill.of(sid) if prefill else None,
                "absent_yesterday": sid in yesterday,
                # غاب أمس ولم يُخطَر وليُّ أمره بعد — الإخطارُ في اليوم نفسِه (م 3.4.1.5).
                "needs_contact": awaiting.get(sid),
                "days": days,
                "gate": gate,
            }
        )
    return render(
        request,
        "wings/record_section.html",
        {
            "klass": klass,
            "day": day,
            # عنوانُ الترويسة وسطرُها يُبنيان هنا: المكوّنُ يأخذ نصّاً لا وسوماً.
            "heading": f"{klass.get_grade_display()} / {klass.section}",
            "subtitle": (
                f"{formats.date_format(day, 'D، d M Y')} · {len(rows)} طالباً · الحصص: {len(periods)}"
            ),
            "periods": [(p, p.status(day, now)) for p in periods],
            "focus": focus,
            "focus_status": focus.status(day, now) if focus else "",
            "measured_now": bool(focus and focus.in_window(day, now)),
            "rows": rows,
            "whereabouts": [w for w in StudentAttendance.WHEREABOUTS if w[0] != "gate"],
            # بصمةُ الخانات كما تُفتح في المفتاح: ملءٌ تبدّل يُسقط المسوّدةَ القديمة.
            "draft_key": (
                f"rec:{klass.id}:{day.isoformat()}:{focus.key if focus else ''}"
                f":{prefill.fingerprint if prefill else ''}"
            ),
            # «ثبّت وانتقل»: الشعبةُ التي تنتظر الحصّةَ نفسَها بعد هذه — إن بقيت.
            "following": following,
        },
    )


@login_required
@capability_required("wings.record_day")
@require_POST
def record_period(request, class_id):
    """تثبيتُ حصّة — ومعه مخالفتا التأخّر والهروب إن استوجبهما الرصد."""
    school, klass = _own_class(request, class_id)
    day = _day(request.POST.get("date"), timezone.localdate())
    start = _time(request.POST.get("start"))
    back = f"{reverse('wings:record_section', args=[klass.id])}?date={day.isoformat()}"

    marks: dict = {}
    for key, value in request.POST.items():
        for prefix, field in (
            ("s-", "status"),
            ("w-", "whereabouts"),
            ("m-", "late_minutes"),
            ("t-", "tapped_at"),
            ("o-", "exit"),
        ):
            if key.startswith(prefix):
                marks.setdefault(key.removeprefix(prefix), {})[field] = value
    try:
        result = confirm_period(klass, day, start, marks, by=request.user)
    except ValueError as err:
        messages.error(request, str(err))
        return redirect(back)

    messages.success(request, f"ثُبّتت {klass.short_code} — {result.says}.")
    if request.POST.get("next"):
        following = next_section_awaiting(klass, day, start)
        if following is not None:
            return redirect(
                f"{reverse('wings:record_section', args=[following.id])}"
                f"?date={day.isoformat()}&p={start:%H:%M}"
            )
        messages.info(request, "لا شعبةَ أخرى في الجناح تنتظر هذه الحصّة.")
        return redirect(f"{reverse('wings:record_index')}?date={day.isoformat()}")
    return redirect(back)


# ═════════════════════════════════════════════════════════════════════
# تصحيحُ إدخالٍ خاطئ — أحداثُ الطالب بحذفٍ مُسبَّب (قرارُ 2026-09-13)
# ═════════════════════════════════════════════════════════════════════


@login_required
@capability_required("wings.record_day")
def student_events(request, class_id, student_id):
    """أحداثُ طالبٍ من شُعب جناحي (غياب/تأخّر/خروج) سطراً سطراً — لحذف ما رُصد بالخطأ.

    الحذفُ بسبب، ويُسجَّل في سجلّ المراجعة، ويُعاد حكمُ الكشف على يومه فتزول مخالفةُ
    التأخّر أو الهروب التي بُنيت عليه. والخانةُ تعود «لم تُرصد» لا «حاضراً».
    """
    from operations.excuses import GRACE_DAYS, kinds
    from operations.guardian_contact import awaiting_contact as _awaiting
    from operations.guardian_contact import contacts_of
    from operations.models import AbsenceExcuse, ClassExit, GuardianContact

    school, klass = _own_class(request, class_id)
    student = get_object_or_404(
        CustomUser, id=student_id, enrollments__class_group=klass, enrollments__is_active=True
    )
    # وقيدُه الجاري في الجناح: قيدٌ قديمٌ نشطٌ في شعبةٍ من جناحي لا يفتحه لي (wings/scope.py).
    student_scope_for(request).require_student(student.id)
    today = timezone.localdate()
    # اليومُ المقصود: ما في الرابط، وإلّا آخرُ يومِ غيابٍ بلا عذر — لا اليوم: كان الفراغُ
    # يُملأ بتاريخ اليوم فيُكتب العذرُ والإخطارُ على يومٍ لم يغب فيه.
    last_absent = (
        StudentAttendance.objects.filter(
            student=student, school=school, status="absent", excuse_type=""
        )
        .order_by("-session__date")
        .values_list("session__date", flat=True)
        .first()
    )
    focus_day = _day(request.GET.get("date"), last_absent or today)
    attendance_events = list(
        StudentAttendance.objects.filter(student=student, school=school)
        .exclude(status="present")
        .select_related("session__subject", "session__class_group")
        .order_by("-session__date", "-session__start_time")[:60]
    )
    exit_events = list(
        ClassExit.objects.filter(student=student, school=school)
        .select_related("session__subject", "allowed_by")
        .order_by("-left_at")[:60]
    )
    return render(
        request,
        "wings/student_events.html",
        {
            "klass": klass,
            "student": student,
            "attendance_events": attendance_events,
            "exit_events": exit_events,
            "can_delete_events": True,
            # تحويلُ الغياب إلى «بعذرٍ مقبول» (قرارُ 2026-09-13) — القائمةُ المغلقة.
            "excuses": AbsenceExcuse.objects.filter(student=student, school=school)
            .select_related("granted_by")
            .order_by("-date_from")[:20],
            "excuse_kinds": kinds(),
            "excuse_day": focus_day,
            # إخطارُ وليّ الأمر — بضغطةٍ بنتيجته (قرارُ 2026-09-13).
            "contacts": contacts_of(student, school),
            "contact_outcomes": GuardianContact.OUTCOMES,
            "contact_day": _awaiting(klass, today).get(student.id) or focus_day,
            "events_count": len(attendance_events) + len(exit_events),
            "grace_days": GRACE_DAYS,
            "may_override": has_capability(request.user, "wings.excuse_after_deadline"),
        },
    )


@login_required
@capability_required("wings.record_day")
@require_POST
def excuse_grant(request, class_id, student_id):
    """قبولُ عذرِ غيابٍ لطالبٍ من شُعب جناحي — في المهلة، وبعدها يُرسَل للنائب.

    لا يُطلب من المشرف أن يعرف أين المهلة: إن انقضت أُرسل عذرُه «بانتظار النائب»
    تلقائيّاً بالضغطة نفسها، ولا يُعيد رفعَ المستند (قرارُ 2026-09-14: أقلُّ النقرات).
    """
    from operations.excuses import ExcuseError, grant_excuse

    school, klass = _own_class(request, class_id)
    student = get_object_or_404(
        CustomUser, id=student_id, enrollments__class_group=klass, enrollments__is_active=True
    )
    # وقيدُه الجاري في الجناح: قيدٌ قديمٌ نشطٌ في شعبةٍ من جناحي لا يفتحه لي (wings/scope.py).
    student_scope_for(request).require_student(student.id)
    back = reverse("wings:student_events", args=[klass.id, student.id])
    date_from = _day(request.POST.get("date_from"))
    date_to = _day(request.POST.get("date_to"), date_from)
    if date_from is None:
        messages.error(request, "اختر تاريخَ الغياب.")
        return redirect(back)
    try:
        excuse = grant_excuse(
            student=student,
            school=school,
            date_from=date_from,
            date_to=date_to,
            kind=request.POST.get("kind", ""),
            notes=request.POST.get("notes", ""),
            document=request.FILES.get("document"),
            by=request.user,
            may_override=has_capability(request.user, "wings.excuse_after_deadline"),
            override_reason=request.POST.get("override_reason", ""),
            forward_if_late=True,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except (ExcuseError, ValidationError) as err:
        messages.error(request, " ".join(getattr(err, "messages", None) or [str(err)]))
        return redirect(back)
    excuse_outcome_message(request, excuse)
    return redirect(back)


def excuse_outcome_message(request, excuse) -> None:
    """رسالةُ ما جرى للعذر — مقبولٌ، أو أُرسل للنائب. واحدةٌ لكلّ شاشةٍ تقبل العذر."""
    if excuse.status == "pending":
        messages.warning(
            request,
            f"مضى يومان على عودة الطالب، فأُرسل العذرُ ({excuse.get_kind_display()}) "
            "إلى النائب الإداريّ — والغيابُ بلا عذرٍ حتى يقبله.",
        )
        return
    messages.success(
        request,
        f"قُبل العذرُ ({excuse.get_kind_display()}) وغُطّي {covered_periods(excuse)} حصّةً"
        + (" — بعد المهلة." if excuse.after_deadline else "."),
    )


def covered_periods(excuse) -> int:
    """حصصُ العذر كما يعدّها ملفُّ الغياب: خانةٌ زمنيّةٌ في يومها، لا سجلُّ حصّة —
    زوجُ الاختيار حصّتان في خانةٍ واحدة، والطالبُ يغيب عنهما مرّةً واحدة."""
    return excuse.rows.values("session__date", "session__start_time").distinct().count()


@login_required
@capability_required("wings.record_day")
@require_POST
def guardian_contact_log(request, class_id, student_id):
    """«اتّصلتُ بوليّ الأمر» بنتيجته — عن يومِ غيابٍ بعينه."""
    from operations.guardian_contact import ContactError, log_contact

    school, klass = _own_class(request, class_id)
    student = get_object_or_404(
        CustomUser, id=student_id, enrollments__class_group=klass, enrollments__is_active=True
    )
    # وقيدُه الجاري في الجناح: قيدٌ قديمٌ نشطٌ في شعبةٍ من جناحي لا يفتحه لي (wings/scope.py).
    student_scope_for(request).require_student(student.id)
    back = reverse("wings:student_events", args=[klass.id, student.id])
    absence_date = _day(request.POST.get("absence_date"))
    if absence_date is None:
        messages.error(request, "اختر يومَ الغياب.")
        return redirect(back)
    try:
        contact = log_contact(
            student=student,
            school=school,
            absence_date=absence_date,
            outcome=request.POST.get("outcome", ""),
            note=request.POST.get("note", ""),
            channel=request.POST.get("channel", "phone"),
            by=request.user,
        )
    except ContactError as err:
        messages.error(request, str(err))
        return redirect(back)
    messages.success(
        request,
        f"سُجّل الإخطارُ عن غياب {absence_date:%d/%m}: {contact.get_outcome_display()}.",
    )
    return redirect(back)


@login_required
@capability_required("wings.record_day")
@require_POST
def excuse_revoke(request, pk):
    """إلغاءُ عذرٍ بسبب — تعود حصصُه «بلا عذر»."""
    from core.models import StudentEnrollment
    from operations.excuses import ExcuseError, revoke_excuse
    from operations.models import AbsenceExcuse

    school = request.user.get_school()
    excuse = get_object_or_404(AbsenceExcuse, pk=pk, school=school)
    active = StudentEnrollment.objects.current_of(excuse.student, school)
    if active is None:
        raise Http404("لا شعبةَ لهذا الطالب")
    _own_class(request, active.class_group_id)
    student_scope_for(request).require_student(excuse.student_id)
    back = reverse("wings:student_events", args=[active.class_group_id, excuse.student_id])
    try:
        restored = revoke_excuse(
            excuse,
            by=request.user,
            reason=request.POST.get("reason", ""),
            may_override=has_capability(request.user, "wings.excuse_after_deadline"),
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ExcuseError as err:
        messages.error(request, str(err))
        return redirect(back)
    messages.success(request, f"أُلغي العذرُ وعادت {restored} حصّةً بلا عذر — وسُجّل في المراجعة.")
    return redirect(back)


@login_required
@capability_required("wings.record_day")
@require_POST
def attendance_event_delete(request, pk):
    """حذفُ سجلّ حضورٍ (غياب/تأخّر) بسبب — ويُعاد حكمُ الكشف على يومه."""
    from operations.undo import delete_attendance_event

    school = request.user.get_school()
    row = get_object_or_404(
        StudentAttendance.objects.select_related("session"), pk=pk, school=school
    )
    _own_class(request, row.session.class_group_id)
    back = reverse("wings:student_events", args=[row.session.class_group_id, row.student_id])
    reason = (request.POST.get("reason") or "").strip()
    if not reason:
        messages.error(request, "اكتب سببَ الحذف.")
        return redirect(back)
    delete_attendance_event(request, row, reason)
    messages.success(request, "حُذف السجلُّ وسُجّل التراجعُ في سجلّ المراجعة.")
    return redirect(back)


@login_required
@capability_required("wings.record_day")
@require_POST
def exit_event_delete(request, pk):
    """حذفُ خروجٍ من الفصل بسبب."""
    from operations.models import ClassExit
    from operations.undo import delete_exit_event

    school = request.user.get_school()
    exit_ = get_object_or_404(ClassExit.objects.select_related("session"), pk=pk, school=school)
    _own_class(request, exit_.session.class_group_id)
    back = reverse("wings:student_events", args=[exit_.session.class_group_id, exit_.student_id])
    reason = (request.POST.get("reason") or "").strip()
    if not reason:
        messages.error(request, "اكتب سببَ الحذف.")
        return redirect(back)
    delete_exit_event(request, exit_, reason)
    messages.success(request, "حُذف الخروجُ وسُجّل التراجعُ في سجلّ المراجعة.")
    return redirect(back)


@login_required
@capability_required("wings.excuse_after_deadline")
def excuse_requests(request):
    """الأعذارُ المرسلةُ للنائب الإداريّ بعد مهلة العودة — يقبل أو يرفض، وكلاهما بسبب."""
    from operations.excuses import pending_for_vice

    school = request.user.get_school()
    return render(
        request,
        "wings/excuse_requests.html",
        {"requests": pending_for_vice(school)},
    )


@login_required
@capability_required("wings.excuse_after_deadline")
@require_POST
def excuse_request_decide(request, pk):
    """قرارُ النائب في عذرٍ أُرسل إليه: «قبول» يكتبه على الحصص، و«رفض» يُبقي الغياب."""
    from operations.excuses import ExcuseError, approve_excuse, reject_excuse
    from operations.models import AbsenceExcuse

    school = request.user.get_school()
    excuse = get_object_or_404(AbsenceExcuse, pk=pk, school=school)
    reason = request.POST.get("reason", "")
    ip = request.META.get("REMOTE_ADDR")
    try:
        decision = request.POST.get("decision")
        if decision not in ("accept", "reject"):
            raise ExcuseError("اختر قبولاً أو رفضاً.")
        if decision == "accept":
            approve_excuse(excuse, by=request.user, reason=reason, ip=ip)
            messages.success(
                request,
                f"قُبل عذرُ {excuse.student.full_name} وغُطّي {covered_periods(excuse)} حصّةً.",
            )
        else:
            reject_excuse(excuse, by=request.user, reason=reason, ip=ip)
            messages.success(request, f"رُفض عذرُ {excuse.student.full_name}.")
    except ExcuseError as err:
        messages.error(request, str(err))
    return redirect("wings:excuse_requests")
