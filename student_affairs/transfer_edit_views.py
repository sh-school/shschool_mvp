"""شاشتا بحث الطالب وتعديل الانتقال المعلَّق (W-20261114-010)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from core.capabilities import capability_required
from wings.scope import student_scope_for

from .models import StudentTransfer
from .transfer_edit import TransferEditForm, initial_for
from .transfer_edit_selectors import edit_target_context, search_transfer_students
from .transfer_edit_services import NOT_PENDING_MESSAGE, update_pending_transfer


@login_required
@capability_required("student_affairs.transfers")
@require_GET
def transfer_student_search(request: HttpRequest) -> HttpResponse:
    """HTMX — اقتراحُ طلبة مدرسة المستخدم بالاسم ضمن نطاقه؛ حرفٌ واحدٌ لا يبحث."""
    results = search_transfer_students(
        request.school, student_scope_for(request), request.GET.get("q", "")
    )
    return render(
        request, "student_affairs/partials/transfer_student_results.html", {"results": results}
    )


@login_required
@capability_required("student_affairs.transfers")
def transfer_edit(request: HttpRequest, pk: str) -> HttpResponse:
    """تعديلُ انتقالٍ معلَّق وحده؛ غيرُ المعلَّق يُرفض برسالةٍ عربيّة ويُعاد إلى تفاصيله."""
    school = request.school
    transfer = get_object_or_404(
        StudentTransfer.objects.select_related("student", "to_class_group"), pk=pk, school=school
    )
    if transfer.status != "pending":
        messages.error(request, NOT_PENDING_MESSAGE)
        return redirect("student_affairs:transfer_detail", pk=transfer.pk)

    if request.method == "POST":
        form = TransferEditForm(request.POST, direction=transfer.direction)
        if form.is_valid():
            try:
                changed = update_pending_transfer(
                    transfer.pk, school, form.cleaned_data, request.user
                )
            except ValueError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(
                    request, "حُفظ تعديل الانتقال." if changed else "لا تغييرَ لحفظه في الانتقال."
                )
                return redirect("student_affairs:transfer_detail", pk=transfer.pk)
    else:
        form = TransferEditForm(initial=initial_for(transfer), direction=transfer.direction)
    source_label, classes = (
        edit_target_context(transfer) if transfer.direction == "internal" else ("", [])
    )
    return render(
        request,
        "student_affairs/transfer_edit.html",
        {"form": form, "transfer": transfer, "classes": classes, "source_label": source_label},
    )
