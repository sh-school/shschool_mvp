"""شاشةُ طلب الانتقال الجديد وشاشةُ مراجعة النقل المباشر (W-20261124-001).

النقلُ المباشر (للمدير والنائب الإداري وحدهما، D-343م) لا يُنفَّذ بمجرّد الإرسال: الطلبُ الأوّل يعرض
صفحةَ تأكيدٍ بمدخلاتٍ مخفيّةٍ يرسمها الخادم، والتنفيذُ بطلب POST ثانٍ يحمل `confirm_direct`،
والصلاحيةُ تُتحقَّق في الطلبين. منطقُ الانتقال والاعتماد كما هو في `internal_transfer` و`transfer_decision`.
"""

from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from core.academic_calendar import academic_year_for
from core.capabilities import capability_required
from wings.scope import student_scope_for

from .forms import TransferForm
from .selectors import transfer_target_classes
from .transfer_create_services import direct_move, prepare_request, save_request
from .transfer_decision import may_decide
from .transfer_edit_selectors import picked_student

#: حقولُ النموذج التي تُنقل مخفيّةً في صفحة التأكيد (الخادمُ يعيد التحقّق منها كلَّها في الطلب الثاني).
_ECHO_FIELDS = (
    "student_id",
    "direction",
    "to_class_group_id",
    "other_school_name",
    "transfer_date",
    "reason",
    "direct",
)


def _form_page(request: HttpRequest, form: TransferForm) -> HttpResponse:
    """عرضُ النموذج: الطالبُ المختار (إن وُجد) وكلُّ شعبةٍ نشطةٍ هدفاً للانتقال الداخلي."""
    school = request.school
    raw_id = form.data.get("student_id") if form.is_bound else form.initial.get("student_id")
    return render(
        request,
        "student_affairs/transfer_form.html",
        {
            "form": form,
            "picked": picked_student(school, student_scope_for(request), raw_id),
            "classes": transfer_target_classes(school),
            "can_direct": may_decide(request.user),
        },
    )


def _confirm_page(request: HttpRequest, form: TransferForm, transfer: Any) -> HttpResponse:
    """صفحةُ المراجعة قبل النقل المباشر: من أين وإلى أين الآن، والمدخلاتُ محفوظةٌ لزرّ الرجوع."""
    picked = picked_student(
        request.school, student_scope_for(request), form.cleaned_data["student_id"]
    )
    hidden = [
        (name, "1" if value is True else str(value))
        for name in _ECHO_FIELDS
        if (value := form.cleaned_data.get(name)) not in (None, "", False)
    ]
    return render(
        request,
        "student_affairs/transfer_direct_confirm.html",
        {
            "student_name": transfer.student.full_name,
            "from_label": picked["class_label"] if picked else "بلا شعبة",
            "to_label": transfer.to_class_group.short_label,
            "transfer_date": transfer.transfer_date,
            "hidden_fields": hidden,
        },
    )


def _execute_direct(request: HttpRequest, form: TransferForm, transfer: Any) -> HttpResponse:
    """التنفيذُ بعد التأكيد: يعيد التحقّق من الصلاحية والهدف والتاريخ في `move_directly` قبل أيّ كتابة."""
    error = direct_move(transfer, request.user, request.school)
    if error:
        form.add_error(None, error)
        return _form_page(request, form)
    messages.success(request, f"نُقل {transfer.student.full_name} إلى شعبته الجديدة مباشرةً.")
    return redirect("student_affairs:transfer_detail", pk=transfer.pk)


def _submit(request: HttpRequest, form: TransferForm) -> HttpResponse:
    """نموذجٌ صالح: نقلٌ مباشرٌ بخطوتين، أو طلبٌ عاديّ يُحفظ معلَّقاً."""
    cd = form.cleaned_data
    # الصلاحيةُ تُفحص في `prepare_request` في كلّ طلبٍ (الأوّل والتأكيد) قبل أيّ كتابة.
    transfer, error = prepare_request(request.school, cd, academic_year_for(request), request.user)
    if error:
        form.add_error(None, error)
        return _form_page(request, form)
    if cd["direct"]:
        if "confirm_direct" not in request.POST:
            return _confirm_page(request, form, transfer)
        return _execute_direct(request, form, transfer)
    save_request(transfer, request.user)
    messages.success(request, f"تم تسجيل طلب انتقال {transfer.student.full_name} بنجاح.")
    return redirect("student_affairs:transfer_list")


@login_required
@capability_required("student_affairs.transfers")
def transfer_create(request: HttpRequest) -> HttpResponse:
    """تسجيل طلب انتقال جديد؛ و«رجوع للتعديل» من صفحة التأكيد يعيد النموذجَ بمدخلاته بلا تحقّق."""
    if request.method != "POST":
        form = TransferForm(initial={"transfer_date": timezone.localdate().isoformat()})
    elif "edit" in request.POST:
        form = TransferForm(initial={n: v for n, v in request.POST.items() if n in _ECHO_FIELDS})
    else:
        form = TransferForm(request.POST)
        if form.is_valid():
            return _submit(request, form)
    return _form_page(request, form)
