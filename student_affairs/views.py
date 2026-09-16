"""
student_affairs/views.py — شؤون الطلاب
16 view — يتبع أنماط المشروع الموجودة بالضبط.
"""

import json
import logging
import os
from datetime import date, timedelta
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.formats import date_format
from django.views.decorators.http import require_POST

from core import brand
from core.academic_calendar import academic_year_for
from core.audit_export import log_export
from core.capabilities import capability_required, has_capability
from core.domain.attendance import attendance_rate, percent
from core.domain.tones import ATTENDANCE_SUMMARY, tone_for
from core.export_utils import (
    excel_to_response,
    generate_export_filename,
    get_export_context,
    get_pdf_footer_html,
    get_pdf_header_html,
    write_excel_table,
    xl_fill,
)
from core.labels import class_label
from core.models.academic import (
    ClassGroup,
    StudentEnrollment,
)
from core.models.access import Membership
from core.models.audit import AuditLog
from core.models.user import CustomUser
from core.pdf_utils import render_pdf
from core.privacy import mask_national_id
from core.sorting import apply_sort
from operations.absence_standing import standing_for
from operations.models import StudentAttendance
from operations.presence import presence_now
from operations.selectors import attendance_status_counts, pending_absence_alerts
from operations.tardiness import tardiness_now
from wings.scope import student_scope_for

from . import selectors
from .models import StudentActivity, StudentTransfer
from .services import TardinessService

logger = logging.getLogger(__name__)

# الأدوار المسموح لها بالوصول لشؤون الطلاب — مستوردة من core.permissions (MTG-2026-012)


# ═════════════════════════════════════════════════════════════════════
# لوحة شؤون الطلاب — الخطوة 3
# ═════════════════════════════════════════════════════════════════════


def _year_in_scope(request, scope) -> str:
    """العامُ المعروض — `?year=` لغير المقيَّد كما كان، والمقيَّدُ بجناحه على عامه الجاري.

    فالرابطُ لا يوسّع نطاقَ المشرف إلى شُعب عامٍ مضى (`StudentScope.year_for`). ويُقرأ
    العامُ الجاري بعد `?year=` لا قبله، فلا يزيد على القيادة استعلامٌ حين تمرّره.
    """
    requested = request.GET.get("year")
    if requested and not scope.is_wing_bound:
        return requested
    return scope.year_for(requested, scope.year or academic_year_for(request))


@login_required
# متابعةُ اليوم — الغائبون والمتأخّرون ومخالفاتُ اليوم — عملُ المشرف الإداريّ اليوميّ،
# فيفتحها بقدرة المتابعة ويرى فيها طلبةَ جناحه وحدَهم (قرارُ المستخدم 2026-09-14).
# و`limited` يُخفي في القالب عن المقيَّد روابطَ ما لا يفتحه — والحراسةُ على الشاشات.
@capability_required("student_affairs.follow_up")
def student_dashboard(request):
    """لوحة شؤون الطلاب — KPIs عبر Service Layer."""
    from .services import StudentService

    school = request.school
    today = timezone.localdate()
    scope = student_scope_for(request)
    year = _year_in_scope(request, scope)

    # ✅ v5.4: StudentService.get_dashboard_context — جميع queries في service layer
    ctx = StudentService.get_dashboard_context(school, year, today=today, scope=scope)
    att = ctx["today_attendance"]
    total_students = ctx["total_students"]
    absent_today = att["absent"] or 0
    late_today = att["late"] or 0
    behavior_today = ctx.get("today_behavior_count", 0)
    stage_map = ctx.get("stage_map", {})

    # ملاحظة: حُذفت أقسام "آخر المخالفات" / "آخر الانتقالات" / "التأخر الصباحي" /
    # "آخر الأنشطة" / "طلاب بدون ولي أمر" بطلب المدير — لا نمرّر context keys لها
    return render(
        request,
        "student_affairs/dashboard.html",
        {
            "today": today,
            "year": year,
            "current_school": school,
            "page_subtitle": _dated_subtitle(
                getattr(school, "name", ""), year, today, wing_bound=scope.is_wing_bound
            ),
            "limited": scope.is_wing_bound,
            "total_students": total_students,
            "absent_today": absent_today,
            "late_today": late_today,
            "today_behavior_count": behavior_today,
            # الجزء 1 — إحصائيات اليوم: المرحلتان تفصيلُ الإجمالي لا بطاقةٌ بسطرين.
            "stage_label": f"إعدادي {stage_map.get(2, 0)} · ثانوي {stage_map.get(3, 0)}",
            "qatari_label": f"{ctx.get('qatari_pct', 0)}%",
            "absent_label": f"{ctx.get('absent_pct', 0)}%",
            "late_label": f"{ctx.get('late_pct', 0)}%",
            # اللونُ يحمل التنبيه — والعددُ نفسُه في ترويسة قائمته، لا تحت النسبة.
            "absent_tone": "red" if absent_today else "green",
            "late_tone": "orange" if late_today else "green",
            "behavior_tone": "red" if behavior_today else "green",
            # الجزء 2 — القوائم اليومية
            "absent_list": ctx.get("absent_list", []),
            "late_list": ctx.get("late_list", []),
            "infraction_rows": [
                {
                    "student": inf.student.full_name,
                    "category": inf.violation_category.name_ar if inf.violation_category else "",
                    "level": inf.level,
                    # د1 نجاح، ود2–د3 تحذير، ود4 خطر — كما كانت في القالب.
                    "badge": _LEVEL_BADGE.get(inf.level, "status-danger"),
                }
                for inf in ctx.get("today_infraction_list", [])
            ],
            "grade_rows": _grade_share(ctx["grade_distribution"], total_students),
        },
    )


#: لونُ شارة درجة المخالفة — وما فوق الثالثة خطر.
_LEVEL_BADGE = {1: "status-success", 2: "status-warning", 3: "status-warning"}

_GRADE_NAMES = dict(ClassGroup.GRADES)


def _dated_subtitle(school_name: str, year: str, day, wing_bound: bool = False) -> str:
    """«المدرسة · 2026-2027 · التاريخ» — سطرُ الترويسة الوصفيّ.

    والمقيَّدُ بجناحه يُقال له ذلك في الترويسة: رقمٌ لجناحٍ يُقرأ رقماً للمدرسة إن سكت.
    """
    parts = [school_name or "المدرسة", "طلبة جناحك" if wing_bound else "", year]
    parts.append(date_format(day, "D، d M Y"))
    return " · ".join(part for part in parts if part)


def _grade_share(rows, total: int) -> list[dict]:
    """توزيعُ الطلاب على الصفوف: الاسمُ الوزاريّ، والعدد، ونصيبُه من الكلّ."""
    return [
        {
            "label": _GRADE_NAMES.get(row["class_group__grade"], row["class_group__grade"]),
            "count": row["count"],
            "pct": round(row["count"] * 100 / total) if total else 0,
        }
        for row in rows
    ]


def _share_tone(pct) -> tuple[str, str]:
    """(لونُ البطاقة، صنفُ الشارة) لنسبة حضور — سُلَّمُ الحضور الواحد: 90 · 75."""
    return tone_for(pct, ATTENDANCE_SUMMARY, empty=("muted", "status-gray"))


#: نسبةُ المخالفين في بطاقة الرقم: 25% فأكثر أحمر، و10% فأكثر برتقاليّ، ودونها أخضر.
INFRACTION_SHARE_KPI = ((25, "red"), (10, "orange"), (None, "green"))
#: مخالفاتُ اليوم: خمسٌ فأكثر أحمر، وواحدةٌ برتقاليّ، ولا شيءَ أخضر.
TODAY_INFRACTIONS_KPI = ((5, "red"), (1, "orange"), (None, "green"))
#: غيرُ المحلولة: عشرٌ فأكثر أحمر، وواحدةٌ برتقاليّ، ولا شيءَ أخضر.
UNRESOLVED_KPI = ((10, "red"), (1, "orange"), (None, "green"))


# ═════════════════════════════════════════════════════════════════════
# سجل الطلاب — الخطوة 4
# ═════════════════════════════════════════════════════════════════════


