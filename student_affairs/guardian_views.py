"""شاشاتُ طلبات الأولياء وشكاواهم (W-20261001-019؛ 01 و02 و05 و06 و08).

وحدةٌ مستقلّة عن `views.py` (الملفُّ عند سقف الحجم). الحارسُ على الدور بقدرةٍ مسمّاة؛ والقراءةُ كلُّها
في `guardian_selectors` مفلترةً بالمدرسة، فطلبُ مدرسةٍ أخرى 404. والتحقّقُ من المرحلة والصلاحيّة الدقيقة
داخل الخدمة لا هنا.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.capabilities import capability_required, has_capability

from . import guardian_requests as flow
from . import guardian_selectors as read
from .guardian_forms import FIELDS_BY_KIND, GuardianRequestForm
from .guardian_request_models import GuardianRequest
from .selectors import transfer_form_options

#: نوعُ الطلب ← (عنوان الصفحة، أيقونة) — النوعُ في الرابط يُرفض إن لم يكن هنا.
KIND_PAGES = {
    GuardianRequest.KIND_REQUEST: ("طلب وليّ أمر", "edit_record"),
    GuardianRequest.KIND_COMPLAINT: ("شكوى وليّ أمر", "edit_record"),
    GuardianRequest.KIND_STATEMENT: ("إفادة طالب", "edit_record"),
    GuardianRequest.KIND_CONTACT_CHANGE: ("طلب تغيير رقم التواصل", "edit_record"),
    GuardianRequest.KIND_HOTLINE: ("استمارة الخطّ الساخن", "edit_record"),
}


@login_required
@capability_required("student_affairs.manage")
def request_list(request):
    """سجلُّ الطلبات مرتَّباً بالأحدث، ويُرشَّح بالنوع والمرحلة."""
    kind = request.GET.get("kind", "")
    stage = request.GET.get("stage", "")
    return render(
        request,
        "student_affairs/guardian_request_list.html",
        {
            "requests": read.list_requests(request.school, kind, stage),
            "kind_filter": kind,
            "stage_filter": stage,
            "kind_choices": GuardianRequest.KIND_CHOICES,
            "stage_choices": GuardianRequest.STAGE_CHOICES,
            "kind_pages": KIND_PAGES,
        },
    )


@login_required
@capability_required("student_affairs.manage")
def request_create(request, kind):
    """إدخالُ طلبٍ جديد من النوع المطلوب."""
    if kind not in KIND_PAGES:
        return redirect("student_affairs:request_list")
    school = request.school
    needs_student = "student_id" in FIELDS_BY_KIND[kind]
    form = GuardianRequestForm(request.POST or None, kind=kind)
    if request.method == "POST" and form.is_valid():
        student = (
            read.school_member(school, form.cleaned_data["student_id"]) if needs_student else None
        )
        fields = form.service_fields()
        if kind == GuardianRequest.KIND_CONTACT_CHANGE and not fields["current_phone"]:
            fields["current_phone"] = student.get_phone_decrypted()
        req = flow.create_request(school, request.user, kind=kind, student=student, **fields)
        messages.success(request, "تم تسجيل الطلب.")
        return redirect("student_affairs:request_detail", pk=req.pk)
    title, icon = KIND_PAGES[kind]
    return render(
        request,
        "student_affairs/guardian_request_form.html",
        {
            "form": form,
            "kind": kind,
            "students": transfer_form_options(school)[0] if needs_student else [],
            "page_title": title,
            "page_icon": icon,
            "capacity_choices": GuardianRequest.CAPACITY_CHOICES,
            "direct_choices": GuardianRequest.DIRECT_CHOICES,
        },
    )


@login_required
@capability_required("student_affairs.manage")
def request_detail(request, pk):
    """تفاصيلُ الطلب ومساره، وأمامها نموذجُ المرحلة التالية للمخوَّل بها."""
    req = read.get_request(request.school, pk)
    return render(
        request,
        "student_affairs/guardian_request_detail.html",
        {
            "req": req,
            "events": read.events_of(req),
            "staff": read.staff_options(request.school) if req.stage == req.STAGE_SUBMITTED else [],
            "can_verify": has_capability(request.user, flow.VERIFY_CAPABILITY),
            "page_title": KIND_PAGES[req.kind][0],
            "contact_choices": GuardianRequest.CONTACT_CHOICES,
        },
    )


def _act(request, pk, run):
    """يُنفّذ انتقالاً ويعيد إلى التفاصيل؛ رفضُ المرحلة رسالةٌ لا خطأ خادم."""
    req = read.get_request(request.school, pk)
    try:
        run(req)
        messages.success(request, "تم تنفيذ الإجراء.")
    except flow.TransitionError as exc:
        messages.error(request, str(exc))
    return redirect("student_affairs:request_detail", pk=req.pk)


@login_required
@capability_required("student_affairs.manage")
@require_POST
def request_refer(request, pk):
    employee = read.school_member(request.school, request.POST.get("employee", ""))
    return _act(request, pk, lambda req: flow.refer(req, request.user, employee))


@login_required
@capability_required("student_affairs.manage")
@require_POST
def request_feedback(request, pk):
    text = request.POST.get("text", "")
    return _act(request, pk, lambda req: flow.record_feedback(req, request.user, text))


@login_required
@capability_required("student_affairs.manage")
@require_POST
def request_contact(request, pk):
    status = request.POST.get("status", "")
    return _act(request, pk, lambda req: flow.confirm_contact(req, request.user, status))


@login_required
@capability_required("student_affairs.manage")
@require_POST
def request_close(request, pk):
    return _act(request, pk, lambda req: flow.close(req, request.user))


@login_required
@capability_required("student_affairs.verify_contact")
@require_POST
def request_verify(request, pk):
    """قبولُ طلب تغيير الرقم أو رفضُه — للنائب الإداريّ والمدير."""
    approve = request.POST.get("decision") == "approve"
    return _act(
        request, pk, lambda req: flow.verify_contact_change(req, request.user, approve=approve)
    )
