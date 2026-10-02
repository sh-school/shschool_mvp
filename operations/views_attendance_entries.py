"""views رصد المعلّم المبدئيّ واعتمادِه (W-20261002-020) — رقيقةٌ: القاعدةُ في `attendance_policy` والكتابةُ في `attendance_entries`.

المعلّمُ الفعليّ يُدخل رصداً مبدئيّاً (`entry_submit`)، ويقرّر حاملُ جناح الشعبة يومَ الحصّة أو القيادةُ حين لا حاملَ فعليّاً
(`approvals` و`approval_decide`)، ويرى النائبُ ما لم يُعتمد بعد مدّةٍ (`unapproved`). والسياسةُ هي الحَكَم في كلّ طلب؛
والقدرةُ على المسار بوّابةٌ أوسعُ لا بديلٌ منها. وكلُّ جلبٍ وكتابةٍ في `TeacherAttendanceService`.
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from core.capabilities import capability_required

from .attendance_entries import EntryConflictError, EntryError, EntryRefusedError
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


def _refusal(exc: EntryRefusedError) -> HttpResponse:
    return HttpResponse(REFUSALS.get(exc.reason, DEFAULT_REFUSAL), status=403)


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
        )
    except EntryRefusedError as exc:
        return _refusal(exc)
    except EntryConflictError:
        return HttpResponse("سبقك إدخالٌ آخرُ — أعِد المحاولة.", status=409)
    except EntryError as exc:
        return HttpResponse(str(exc), status=400)
    context = {"session": session, "line": line, "can_enter": True}
    return render(request, "teacher/partials/entry_cell.html", context)


@login_required
@capability_required("wings.record_day")
def approvals(request):
    """طابورُ الاعتماد: ما يملك هذا المستخدمُ قرارَه (حاملُ الجناح، أو القيادةُ حين لا حاملَ فعليّاً)."""
    items = TeacherAttendanceService.queue(request.user, request.school)
    return render(request, "attendance/approvals.html", {"items": items})


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
    except EntryConflictError:
        return HttpResponse(
            "رصدٌ آخرُ (مشرفٌ أو عيادةٌ) قائمٌ على هذا الطالب — لا كتابةَ فوقه؛ ارفضْ الإدخالَ بسبب.",
            status=409,
        )
    except EntryError as exc:
        return HttpResponse(str(exc), status=400)
    context = {"entry": entry, "decision": decision}
    return render(request, "attendance/partials/decided_row.html", context)


@login_required
@capability_required("wings.record_day")
def unapproved(request):
    """تقريرُ «غيرُ معتمَد بعد X ساعة» — بالعدد لا بأسماء الطلاب، ويُظهر ما لا حاملَ فعليّاً له."""
    rows, hours = TeacherAttendanceService.report(request.school, request.GET.get("hours"))
    return render(request, "attendance/unapproved.html", {"rows": rows, "hours": hours})