#: صفحةُ السجلّ — كصفحة سجلّ الكادر، فلا يختلف إيقاعُ الشاشتين على قارئهما.
STUDENT_PAGE_SIZE = 50

#: مفاتيحُ الفرز المصرَّحة. و`?sort=` نصٌّ من المستخدم فلا يبلغ `order_by`
#: إلّا عبر هذه القائمة. وكلُّها تنتهي بالاسم فاصلاً يقطع التساوي.
STUDENT_SORTS = {
    "name": ("name_key",),
    "national": ("national_key", "name_key"),
    # الصفُّ والشعبةُ عمودٌ واحدٌ يُعرض، فمفتاحُهما واحدٌ يُفرَز.
    "class": ("grade_key", "section_key", "name_key"),
    "guardian": ("guardian_key", "name_key"),
}


#: حالاتُ السجلّ في ترشيح القيد — المقيَّدون افتراضاً.
STUDENT_STATUSES = (
    ("enrolled", "مقيَّدون هذا العام"),
    ("unenrolled", "بلا قيدٍ نشط"),
    ("all", "الكلّ"),
)
#: والمقيَّدُ بجناحه لا يرى إلّا المقيَّدين: طالبٌ بلا قيدٍ نشطٍ لا جناحَ له،
#: فـ`all` و`unenrolled` لا تفتحان له المدرسة.
WING_STUDENT_STATUSES = STUDENT_STATUSES[:1]


def _student_row(m, relations: dict[str, str]) -> dict:
    """صفُّ السجلّ كما يُعرض — من عضويّةٍ معلَّمةٍ بـ`selectors.student_register`."""
    return {
        "id": m.user_id,
        "full_name": m.user.full_name,
        # آخرُ أربعِ خاناتٍ وما قبلها مستور: القارئُ يحتاج أن يميّز لا أن
        # يعرف، والرقمُ كاملاً في ملفّ صاحبه لمن فتحه بقصد.
        "national_id": mask_national_id(m.user.national_id),
        # «07/2» كما تكتبه الوزارة — عمودٌ واحدٌ لا عمودان، ورقمُ الصفّ
        # بلا حرفٍ وبخانتين، فيطابق ما في يد القارئ من كشوف.
        "class_label": class_label(m.grade_code, m.section_code),
        "guardian_name": m.guardian_name or "",
        "guardian_phone": m.guardian_phone or "",
        "guardian_relation": relations.get(m.guardian_relation, ""),
        "can_sign_in": m.user.is_active and m.user.has_usable_password(),
    }


@login_required
# قائمةٌ تُقرأ ولا تُكتب — فحارسُها `VIEW` لا `MANAGE`. والمجموعتان مفصولتان
# أصلاً في `core/permissions.py` بقرار MTG-2026-012: المنسّقُ والأخصائيّان
# يرون الطلبة ولا يبتّون في قيدهم. وكانت القائمةُ تعرض الشاشةَ للمنسّق
# ويردُّه حارسُها — إذنٌ مكتوبٌ في موضعٍ وممنوعٌ في آخر.
@capability_required("student_affairs.view")
def student_list(request):
    """قائمة الطلاب مع بحث وفلتر حسب الصف والشعبة — الاستعلامُ في `selectors.student_register`.

    والمشرفُ الإداريُّ يقرؤها لطلبة جناحه وحدَهم (قرارُ المستخدم 2026-09-14): النطاقُ
    يُطبَّق على الاستعلام الأساسيّ **قبل** كلّ مرشِّحٍ وفرزٍ وترقيم.
    """
    school = request.school
    scope = student_scope_for(request)
    year = _year_in_scope(request, scope)
    q = request.GET.get("q", "").strip()
    grade_filter = request.GET.get("grade", "")
    section_filter = request.GET.get("section", "")
    parent_status = request.GET.get("parent_status", "")
    status = "enrolled" if scope.is_wing_bound else (request.GET.get("status") or "enrolled")

    students = selectors.student_register(
        school,
        year,
        grade=grade_filter,
        section=section_filter,
        parent_status=parent_status,
        status=status,
        q=q,
        scope=scope,
    )
    students, sort = apply_sort(students, request, allowed=STUDENT_SORTS, default="name")
    paginator = Paginator(students, STUDENT_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))
    relations = selectors.guardian_relation_labels()
    grades, sections = selectors.register_filter_options(school, year, scope)

    ctx = {
        "students": [_student_row(m, relations) for m in page_obj],
        # وكان العددُ عددَ الصفّ المعروض، فتقول الترويسةُ «200 طالب مسجّل»
        # لمدرسةٍ فيها سبعُمئةٍ وخمسةٌ وثلاثون. العددُ عددُ السجلّ.
        "total": paginator.count,
        "page_obj": page_obj,
        "sort": sort,
        "status": status,
        "statuses": WING_STUDENT_STATUSES if scope.is_wing_bound else STUDENT_STATUSES,
        "q": q,
        "grade_filter": grade_filter,
        "section_filter": section_filter,
        "parent_status": parent_status,
        "grades": grades,
        "sections": sections,
        "year": year,
        "page_subtitle": f"{year} · طلبة جناحك" if scope.is_wing_bound else year,
        # القالبُ يُخفي عن المقيَّد روابطَ ما لا يفتحه، وزرَّ «تعديل» — والحراسةُ على الشاشات.
        "limited": scope.is_wing_bound,
        "can_edit": _profile_actions(request.user, scope)["can_edit"],
    }

    # HTMX: إرجاع الجدول فقط
    if request.headers.get("HX-Request"):
        return render(request, "student_affairs/_student_table.html", ctx)
    return render(request, "student_affairs/student_list.html", ctx)


@login_required
@capability_required("student_affairs.manage")
def student_table_partial(request):
    """HTMX partial — يُعيد التوجيه لـ student_list مع نفس المعاملات."""
    return student_list(request)


# ═════════════════════════════════════════════════════════════════════
# تصدير Excel
# ═════════════════════════════════════════════════════════════════════


def _sheet(ws, title: str):
    """ورقةُ Excel بعنوانها ومن اليمين إلى اليسار."""
    ws.title = title
    ws.sheet_view.rightToLeft = True
    return ws


@login_required
@capability_required("student_affairs.manage")
def student_export_excel(request):
    """تصدير قائمة الطلاب إلى Excel — مع هيدر وفوتر احترافي."""
    import openpyxl

    school = request.school
    year = academic_year_for(request)
    students = selectors.students_for_export(
        school,
        year,
        q=request.GET.get("q", "").strip(),
        grade=request.GET.get("grade", ""),
        section=request.GET.get("section", ""),
    )

    wb = openpyxl.Workbook()
    # الرقم الشخصيّ: مستور — سجلُّ الطلبة كشفٌ جماعيّ لا يعود بالاستيراد
    # (قالبُ الاستيراد في `core.views_students`).
    rows = write_excel_table(
        _sheet(wb.active, "سجل الطلاب"),
        get_export_context(request, "سجل الطلاب"),
        ["#", "الاسم الكامل", "الرقم الشخصي", "الصف", "الشعبة", "الجوال", "البريد"],
        (
            [
                i,
                m.user.full_name,
                mask_national_id(m.user.national_id),
                enrolment.get("class_group__grade", "—"),
                enrolment.get("class_group__section", "—"),
                m.user.phone or "—",
                m.user.email or "—",
            ]
            for i, (m, enrolment) in enumerate(students, 1)
        ),
    )

    log_export(
        request,
        "student_affairs.students_xlsx",
        rows=rows,
        full_national_id=False,
        object_repr=f"سجل الطلاب Excel — {year}",
    )
    return excel_to_response(wb, generate_export_filename("students", "list", "xlsx"))


# ═════════════════════════════════════════════════════════════════════
# إضافة / تعديل / تعطيل — الخطوات 5 + 7
# ═════════════════════════════════════════════════════════════════════


