"""
wings/views_absence_file.py — البحثُ عن طالبٍ في جناحي، وملفُّ غيابه يوماً بيوم.

قرارُ 2026-09-14 والمعيارُ الحاكم: «التسهيلُ والتبسيطُ وبأقلّ عدد من النقرات».

- **البحث**: ثلاثةُ أحرفٍ من الاسم أو أوّلُ الرقم الشخصيّ، في طلاب **أجنحتي وحدها**. ونتيجةٌ
  واحدةٌ تفتح ملفَّه مباشرةً بلا قائمة.
- **الملفّ**: أيّامُ الغياب وحدها، الأحدثُ أوّلاً. وبجانب كلّ يومٍ «اتّصلتُ» (ثلاثةُ أزرارٍ
  بالنتيجة، ضغطةٌ تحفظ) و«عذر» (المستندُ ثمّ زرُّ النوع، ضغطةٌ تحفظ). لا تاريخَ يُكتب:
  يومُ الإخطار يومُ السطر، والعذرُ يشمل أيّامَ الغياب المتّصلة به.
- بعد مهلة العودة يصير زرُّ العذر «أرسل للنائب» ويُحفظ العذرُ بانتظاره.
"""

from __future__ import annotations

import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import F, Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.academic_calendar import academic_year_for_school, academic_year_window
from core.capabilities import capability_required, has_capability
from core.models import ClassGroup, CustomUser, ParentStudentLink, School, StudentEnrollment
from core.sorting import arabic_key, normalise_arabic

from .scope import student_scope_for
from .services import wings_of
from .views import _day, _own_class, excuse_outcome_message

#: أقلُّ ما يُبحث به، وأكثرُ ما يُعرض — ومن لم يجده في عشرين فليزد حرفاً.
MIN_QUERY = 2
MAX_RESULTS = 20


def _own_student(request: HttpRequest, student_id: object) -> tuple[School, ClassGroup, CustomUser]:
    """طالبٌ **قيدُه الجاري** في شعبةٍ من أجنحتي — وإلّا 404 (المشرفُ لجناحه فقط).

    القيدُ الجاري أحدثُ قيود الطالب النشطة (`current_of`): مئاتُ الطلبة يحملون قيدَ العام
    الماضي بجانب قيد هذا العام، و`.first()` بلا ترتيبٍ يختار أحدَهما عشوائيّاً — فيُردّ مشرفُ
    الطالب اليوم، أو يُفتح الملفُّ لمشرف جناحه القديم.
    """
    school = request.user.get_school()  # type: ignore[union-attr]
    enrollment = StudentEnrollment.objects.current_of(student_id, school)
    if enrollment is None:
        raise Http404("لا شعبةَ لهذا الطالب")
    school, klass = _own_class(request, enrollment.class_group_id)  # type: ignore[no-untyped-call]
    student_scope_for(request).require_student(enrollment.student_id)
    return school, klass, enrollment.student


def _scoped_ids(request: HttpRequest) -> frozenset[object] | list[object]:
    """طلبةُ النطاق للمقيَّد بجناحه؛ ولغيره لا تضييقَ فوق أجنحته (القيادةُ ترى الخمسة)."""
    scope = student_scope_for(request)
    if scope.is_wing_bound:
        return scope.student_ids()
    return StudentEnrollment.objects.filter(is_active=True).values_list("student_id", flat=True)  # type: ignore[return-value]


def _file_url(student_id: object, day: dt.date | None = None) -> str:
    url = reverse("wings:absence_file", args=[student_id])
    return f"{url}#day-{day:%Y-%m-%d}" if day else url


@login_required
@capability_required("wings.record_day")
def student_search(request: HttpRequest) -> HttpResponse:
    """طلابُ أجنحتي بالاسم أو الرقم الشخصيّ — ونتيجةٌ واحدةٌ تفتح الملفَّ مباشرةً."""
    school = request.user.get_school()
    query = (request.GET.get("q") or "").strip()
    results = []
    if len(query) >= MIN_QUERY:
        wings = wings_of(request.user, school, academic_year_for_school(school))
        shaped = normalise_arabic(query)
        results = list(
            StudentEnrollment.objects.filter(
                is_active=True,
                class_group__school=school,
                class_group__wing__in=wings,
            )
            .annotate(name_key=arabic_key(F("student__full_name")))  # type: ignore[no-untyped-call]
            .filter(Q(name_key__icontains=shaped) | Q(student__national_id__startswith=query))
            # من قيدُه الجاري في جناحي — لا من بقي له قيدٌ قديمٌ نشطٌ في شعبةٍ منه.
            .filter(student_id__in=_scoped_ids(request))
            .select_related("student", "class_group")
            .order_by("student__full_name")[: MAX_RESULTS + 1]
        )
        if len(results) == 1:
            return redirect(_file_url(results[0].student_id))
    return render(
        request,
        "wings/student_search.html",
        {
            "query": query,
            "results": results[:MAX_RESULTS],
            "more": len(results) > MAX_RESULTS,
            "too_short": bool(query) and len(query) < MIN_QUERY,
        },
    )


