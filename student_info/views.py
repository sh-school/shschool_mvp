"""
شاشاتُ مركز معلومات الطلبة.

المدخلُ الشُّعبُ ثمّ الطالب، كما طلبت المدرسة: تفتح الشعبةَ فترى طلابها،
وتفتح الطالبَ فترى ملفّه كاملاً. والقوائمُ السبعُ في القائمة الرئيسيّة تفتح
كلٌّ منها شاشتَها مباشرةً لمن أراد النظرَ عرضاً لا طولاً.

والمشرفُ الإداريُّ لجناحه وحدَه (قرارا 2026-09-14/15): كلُّ شاشةٍ تأخذ
`student_scope_for(request)`، وكلُّ معرّفِ شعبةٍ أو طالبٍ في الرابط يمرّ على
`require_class` / `require_student` فيعود 404 لما خرج عن جناحه. ولا يرى من ملفّ
طالبِ جناحه الدرجاتِ ولا ملاحظاتِ الأخصائيَّين، ولا تُفتح له المستوياتُ ولا الأنشطة.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_http_methods

from core.academic_calendar import academic_year_for
from core.capabilities import capability_required
from core.models import AuditLog, CustomUser
from core.models.academic import ClassGroup
from core.sorting import apply_sort
from student_info import services
from student_info.access import (
    can_read_student,
    sees_whole_school,
    visible_class_groups,
    writable_categories,
)
from student_info.forms import StudentNoteForm
from student_info.models import NOTE_CATEGORIES, SENSITIVE_CATEGORIES, StudentNote
from wings.scope import SPECIALIST_CATEGORIES, student_scope_for

CATEGORY_LABELS = dict(NOTE_CATEGORIES)

# حقولُ الفرز المسموحة: `?sort=` نصٌّ من المستخدم لا يُمرَّر إلى ORM إلّا مصفّى.
# ولكلّ مفتاحٍ حقلٌ ثانٍ يقطع التساوي فلا يتأرجح ترتيبُ الصفحات بين طلبين.
NOTE_SORTS = {
    "date": ("occurred_on", "-created_at"),
    "student": ("student__full_name", "-occurred_on"),
    "title": ("title", "-occurred_on"),
    "author": ("created_by__full_name", "-occurred_on"),
}

ACTIVITY_SORTS = {
    "date": ("date", "-id"),
    "student": ("student__full_name", "-date"),
    "activity": ("title", "-date"),
    "type": ("activity_type", "-date"),
    "scope": ("scope", "-date"),
}


def _no_access(request, message="هذا الطالب خارج نطاقك — لا تُعرض ملفّاتُ من لا تُدرّسهم."):
    """خارجُ النطاق: المقيَّدُ بجناحه 404 — وجودُ الطالب في جناحٍ غيره ليس شأنَه —
    والمعلّمُ يُعاد إلى الشُّعب برسالةٍ كما كان."""
    if student_scope_for(request).is_wing_bound:
        raise Http404("خارج نطاق جناحك")
    messages.error(request, message)
    return redirect("student_info:sections")


def _year(request, scope):
    """العامُ المعروض: `?year=` لغير المقيَّد كما كان، والعامُ الجاري للمقيَّد بجناحه.

    ولا يُحسب العامُ الجاري لمن طلب عاماً بعينه وهو غيرُ مقيَّد — فلا استعلامَ زائدٌ
    على القيادة والمعلّمين.
    """
    requested = request.GET.get("year")
    if requested and not scope.is_wing_bound:
        return requested
    return scope.year_for(requested, scope.year or academic_year_for(request))


def _refuse_wing_bound(request):
    """شاشةٌ ليست من مهامّ المشرف الإداريّ: 404 له، ولغيره كما كانت."""
    if student_scope_for(request).is_wing_bound:
        raise Http404("ليست من شاشات جناحك")


def _audit_sensitive_read(request, student, categories):
    """أثرٌ لا يُمحى لكلّ قراءةِ ملاحظةِ أخصائيّ (PDPPL م.19)."""
    touched = sorted(set(categories) & set(SENSITIVE_CATEGORIES))
    if not touched:
        return
    AuditLog.log(
        user=request.user,
        action="view",
        model_name="StudentNote",
        object_id=student.id,
        object_repr=f"{student.full_name} — {'، '.join(CATEGORY_LABELS[c] for c in touched)}",
        changes={"categories": touched},
        request=request,
    )


# ── المدخل: الشُّعب ثمّ الطالب ────────────────────────────────────────


@login_required
@capability_required("student_info.read")
def sections(request):
    """الشُّعبُ — مدخلُ المركز. والمشرفُ الإداريُّ: شُعبُ أجنحته وحدها."""
    school = request.user.get_school()
    scope = student_scope_for(request)
    year = _year(request, scope)
    groups = services.sections_with_counts(
        visible_class_groups(request.user, school, year, scope=scope), scope=scope
    )
    return render(
        request,
        "student_info/sections.html",
        {
            "groups": groups,
            "cards": [_section_card(g, year) for g in groups],
            "subtitle": f"اختر شعبةً ثمّ طالباً — {_ltr(year)}",
            "year": year,
            "school": school,
            "wing_bound": scope.is_wing_bound,
        },
    )


def _section_card(group, year):
    """عنوانُ بطاقة الشعبة وعددُها ورابطُها — نصٌّ مركّبٌ يُبنى هنا لا في القالب."""
    url = reverse("student_info:section_students", args=[group.id])
    return {
        "group": group,
        "title": f"{group.grade[1:]}/{group.section}",
        "count": f"{group.student_count} طالباً",
        "href": f"{url}?{urlencode({'year': year})}",
    }


@login_required
@capability_required("student_info.read")
def section_students(request, class_id):
    """طلابُ شعبةٍ واحدة."""
    school = request.user.get_school()
    scope = student_scope_for(request)
    scope.require_class(class_id)
    year = _year(request, scope)
    group = get_object_or_404(ClassGroup, id=class_id, school=school)
    visible = visible_class_groups(request.user, school, year, scope=scope)
    if group.id not in {g.id for g in visible}:
        return _no_access(request, "هذه الشعبة خارج نطاقك.")
    return render(
        request,
        "student_info/section_students.html",
        {
            "group": group,
            "title": f"{group.get_grade_display()} — الشعبة {group.section}",
            "subtitle": " · ".join(filter(None, [group.get_track_display(), _ltr(year)])),
            # الطالبُ بقيده الجاري: قيدٌ قديمٌ نشطٌ في هذه الشعبة لا يُظهر للمشرف
            # طالباً صار في جناحٍ آخر.
            "enrollments": scope.narrow(services.students_of_section(group), "student_id"),
            "year": year,
        },
    )


@login_required
@capability_required("student_info.read")
def student_file(request, student_id):
    """ملفُّ الطالب الجامع: تحصيلُه، وملاحظاتُ الجهات الخمس، وأنشطتُه.

    والمقيَّدُ بجناحه لا يُحسب له التحصيلُ ولا تُجلب له ملاحظاتُ الأخصائيَّين أصلاً.
    """
    school = request.user.get_school()
    scope = student_scope_for(request)
    scope.require_student(student_id)
    year = _year(request, scope)
    student = get_object_or_404(CustomUser, id=student_id, memberships__school=school)

    if not can_read_student(request.user, student, school, year, scope=scope):
        return _no_access(request)

    hidden = SPECIALIST_CATEGORIES if scope.hides_specialist_notes else ()
    grouped = services.notes_by_category(student, year, hidden=hidden)
    _audit_sensitive_read(request, student, [c for c, notes in grouped.items() if notes])
    class_group = services.current_class_group(student, year)
    shows_grades = not scope.hides_grades

    return render(
        request,
        "student_info/student_file.html",
        {
            "student": student,
            "year": year,
            "class_group": class_group,
            "subtitle": _file_subtitle(class_group, year),
            "shows_grades": shows_grades,
            "results": services.student_results(student, year) if shows_grades else [],
            "average": services.student_average(student, year) if shows_grades else None,
            "note_groups": [
                {"key": key, "label": CATEGORY_LABELS[key], "notes": grouped[key]}
                for key, _ in NOTE_CATEGORIES
                if key in grouped
            ],
            "activities": services.student_activities(student, year),
            "can_write": writable_categories(request.user),
        },
    )


def _file_subtitle(class_group, year):
    """«الصفّ — الشعبة · المسار · العام» — ومن لا شعبةَ له هذا العام: العامُ وحده."""
    if not class_group:
        return _ltr(year)
    head = f"{class_group.get_grade_display()} — الشعبة {class_group.section}"
    return " · ".join(filter(None, [head, class_group.get_track_display(), _ltr(year)]))


def _ltr(year) -> str:
    """«2026-2027» داخل سطرٍ عربيّ يُقرأ «2027-2026» — فيُعزل اتّجاهُه."""
    return f"\u2066{year}\u2069"


# ── المستويات التعليمية وربطها بالتحصيل ──────────────────────────────


@login_required
@capability_required("student_info.read")
def levels(request):
    """شرائحُ التحصيل: الإجمالُ، ولكلّ صفٍّ، ولكلّ مادّة — بمرشِّح الصفّ والمسار.

    والتحصيلُ ليس من مهامّ المشرف الإداريّ في الدليل، فهي مغلقةٌ عليه (404).
    """
    _refuse_wing_bound(request)
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)
    grade = request.GET.get("grade", "")
    track = request.GET.get("track", "")
    grades, tracks = services.grade_and_track_choices(school, year)
    data = services.achievement_overview(school, year, grade=grade, track=track)
    return render(
        request,
        "student_info/levels.html",
        {
            "year": year,
            "grade": grade,
            "track": track,
            "grades": grades,
            "tracks": tracks,
            "bands": services.ACHIEVEMENT_BANDS,
            "band_kpis": services.band_kpis(data["overall"]),
            "subtitle": f"{data['total']} نتيجةً مرصودة — {_ltr(year)}",
            "data": data,
        },
    )


# ── الملاحظات: شاشةٌ لكلّ جهة ─────────────────────────────────────────


@login_required
@capability_required("student_info.read")
def notes(request, category):
    """قائمةُ ملاحظاتِ جهةٍ واحدة — مقصورةً على الطلاب الذين يراهم صاحبُ الطلب.

    والمقيَّدُ بجناحه: طلبةُ جناحه بقيدهم الجاري، ولا تُفتح له خانتا الأخصائيَّين (404).
    """
    if category not in CATEGORY_LABELS:
        messages.error(request, "جهةٌ غير معروفة.")
        return redirect("student_info:sections")

    scope = student_scope_for(request)
    if scope.hides_specialist_notes and category in SPECIALIST_CATEGORIES:
        raise Http404("ليست من خانات جناحك")

    school = request.user.get_school()
    year = _year(request, scope)
    qs = StudentNote.objects.filter(
        school=school, category=category, academic_year=year
    ).select_related("student", "created_by")

    # التضييقُ قبل الفرز والعدّ والتقسيم: `paginator.count` وأثرُ التدقيق بعده.
    if scope.is_wing_bound:
        qs = scope.narrow(qs, "student_id")
    # الاستعلامُ عن الشُّعب المرئيّة لا يُدفع ثمنُه إلّا لمن يحتاجه
    elif not sees_whole_school(request.user):
        qs = qs.filter(
            student__enrollments__is_active=True,
            student__enrollments__class_group_id__in={
                g.id for g in visible_class_groups(request.user, school, year)
            },
        ).distinct()

    # الفرزُ قبل التقسيم: القائمةُ كلُّها تُرتَّب ثمّ تُقتطع صفحةٌ منها.
    qs, sort = apply_sort(qs, request, NOTE_SORTS, "date")
    page = Paginator(qs, 40).get_page(request.GET.get("page"))
    if category in SENSITIVE_CATEGORIES:
        AuditLog.log(
            user=request.user,
            action="view",
            model_name="StudentNote",
            object_repr=f"قائمة {CATEGORY_LABELS[category]} — {page.paginator.count} ملاحظة",
            changes={"categories": [category], "scope": "list"},
            request=request,
        )

    return render(
        request,
        "student_info/notes.html",
        {
            "category": category,
            "label": CATEGORY_LABELS[category],
            "page": page,
            "sort": sort,
            "year": year,
            "can_write": category in writable_categories(request.user),
        },
    )


@login_required
@capability_required("student_info.read")
@require_http_methods(["GET", "POST"])
def note_create(request, student_id):
    """كتابةُ ملاحظةٍ على طالب — في خانةِ جهتِه وحدها.

    والمقيَّدُ بجناحه: على طلبة جناحه وحدهم (404 لغيرهم في GET وPOST)، وفي العام الجاري
    مهما جاء في `?year=`.
    """
    school = request.user.get_school()
    scope = student_scope_for(request)
    scope.require_student(student_id)
    year = _year(request, scope)
    student = get_object_or_404(CustomUser, id=student_id, memberships__school=school)

    if not can_read_student(request.user, student, school, year, scope=scope):
        return _no_access(request)
    if not writable_categories(request.user):
        messages.error(request, "لا خانةَ تكتب فيها.")
        return redirect(reverse("student_info:student_file", args=[student.id]) + f"?year={year}")

    form = StudentNoteForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        note = form.save(commit=False)
        note.school = school
        note.student = student
        note.academic_year = year
        note.created_by = request.user
        note.updated_by = request.user
        note.save()
        messages.success(request, "أُضيفت الملاحظة.")
        return redirect(reverse("student_info:student_file", args=[student.id]) + f"?year={year}")

    return render(
        request,
        "student_info/note_form.html",
        {"form": form, "student": student, "year": year},
    )


# ── الأنشطة ───────────────────────────────────────────────────────────


@login_required
@capability_required("student_info.read")
def activities(request):
    """أنشطةُ الطلاب — من `StudentActivity` القائم، لا نموذجٍ ثانٍ يوازيه.

    والأنشطةُ ليست من مهامّ المشرف الإداريّ، فهي مغلقةٌ عليه (404).
    """
    from student_affairs.models import StudentActivity

    _refuse_wing_bound(request)
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)
    qs = StudentActivity.objects.filter(school=school, academic_year=year).select_related(
        "student", "recorded_by"
    )
    if not sees_whole_school(request.user):
        visible_ids = {g.id for g in visible_class_groups(request.user, school, year)}
        qs = qs.filter(
            student__enrollments__is_active=True,
            student__enrollments__class_group_id__in=visible_ids,
        ).distinct()

    qs, sort = apply_sort(qs, request, ACTIVITY_SORTS, "date")
    page = Paginator(qs, 40).get_page(request.GET.get("page"))
    return render(
        request,
        "student_info/activities.html",
        {"page": page, "sort": sort, "year": year},
    )