@login_required
@capability_required("student_affairs.manage")
def student_add(request):
    """
    إضافة طالب جديد — مُفوَّض لـ StudentService.create_student().
    الـ View مسؤول فقط عن: قراءة الطلب + تحويل النموذج + عرض النتيجة.
    منطق إنشاء 4 السجلات (User + Profile + Membership + Enrollment) في Service Layer.
    """
    from .forms import StudentAddForm
    from .services import StudentService

    school = request.school
    year = academic_year_for(request)

    if request.method == "POST":
        form = StudentAddForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data

            # ── تحديد الشعبة (المطلوب للـ Service) ──
            class_group = ClassGroup.objects.filter(
                school=school,
                grade=cd["grade"],
                section=cd["section"],
                academic_year=year,
                is_active=True,
            ).first()
            if not class_group:
                messages.error(
                    request,
                    f"لا توجد شعبة {cd['section']} في الصف {cd['grade']} للعام {year}.",
                )
                return render(
                    request,
                    "student_affairs/student_form.html",
                    {
                        "form": form,
                        "mode": "add",
                        "year": year,
                        "grades": ClassGroup.GRADES,
                        "school": school,
                    },
                )

            # ── تفويض الإنشاء للـ Service Layer ──
            try:
                user = StudentService.create_student(
                    school,
                    {
                        "national_id": cd["national_id"],
                        "full_name": cd["full_name"],
                        "phone": cd.get("phone", ""),
                        "email": cd.get("email", ""),
                        "gender": cd.get("gender", ""),
                        "birth_date": cd.get("birth_date"),
                        "nationality": cd.get("nationality", ""),
                        "class_group_id": class_group.pk,
                    },
                )
                messages.success(
                    request,
                    f"تم إضافة الطالب {user.full_name} في "
                    f"{class_group.grade}/{class_group.section} بنجاح.",
                )
                return redirect("student_affairs:student_profile", student_id=user.id)

            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"خطأ غير متوقع أثناء إضافة الطالب: {e}")
    else:
        form = StudentAddForm()

    return render(
        request,
        "student_affairs/student_form.html",
        {
            "form": form,
            "mode": "add",
            "year": year,
            "grades": ClassGroup.GRADES,
            "school": school,
        },
    )


@login_required
@capability_required("student_affairs.manage")
def student_edit(request, student_id):
    """تعديل بيانات طالب موجود."""
    school = request.school
    student = get_object_or_404(
        CustomUser,
        id=student_id,
        memberships__school=school,
        memberships__is_active=True,
    )
    year = academic_year_for(request)
    profile = getattr(student, "profile", None)
    enrollment = (
        StudentEnrollment.objects.filter(
            student=student,
            class_group__academic_year=year,
            is_active=True,
        )
        .select_related("class_group")
        .first()
    )

    from .forms import StudentEditForm

    if request.method == "POST":
        form = StudentEditForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            from .services import StudentService

            # ── تفويض التحديث للـ Service Layer (ذرّي) ──
            try:
                StudentService.update_student(
                    student,
                    school,
                    {
                        "full_name": cd["full_name"],
                        "phone": cd.get("phone", ""),
                        "email": cd.get("email", ""),
                        "birth_date": cd.get("birth_date"),
                        "notes": cd.get("notes", ""),
                        "grade": cd["grade"],
                        "section": cd["section"],
                    },
                )
                messages.success(request, f"تم تحديث بيانات {student.full_name} بنجاح.")
                return redirect("student_affairs:student_profile", student_id=student.id)
            except ValueError as e:
                messages.error(request, str(e))
            except Exception:
                logger.exception("خطأ غير متوقع أثناء تحديث الطالب %s", student_id)
                messages.error(request, "حدث خطأ غير متوقع أثناء التحديث.")
    else:
        form = StudentEditForm(
            initial={
                "full_name": student.full_name,
                "phone": student.phone,
                "email": student.email,
                "grade": enrollment.class_group.grade if enrollment else "",
                "section": enrollment.class_group.section if enrollment else "",
                "birth_date": profile.birth_date if profile else None,
                "notes": profile.notes if profile else "",
            }
        )

    return render(
        request,
        "student_affairs/student_form.html",
        {
            "form": form,
            "mode": "edit",
            "student": student,
            "year": year,
            "grades": ClassGroup.GRADES,
            "school": school,
        },
    )


@login_required
@capability_required("student_affairs.deactivate")
@require_POST
def student_deactivate(request, student_id):
    """
    تعطيل طالب — مُفوَّض لـ StudentService.deactivate_student().
    is_active=False فقط — لا حذف فيزيائي (PDPPL: حفظ السجل التاريخي).
    """
    from .services import StudentService

    school = request.school
    student = get_object_or_404(
        CustomUser,
        id=student_id,
        memberships__school=school,
        memberships__is_active=True,
    )

    StudentService.deactivate_student(
        student=student,
        school=school,
        user=request.user,
    )

    messages.success(request, f"تم تعطيل الطالب {student.full_name}. البيانات محفوظة ولم تُحذف.")
    return redirect("student_affairs:student_list")


# ═════════════════════════════════════════════════════════════════════
# ملف الطالب الشامل — الخطوة 6
# ═════════════════════════════════════════════════════════════════════


def _profile_subtitle(student, profile, enrollment) -> str:
    """سطرُ ترويسة ملفّ الطالب: الصفّ · ذيلُ الرقم المستور · الجنس."""
    parts = []
    if enrollment:
        parts.append(class_label(enrollment.class_group.grade, enrollment.class_group.section))
    if student.national_id:
        parts.append(f"****{mask_national_id(student.national_id)[-4:]}")
    if profile and profile.gender:
        parts.append("ذكر" if profile.gender == "M" else "أنثى")
    return " · ".join(parts)


def _profile_actions(user, scope) -> dict:
    """أزرارُ ملفّ الطالب ذواتُ المعرّف — `can_open` لا يقرأ رابطاً بوسائط.

    غيرُ المقيَّد يرى الأزرارَ كما كانت حرفاً؛ والمقيَّدُ بجناحه يُعرض له منها ما
    يفتحه حارسُه وحدَه. والحراسةُ على الشاشات نفسِها لا هنا.
    """
    if not scope.is_wing_bound:
        return {"can_edit": True, "can_summon": True, "can_see_results": True}
    return {
        "can_edit": has_capability(user, "student_affairs.manage"),
        "can_summon": has_capability(user, "behavior.summon_parent"),
        "can_see_results": not scope.hides_grades and has_capability(user, "reports.results"),
    }


@login_required
# كلُّ قائمةٍ في شؤون الطلبة تنتهي إلى هذا الملفّ، فالفحصُ عنده هو الحارسُ الحقيقيّ:
# المشرفُ الإداريُّ يفتحه لطالبٍ من جناحه وحدَه، وغيرُه 404 لا يُميَّز عن غير الموجود.
@capability_required("student_affairs.follow_up")
def student_profile(request, student_id):
    """ملف الطالب الشامل — يجمع بيانات من 7 تطبيقات (`selectors.student_profile_records`).

    وللمقيَّد بجناحه (قرارُ المستخدم 2026-09-15) لا تُحسب ولا تُعرض: الدرجاتُ،
    وفصيلةُ الدم وأسبابُ زيارات العيادة، والإعاراتُ، والأنشطةُ، والانتقالات.
    """
    school = request.school
    scope = student_scope_for(request)
    # قبل جلب الطالب، وعلى العام الجاري لا على `?year=`.
    scope.require_student(student_id)
    student = get_object_or_404(
        CustomUser,
        id=student_id,
        memberships__school=school,
        memberships__is_active=True,
    )
    year = _year_in_scope(request, scope)
    profile = getattr(student, "profile", None)
    records = selectors.student_profile_records(student, school, year, scope)
    enrollment = records["enrollment"]
    attendance = records["attendance"]

    return render(
        request,
        "student_affairs/student_profile.html",
        {
            **records,
            # ما يُرسم: سطرُ الترويسة ولونُ الحضور (90 · 75 — عتبتا القالب).
            "profile_subtitle": _profile_subtitle(student, profile, enrollment),
            "attendance_label": f"{attendance['pct']}%",
            "attendance_sub": f"من {attendance['total']} حصة",
            "attendance_tone": _share_tone(attendance["pct"])[0],
            "subjects_sub": f"ناجح {records['grades_summary'].get('passed') or 0}",
            "student": student,
            "profile": profile,
            # موقفُه من عتبات الغياب (سياسة تقييم الطلبة) — عرضٌ محض: كم يوماً،
            # وأيّ عتبةٍ قادمة، وكم يفصله عنها. لا حجبَ ولا إشعار.
            "absence_standing": standing_for(
                student, school, grade=enrollment.class_group.grade if enrollment else None
            ),
            # عدّادا التأخّر عن الحصص — مرّاتٍ ودقائق، للفصل والعام وبالمادّة.
            "tardiness": tardiness_now(student, school),
            # دقائقُ الحضور الفعليّ بالمادّة — ما يُقارَن بالتحصيل (قرارُ 2026-09-13).
            "presence": presence_now(student, school),
            "year": year,
            # القالبُ يُخفي ولا يحرس: الأقسامُ المحجوبةُ لم تُحسب أصلاً.
            "limited": scope.is_wing_bound,
            **_profile_actions(request.user, scope),
        },
    )