@login_required
@capability_required("wings.record_day")
def absence_file(request: HttpRequest, student_id: object) -> HttpResponse:
    """ملفُّ غياب الطالب: أيّامُ غيابه هذا العام، وبجانب كلٍّ «اتّصلتُ» و«عذر»."""
    from operations.absence_file import absence_days
    from operations.absence_standing import standing_for
    from operations.excuses import kinds
    from operations.models import GuardianContact

    school, klass, student = _own_student(request, student_id)
    today = timezone.localdate()
    window = academic_year_window(school, today)  # type: ignore[no-untyped-call]
    # مَن يُتّصل به وبأيّ رقم: الأساسيُّ أوّلاً — كانت «اتّصلتُ» تُعرض بلا اسمٍ ولا هاتف.
    guardians = [
        {
            "name": link.parent.full_name,
            "relation": link.get_relationship_display(),
            "phone": (link.parent.phone or "").strip(),
        }
        for link in ParentStudentLink.objects.filter(student=student, school=school)
        .select_related("parent")
        .order_by("-is_primary", "created_at")[:3]
    ]
    start = window[0] if window else today.replace(month=9, day=1)
    return render(
        request,
        "wings/absence_file.html",
        {
            "klass": klass,
            "student": student,
            "days": absence_days(student, school, start, today),
            "standing": standing_for(student, school, grade=klass.grade, on=today),
            "excuse_kinds": kinds(),
            "guardians": guardians,
            # «أخطِر» في اللوحة والكشف يفتح لوحةَ الاتّصال على يومها مباشرةً.
            "call_day": _day(request.GET.get("call")),  # type: ignore[no-untyped-call]
            "contact_outcomes": GuardianContact.OUTCOMES,
            "may_override": has_capability(request.user, "wings.excuse_after_deadline"),
        },
    )


@login_required
@capability_required("wings.record_day")
@require_POST
def absence_file_excuse(request: HttpRequest, student_id: object) -> HttpResponse:
    """«عذر» من سطر اليوم: المدّةُ من السطر، والنوعُ من الزرّ المضغوط."""
    from operations.excuses import ExcuseError, grant_excuse

    school, _klass, student = _own_student(request, student_id)
    date_from = _day(request.POST.get("date_from"))  # type: ignore[no-untyped-call]
    date_to = _day(request.POST.get("date_to"), date_from)  # type: ignore[no-untyped-call]
    if date_from is None or date_to is None:
        messages.error(request, "لم يُعرف يومُ الغياب — افتح الملفَّ من جديد.")
        return redirect(_file_url(student.id))
    try:
        excuse = grant_excuse(
            student=student,
            school=school,
            date_from=date_from,
            date_to=date_to,
            kind=request.POST.get("kind", ""),
            notes=request.POST.get("notes", ""),
            document=request.FILES.get("document"),
            by=request.user,
            may_override=has_capability(request.user, "wings.excuse_after_deadline"),
            override_reason=request.POST.get("override_reason", ""),
            forward_if_late=True,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except (ExcuseError, ValidationError) as err:
        messages.error(request, " ".join(getattr(err, "messages", None) or [str(err)]))
        return redirect(_file_url(student.id))
    excuse_outcome_message(request, excuse)  # type: ignore[no-untyped-call]
    return redirect(_file_url(student.id, date_to))


@login_required
@capability_required("wings.record_day")
@require_POST
def absence_file_contact(request: HttpRequest, student_id: object) -> HttpResponse:
    """«اتّصلتُ» من سطر اليوم: يومُ الغياب من السطر، والنتيجةُ من الزرّ المضغوط."""
    from operations.guardian_contact import ContactError, log_contact

    school, _klass, student = _own_student(request, student_id)
    absence_date = _day(request.POST.get("absence_date"))  # type: ignore[no-untyped-call]
    if absence_date is None:
        messages.error(request, "لم يُعرف يومُ الغياب — افتح الملفَّ من جديد.")
        return redirect(_file_url(student.id))
    try:
        contact = log_contact(
            student=student,
            school=school,
            absence_date=absence_date,
            outcome=request.POST.get("outcome", ""),
            by=request.user,
        )
    except ContactError as err:
        messages.error(request, str(err))
        return redirect(_file_url(student.id))
    messages.success(
        request,
        f"سُجّل الإخطارُ عن غياب {absence_date.day}/{absence_date.month}: {contact.get_outcome_display()}.",
    )
    return redirect(_file_url(student.id, absence_date))
