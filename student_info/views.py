"""
شاشاتُ مركز معلومات الطلبة.

المدخلُ الشُّعبُ ثمّ الطالب، كما طلبت المدرسة: تفتح الشعبةَ فترى طلابها،
وتفتح الطالبَ فترى ملفّه كاملاً. والقوائمُ السبعُ في القائمة الرئيسيّة تفتح
كلٌّ منها شاشتَها مباشرةً لمن أراد النظرَ عرضاً لا طولاً.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from core.academic_calendar import academic_year_for
from core.models import AuditLog, CustomUser
from core.models.academic import ClassGroup
from core.permissions import role_required
from core.sorting import apply_sort
from student_info import services
from student_info.access import (
    MODULE_ROLES,
    can_read_student,
    visible_class_groups,
    writable_categories,
)
from student_info.forms import StudentNoteForm
from student_info.models import NOTE_CATEGORIES, SENSITIVE_CATEGORIES, StudentNote

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


def _no_access(request):
    messages.error(request, "هذا الطالب خارج نطاقك — لا تُعرض ملفّاتُ من لا تُدرّسهم.")
    return redirect("student_info:sections")


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
@role_required(MODULE_ROLES)
def sections(request):
    """الشُّعبُ — مدخلُ المركز."""
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)
    groups = services.sections_with_counts(visible_class_groups(request.user, school, year))
    return render(
        request,
        "student_info/sections.html",
        {"groups": groups, "year": year, "school": school},
    )


@login_required
@role_required(MODULE_ROLES)
def section_students(request, class_id):
    """طلابُ شعبةٍ واحدة."""
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)
    group = get_object_or_404(ClassGroup, id=class_id, school=school)
    if group.id not in {g.id for g in visible_class_groups(request.user, school, year)}:
        messages.error(request, "هذه الشعبة خارج نطاقك.")
        return redirect("student_info:sections")
    return render(
        request,
        "student_info/section_students.html",
        {
            "group": group,
            "enrollments": services.students_of_section(group),
            "year": year,
        },
    )


@login_required
@role_required(MODULE_ROLES)
def student_file(request, student_id):
    """ملفُّ الطالب الجامع: تحصيلُه، وملاحظاتُ الجهات الخمس، وأنشطتُه."""
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)
    student = get_object_or_404(CustomUser, id=student_id, memberships__school=school)

    if not can_read_student(request.user, student, school, year):
        return _no_access(request)

    grouped = services.notes_by_category(student, year)
    _audit_sensitive_read(request, student, [c for c, notes in grouped.items() if notes])

    return render(
        request,
        "student_info/student_file.html",
        {
            "student": student,
            "year": year,
            "class_group": services.current_class_group(student, year),
            "results": services.student_results(student, year),
            "average": services.student_average(student, year),
            "note_groups": [
                {"key": key, "label": CATEGORY_LABELS[key], "notes": grouped[key]}
                for key, _ in NOTE_CATEGORIES
            ],
            "activities": services.student_activities(student, year),
            "can_write": writable_categories(request.user),
        },
    )


# ── المستويات التعليمية وربطها بالتحصيل ──────────────────────────────


@login_required
@role_required(MODULE_ROLES)
def levels(request):
    """شرائحُ التحصيل: الإجمالُ، ولكلّ صفٍّ، ولكلّ مادّة — بمرشِّح الصفّ والمسار."""
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
            "data": data,
        },
    )


# ── الملاحظات: شاشةٌ لكلّ جهة ─────────────────────────────────────────


@login_required
@role_required(MODULE_ROLES)
def notes(request, category):
    """قائمةُ ملاحظاتِ جهةٍ واحدة — مقصورةً على الطلاب الذين يراهم صاحبُ الطلب."""
    if category not in CATEGORY_LABELS:
        messages.error(request, "جهةٌ غير معروفة.")
        return redirect("student_info:sections")

    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)
    qs = StudentNote.objects.filter(
        school=school, category=category, academic_year=year
    ).select_related("student", "created_by")

    # الاستعلامُ عن الشُّعب المرئيّة لا يُدفع ثمنُه إلّا لمن يحتاجه
    if not _sees_whole_school(request.user):
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


def _sees_whole_school(user):
    from student_info.access import SCHOOL_WIDE_READERS

    return user.is_superuser or user.get_role() in SCHOOL_WIDE_READERS


@login_required
@role_required(MODULE_ROLES)
@require_http_methods(["GET", "POST"])
def note_create(request, student_id):
    """كتابةُ ملاحظةٍ على طالب — في خانةِ جهتِه وحدها."""
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)
    student = get_object_or_404(CustomUser, id=student_id, memberships__school=school)

    if not can_read_student(request.user, student, school, year):
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
@role_required(MODULE_ROLES)
def activities(request):
    """أنشطةُ الطلاب — من `StudentActivity` القائم، لا نموذجٍ ثانٍ يوازيه."""
    from student_affairs.models import StudentActivity

    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)
    qs = StudentActivity.objects.filter(school=school, academic_year=year).select_related(
        "student", "recorded_by"
    )
    if not _sees_whole_school(request.user):
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