# ═════════════════════════════════════════════════════════════════════
# الانتقالات — الخطوة 8
# ═════════════════════════════════════════════════════════════════════


@login_required
@capability_required("student_affairs.manage")
def transfer_list(request):
    """قائمة الانتقالات مع فلتر حسب الحالة والاتجاه."""
    school = request.school
    transfers = (
        StudentTransfer.objects.filter(school=school)
        .select_related("student")
        .order_by("-created_at")
    )

    status_filter = request.GET.get("status", "")
    direction_filter = request.GET.get("direction", "")
    if status_filter:
        transfers = transfers.filter(status=status_filter)
    if direction_filter:
        transfers = transfers.filter(direction=direction_filter)

    return render(
        request,
        "student_affairs/transfer_list.html",
        {
            "transfers": transfers[:100],
            "status_filter": status_filter,
            "direction_filter": direction_filter,
            "status_choices": StudentTransfer.STATUS_CHOICES,
            "direction_choices": StudentTransfer.DIRECTION_CHOICES,
        },
    )


@login_required
@capability_required("student_affairs.manage")
def transfer_create(request):
    """تسجيل طلب انتقال جديد."""
    school = request.school

    from .forms import TransferForm

    if request.method == "POST":
        form = TransferForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            student = get_object_or_404(
                CustomUser,
                id=cd["student_id"],
                memberships__school=school,
                memberships__is_active=True,
            )
            StudentTransfer.objects.create(
                school=school,
                student=student,
                direction=cd["direction"],
                other_school_name=cd["other_school_name"],
                from_grade=cd.get("from_grade", ""),
                to_grade=cd.get("to_grade", ""),
                transfer_date=cd["transfer_date"],
                reason=cd.get("reason", ""),
                academic_year=academic_year_for(request),
                created_by=request.user,
                updated_by=request.user,
            )
            messages.success(request, f"تم تسجيل طلب انتقال {student.full_name} بنجاح.")
            return redirect("student_affairs:transfer_list")
    else:
        form = TransferForm()

    # قائمة الطلاب للاختيار
    students = (
        Membership.objects.filter(school=school, role__name="student", is_active=True)
        .select_related("user")
        .order_by("user__full_name")
    )
    return render(
        request,
        "student_affairs/transfer_form.html",
        {
            "form": form,
            "students": students,
        },
    )


@login_required
@capability_required("student_affairs.manage")
def transfer_detail(request, pk):
    """تفاصيل طلب انتقال."""
    school = request.school
    transfer = get_object_or_404(StudentTransfer, pk=pk, school=school)
    return render(
        request,
        "student_affairs/transfer_detail.html",
        {
            "transfer": transfer,
            "page_subtitle": f"{transfer.student.full_name} — {transfer.get_direction_display()}",
        },
    )


@login_required
@capability_required("student_affairs.manage")
@require_POST
def transfer_review(request, pk):
    """مراجعة طلب انتقال — موافقة / رفض / إتمام."""
    school = request.school
    transfer = get_object_or_404(StudentTransfer, pk=pk, school=school)

    from .forms import TransferReviewForm

    form = TransferReviewForm(request.POST)
    if form.is_valid():
        action = form.cleaned_data["action"]
        notes = form.cleaned_data.get("notes", "")

        transfer.status = action
        transfer.notes = notes
        transfer.updated_by = request.user
        transfer.save()

        # إذا اكتمل الانتقال الصادر → تعطيل الطالب
        if action == "completed" and transfer.direction == "out":
            Membership.objects.filter(
                user=transfer.student,
                school=school,
                role__name="student",
                is_active=True,
            ).update(is_active=False)
            StudentEnrollment.objects.filter(
                student=transfer.student,
                class_group__school=school,
                is_active=True,
            ).update(is_active=False)

        status_label = dict(StudentTransfer.STATUS_CHOICES).get(action, action)
        messages.success(request, f"تم تحديث حالة الانتقال إلى: {status_label}")

    return redirect("student_affairs:transfer_detail", pk=pk)


# ═════════════════════════════════════════════════════════════════════
# الحضور والسلوك (ملخصات)
# ═════════════════════════════════════════════════════════════════════


def _followup_scope(request):
    """نطاقُ صاحب الطلب في شاشات المتابعة: المدرسةُ للقيادة، وشُعبُ جناحه للمشرف.

    `wings.scope.student_scope_for` وحدَها تجيب، وتُحسب مرّةً للطلب. وكلُّ قراءةٍ
    في هذه الشاشات تمرّ على النطاق قبل المرشِّحات والعدّ والاقتطاع والتصدير —
    وغيرُ المقيَّد يُعاد له استعلامُه كما هو بلا استعلامٍ زائد.
    """
    return student_scope_for(request)


def _followup_wing_label(scope) -> str:
    """«جناح 1، جناح 2» للمقيَّد بجناحه — ولا شيءَ لغيره فتبقى عناوينُ القيادة حرفاً.

    ملفٌّ صُدِّر من جناحٍ لا يُقرأ بعد أسبوعٍ على أنّه المدرسةُ كلُّها.
    """
    if not scope.is_wing_bound:
        return ""
    return "، ".join(selectors.wing_names(scope.wing_ids or ())) or "بلا جناح"


def _with_wing(text: str, wing: str) -> str:
    return f"{text} — {wing}" if wing else text


def _attendance_summary(counts: dict) -> dict:
    """ملخّصُ حضور اليوم بمفاتيح القالبين — والنسبةُ من `core.domain.attendance`."""
    return {
        "present": counts["present"],
        "absent": counts["absent"],
        "late": counts["late"],
        "excused": counts["excused"],
        "total": counts["total"],
        "pct": attendance_rate(counts["present"], counts["total"]),
    }


def _absence_badge(days: int) -> str:
    """الغيابُ المتكرّر: عشرةُ أيّامٍ فأكثر خطر، وخمسةٌ تحذير — عتبتا القالب."""
    return "status-danger" if days >= 10 else "status-warning" if days >= 5 else "status-info"


def _grade_attendance_row(row: dict) -> dict:
    grade = row["session__class_group__grade"]
    pct = attendance_rate(row["present_count"], row["total"])
    return {
        **row,
        "label": _GRADE_NAMES.get(grade, grade),
        "pct": pct,
        "badge": _share_tone(pct)[1],
    }


