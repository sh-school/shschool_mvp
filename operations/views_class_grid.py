"""جدولُ الشعبة العموديّ لرصد الغياب (W-20261006-005): قائمةُ الشُّعب، والصفحةُ، والحفظُ بالعمود، وسجلُّ الخليّة، و«دخول متأخّر».

كلُّ حكمٍ في `services/class_grid.py`؛ هنا ترجمةٌ إلى HTTP فقط: ما لا يحقّ له ← **404 لا 403** (لا يُعرف أنّ الشعبة موجودة)، وما رُفض بسببٍ
← JSON برمزه. والمفتاحُ مطفأً ← 404 لكلّ هذه المسارات (يخدم الكشفُ الحاليّ). الصلاحيةُ تُفحص داخل الخدمة (معلّمُ الإسناد وحاملُ الجناح والقيادةُ
والنائبُ للقراءة) — فلا قدرةَ مفردةَ تغطّيهم؛ والمسارُ في `GUARDED_INSIDE`.
"""

import json

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .services import class_grid as grid


def _json_body(request):
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


@login_required
def grid_classes(request):
    """شُعبي للجدول — إسنادُ المعلّم وأجنحةُ المشرف، وللقيادة والنائب كلُّ الشُّعب."""
    from .services import provisional_session

    if not provisional_session.grid_enabled():
        raise Http404
    return render(
        request,
        "teacher/provisional_classes.html",
        {"classes": grid.classes_for(request.user, request.school), "grid": True},
    )


@login_required
def class_grid(request, class_id):
    try:
        context = grid.page(request.user, request.school, class_id)
    except grid.GridNotFoundError:
        raise Http404 from None
    return render(request, "teacher/class_grid.html", {"grid_page": context})


@login_required
@require_POST
def class_grid_save(request, class_id):
    """حفظُ عمود: JSON `{period, cells:[{student, status, head}], fill_empty, bulk, reason}` — يردّ 207 بقائمة المتعارضات إن وُجدت."""
    body = _json_body(request)
    if body is None:
        return HttpResponseBadRequest("حمولةٌ غيرُ صالحة")
    try:
        result = grid.save_column(
            request.user,
            request.school,
            class_id,
            body.get("period"),
            body.get("cells", []),
            fill_empty=bool(body.get("fill_empty")),
            bulk=str(body.get("bulk") or ""),
            reason=str(body.get("reason") or ""),
            request=request,
        )
    except grid.GridNotFoundError:
        raise Http404 from None
    except grid.GridRefusedError as refusal:
        return JsonResponse(
            {"ok": False, "reason": refusal.reason, "message": str(refusal)}, status=403
        )
    status = 207 if (result.conflicts or result.errors) else 200
    return JsonResponse(
        {
            "ok": not (result.conflicts or result.errors),
            "session": str(result.session_id),
            "saved": result.saved,
            "conflicts": result.conflicts,
            "errors": result.errors,
            "defaults": result.defaults,
        },
        status=status,
    )


@login_required
def class_grid_history(request, class_id, student_id, number):
    """سجلُّ خليّةٍ: من كتب ومتى ومن صحّح — جزءٌ يُحمَّل في نافذةٍ."""
    try:
        klass, student, rows = grid.history(
            request.user, request.school, class_id, student_id, number
        )
    except grid.GridNotFoundError:
        raise Http404 from None
    return render(
        request,
        "teacher/partials/class_grid_history.html",
        {"klass": klass, "student": student, "rows": rows, "number": number},
    )


@login_required
@require_POST
def class_grid_late(request, class_id):
    """«دخول متأخّر» لطالبٍ في الحصّة الجارية وقتَ الضغط."""
    try:
        result = grid.mark_late_now(
            request.user, request.school, class_id, request.POST.get("student"), request=request
        )
    except grid.GridNotFoundError:
        raise Http404 from None
    except grid.GridRefusedError as refusal:
        return JsonResponse(
            {"ok": False, "reason": refusal.reason, "message": str(refusal)}, status=403
        )
    status = 207 if (result.conflicts or result.errors) else 200
    return JsonResponse(
        {"ok": status == 200, "saved": result.saved, "conflicts": result.conflicts}, status=status
    )
