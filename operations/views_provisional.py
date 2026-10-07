"""رصدٌ بحصّةٍ مؤقّتة للمعلّم (W-20261005-006): قائمةُ شُعب إسناده، وصفحةُ الشعبة بمنتقي الحصّة ح1–ح7 فوق قائمة الطلبة، والإنشاء.

كلُّ حكمٍ في `services/provisional_session.py`؛ هنا ترجمةٌ إلى HTTP فقط: ما لا يحقّ له ← **404 لا 403** (لا يُعرف أنّ الشعبة موجودة)،
وما رُفض بسببٍ ← رسالةٌ والعودةُ إلى الصفحة. والمفتاحُ مطفأً ← 404 لكلّ هذه المسارات (يعود السلوكُ السابق حرفاً).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.capabilities import capability_required

from .services import provisional_session as provisional
from .views_class_grid import grid_classes


def _class_or_404(request, class_id):
    school = request.school
    try:
        return school, provisional.assigned_class(request.user, school, class_id)
    except provisional.ProvisionalNotAllowedError:
        raise Http404("ليست من شُعب إسنادك") from None


@login_required
def provisional_classes(request):
    """شُعبُ إسناد المعلّم — منها يبدأ الرصدُ بحصّةٍ مؤقّتة؛ ومع مفتاح الجدول القائمةُ نفسُها تفتح جدولَ الشعبة (W-20261006-005)."""
    if provisional.grid_enabled():
        return grid_classes(request)
    return _picker_classes(request)


@capability_required("attendance.mark")
def _picker_classes(request):
    if not provisional.picker_enabled():
        raise Http404
    school = request.school
    return render(
        request,
        "teacher/provisional_classes.html",
        {"classes": provisional.assigned_classes(request.user, school)},
    )


@login_required
@capability_required("attendance.mark")
def provisional_class(request, class_id):
    """صفحةُ الشعبة: منتقي الحصّة ح1–ح7 **فوق** الشبكة، وبعد الاختيار شبكةُ كشف الحصّة نفسُها في الصفحة (السياقُ في الخدمة)."""
    if not provisional.picker_enabled():
        raise Http404
    school, klass = _class_or_404(request, class_id)
    try:
        context = provisional.class_page_context(
            request.user, school, klass, request.GET.get("session")
        )
    except provisional.ProvisionalNotAllowedError:
        raise Http404("لا حصّةَ مؤقّتةً إلا في اليوم الدراسيّ الجاري") from None
    return render(request, "teacher/provisional_class.html", context)


@login_required
@capability_required("attendance.mark")
@require_POST
def provisional_create(request, class_id):
    """ينشئ المؤقّتةَ للحصّة المختارة (أو يفتح حصّتَه القائمة) ويعود إلى صفحة الشعبة بشبكة كشفها."""
    if not provisional.picker_enabled():
        raise Http404
    school, klass = _class_or_404(request, class_id)
    back = reverse("provisional_class", args=[klass.id])
    try:
        session, _created = provisional.create(
            request.user,
            school,
            klass.id,
            request.POST.get("period"),
            subject_id=request.POST.get("subject"),
            request=request,
        )
    except provisional.ProvisionalNotAllowedError:
        raise Http404("لا حصّةَ مؤقّتةً هنا") from None
    except provisional.ProvisionalRefusedError as refusal:
        messages.error(request, str(refusal))
        return redirect(back)
    # الشبكةُ تُفتح في صفحة الشعبة نفسِها لا صفحةٍ أخرى (D-229م)
    return redirect(f"{back}?session={session.id}")