@login_required
@capability_required("student_affairs.follow_up")
def attendance_overview(request):
    """إحصائيات الحضور والغياب — شاملة مع Trends."""
    school = request.school
    today = timezone.localdate()
    scope = _followup_scope(request)
    summary = _attendance_summary(
        attendance_status_counts(school, scope=scope, session__date=today)
    )
    ranking = selectors.absence_ranking(
        school, today - timedelta(days=30), "student__id", "student__full_name", scope=scope
    )[:20]
    trend = selectors.daily_attendance_trend(school, today, scope=scope)

    return render(
        request,
        "student_affairs/attendance_overview.html",
        {
            "summary": summary,
            "today": today,
            # المقيَّدُ على العام الجاري دائماً — `?year=` لا يوسّع نطاقَه؛ وغيرُه كما كان.
            "year": scope.year_for(request.GET.get("year"), "") or academic_year_for(request),
            "page_subtitle": _with_wing(
                f"ملخص الحضور والغياب — {date_format(today, 'D، d M Y')}",
                _followup_wing_label(scope),
            ),
            "wing_bound": scope.is_wing_bound,
            # ما يُرسم: الألوانُ بعتباتها هنا لا شروطاً في القالب.
            "pct_label": f"{summary['pct']}%",
            "pct_tone": _share_tone(summary["pct"])[0],
            "worst_students": [
                {**row, "badge": _absence_badge(row["absence_count"])} for row in ranking
            ],
            "class_breakdown": [
                _grade_attendance_row(row)
                for row in selectors.attendance_by_grade_on(school, today, scope)
            ],
            "chart_labels_json": json.dumps(trend.labels),
            "chart_present_json": json.dumps(trend.present),
            "chart_absent_json": json.dumps(trend.absent),
            "alerts": pending_absence_alerts(school, scope=scope),
            "grades": ClassGroup.GRADES,
            "grade_filter": request.GET.get("grade", ""),
        },
    )


def _status_fill(status: str):
    """الغائبُ بخلفيّة الخطر والمتأخّرُ بخلفيّة التحذير — وما سواهما بتناوب الجدول."""
    if status == "absent":
        return xl_fill(brand.STATUS_DANGER_BG)
    if status == "late":
        return xl_fill(brand.STATUS_WARNING_BG)
    return None


#: حقولُ ورقة «الغياب المتكرّر» في التصدير — الاسمُ والرقمُ (يُستر عند الكتابة).
_ABSENCE_EXPORT_FIELDS = ("student__full_name", "student__national_id")

ATTENDANCE_STATUS_AR = {"present": "حاضر", "absent": "غائب", "late": "متأخر", "excused": "معذور"}


@login_required
@capability_required("student_affairs.follow_up")
def attendance_export_excel(request):
    """تصدير إحصائيات الغياب — أكثر الطلاب غياباً (آخر 30 يوم) + حضور اليوم."""
    import openpyxl

    school = request.school
    today = timezone.localdate()
    scope = _followup_scope(request)
    wing = _followup_wing_label(scope)
    ctx = get_export_context(request, _with_wing("تقرير الحضور والغياب", wing))
    wb = openpyxl.Workbook()

    # ── الغيابُ المتكرّر ── الرقم الشخصيّ: مستور — إحصاءُ غيابٍ كشفٌ جماعيّ.
    absences = selectors.absence_ranking(
        school, today - timedelta(days=30), *_ABSENCE_EXPORT_FIELDS, scope=scope
    )
    absent_rows = write_excel_table(
        _sheet(wb.active, "الغياب المتكرر"),
        ctx,
        ["#", "اسم الطالب", "الرقم الشخصي", "أيام الغياب (30 يوم)"],
        (
            [
                i,
                r["student__full_name"],
                mask_national_id(r["student__national_id"]),
                r["absence_count"],
            ]
            for i, r in enumerate(absences, 1)
        ),
    )

    # ── سجلُّ حضور اليوم ──
    records = list(selectors.attendance_on_by_class(school, today, scope))
    today_rows = write_excel_table(
        _sheet(wb.create_sheet(), "حضور اليوم"),
        ctx,
        ["#", "اسم الطالب", "الصف", "الشعبة", "الحالة"],
        (
            [
                i,
                rec.student.full_name,
                rec.session.class_group.grade,
                rec.session.class_group.section,
                ATTENDANCE_STATUS_AR.get(rec.status, rec.status),
            ]
            for i, rec in enumerate(records, 1)
        ),
        fill_for=lambda i, _values: _status_fill(records[i - 1].status),
    )

    log_export(
        request,
        "student_affairs.attendance_xlsx",
        rows=absent_rows + today_rows,
        full_national_id=False,
        object_repr=_with_wing(f"إحصائيات الغياب Excel — {today:%Y-%m-%d}", wing),
    )
    return excel_to_response(wb, generate_export_filename("attendance", "stats", "xlsx"))


#: درجاتُ المخالفة بعناوينها في بطاقة التوزيع.
DEGREE_LABELS = (
    (1, "الدرجة 1 — تحذير"),
    (2, "الدرجة 2 — إنذار"),
    (3, "الدرجة 3 — خطيرة"),
    (4, "الدرجة 4 — جسيمة"),
)

#: ما يُعرض من ملخّص السلوك كما حسبه `selectors.behaviour_year_summary`.
_BEHAVIOUR_KEYS = (
    "total_infractions",
    "unresolved",
    "students_with_infractions",
    "total_students",
    "infraction_pct",
    "worst_students",
)


@login_required
@capability_required("student_affairs.follow_up")
def behavior_overview(request):
    """ملخص سلوك الطلاب — إحصائيات شاملة."""
    school = request.school
    today = timezone.localdate()
    scope = _followup_scope(request)
    # كلُّ مخالفةٍ تُعدّ هنا — للعام وللرسم — تمرّ على النطاق أوّلاً.
    summary = selectors.behaviour_year_summary(school, today, scope)
    degree_map = {degree: {"count": count} for degree, count in summary["degree_counts"]}
    today_infractions = summary["year_infractions"].filter(date=today).count()
    chart_labels, chart_data = selectors.monthly_infraction_trend(school, today, scope=scope)

    return render(
        request,
        "student_affairs/behavior_overview.html",
        {
            **{key: summary[key] for key in _BEHAVIOUR_KEYS},
            "pct_label": f"{summary['infraction_pct']}%",
            "offenders_label": f"{summary['students_with_infractions']} من {summary['total_students']}",
            # ألوانُ البطاقات بعتباتها التي كانت في القالب: نسبةُ المخالفين دون 10%
            # أخضر ودون 25% برتقاليّ؛ ومخالفاتُ اليوم وغيرُ المحلولة صفرٌ أخضر.
            "pct_tone": tone_for(summary["infraction_pct"], INFRACTION_SHARE_KPI),
            "today_tone": tone_for(today_infractions, TODAY_INFRACTIONS_KPI),
            "unresolved_tone": tone_for(summary["unresolved"], UNRESOLVED_KPI),
            "degree_rows": [
                (label, degree_map.get(degree, {}).get("count", 0))
                for degree, label in DEGREE_LABELS
            ],
            "today": today,
            "today_infractions": today_infractions,
            "degree_map": degree_map,
            "chart_labels_json": json.dumps(chart_labels),
            "chart_data_json": json.dumps(chart_data),
            "grades": ClassGroup.GRADES,
            "grade_filter": request.GET.get("grade", ""),
            "wing_bound": scope.is_wing_bound,
            # الشهرُ واسمُ الجناح للمقيَّد؛ والقيادةُ على الشهر وحدَه كما يرسمه القالب.
            "wing_subtitle": _with_wing(date_format(today, "F Y"), _followup_wing_label(scope))
            if scope.is_wing_bound
            else "",
        },
    )


# ═════════════════════════════════════════════════════════════════════
# الأنشطة والإنجازات — الخطوة 9
# ═════════════════════════════════════════════════════════════════════


@login_required
@capability_required("student_affairs.activities")
def activity_list(request):
    """قائمة الأنشطة والإنجازات مع فلتر."""
    school = request.school
    year = request.GET.get("year") or academic_year_for(request)
    activities = (
        StudentActivity.objects.filter(school=school, academic_year=year)
        .select_related("student")
        .order_by("-date")
    )

    type_filter = request.GET.get("type", "")
    scope_filter = request.GET.get("scope", "")
    if type_filter:
        activities = activities.filter(activity_type=type_filter)
    if scope_filter:
        activities = activities.filter(scope=scope_filter)

    return render(
        request,
        "student_affairs/activity_list.html",
        {
            "activities": activities[:200],
            "type_filter": type_filter,
            "scope_filter": scope_filter,
            "type_choices": StudentActivity.TYPE_CHOICES,
            "scope_choices": StudentActivity.SCOPE_CHOICES,
            "year": year,
        },
    )


