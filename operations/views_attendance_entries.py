"""views رصد المعلّم المبدئيّ واعتمادِه (W-20261002-020) — رقيقةٌ: القاعدةُ في `attendance_policy` والكتابةُ في `attendance_entries`.

المعلّمُ الفعليّ يُدخل رصداً مبدئيّاً (`entry_submit`)، ويقرّر حاملُ جناح الشعبة يومَ الحصّة أو القيادةُ حين لا حاملَ فعليّاً
(`approvals` و`approval_decide`)، ويرى النائبُ ما لم يُعتمد بعد مدّةٍ (`unapproved`). والسياسةُ هي الحَكَم في كلّ طلب؛
والقدرةُ على المسار بوّابةٌ أوسعُ لا بديلٌ منها. وكلُّ جلبٍ وكتابةٍ في `TeacherAttendanceService`.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.capabilities import capability_required

from .attendance_entries import EVIDENCE_TYPES, EntryConflictError, EntryError, EntryRefusedError
from .attendance_selectors import entry_mark_of
from .services.attendance_teacher import TeacherAttendanceService

#: رموزُ منعِ السياسة بنصٍّ للمستخدم — رمزٌ لا نصَّ له يُعرض عامّاً بلا تسريب.
REFUSALS = {
    "not_teacher": "الإدخالُ لمعلّم الحصّة الفعليّ وحدَه.",
    "before_start": "لم تبدأ الحصّةُ بعد.",
    "after_window": "انتهت نافذةُ الإدخال (آخرُ اليوم الدراسيّ).",
    "not_enrolled": "الطالبُ غيرُ مقيَّدٍ في شعبة هذه الحصّة.",
    "cancelled": "الحصّةُ ملغاة.",
    "developer": "لا يُدخل المطوّرُ ولا يعتمد.",
    "own_session": "لا تعتمد رصدَ حصّتك — يعتمده غيرُك.",
    "own_entry": "لا تعتمد ما أدخلتَه بنفسك.",
    "not_holder": "الاعتمادُ لحامل جناح الشعبة يومَ الحصّة.",
    "final_entry": "رصدُ التربية الخاصّة نهائيٌّ بلا اعتماد.",
}
DEFAULT_REFUSAL = "لا تملك هذا الإجراء على هذه الحصّة."

#: رسائلُ أخطاء الطلب بالرمز `exc.code` — **ثابتةٌ من هذا الجدول** لا نصَّ الاستثناء: لا يُعاد للعميل `str(exc)` أبداً (CodeQL
#: py/stack-trace-exposure، قرارُ المالك: يُغلق بالكود لا بالاستبعاد). رمزٌ مجهولٌ يأخذ `DEFAULT_ENTRY_ERROR`.
ENTRY_ERRORS = {
    "bad_status": "حالةٌ غيرُ مسموحةٍ للإدخال.",
    "reason_required": "هذا الإجراءُ يلزمه سبب.",
    "reason_too_long": "السببُ أطولُ من الحدّ المسموح.",
    "unchanged": "الحالةُ المعتمَدةُ كما هي — لا تصحيحَ.",
    "superseded": "حلّت محلَّه نسخةٌ أحدث — القرارُ على الأحدث.",
    "bad_evidence": "نوعُ الدليل غيرُ معروف.",
    "concurrent": "سبقك إدخالٌ آخرُ — أعِد المحاولة.",
    "non_teacher_row": "رصدٌ آخرُ (مشرفٌ أو عيادةٌ أو بوّابةٌ) قائمٌ على هذا الطالب — لا كتابةَ فوقه؛ ارفضْ الإدخالَ بسبب.",
    "non_correctable_row": "الرصدُ القائمُ مصدرُه العيادةُ أو البوّابةُ أو النظام — لا كتابةَ فوقه.",
}
DEFAULT_ENTRY_ERROR = "تعذّر تنفيذ الطلب."


def _refusal(exc: EntryRefusedError) -> HttpResponse:
    return HttpResponse(REFUSALS.get(exc.reason, DEFAULT_REFUSAL), status=403)


def _entry_error(exc: EntryError, status: int) -> HttpResponse:
    return HttpResponse(ENTRY_ERRORS.get(exc.code, DEFAULT_ENTRY_ERROR), status=status)


@login_required
@capability_required("attendance.mark")
@require_POST
def entry_submit(request, session_id):
    """HTMX: إدخالُ المعلّم الفعليّ (أو تصحيحُه) لطالبٍ في حصّته — مبدئيٌّ ينتظر الاعتماد."""
    post = request.POST
    try:
        session, line = TeacherAttendanceService.enter(
            request.user,
            request.school,
            session_id,
            post.get("student_id"),
            status=post.get("status", ""),
            minutes=post.get("minutes"),
            reason=post.get("reason", ""),
            tapped_at=post.get("tapped_at"),
        )
    except EntryRefusedError as exc:
        return _refusal(exc)
    except EntryConflictError as exc:
        return _entry_error(exc, 409)
    except EntryError as exc:
        return _entry_error(exc, 400)
    context = {"session": session, "line": line, "can_enter": True}
    return render(request, "teacher/partials/entry_cell.html", context)


@login_required
@capability_required("attendance.mark")
@require_POST
def period_entries(request, session_id):
    """«ثبّتِ الحصّة» من كشف المعلّم (القالبُ نفسُه كشفِ المشرف): إدخالاتٌ مبدئيّةٌ تنتظر اعتمادَ الحامل، والخروجُ `ClassExit`."""
    try:
        _session, result, following = TeacherAttendanceService.enter_marks(
            request.user, request.school, session_id, request.POST
        )
    except EntryRefusedError as exc:
        return _refusal(exc)
    except EntryConflictError as exc:
        return _entry_error(exc, 409)
    except EntryError as exc:
        return _entry_error(exc, 400)
    parts = []
    if result.entered:
        parts.append(f"أُدخل {result.entered} مبدئيّاً — يعتمده حاملُ الجناح")
    if result.exits:
        parts.append(f"سُجّل خروجُ {result.exits}")
    if result.needs_reason:
        parts.append(f"{result.needs_reason} معتمَدٌ يلزم تصحيحَه سببٌ (لم يُمسّ)")
    if result.conflicts:
        parts.append(f"{result.conflicts} خروجٌ أُغلق لأنّ الطالب وُسم غائباً")
    messages.success(request, " · ".join(parts) or "لا تغييرَ في الحصّة.")
    target = following.id if following is not None else session_id
    return redirect(reverse("attendance", args=[target]))


@login_required
@capability_required("wings.record_day")
def approvals(request):
    """طابورُ الاعتماد: ما يملك هذا المستخدمُ قرارَه (حاملُ الجناح، أو القيادةُ حين لا حاملَ فعليّاً)."""
    groups = TeacherAttendanceService.approval_groups(request.user, request.school)
    return render(
        request,
        "attendance/approvals.html",
        {"groups": groups, "entries_total": sum(g.total for g in groups)},
    )


@login_required
@capability_required("wings.record_day")
@require_POST
def approve_session(request, session_id):
    """اعتمادُ حصّةٍ كاملةٍ دفعةً واحدة — كلُّ إدخالٍ بقراره المسجَّل باسمه؛ والرفضُ بنداً بنداً."""
    approved, skipped = TeacherAttendanceService.approve_session(
        request.user, request.school, session_id
    )
    text = f"اعتُمدت الحصّة: {approved} إدخالاً"
    if skipped:
        text += f" · وتُخطّي {skipped} (تعارضٌ أو نسخةٌ أحدث) بقيت في القائمة لتنظر فيها"
    (messages.warning if skipped else messages.success)(request, text + ".")
    return redirect("attendance_approvals")


@login_required
@capability_required("wings.record_day")
@require_POST
def approval_decide(request, entry_id):
    """HTMX: اعتمادُ إدخالٍ معلَّقٍ أو رفضُه — الرفضُ يلزمه سبب."""
    post = request.POST
    try:
        entry, decision = TeacherAttendanceService.decide(
            request.user,
            request.school,
            entry_id,
            approve=post.get("decision") == "approve",
            reason=post.get("reason", ""),
        )
    except EntryRefusedError as exc:
        return _refusal(exc)
    except EntryConflictError as exc:
        return _entry_error(exc, 409)
    except EntryError as exc:
        return _entry_error(exc, 400)
    if post.get("surface") == "grid":
        # الاعتمادُ من خليّة شبكة المشرف: تُرسَم علامةُ الإدخال وحدَها لا بطاقةُ الطابور.
        mark = entry_mark_of(entry.id, request.user)
        return render(request, "wings/partials/entry_mark.html", {"mark": mark})
    context = {"entry": entry, "decision": decision}
    return render(request, "attendance/partials/decided_row.html", context)


@login_required
@capability_required("wings.record_day")
def unapproved(request):
    """تقريرُ «غيرُ معتمَد بعد X ساعة» — بالعدد لا بأسماء الطلاب، ويُظهر ما لا حاملَ فعليّاً له."""
    rows, hours, corrections = TeacherAttendanceService.report(
        request.user, request.school, request.GET.get("hours")
    )
    context = {"rows": rows, "hours": hours, "corrections": corrections}
    return render(request, "attendance/unapproved.html", context)


@login_required
@capability_required("wings.record_day")
def correct_page(request, session_id):
    """شاشةُ «تصحيحٌ دون معاينة»: طلبةُ الحصّة ونماذجُ التصحيح، لمن له الاعتمادُ على الحصّة وحدَه."""
    try:
        session, lines = TeacherAttendanceService.correction_page(
            request.user, request.school, session_id
        )
    except EntryRefusedError as exc:
        return _refusal(exc)
    context = {"session": session, "lines": lines, "evidence_types": EVIDENCE_TYPES}
    return render(request, "attendance/correct.html", context)


@login_required
@capability_required("wings.record_day")
@require_POST
def correct_submit(request, session_id):
    """HTMX: تصحيحُ المشرف لرصدٍ لم يشاهده — سببٌ ونوعُ دليلٍ إلزاميّان."""
    post = request.POST
    try:
        session, line = TeacherAttendanceService.correct(
            request.user,
            request.school,
            session_id,
            post.get("student_id"),
            status=post.get("status", ""),
            evidence_type=post.get("evidence_type", ""),
            reason=post.get("reason", ""),
        )
    except EntryRefusedError as exc:
        return _refusal(exc)
    except EntryConflictError as exc:
        return _entry_error(exc, 409)
    except EntryError as exc:
        return _entry_error(exc, 400)
    context = {"session": session, "line": line, "evidence_types": EVIDENCE_TYPES}
    return render(request, "attendance/partials/correct_row.html", context)
