"""[STUDENT_AFFAIRS] W-20261107-020: تسجيل تحرّك الطالب مباشرةً من شاشة «تحركات الطلبة».

وحدةٌ مستقلّة عن `views.py` حفاظاً على سقف حجمه. لا بنيةَ جديدة: الكتابةُ تمرّ على
`operations.class_exit.leave/come_back` نفسِها التي يستعملها زرّ «خرج بإذن» في كشف الحصّة،
فيُربط الخروجُ بحصّة الطالب الجارية في جدول اليوم. ومشرفُ الجناح مقيَّدٌ بطلاب جناحه
(`wings.scope`) — وما خرج عنه 404.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.academic_calendar import academic_year_for
from core.capabilities import capability_required
from core.labels import class_label
from core.models.academic import ClassGroup
from core.models.user import CustomUser
from operations import class_exit
from operations.models import ClassExit
from wings.scope import student_scope_for

from .forms import MovementLeaveForm
from .morning_tardiness import current_session


def entry_context(request, scope) -> dict:
    """سياقُ نموذج التسجيل: الصفُّ ثم الشعبةُ ثم الطالب — كلُّ خطوةٍ تُضيَّق بنطاق المستخدم.

    الاختيارُ بلا جافاسكربت: نموذجُ GET يحدّد الشعبة، ثم يظهر نموذجُ POST بطلابها.
    """
    if scope.is_wing_bound:
        groups = scope.class_groups()
    else:
        groups = ClassGroup.objects.filter(
            school=request.school, is_active=True, academic_year=academic_year_for(request)
        )
    groups = list(groups.order_by("section"))

    grade = request.GET.get("mv_grade", "")
    section_id = request.GET.get("mv_section", "")
    sections = [(g.pk, class_label(g.grade, g.section)) for g in groups if g.grade == grade]
    chosen = next((g for g in groups if str(g.pk) == section_id and g.grade == grade), None)
    students: list[CustomUser] = []
    if chosen is not None:
        students = list(
            CustomUser.objects.filter(
                enrollments__class_group=chosen, enrollments__is_active=True
            ).order_by("full_name")
        )
    grades_present = {g.grade for g in groups}
    return {
        "entry_grades": [(v, label) for v, label in ClassGroup.GRADES if v in grades_present],
        "entry_grade": grade,
        "entry_sections": sections,
        "entry_section": str(chosen.pk) if chosen else "",
        "entry_students": students,
        "entry_destinations": [*ClassExit.DESTINATIONS, ("school", "الخروج من المدرسة")],
        "entry_now": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
    }


@login_required
@capability_required("student_affairs.follow_up")
@require_POST
def movement_leave(request):
    """يسجّل خروجَ طالبٍ إلى وجهةٍ في حصّته الجارية، أو يحوّل «الخروجَ من المدرسة» إلى أذوناته."""
    back = redirect("student_affairs:student_movements")
    form = MovementLeaveForm(request.POST)
    if not form.is_valid():
        for errors in form.errors.values():
            messages.error(request, errors[0])
        return back
    data = form.cleaned_data
    scope = student_scope_for(request)
    scope.require_student(data["student"])
    student = get_object_or_404(
        CustomUser.objects.filter(
            enrollments__is_active=True, enrollments__class_group__school=request.school
        ).distinct(),
        pk=data["student"],
    )
    if data["destination"] == "school":
        return redirect(reverse("wings:exit_permit_new", args=[student.pk]))

    left_at = data["left_at"] or timezone.now()
    if timezone.is_naive(left_at):
        left_at = timezone.make_aware(left_at)
    session = current_session(request.school, student, scope, left_at)
    if session is None:
        messages.error(
            request,
            f"لا حصّةَ جاريةً للطالب {student.full_name} في هذا الوقت — لم يُسجَّل الخروج.",
        )
        return back
    exit_ = class_exit.leave(session, student, data["destination"], request.user, now=left_at)
    if exit_ is None:
        messages.error(request, f"{student.full_name} مسجَّلٌ غائباً في هذه الحصّة — لا يُفتح له خروج.")
    else:
        messages.success(request, f"سُجّل خروج {student.full_name}.")
    return back


@login_required
@capability_required("student_affairs.follow_up")
@require_POST
def movement_return(request, pk):
    """زرّ «عاد»: يسجّل وقتَ العودة لخروجٍ مفتوح — وخارجُ نطاق الجناح 404."""
    scope = student_scope_for(request)
    exit_ = get_object_or_404(
        scope.narrow(ClassExit.objects.filter(school=request.school)).select_related(
            "session", "student"
        ),
        pk=pk,
    )
    if exit_.returned_at is not None:
        raise Http404("عاد الطالب من قبل")
    class_exit.come_back(exit_.session, exit_.student, by=request.user)
    messages.success(request, f"سُجّلت عودة {exit_.student.full_name}.")
    return redirect("student_affairs:student_movements")