@login_required
@capability_required("student_affairs.activities")
def activity_add(request):
    """تسجيل نشاط أو إنجاز جديد."""
    school = request.school

    from .forms import ActivityForm

    if request.method == "POST":
        form = ActivityForm(request.POST, request.FILES)
        if form.is_valid():
            cd = form.cleaned_data
            student = get_object_or_404(
                CustomUser,
                id=cd["student_id"],
                memberships__school=school,
                memberships__is_active=True,
            )
            StudentActivity.objects.create(
                school=school,
                student=student,
                activity_type=cd["activity_type"],
                title=cd["title"],
                description=cd.get("description", ""),
                scope=cd["scope"],
                date=cd["date"],
                academic_year=academic_year_for(request),
                recorded_by=request.user,
                attachment=cd.get("attachment"),
            )
            messages.success(
                request, f"تم تسجيل النشاط «{cd['title']}» للطالب {student.full_name}."
            )
            return redirect("student_affairs:activity_list")
    else:
        form = ActivityForm()

    students = (
        Membership.objects.filter(school=school, role__name="student", is_active=True)
        .select_related("user")
        .order_by("user__full_name")
    )
    return render(
        request,
        "student_affairs/activity_form.html",
        {
            "form": form,
            "students": students,
            "mode": "add",
        },
    )


@login_required
@capability_required("student_affairs.activities")
def activity_edit(request, pk):
    """تعديل نشاط."""
    school = request.school
    activity = get_object_or_404(StudentActivity, pk=pk, school=school)

    from .forms import ActivityForm

    if request.method == "POST":
        form = ActivityForm(request.POST, request.FILES)
        if form.is_valid():
            cd = form.cleaned_data
            activity.activity_type = cd["activity_type"]
            activity.title = cd["title"]
            activity.description = cd.get("description", "")
            activity.scope = cd["scope"]
            activity.date = cd["date"]
            if cd.get("attachment"):
                activity.attachment = cd["attachment"]
            activity.save()
            messages.success(request, f"تم تحديث النشاط «{activity.title}».")
            return redirect("student_affairs:activity_list")
    else:
        form = ActivityForm(
            initial={
                "student_id": activity.student_id,
                "activity_type": activity.activity_type,
                "title": activity.title,
                "description": activity.description,
                "scope": activity.scope,
                "date": activity.date,
            }
        )

    students = (
        Membership.objects.filter(school=school, role__name="student", is_active=True)
        .select_related("user")
        .order_by("user__full_name")
    )
    return render(
        request,
        "student_affairs/activity_form.html",
        {
            "form": form,
            "students": students,
            "mode": "edit",
            "activity": activity,
        },
    )


@login_required
@capability_required("student_affairs.activities")
@require_POST
def activity_delete(request, pk):
    """حذف نشاط."""
    school = request.school
    activity = get_object_or_404(StudentActivity, pk=pk, school=school)
    title = activity.title
    activity.delete()
    messages.success(request, f"تم حذف النشاط «{title}».")
    return redirect("student_affairs:activity_list")


# ═════════════════════════════════════════════════════════════════════
# تصدير ملف الطالب PDF
# ═════════════════════════════════════════════════════════════════════


@login_required
# نسخةُ الملفّ نفسِه — فتتقيّد كما يتقيّد: طالبٌ من جناح المشرف وحدَه.
@capability_required("student_affairs.follow_up")
def student_profile_pdf(request, student_id):
    """ملف الطالب الشامل — PDF للطباعة (A4).

    وللمقيَّد بجناحه: لا درجاتٍ ولا أنشطة — فوثيقتُه متابعةٌ لا وثيقةٌ رسميّة.
    """
    school = request.school
    scope = student_scope_for(request)
    scope.require_student(student_id)
    student = get_object_or_404(
        CustomUser,
        id=student_id,
        memberships__school=school,
        memberships__is_active=True,
    )
    year = _year_in_scope(request, scope)
    limited = scope.is_wing_bound
    today = timezone.localdate()
    records = selectors.student_profile_pdf_records(student, school, year, today, scope)

    ctx = get_export_context(request, "ملف الطالب الشامل")
    # ملفُّ طالبٍ واحدٍ وثيقةٌ فرديّة: الرقمُ كاملاً — للمشرف كما للقيادة، فالوثيقةُ المستورةُ
    # لا تُغني عن صاحبها (test_national_id_masking) — والتدقيقُ ثمنُه.
    log_export(
        request,
        "student_affairs.student_profile_pdf",
        rows=1,
        full_national_id=True,
        object_id=student.pk,
        object_repr=(
            f"ملف الطالب {student.full_name} — {year}" + (" — طلبة الجناح" if limited else "")
        ),
    )

    html_string = render_to_string(
        "student_affairs/student_profile_pdf.html",
        {
            "student": student,
            "school": school,
            **records,
            "today": today,
            "year": year,
            "limited": limited,
            **ctx,
        },
    )
    return render_pdf(html_string, f"student_{student.full_name}.pdf")


# ═════════════════════════════════════════════════════════════════════
# تقديم ملفات media محمية — F-001 Security Fix
# ═════════════════════════════════════════════════════════════════════


@login_required
# مرفقُ عذر التأخّر من عمل المشرف الإداريّ (الدليل 2026 م 3.4.2.2) — لطلبة جناحه وحدَهم.
@capability_required("student_affairs.follow_up")
def protected_media(request, path):
    """تقديم ملفات media محمية — يتحقق من المدرسة قبل التقديم عبر X-Accel-Redirect."""
    # F-001-a: Path traversal sanitization
    if ".." in path or path.startswith("/"):
        raise Http404

    school = request.school

    # تحقق أن الملف يخص مدرسة المستخدم — وطالباً من جناحه للمقيَّد، وإلّا 404
    # لا يُميَّز عن ملفٍّ غير موجود.
    get_object_or_404(
        student_scope_for(request).narrow(StudentAttendance.objects.filter(school=school)),
        excuse_file=path,
    )

    # F-001-b: Content-Disposition RFC 5987 encoding
    safe_name = quote(os.path.basename(path))
    response = HttpResponse()
    response["X-Accel-Redirect"] = f"/media/{path}"
    response["Content-Disposition"] = f'attachment; filename="{safe_name}"'
    del response["Content-Type"]  # دع Nginx يحدد النوع تلقائياً
    return response


# ═════════════════════════════════════════════════════════════════════
# التأخر الصباحي
# ═════════════════════════════════════════════════════════════════════


def _selected_date(request) -> date:
    """`?date=` بصيغة ISO — أو اليومُ إن غاب أو فسد."""
    raw = request.GET.get("date")
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return timezone.localdate()


def _late_tone(total_late: int) -> str:
    """صفرٌ أخضر، وحتى خمسةٍ برتقاليّ، وما فوقها أحمر — عتباتُ القالب."""
    return "green" if not total_late else "orange" if total_late <= 5 else "red"


