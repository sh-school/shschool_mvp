"""رصدٌ بحصّةٍ مؤقّتة للمعلّم (W-20261005-006): قائمةُ شُعب إسناده، وصفحةُ الشعبة بمنتقي الحصّة ح1–ح7 فوق قائمة الطلبة، والإنشاء.

كلُّ حكمٍ في `services/provisional_session.py`؛ هنا ترجمةٌ إلى HTTP فقط: ما لا يحقّ له ← **404 لا 403** (لا يُعرف أنّ الشعبة موجودة)،
وما رُفض بسببٍ ← رسالةٌ والعودةُ إلى الصفحة. والمفتاحُ مطفأً ← 404 لكلّ هذه المسارات (يعود السلوكُ السابق حرفاً).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.capabilities import capability_required
from core.models import StudentEnrollment

from .models import Session
from .services import provisional_session as provisional
from .services.attendance_teacher import TeacherAttendanceService


def _class_or_404(request, class_id):
    school = request.school
    try:
        return school, provisional.assigned_class(request.user, school, class_id)
    except provisional.ProvisionalNotAllowedError:
        raise Http404("ليست من شُعب إسنادك") from None


@login_required
@capability_required("attendance.mark")
def provisional_classes(request):
    """شُعبُ إسناد المعلّم — منها يبدأ الرصدُ بحصّةٍ مؤقّتة."""
    if not provisional.enabled():
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
    """صفحةُ الشعبة: منتقي الحصّة ح1–ح7 **فوق** قائمة الطلبة، فيختار المعلّمُ حصّتَه قبل الرصد."""
    school, klass = _class_or_404(request, class_id)
    try:
        choices = provisional.period_choices(request.user, school, klass)
    except provisional.ProvisionalNotAllowedError:
        raise Http404("لا حصّةَ مؤقّتةً إلا في اليوم الدراسيّ الجاري") from None
    students = (
        StudentEnrollment.objects.filter(class_group=klass, is_active=True)
        .select_related("student")
        .order_by("student__full_name")
    )
    context = {"klass": klass, "choices": choices, "enrollments": students}
    chosen = _chosen_session(request, school, klass)
    if chosen is not None:
        # **شبكةُ كشف الحصّة نفسُها** في الصفحة نفسِها بعد اختيار الحصّة (D-229م): كشفُ المعلّم المشترك بحاضر/غائب/متأخّر/خروج كما في كشف المشرف.
        context.update(
            {
                **TeacherAttendanceService.page_context(request.user, chosen),
                **TeacherAttendanceService.sheet(request.user, chosen),
            }
        )
    return render(request, "teacher/provisional_class.html", context)


def _chosen_session(request, school, klass):
    """الحصّةُ المختارةُ `?session=<معرّف>` إن كانت **حصّةَ هذا المعلّم اليومَ في هذه الشعبة** — وإلا لا شيء (لا يُكشف وجودُ غيرها)."""
    raw = request.GET.get("session")
    if not raw:
        return None
    try:
        return (
            Session.objects.select_related("class_group__wing", "subject")
            .exclude(status="cancelled")
            .get(
                pk=raw,
                school=school,
                class_group=klass,
                teacher=request.user,
                date=timezone.localdate(),
            )
        )
    except (Session.DoesNotExist, ValueError, ValidationError):
        return None


@login_required
@capability_required("attendance.mark")
@require_POST
def provisional_create(request, class_id):
    """ينشئ المؤقّتةَ للحصّة المختارة (أو يفتح حصّتَه القائمة) ويعود إلى صفحة الشعبة بشبكة كشفها."""
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
