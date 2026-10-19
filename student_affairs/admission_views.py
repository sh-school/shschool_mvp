"""عروضُ طلب الالتحاق (نموذج 07، المرحلة 1) — وحدةٌ مستقلّة عن `views.py` (W-20261001-033).

العرضُ يقرأ الطلبَ ويمرّره: القراءةُ في `admission_selectors` والكتابةُ في `admission_services`.
الرقمُ الشخصيّ مستورٌ في الصفحات؛ والحالةُ الصحّيّة تظهر في التفاصيل لمن يملك قدرةَ الانتقالات وحدَه.
"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.academic_calendar import academic_year_for
from core.capabilities import capability_required
from core.privacy import mask_national_id

from .admission_forms import AdmissionApplicationForm
from .admission_models import AdmissionApplication
from .admission_selectors import (
    admission_list as list_admissions,
)
from .admission_selectors import (
    admission_or_404,
    class_group_in,
    placement_classes,
)
from .admission_services import apply_action, create_application
from .transfer_chain import STAGES, available_actions, document_rows

logger = logging.getLogger(__name__)


def _stage_rows(application):
    return [
        {
            "label": label,
            "by": getattr(application, f"{key}_by"),
            "at": getattr(application, f"{key}_at"),
        }
        for key, label in STAGES
    ]


@login_required
@capability_required("student_affairs.transfers")
def admission_list(request):
    """قائمةُ طلبات الالتحاق، وتصفيةٌ بالحالة؛ بلا رقمٍ شخصيّ ولا حالةٍ صحّيّة."""
    status_filter = request.GET.get("status", "")
    return render(
        request,
        "student_affairs/admission_list.html",
        {
            "applications": list_admissions(request.school, status_filter),
            "status_filter": status_filter,
            "status_choices": AdmissionApplication.STATUS_CHOICES,
        },
    )


@login_required
@capability_required("student_affairs.transfers")
def admission_create(request):
    """تسجيلُ طلب التحاقٍ جديد بلا حسابٍ للطالب."""
    form = AdmissionApplicationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            application = create_application(
                request.school, form.cleaned_data, request.user, academic_year_for(request)
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "سُجّل طلب الالتحاق.")
            return redirect("student_affairs:admission_detail", pk=application.pk)
    return render(request, "student_affairs/admission_form.html", {"form": form})


@login_required
@capability_required("student_affairs.transfers")
def admission_detail(request, pk):
    application = admission_or_404(request.school, pk)
    return render(
        request,
        "student_affairs/admission_detail.html",
        {
            "application": application,
            "masked_student_id": mask_national_id(application.student_national_id),
            "masked_applicant_id": mask_national_id(application.applicant_national_id),
            "stages": _stage_rows(application),
            "documents": document_rows(application),
            "actions": available_actions(application),
            "classes": placement_classes(application),
        },
    )


@login_required
@capability_required("student_affairs.transfers")
@require_POST
def admission_action(request, pk):
    """إجراءٌ من السلسلة: تدقيقٌ أو اعتمادٌ أو رفضٌ أو تشعيبٌ أو إدخالٌ أو إلغاء."""
    application = admission_or_404(request.school, pk)
    class_group = None
    if request.POST.get("class_group"):
        class_group = class_group_in(request.school, request.POST["class_group"])
    try:
        student = apply_action(
            application,
            request.POST.get("action", ""),
            request.POST.get("notes", "").strip(),
            request.user,
            documents=request.POST.getlist("documents"),
            missing_reason=request.POST.get("missing_reason", ""),
            class_group=class_group,
            gender=request.POST.get("gender", ""),
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("student_affairs:admission_detail", pk=application.pk)
    if student is not None:
        from .services import StudentService

        # كلمةُ المرور العشوائيّة تُعرض في هذه الاستجابة وحدَها كما في إضافة طالب
        return render(
            request,
            "student_affairs/student_credentials.html",
            {
                "student": student,
                "class_label": str(application.to_class_group),
                "credentials": StudentService.credentials_sheet(student),
            },
        )
    messages.success(request, "حُفظ الإجراء.")
    return redirect("student_affairs:admission_detail", pk=application.pk)