@login_required
# و`wing_bound` في القالب: المقيَّدُ يُلغي ما رُصد صباحاً وحدَه — لا تأخّرَ حصّةٍ من كشف الجناح.
@capability_required("student_affairs.follow_up")
def tardiness_list(request):
    """قائمة الطلاب المتأخرين — مفلترة حسب التاريخ والصف."""
    school = request.school
    scope = _followup_scope(request)
    selected_date = _selected_date(request)
    grade_filter = request.GET.get("grade", "")
    section_filter = request.GET.get("section", "")

    late = selectors.late_arrivals(
        school, selected_date, grade=grade_filter, section=section_filter, scope=scope
    )
    late_records = list(selectors.late_register(late))
    cumulative_counts = selectors.cumulative_late_counts(school, academic_year_for(request), scope)
    for rec in late_records:
        rec.cumulative_late = cumulative_counts.get(rec.student_id, 0)
        # خمسُ مرّاتٍ فأكثر هذا العام تُلوَّن خطراً — العتبةُ التي كانت في القالب.
        rec.cumulative_badge = "status-danger" if rec.cumulative_late >= 5 else "status-gray"
        rec.class_text = class_label(rec.session.class_group.grade, rec.session.class_group.section)

    total_late = len(late_records)
    total_students_today = selectors.students_marked_on(school, selected_date, scope)
    late_pct = percent(total_late, total_students_today)
    class_breakdown = selectors.late_by_class(late)
    return render(
        request,
        "student_affairs/tardiness_list.html",
        {
            "page_subtitle": _with_wing(
                f"الطلاب المتأخرون — {date_format(selected_date, 'D، d M Y')}",
                _followup_wing_label(scope),
            ),
            "empty_label": f"لا يوجد طلاب متأخرون في {date_format(selected_date, 'd M Y')}",
            "total_late_tone": _late_tone(total_late),
            "late_pct_label": f"{late_pct}%",
            "late_pct_sub": f"من {total_students_today}",
            "class_chips": [
                {
                    "label": class_label(
                        row["session__class_group__grade"], row["session__class_group__section"]
                    ),
                    "count": row["count"],
                }
                for row in class_breakdown
            ],
            "late_records": late_records,
            "selected_date": selected_date,
            "total_late": total_late,
            "total_students_today": total_students_today,
            "late_pct": late_pct,
            "class_breakdown": class_breakdown,
            "stage_breakdown": selectors.late_by_stage(late),
            "weekly_late": selectors.late_this_week(school, selected_date, scope),
            "grades": ClassGroup.GRADES,
            "grade_filter": grade_filter,
            "section_filter": section_filter,
            "cumulative_counts": cumulative_counts,
            "is_today": selected_date == timezone.localdate(),
            "wing_bound": scope.is_wing_bound,
        },
    )


# ═════════════════════════════════════════════════════════════════════
# تصديرات Excel إضافية — سلوك + تأخر + أنشطة
# ═════════════════════════════════════════════════════════════════════


@login_required
@capability_required("student_affairs.follow_up")
def behavior_export_excel(request):
    """تصدير إحصائيات السلوك — المخالفات + أكثر الطلاب."""
    import openpyxl

    scope = _followup_scope(request)
    wing = _followup_wing_label(scope)
    wb = openpyxl.Workbook()
    # الرقم الشخصيّ: مستور — إحصاءُ مخالفاتٍ كشفٌ جماعيّ.
    rows = write_excel_table(
        _sheet(wb.active, "السلوك"),
        get_export_context(request, _with_wing("تقرير السلوك الطلابي", wing)),
        ["#", "اسم الطالب", "الرقم الشخصي", "عدد المخالفات"],
        (
            [
                i,
                rec["student__full_name"],
                mask_national_id(rec["student__national_id"]),
                rec["count"],
            ]
            for i, rec in enumerate(
                selectors.infraction_counts_by_student(request.school, scope), 1
            )
        ),
    )
    log_export(
        request,
        "student_affairs.behavior_xlsx",
        rows=rows,
        full_national_id=False,
        object_repr=_with_wing("إحصائيات السلوك Excel", wing),
    )
    return excel_to_response(wb, generate_export_filename("behavior", "stats", "xlsx"))


@login_required
@capability_required("student_affairs.follow_up")
def tardiness_export_excel(request):
    """تصدير قائمة المتأخرين ليوم محدد."""
    import openpyxl

    school = request.school
    scope = _followup_scope(request)
    wing = _followup_wing_label(scope)
    selected_date = _selected_date(request)
    late = selectors.late_register(
        selectors.late_arrivals(school, selected_date, scope=scope), by_section=False
    )
    cumulative = selectors.cumulative_late_counts(school, academic_year_for(request), scope)

    wb = openpyxl.Workbook()
    rows = write_excel_table(
        _sheet(wb.active, "التأخر"),
        get_export_context(
            request,
            _with_wing(f"تقرير التأخر الصباحي — {selected_date.strftime('%d/%m/%Y')}", wing),
        ),
        [
            "#",
            "اسم الطالب",
            "الصف",
            "الشعبة",
            "التكرار",
            "توقيت التسجيل",
            "الملاحظات",
            "المادة",
            "مرفق",
        ],
        (
            [
                i,
                rec.student.full_name,
                rec.session.class_group.grade,
                rec.session.class_group.section,
                cumulative.get(rec.student_id, 0),
                rec.tardiness_recorded_at.strftime("%H:%M") if rec.tardiness_recorded_at else "—",
                rec.excuse_notes or "—",
                rec.session.subject.name_ar if rec.session.subject else "—",
                "نعم" if rec.excuse_file else "—",
            ]
            for i, rec in enumerate(late, 1)
        ),
    )
    log_export(
        request,
        "student_affairs.tardiness_xlsx",
        rows=rows,
        object_repr=_with_wing(f"المتأخّرون Excel — {selected_date:%Y-%m-%d}", wing),
    )
    return excel_to_response(wb, generate_export_filename("tardiness", "daily", "xlsx"))


@login_required
@capability_required("student_affairs.activities")
def activities_export_excel(request):
    """تصدير قائمة الأنشطة والإنجازات."""
    import openpyxl

    type_map = dict(StudentActivity.TYPE_CHOICES)
    scope_map = dict(StudentActivity.SCOPE_CHOICES)
    activities = (
        StudentActivity.objects.filter(school=request.school)
        .select_related("student")
        .order_by("-date")
    )

    wb = openpyxl.Workbook()
    rows = write_excel_table(
        _sheet(wb.active, "الأنشطة"),
        get_export_context(request, "تقرير الأنشطة والإنجازات"),
        ["#", "اسم الطالب", "النشاط", "النوع", "النطاق", "التاريخ"],
        (
            [
                i,
                act.student.full_name,
                act.title,
                type_map.get(act.activity_type, act.activity_type),
                scope_map.get(act.scope, act.scope),
                act.date.strftime("%d/%m/%Y") if act.date else "—",
            ]
            for i, act in enumerate(activities, 1)
        ),
    )
    log_export(
        request,
        "student_affairs.activities_xlsx",
        rows=rows,
        object_repr="الأنشطة والإنجازات Excel",
    )
    return excel_to_response(wb, generate_export_filename("activities", "list", "xlsx"))


# ═════════════════════════════════════════════════════════════════════
# تصديرات PDF — حضور + سلوك + تأخر
# ═════════════════════════════════════════════════════════════════════


@login_required
@capability_required("student_affairs.follow_up")
def attendance_overview_pdf(request):
    """تصدير إحصائيات الحضور والغياب — PDF."""
    school = request.school
    today = timezone.localdate()
    scope = _followup_scope(request)
    wing = _followup_wing_label(scope)
    counts = attendance_status_counts(school, scope=scope, session__date=today)
    worst_students = selectors.absence_ranking(
        school, today - timedelta(days=30), "student__id", "student__full_name", scope=scope
    )[:20]

    ctx = get_export_context(request, _with_wing("تقرير الحضور والغياب", wing))
    html = render_to_string(
        "student_affairs/attendance_overview_pdf.html",
        {
            "summary": _attendance_summary(counts),
            "today": today,
            "worst_students": worst_students,
            "pdf_header": get_pdf_header_html(ctx),
            "pdf_footer": get_pdf_footer_html(ctx),
            **ctx,
        },
    )

    log_export(
        request,
        "student_affairs.attendance_overview_pdf",
        rows=len(worst_students),
        object_repr=_with_wing(f"تقرير الحضور والغياب — {today:%Y-%m-%d}", wing),
    )
    return render_pdf(
        html, generate_export_filename("attendance", "overview", "pdf"), paper_size="A4"
    )


@login_required
@capability_required("student_affairs.follow_up")
def behavior_overview_pdf(request):
    """تصدير ملخص السلوك — PDF."""
    today = timezone.localdate()
    scope = _followup_scope(request)
    wing = _followup_wing_label(scope)
    summary = selectors.behaviour_year_summary(request.school, today, scope)

    ctx = get_export_context(request, _with_wing("تقرير السلوك", wing))
    html = render_to_string(
        "student_affairs/behavior_overview_pdf.html",
        {
            "today": today,
            "total_infractions": summary["total_infractions"],
            "unresolved": summary["unresolved"],
            "infraction_pct": summary["infraction_pct"],
            "degree_rows": [{"degree": d, "count": c} for d, c in summary["degree_counts"]],
            "worst_students": summary["worst_students"],
            "pdf_header": get_pdf_header_html(ctx),
            "pdf_footer": get_pdf_footer_html(ctx),
            **ctx,
        },
    )

    log_export(
        request,
        "student_affairs.behavior_overview_pdf",
        rows=len(summary["worst_students"]),
        object_repr=_with_wing(f"تقرير السلوك — {today:%Y-%m-%d}", wing),
    )
    return render_pdf(
        html, generate_export_filename("behavior", "overview", "pdf"), paper_size="A4"
    )


@login_required
@capability_required("student_affairs.follow_up")
def tardiness_pdf(request):
    """تصدير قائمة المتأخرين — PDF."""
    school = request.school
    scope = _followup_scope(request)
    wing = _followup_wing_label(scope)
    selected_date = _selected_date(request)
    late_records = list(
        selectors.late_register(selectors.late_arrivals(school, selected_date, scope=scope))
    )
    cumulative_counts = selectors.cumulative_late_counts(school, academic_year_for(request), scope)
    for rec in late_records:
        rec.cumulative = cumulative_counts.get(rec.student_id, 0)
    total_late = len(late_records)
    marked = selectors.students_marked_on(school, selected_date, scope)

    ctx = get_export_context(request, _with_wing("تقرير التأخر الصباحي", wing))
    html = render_to_string(
        "student_affairs/tardiness_pdf.html",
        {
            "selected_date": selected_date,
            "late_records": late_records,
            "total_late": total_late,
            "late_pct": percent(total_late, marked),
            "weekly_late": selectors.late_this_week(school, selected_date, scope),
            "pdf_header": get_pdf_header_html(ctx),
            "pdf_footer": get_pdf_footer_html(ctx),
            **ctx,
        },
    )

    log_export(
        request,
        "student_affairs.tardiness_pdf",
        rows=total_late,
        object_repr=_with_wing(f"المتأخّرون — {selected_date:%Y-%m-%d}", wing),
    )
    return render_pdf(html, generate_export_filename("tardiness", "list", "pdf"), paper_size="A4")


# ═════════════════════════════════════════════════════════════════════
# تسجيل التأخير الصباحي — SOS-20260504-5191
# ═════════════════════════════════════════════════════════════════════


@login_required
@capability_required("student_affairs.tardiness")
def tardiness_search_students(request):
    """HTMX — بحث عن طلاب بالاسم لتسجيل تأخير."""
    from django.http import JsonResponse

    q = request.GET.get("q", "").strip()
    school = request.school
    today = timezone.localdate()

    if len(q) < 2:
        return JsonResponse({"results": []})

    # المقيَّدُ يبحث في طلبة جناحه وحدهم — اسمُ طالبِ جناحٍ آخر لا يُعاد.
    scope = _followup_scope(request)
    students = (
        scope.narrow(
            CustomUser.objects.filter(
                memberships__school=school,
                memberships__role__name="student",
                memberships__is_active=True,
                full_name__icontains=q,
            ),
            "pk",
        )
        .distinct()
        .values("id", "full_name", "national_id")[:15]
    )

    already_late_ids = set(
        scope.narrow(
            StudentAttendance.objects.filter(
                school=school,
                status="late",
                session__date=today,
            )
        ).values_list("student_id", flat=True)
    )

    results = []
    for s in students:
        results.append(
            {
                "id": str(s["id"]),
                "name": s["full_name"],
                # ردُّ بحثٍ يضمّ خمسةَ عشرَ طالباً كشفٌ جماعيّ — يميّز ولا يعرّف.
                "nid": mask_national_id(s["national_id"]),
                "already_late": s["id"] in already_late_ids,
            }
        )

    return JsonResponse({"results": results})


#: مرفقُ إذن التأخّر: PDF أو صورة، حتى خمسة ميغابايت.
EXCUSE_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png")
EXCUSE_CONTENT_TYPES = ("application/pdf", "image/jpeg", "image/png")
EXCUSE_MAX_BYTES = 5 * 1024 * 1024


def _excuse_file_error(excuse_file) -> str | None:
    """سببُ رفض المرفق بعبارته للمستخدم — أو `None` إن قُبل أو لم يُرفق."""
    if not excuse_file:
        return None
    ext = os.path.splitext(excuse_file.name)[1].lower()
    if ext not in EXCUSE_EXTENSIONS or excuse_file.content_type not in EXCUSE_CONTENT_TYPES:
        return "نوع الملف غير مسموح — يُقبل: PDF, JPG, PNG فقط."
    if excuse_file.size > EXCUSE_MAX_BYTES:
        return "حجم الملف يتجاوز 5 ميغابايت."
    return None


@login_required
@capability_required("student_affairs.tardiness")
@require_POST
def tardiness_record(request):
    """POST — تسجيل تأخير صباحي لطالب (الكتابةُ في `TardinessService`)."""
    school = request.school
    excuse_file = request.FILES.get("excuse_file")

    # ── التحقّقُ من الملفّ قبل أيّ عمليّة DB ──
    error = _excuse_file_error(excuse_file)
    if error:
        messages.error(request, error)
        return redirect("student_affairs:tardiness_list")

    # طالبُ جناحٍ آخر: 404 قبل أيّ قراءةٍ أو كتابة — ومعرّفٌ فاسدٌ مثلُه للمقيَّد.
    scope = _followup_scope(request)
    scope.require_student(request.POST.get("student_id"))

    student = get_object_or_404(
        CustomUser,
        pk=request.POST.get("student_id"),
        memberships__school=school,
        memberships__role__name="student",
        memberships__is_active=True,
    )
    minutes = request.POST.get("excuse_minutes", "").strip()
    now = timezone.localtime()
    attendance = TardinessService.record_morning_tardiness(
        school=school,
        student=student,
        minutes=int(minutes) if minutes.isdigit() else None,
        excuse_file=excuse_file,
        marked_by=request.user,
        now=now,
        ip_address=request.META.get("REMOTE_ADDR"),
        scope=scope,
        audit_suffix=_with_wing("", _followup_wing_label(scope)),
    )
    if attendance is None:
        messages.error(request, "لا توجد حصة مجدولة اليوم لتسجيل التأخير.")
        return redirect("student_affairs:tardiness_list")

    messages.success(
        request, f"تم تسجيل تأخير {student.full_name} — الساعة {now.strftime('%H:%M')}"
    )
    return redirect("student_affairs:tardiness_list")


@login_required
@capability_required("student_affairs.tardiness")
@require_POST
def tardiness_delete(request, pk):
    """حذف سجل تأخير (إعادته لحاضر)."""
    school = request.school
    scope = _followup_scope(request)
    rec = get_object_or_404(
        selectors.cancellable_late_records(school, scope, timezone.localdate()), pk=pk
    )
    rec.status = "present"
    rec.tardiness_minutes = None
    rec.excuse_notes = ""
    rec.tardiness_recorded_at = None
    if rec.excuse_file:
        rec.excuse_file.delete(save=False)
    rec.excuse_file = ""
    fields = [
        "status",
        "tardiness_minutes",
        "excuse_notes",
        "tardiness_recorded_at",
        "excuse_file",
        "updated_at",
    ]
    if rec.whereabouts == "gate":
        # «عند البوّابة» وسمُ الرصد الصباحيّ — يزول بإلغائه فلا يبقى على حاضر.
        rec.whereabouts = ""
        fields.append("whereabouts")
    rec.save(update_fields=fields)

    # ── Audit Trail (PDPPL) ──
    AuditLog.objects.create(
        user=request.user,
        school=school,
        action="delete",
        model_name="other",
        object_id=str(rec.pk),
        object_repr=_with_wing(f"إلغاء تأخير {rec.student.full_name}", _followup_wing_label(scope)),
        ip_address=request.META.get("REMOTE_ADDR"),
    )

    messages.success(request, f"تم إلغاء تأخير {rec.student.full_name}")
    return redirect("student_affairs:tardiness_list")
