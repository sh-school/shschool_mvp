"""
student_affairs/views.py — شؤون الطلاب
16 view — يتبع أنماط المشروع الموجودة بالضبط.
"""

import json
import logging
import os
from datetime import timedelta
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import CharField, Count, Exists, F, Func, OuterRef, Q, Subquery, Value
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.formats import date_format
from django.views.decorators.http import require_POST

from assessments.models import AnnualSubjectResult
from behavior.models import BehaviorInfraction
from clinic.models import ClinicVisit, HealthRecord
from core import brand
from core.academic_calendar import academic_year_for, academic_year_window
from core.audit_export import log_export
from core.capabilities import capability_required, has_capability
from core.domain.attendance import attendance_rate
from core.domain.tones import ATTENDANCE_SUMMARY, tone_for
from core.export_utils import (
    add_excel_footer,
    add_excel_header,
    excel_table_styles,
    excel_to_response,
    generate_export_filename,
    get_export_context,
    get_pdf_footer_html,
    get_pdf_header_html,
    xl_fill,
)
from core.labels import class_label
from core.models.academic import (
    ClassGroup,
    ParentStudentLink,
    StudentEnrollment,
    grade_number,
    grade_order,
)
from core.models.access import Membership
from core.models.audit import AuditLog
from core.models.user import CustomUser
from core.pdf_utils import render_pdf
from core.privacy import mask_national_id
from core.sorting import apply_sort, arabic_key, blank_as_null, normalise_arabic
from library.models import BookBorrowing
from operations.absence_standing import standing_for
from operations.models import AbsenceAlert, Session, StudentAttendance
from operations.presence import presence_now
from operations.tardiness import tardiness_now
from wings.scope import student_scope_for

from .models import StudentActivity, StudentTransfer

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
            # القالبُ يُخفي عن المقيَّد روابطَ ما لا يفتحه — والحراسةُ على الشاشات.
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


@login_required
# قائمةٌ تُقرأ ولا تُكتب — فحارسُها `VIEW` لا `MANAGE`. والمجموعتان مفصولتان
# أصلاً في `core/permissions.py` بقرار MTG-2026-012: المنسّقُ والأخصائيّان
# يرون الطلبة ولا يبتّون في قيدهم. وكانت القائمةُ تعرض الشاشةَ للمنسّق
# ويردُّه حارسُها — إذنٌ مكتوبٌ في موضعٍ وممنوعٌ في آخر.
@capability_required("student_affairs.view")
def student_list(request):
    """قائمة الطلاب مع بحث وفلتر حسب الصف والشعبة.

    والمشرفُ الإداريُّ يقرؤها لطلبة جناحه وحدَهم (قرارُ المستخدم 2026-09-14): النطاقُ
    يُطبَّق على الاستعلام الأساسيّ **قبل** كلّ مرشِّحٍ وفرزٍ وترقيم، فالعددُ والصفحاتُ
    والبحثُ بالرقم الشخصيّ لا تبلغ طالباً خارجه.
    """
    school = request.school
    scope = student_scope_for(request)
    year = _year_in_scope(request, scope)

    # ── الاستعلام الأساسي: طلاب فعّالون في المدرسة — أو في الجناح ──
    students = scope.narrow(
        Membership.objects.filter(
            school=school,
            role__name="student",
            is_active=True,
        )
        .select_related("user", "user__profile")
        .order_by("user__full_name"),
        "user_id",
    )

    # ── الفلاتر ──
    q = request.GET.get("q", "").strip()
    grade_filter = request.GET.get("grade", "")
    section_filter = request.GET.get("section", "")
    parent_status = request.GET.get("parent_status", "")

    if grade_filter:
        # ✅ subquery مباشر — لا تحميل IDs إلى Python
        grade_enrollment_exists = Exists(
            scope.narrow_classes(
                StudentEnrollment.objects.filter(
                    class_group__school=school,
                    class_group__academic_year=year,
                    class_group__grade=grade_filter,
                    is_active=True,
                    student_id=OuterRef("user_id"),
                )
            )
        )
        students = students.filter(grade_enrollment_exists)

    if section_filter:
        section_enrollment_exists = Exists(
            scope.narrow_classes(
                StudentEnrollment.objects.filter(
                    class_group__school=school,
                    class_group__academic_year=year,
                    class_group__section=section_filter,
                    is_active=True,
                    student_id=OuterRef("user_id"),
                )
            )
        )
        students = students.filter(section_enrollment_exists)

    if parent_status:
        # ✅ Exists subquery بدل Python set arithmetic — O(1) ذاكرة
        parent_link_exists = Exists(
            ParentStudentLink.objects.filter(school=school, student_id=OuterRef("user_id"))
        )
        if parent_status == "linked":
            students = students.annotate(_has_parent=parent_link_exists).filter(_has_parent=True)
        elif parent_status == "unlinked":
            students = students.annotate(_has_parent=parent_link_exists).filter(_has_parent=False)

    # ── المقيَّدُ أوّلاً، ومن أُغلق قيدُه لا يسقط بل يُرشَّح ──────────────
    #
    # العضويّةُ تقول «هذا طالبُ المدرسة» والقيدُ يقول «هذا صفُّه هذا العام»،
    # وهما شيئان: من نُقل هذا الصيفَ أُغلق قيدُه وبقيت عضويّتُه. فكان السجلُّ
    # يعدّهما واحداً ويقول «881 طالباً مسجّلاً» لمدرسةٍ سجلُّ قيدها 735 —
    # ويخالف الكشفَ الوزاريَّ في رقمٍ يُقرأ في أوّل الشاشة.
    #
    # فالافتراضُ المقيَّدون، ومن لا قيدَ له يُرى بترشيحٍ صريحٍ لا يضيع.
    # والمقيَّدُ بجناحه لا يرى إلّا المقيَّدين: طالبٌ بلا قيدٍ نشطٍ لا جناحَ له،
    # فـ`all` و`unenrolled` لا تفتحان له المدرسة.
    status = "enrolled" if scope.is_wing_bound else (request.GET.get("status") or "enrolled")
    is_enrolled = Exists(
        StudentEnrollment.objects.filter(
            student_id=OuterRef("user_id"),
            class_group__school=school,
            class_group__academic_year=year,
            is_active=True,
        )
    )
    if status == "enrolled":
        students = students.filter(is_enrolled)
    elif status == "unenrolled":
        students = students.exclude(is_enrolled)

    # ── الصفُّ والشعبةُ صفتا قيدٍ لا صفتا شخص، والتصفّحُ على الأشخاص ──
    #
    # فتُجلبان بالاستعلام نفسِه ليصحّ الفرزُ بهما على السجلّ كلِّه لا على
    # الصفحة الظاهرة. وكان الفرزُ في المتصفّح على مئتين مقطوعةٍ من سبعمئةٍ
    # وخمسٍ وثلاثين — يُوهم القارئَ أنّه رأى الأوّلَ وهو أوّلُ صفحةٍ واحدة.
    enrolment = scope.narrow_classes(
        StudentEnrollment.objects.filter(
            student_id=OuterRef("user_id"),
            class_group__academic_year=year,
            is_active=True,
        )
    ).order_by("-class_group__academic_year", "-enrolled_at")
    guardian = ParentStudentLink.objects.filter(
        student_id=OuterRef("user_id"), school=school
    ).order_by("-is_primary", "created_at")

    students = students.annotate(
        grade_code=Subquery(enrolment.values("class_group__grade")[:1]),
        section_code=Subquery(enrolment.values("class_group__section")[:1]),
        name_key=arabic_key(F("user__full_name")),
        national_key=blank_as_null("user__national_id"),
        # وليُّ الأمر: الأساسيُّ أوّلاً، فإن لم يُعلَّم أحدٌ فأقدمُ ارتباط.
        # وجوّالُه هو الفعلُ المقصودُ من هذه الشاشة — الاتّصالُ بالأسرة.
        guardian_name=Subquery(guardian.values("parent__full_name")[:1]),
        guardian_phone=Subquery(guardian.values("parent__phone")[:1]),
        guardian_relation=Subquery(guardian.values("relationship")[:1]),
    ).annotate(
        # «G10» نصّاً يسبق «G7»، وعدداً يليه. فيُحشى الجزءُ الرقميُّ بصفرٍ
        # فيصير ترتيبُ الحروف ترتيبَ الأعداد — ومن لا قيدَ له يبقى عَدَماً
        # فيسقط إلى الذيل في الاتّجاهين لا يتصدّر التنازليّ.
        # وتُنزع الحروفُ أوّلاً: `RIGHT('G7', 2)` تلتقط الحرفَ فتُعيد «G7»،
        # و«10» أصغرُ من «G7» في ترتيب المحارف — فيسبق العاشرُ السابع.
        grade_key=Func(
            Func(
                F("grade_code"),
                Value(r"\D"),
                Value(""),
                Value("g"),
                function="REGEXP_REPLACE",
                output_field=CharField(),
            ),
            Value(2),
            Value("0"),
            function="LPAD",
            output_field=CharField(),
        ),
        section_key=blank_as_null("section_code"),
        guardian_key=arabic_key(F("guardian_name")),
    )

    # والبحثُ يقع على الرقم **الكامل** لا على المستور: من كتب رقماً كاملاً
    # وجد صاحبَه، وإن كان الجدولُ لا يعرض منه إلّا ذيلَه.
    if q:
        shaped = normalise_arabic(q)
        students = students.filter(
            Q(name_key__icontains=shaped)
            | Q(user__national_id__icontains=q)
            | Q(guardian_key__icontains=shaped)
            | Q(guardian_phone__icontains=q)
            | Q(grade_code__icontains=q)
            | Q(section_code__icontains=q)
        )

    students, sort = apply_sort(students, request, allowed=STUDENT_SORTS, default="name")

    paginator = Paginator(students, STUDENT_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    # الصلةُ تُعرض بعنوانها العربيّ لا بمفتاحها المخزَّن، والقائمةُ من النموذج
    # نفسِه فلا قاموسَ ثانٍ يتخلّف عنه.
    relations = dict(ParentStudentLink._meta.get_field("relationship").choices)

    student_rows = [
        {
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
        for m in page_obj
    ]

    # ── خيارات الفلتر — من شُعب الجناح للمقيَّد ──
    groups = scope.narrow_classes(
        ClassGroup.objects.filter(school=school, academic_year=year, is_active=True), "pk"
    )
    available_grades = sorted(set(groups.values_list("grade", flat=True)), key=grade_number)
    available_sections = groups.values_list("section", flat=True).distinct().order_by("section")

    ctx = {
        "students": student_rows,
        # وكان العددُ عددَ الصفّ المعروض، فتقول الترويسةُ «200 طالب مسجّل»
        # لمدرسةٍ فيها سبعُمئةٍ وخمسةٌ وثلاثون. العددُ عددُ السجلّ.
        "total": paginator.count,
        "page_obj": page_obj,
        "sort": sort,
        "status": status,
        "statuses": (
            (("enrolled", "مقيَّدون هذا العام"),)
            if scope.is_wing_bound
            else (
                ("enrolled", "مقيَّدون هذا العام"),
                ("unenrolled", "بلا قيدٍ نشط"),
                ("all", "الكلّ"),
            )
        ),
        "q": q,
        "grade_filter": grade_filter,
        "section_filter": section_filter,
        "parent_status": parent_status,
        "grades": available_grades,
        "sections": available_sections,
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


@login_required
@capability_required("student_affairs.manage")
def student_export_excel(request):
    """تصدير قائمة الطلاب إلى Excel — مع هيدر وفوتر احترافي."""
    import openpyxl
    from openpyxl.styles import Alignment

    school = request.school
    year = academic_year_for(request)
    q = request.GET.get("q", "").strip()
    grade_filter = request.GET.get("grade", "")
    section_filter = request.GET.get("section", "")

    ctx = get_export_context(request, "سجل الطلاب")

    # نفس فلترة student_list
    students = (
        Membership.objects.filter(
            school=school,
            role__name="student",
            is_active=True,
        )
        .select_related("user")
        .order_by("user__full_name")
    )

    if q:
        students = students.filter(
            Q(user__full_name__icontains=q) | Q(user__national_id__icontains=q)
        )

    enrollment_data = {}
    for enr in StudentEnrollment.objects.filter(
        class_group__school=school,
        class_group__academic_year=year,
        is_active=True,
    ).values("student_id", "class_group__grade", "class_group__section"):
        enrollment_data[enr["student_id"]] = enr

    if grade_filter:
        enrolled_ids = [
            sid
            for sid, data in enrollment_data.items()
            if data["class_group__grade"] == grade_filter
        ]
        students = students.filter(user_id__in=enrolled_ids)
    if section_filter:
        enrolled_ids = [
            sid
            for sid, data in enrollment_data.items()
            if data.get("class_group__section") == section_filter
        ]
        students = students.filter(user_id__in=enrolled_ids)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "سجل الطلاب"
    ws.sheet_view.rightToLeft = True

    # هيدر احترافي
    headers = ["#", "الاسم الكامل", "الرقم الشخصي", "الصف", "الشعبة", "الجوال", "البريد"]
    num_cols = len(headers)
    data_start = add_excel_header(ws, ctx, num_cols)

    # Header row
    table = excel_table_styles()
    header_fill, header_font, cell_font = table.header_fill, table.header_font, table.cell_font
    thin_border, alt_fill = table.border, table.alt_fill

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=data_start, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border

    # الرقم الشخصيّ: مستور — سجلُّ الطلبة كشفٌ جماعيّ لا يعود بالاستيراد
    # (قالبُ الاستيراد في `core.views_students`).
    for i, m in enumerate(students, 1):
        enr = enrollment_data.get(m.user_id, {})
        row_data = [
            i,
            m.user.full_name,
            mask_national_id(m.user.national_id),
            enr.get("class_group__grade", "—"),
            enr.get("class_group__section", "—"),
            m.user.phone or "—",
            m.user.email or "—",
        ]
        for col, val in enumerate(row_data, 1):
            cell = ws.cell(row=data_start + i, column=col, value=val)
            cell.font = cell_font
            cell.border = thin_border
            if i % 2 == 0:
                cell.fill = alt_fill

    # Auto-width
    for col_idx in range(1, num_cols + 1):
        max_len = 0
        for row_idx in range(data_start, data_start + students.count() + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            max_len = max(max_len, len(str(cell.value or "")))
        col_letter = chr(64 + col_idx)
        ws.column_dimensions[col_letter].width = min(max_len + 4, 40)

    # فوتر احترافي
    last_data_row = data_start + students.count()
    add_excel_footer(ws, ctx, last_data_row, num_cols)

    log_export(
        request,
        "student_affairs.students_xlsx",
        rows=last_data_row - data_start,
        full_national_id=False,
        object_repr=f"سجل الطلاب Excel — {year}",
    )
    filename = generate_export_filename("students", "list", "xlsx")
    return excel_to_response(wb, filename)


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
    """ملف الطالب الشامل — يجمع بيانات من 7 تطبيقات.

    وللمقيَّد بجناحه (قرارُ المستخدم 2026-09-15) لا تُحسب ولا تُعرض: الدرجاتُ،
    وفصيلةُ الدم وأسبابُ زيارات العيادة (يرى تاريخَ الزيارة و«أُعيد إلى المنزل»)،
    والإعاراتُ، والأنشطةُ، والانتقالات.
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
    limited = scope.is_wing_bound

    # ── 1. البيانات الشخصية (core) ──
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
    parent_links = ParentStudentLink.objects.filter(
        student=student,
        school=school,
    ).select_related("parent")

    # ── 2. الحضور (operations) ──
    # كان الترشيح `session__date__year=` — أي **السنة الميلادية**. والعام
    # الدراسي يمتدّ من أغسطس إلى يونيو، فكانت الصفحة تعرض شطره الواقع في
    # السنة الجارية وحده: في سبتمبر ترى ثلاثة أسابيع، وفي يناير تفقد الفصل
    # الأول كلّه. ولا شيء يقول إن الرقم ناقص.
    window = academic_year_window(school)
    attendance_qs = StudentAttendance.objects.filter(
        student=student,
        school=school,
        session__date__gte=window[0],
        session__date__lte=window[1],
    )
    attendance_summary = {
        "present": attendance_qs.filter(status="present").count(),
        "absent": attendance_qs.filter(status="absent").count(),
        "late": attendance_qs.filter(status="late").count(),
        "excused": attendance_qs.filter(status="excused").count(),
        "total": attendance_qs.count(),
    }
    if attendance_summary["total"] > 0:
        attendance_summary["pct"] = round(
            attendance_summary["present"] / attendance_summary["total"] * 100, 1
        )
    else:
        attendance_summary["pct"] = 0

    # ── 2ب. موقفه من عتبات الغياب (سياسة تقييم الطلبة) ──
    # عرضٌ محض: كم يوماً، وأيّ عتبةٍ قادمة، وكم يفصله عنها. لا حجبَ ولا إشعار.
    absence_standing = standing_for(
        student,
        school,
        grade=enrollment.class_group.grade if enrollment else None,
    )

    # ── 2ج. عدّادا التأخّر عن الحصص — مرّاتٍ ودقائق، للفصل والعام وبالمادّة ──
    tardiness = tardiness_now(student, school)
    # ── 2د. دقائقُ الحضور الفعليّ بالمادّة — ما يُقارَن بالتحصيل (قرارُ 2026-09-13) ──
    presence = presence_now(student, school)

    # ── 3. السلوك (behavior) ──
    infractions = (
        BehaviorInfraction.objects.filter(student=student, school=school)
        .select_related("violation_category")
        .order_by("-date")
    )
    # نظام النقاط ملغى — summary يعتمد على عدد المخالفات فقط
    behavior_summary = {
        "total": infractions.count(),
        "by_level": {lvl: infractions.filter(level=lvl).count() for lvl in range(1, 5)},
        "recent": infractions[:5],
    }

    # ── 4. العيادة (clinic) — ClinicVisit + HealthRecord مُستورَدان من أعلى الملف ──
    visits = ClinicVisit.objects.filter(student=student, school=school).order_by("-visit_date")
    if scope.clinic_summary_only:
        # التاريخُ و«أُعيد إلى المنزل» وحدَهما يبلغان القالب — لا السببُ ولا الحرارة.
        clinic_visits = visits.values("visit_date", "is_sent_home")[:5]
        health_record = None
    else:
        clinic_visits = visits[:5]
        health_record = HealthRecord.objects.filter(student=student).first()

    # ── 5. الدرجات (assessments) — AnnualSubjectResult مُستورَد من أعلى الملف ──
    if scope.hides_grades:
        grades = AnnualSubjectResult.objects.none()
        grades_summary = {}
    else:
        grades = (
            AnnualSubjectResult.objects.filter(
                student=student,
                school=school,
                academic_year=year,
            )
            .select_related("setup__subject", "setup__class_group")
            .order_by("setup__subject__name_ar")
        )
        grades_summary = grades.aggregate(
            total_subjects=Count("id"),
            passed=Count("id", filter=Q(status="pass")),
            failed=Count("id", filter=Q(status="fail")),
        )

    if limited:
        # الإعاراتُ والأنشطةُ والانتقالاتُ ليست من متابعة المشرف — فلا تُحسب له.
        borrowings, activities, transfers = [], [], []
    else:
        # ── 6. المكتبة (library) — BookBorrowing مُستورَد من أعلى الملف ──
        borrowings = (
            BookBorrowing.objects.filter(user=student)
            .select_related("book")
            .order_by("-borrow_date")[:5]
        )

        # ── 7. الأنشطة (student_affairs) ──
        activities = StudentActivity.objects.filter(student=student, school=school).order_by(
            "-date"
        )[:10]

        # ── الانتقالات ──
        transfers = StudentTransfer.objects.filter(student=student, school=school).order_by(
            "-created_at"
        )[:5]

    # ── ما يُرسم: سطرُ الترويسة ولونُ الحضور (90 · 75 — عتبتا القالب) ──
    subtitle_parts = []
    if enrollment:
        subtitle_parts.append(
            class_label(enrollment.class_group.grade, enrollment.class_group.section)
        )
    if student.national_id:
        subtitle_parts.append(f"****{mask_national_id(student.national_id)[-4:]}")
    if profile and profile.gender:
        subtitle_parts.append("ذكر" if profile.gender == "M" else "أنثى")

    return render(
        request,
        "student_affairs/student_profile.html",
        {
            "profile_subtitle": " · ".join(subtitle_parts),
            "attendance_label": f"{attendance_summary['pct']}%",
            "attendance_sub": f"من {attendance_summary['total']} حصة",
            "attendance_tone": _share_tone(attendance_summary["pct"])[0],
            "subjects_sub": f"ناجح {grades_summary.get('passed') or 0}",
            "student": student,
            "profile": profile,
            "enrollment": enrollment,
            "parent_links": parent_links,
            "attendance": attendance_summary,
            "absence_standing": absence_standing,
            "tardiness": tardiness,
            "presence": presence,
            "behavior": behavior_summary,
            "clinic_visits": clinic_visits,
            "health_record": health_record,
            "grades": grades,
            "grades_summary": grades_summary,
            "borrowings": borrowings,
            "activities": activities,
            "transfers": transfers,
            "year": year,
            # القالبُ يُخفي ولا يحرس: الأقسامُ المحجوبةُ لم تُحسب أصلاً.
            "limited": limited,
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


@login_required
@capability_required("student_affairs.manage")
def attendance_overview(request):
    """إحصائيات الحضور والغياب — شاملة مع Trends."""
    school = request.school
    today = timezone.localdate()
    year = request.GET.get("year") or academic_year_for(request)
    grade_filter = request.GET.get("grade", "")

    # ── إحصائيات اليوم — استعلامٌ واحدٌ بدل خمسة ──
    today_counts = StudentAttendance.objects.filter(school=school, session__date=today).aggregate(
        total=Count("id"),
        present=Count("id", filter=Q(status="present")),
        absent=Count("id", filter=Q(status="absent")),
        late=Count("id", filter=Q(status="late")),
        excused=Count("id", filter=Q(status="excused")),
    )
    pct = attendance_rate(today_counts["present"], today_counts["total"])

    summary = {
        "present": today_counts["present"],
        "absent": today_counts["absent"],
        "late": today_counts["late"],
        "excused": today_counts["excused"],
        "total": today_counts["total"],
        "pct": pct,
    }

    # ── أكثر 20 طالب غياباً (آخر 30 يوم) ──
    thirty_days_ago = today - timedelta(days=30)
    worst_students_qs = (
        StudentAttendance.objects.filter(
            school=school,
            status="absent",
            session__date__gte=thirty_days_ago,
        )
        .values("student__id", "student__full_name")
        .annotate(absence_count=Count("id"))
        .order_by("-absence_count")[:20]
    )

    # ── توزيع حسب الصف (الحضور اليوم) ──
    class_breakdown = (
        StudentAttendance.objects.filter(school=school, session__date=today)
        .values("session__class_group__grade")
        .annotate(
            total=Count("id"),
            present_count=Count("id", filter=Q(status="present")),
            absent_count=Count("id", filter=Q(status="absent")),
            late_count=Count("id", filter=Q(status="late")),
        )
        .order_by(grade_order("session__class_group__grade"))
    )

    # ── بيانات Chart (آخر 14 يوم) — استعلامٌ واحدٌ مجمَّعٌ باليوم بدل 42 ──
    chart_start = today - timedelta(days=13)
    by_day = {
        row["session__date"]: row
        for row in StudentAttendance.objects.filter(
            school=school, session__date__gte=chart_start, session__date__lte=today
        )
        .values("session__date")
        .annotate(
            total=Count("id"),
            present=Count("id", filter=Q(status="present")),
            absent=Count("id", filter=Q(status="absent")),
        )
    }
    chart_labels = []
    chart_present = []
    chart_absent = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        day = by_day.get(d, {"total": 0, "present": 0, "absent": 0})
        chart_labels.append(d.strftime("%m/%d"))
        chart_present.append(attendance_rate(day["present"], day["total"]))
        chart_absent.append(attendance_rate(day["absent"], day["total"]))

    # ── تنبيهات الغياب المتكرر — AbsenceAlert مُستورَد من أعلى الملف ──
    alerts = (
        AbsenceAlert.objects.filter(school=school, status="pending")
        .select_related("student")
        .order_by("-absence_count")[:10]
    )

    # ── الصفوف المتاحة للفلتر ──
    grades = ClassGroup.GRADES

    # ── ما يُرسم: الألوانُ بعتباتها هنا لا شروطاً في القالب ──
    pct_tone, _badge = _share_tone(pct)
    class_rows = []
    for row in class_breakdown:
        row_pct = attendance_rate(row["present_count"], row["total"])
        class_rows.append(
            {
                **row,
                "label": _GRADE_NAMES.get(
                    row["session__class_group__grade"], row["session__class_group__grade"]
                ),
                "pct": row_pct,
                "badge": _share_tone(row_pct)[1],
            }
        )
    # الغيابُ المتكرّر: عشرةُ أيّامٍ فأكثر خطر، وخمسةٌ تحذير — عتبتا القالب.
    worst_students = [
        {
            **s,
            "badge": "status-danger"
            if s["absence_count"] >= 10
            else "status-warning"
            if s["absence_count"] >= 5
            else "status-info",
        }
        for s in worst_students_qs
    ]

    return render(
        request,
        "student_affairs/attendance_overview.html",
        {
            "summary": summary,
            "today": today,
            "year": year,
            "page_subtitle": f"ملخص الحضور والغياب — {date_format(today, 'D، d M Y')}",
            "pct_label": f"{pct}%",
            "pct_tone": pct_tone,
            "worst_students": worst_students,
            "class_breakdown": class_rows,
            "chart_labels_json": json.dumps(chart_labels),
            "chart_present_json": json.dumps(chart_present),
            "chart_absent_json": json.dumps(chart_absent),
            "alerts": alerts,
            "grades": grades,
            "grade_filter": grade_filter,
        },
    )


@login_required
@capability_required("student_affairs.manage")
def attendance_export_excel(request):
    """تصدير إحصائيات الغياب — أكثر الطلاب غياباً (آخر 30 يوم) + حضور اليوم."""
    import openpyxl
    from openpyxl.styles import Alignment

    school = request.school
    today = timezone.localdate()
    thirty_ago = today - timedelta(days=30)

    ctx = get_export_context(request, "تقرير الحضور والغياب")

    # أكثر الطلاب غياباً — Count مُستورَد من أعلى الملف
    absence_data = (
        StudentAttendance.objects.filter(
            school=school,
            status="absent",
            session__date__gte=thirty_ago,
        )
        .values("student__full_name", "student__national_id")
        .annotate(absence_count=Count("id"))
        .order_by("-absence_count")
    )

    # سجل الحضور اليومي
    today_records = (
        StudentAttendance.objects.filter(school=school, session__date=today)
        .select_related("student", "session__class_group")
        .order_by(grade_order("session__class_group__grade"), "student__full_name")
    )

    # أنماط مشتركة
    table = excel_table_styles()
    header_fill, header_font, cell_font = table.header_fill, table.header_font, table.cell_font
    thin_border, alt_fill = table.border, table.alt_fill

    wb = openpyxl.Workbook()

    # ── Sheet 1: الغياب المتكرر ──
    ws1 = wb.active
    ws1.title = "الغياب المتكرر"
    ws1.sheet_view.rightToLeft = True

    s1_headers = ["#", "اسم الطالب", "الرقم الشخصي", "أيام الغياب (30 يوم)"]
    s1_num_cols = len(s1_headers)
    s1_data_start = add_excel_header(ws1, ctx, s1_num_cols)

    for col, h in enumerate(s1_headers, 1):
        cell = ws1.cell(row=s1_data_start, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border

    # الرقم الشخصيّ: مستور — إحصاءُ غيابٍ كشفٌ جماعيّ.
    absence_count_total = 0
    for i, rec in enumerate(absence_data, 1):
        absence_count_total = i
        row_data = [
            i,
            rec["student__full_name"],
            mask_national_id(rec["student__national_id"]),
            rec["absence_count"],
        ]
        for col, val in enumerate(row_data, 1):
            cell = ws1.cell(row=s1_data_start + i, column=col, value=val)
            cell.font = cell_font
            cell.border = thin_border
            if i % 2 == 0:
                cell.fill = alt_fill

    for col_idx in range(1, 5):  # 4 columns
        max_len = 0
        for row_idx in range(s1_data_start, s1_data_start + len(absence_data) + 1):
            cell = ws1.cell(row=row_idx, column=col_idx)
            max_len = max(max_len, len(str(cell.value or "")))
        ws1.column_dimensions[chr(64 + col_idx)].width = min(max_len + 4, 40)

    add_excel_footer(ws1, ctx, s1_data_start + absence_count_total, s1_num_cols)

    # ── Sheet 2: سجل حضور اليوم ──
    ws2 = wb.create_sheet("حضور اليوم")
    ws2.sheet_view.rightToLeft = True

    s2_headers = ["#", "اسم الطالب", "الصف", "الشعبة", "الحالة"]
    s2_num_cols = len(s2_headers)
    s2_data_start = add_excel_header(ws2, ctx, s2_num_cols)

    for col, h in enumerate(s2_headers, 1):
        cell = ws2.cell(row=s2_data_start, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border

    status_map = {"present": "حاضر", "absent": "غائب", "late": "متأخر", "excused": "معذور"}
    today_count = 0
    for i, rec in enumerate(today_records, 1):
        today_count = i
        row_data = [
            i,
            rec.student.full_name,
            rec.session.class_group.grade,
            rec.session.class_group.section,
            status_map.get(rec.status, rec.status),
        ]
        for col, val in enumerate(row_data, 1):
            cell = ws2.cell(row=s2_data_start + i, column=col, value=val)
            cell.font = cell_font
            cell.border = thin_border
            if rec.status == "absent":
                cell.fill = xl_fill(brand.STATUS_DANGER_BG)
            elif rec.status == "late":
                cell.fill = xl_fill(brand.STATUS_WARNING_BG)
            elif i % 2 == 0:
                cell.fill = alt_fill

    for col_idx in range(1, 6):  # 5 columns
        max_len = 0
        for row_idx in range(s2_data_start, s2_data_start + today_count + 1):
            cell = ws2.cell(row=row_idx, column=col_idx)
            max_len = max(max_len, len(str(cell.value or "")))
        ws2.column_dimensions[chr(64 + col_idx)].width = min(max_len + 4, 40)

    add_excel_footer(ws2, ctx, s2_data_start + today_count, s2_num_cols)

    log_export(
        request,
        "student_affairs.attendance_xlsx",
        rows=absence_count_total + today_count,
        full_national_id=False,
        object_repr=f"إحصائيات الغياب Excel — {today:%Y-%m-%d}",
    )
    filename = generate_export_filename("attendance", "stats", "xlsx")
    return excel_to_response(wb, filename)


def _behaviour_window(school, today):
    """نافذة العام الدراسي — وترتدّ إلى السنة الميلادية إن لم يُبذر تقويم."""
    from datetime import date

    window = academic_year_window(school)
    if window is not None:
        return window
    return date(today.year, 1, 1), date(today.year, 12, 31)


@login_required
@capability_required("student_affairs.manage")
def behavior_overview(request):
    """ملخص سلوك الطلاب — إحصائيات شاملة."""
    school = request.school
    today = timezone.localdate()
    grade_filter = request.GET.get("grade", "")

    # ── مخالفات العام الدراسي ──
    # كان الترشيح `date__year` — أي السنة الميلادية. والعام يمتدّ أغسطس–يونيو،
    # فيسقط الفصل الأول كلّه في يناير والعنوان يقول «السنة الحالية».
    _start, _end = _behaviour_window(school, today)
    year_infractions = BehaviorInfraction.objects.filter(
        school=school,
        date__gte=_start,
        date__lte=_end,
    )
    total_infractions = year_infractions.count()
    unresolved = year_infractions.filter(is_resolved=False).count()

    # ── عدد الطلاب المخالفين (فريد) ──
    students_with_infractions = year_infractions.values("student").distinct().count()

    # ── إجمالي الطلاب المسجلين ──
    total_students = Membership.objects.filter(
        school=school,
        role__name="student",
        is_active=True,
    ).count()
    infraction_pct = (
        round(students_with_infractions * 100 / total_students) if total_students else 0
    )

    # ── توزيع حسب درجة المخالفة (1-4) — نظام النقاط ملغى ──
    degree_distribution = (
        year_infractions.values("violation_category__degree")
        .annotate(count=Count("id"))
        .order_by("violation_category__degree")
    )
    degree_map = {}
    for row in degree_distribution:
        deg = row["violation_category__degree"]
        if deg:
            degree_map[deg] = {"count": row["count"]}

    # ── أكثر 15 طالب مخالفات — مُرتَّبة حسب العدد ──
    worst_students = (
        year_infractions.values("student__id", "student__full_name")
        .annotate(infraction_count=Count("id"))
        .order_by("-infraction_count")[:15]
    )

    # ── اتجاه المخالفات الشهري (آخر 6 أشهر) ──
    chart_labels = []
    chart_data = []
    for i in range(5, -1, -1):
        month_start = (today.replace(day=1) - timedelta(days=30 * i)).replace(day=1)
        if i > 0:
            next_month = (month_start + timedelta(days=32)).replace(day=1)
        else:
            next_month = today + timedelta(days=1)
        count = BehaviorInfraction.objects.filter(
            school=school,
            date__gte=month_start,
            date__lt=next_month,
        ).count()
        chart_labels.append(month_start.strftime("%b"))
        chart_data.append(count)

    # ── مخالفات اليوم ──
    today_infractions = year_infractions.filter(date=today).count()

    # ── الصفوف المتاحة للفلتر ──
    grades = ClassGroup.GRADES

    # ── ألوانُ البطاقات بعتباتها التي كانت في القالب ──
    # نسبةُ المخالفين: دون 10% أخضر، ودون 25% برتقاليّ — وبها يُلوَّن الإجماليّ أيضاً.
    pct_tone = tone_for(infraction_pct, INFRACTION_SHARE_KPI)
    # مخالفاتُ اليوم: صفرٌ أخضر، ودون 5 برتقاليّ. وغيرُ المحلولة: صفرٌ أخضر، ودون 10 برتقاليّ.
    today_tone = tone_for(today_infractions, TODAY_INFRACTIONS_KPI)
    unresolved_tone = tone_for(unresolved, UNRESOLVED_KPI)
    degree_rows = [
        (label, degree_map.get(degree, {}).get("count", 0))
        for degree, label in (
            (1, "الدرجة 1 — تحذير"),
            (2, "الدرجة 2 — إنذار"),
            (3, "الدرجة 3 — خطيرة"),
            (4, "الدرجة 4 — جسيمة"),
        )
    ]

    return render(
        request,
        "student_affairs/behavior_overview.html",
        {
            "pct_label": f"{infraction_pct}%",
            "offenders_label": f"{students_with_infractions} من {total_students}",
            "pct_tone": pct_tone,
            "today_tone": today_tone,
            "unresolved_tone": unresolved_tone,
            "degree_rows": degree_rows,
            "today": today,
            "total_infractions": total_infractions,
            "unresolved": unresolved,
            "students_with_infractions": students_with_infractions,
            "total_students": total_students,
            "infraction_pct": infraction_pct,
            "today_infractions": today_infractions,
            "degree_map": degree_map,
            "worst_students": worst_students,
            "chart_labels_json": json.dumps(chart_labels),
            "chart_data_json": json.dumps(chart_data),
            "grades": grades,
            "grade_filter": grade_filter,
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

    وللمقيَّد بجناحه: لا درجاتٍ ولا أنشطة، والرقمُ الشخصيُّ مستور — فوثيقتُه متابعةٌ
    لا وثيقةٌ رسميّة، والرقمُ كاملاً لمن يُصدر الوثيقةَ الرسميّة.
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

    # enrollment
    enrollment = (
        StudentEnrollment.objects.filter(
            student=student,
            class_group__academic_year=year,
            is_active=True,
        )
        .select_related("class_group")
        .first()
    )

    # حضور آخر 30 يوم
    today = timezone.localdate()
    thirty_ago = today - timedelta(days=30)
    attendance = (
        StudentAttendance.objects.filter(
            school=school,
            student=student,
            session__date__gte=thirty_ago,
        )
        .select_related("session__subject")
        .order_by("-session__date")
    )

    att_summary = {
        "total": attendance.count(),
        "present": attendance.filter(status="present").count(),
        "absent": attendance.filter(status="absent").count(),
        "late": attendance.filter(status="late").count(),
    }

    # سلوك — نظام النقاط ملغى
    infractions = (
        BehaviorInfraction.objects.filter(school=school, student=student)
        .select_related("violation_category")
        .order_by("-date")[:20]
    )

    # درجات — AnnualSubjectResult مُستورَد من أعلى الملف
    if scope.hides_grades:
        grades = AnnualSubjectResult.objects.none()
    else:
        grades = (
            AnnualSubjectResult.objects.filter(
                student=student,
                school=school,
                academic_year=year,
            )
            .select_related("setup__subject")
            .order_by("setup__subject__name_ar")
        )

    # أنشطة — ليست من متابعة المقيَّد بجناحه
    if limited:
        activities = StudentActivity.objects.none()
    else:
        activities = StudentActivity.objects.filter(school=school, student=student).order_by(
            "-date"
        )[:10]

    # أولياء الأمور
    parent_links = ParentStudentLink.objects.filter(
        school=school,
        student=student,
    ).select_related("parent")

    ctx = get_export_context(request, "ملف الطالب الشامل")
    # ملفُّ طالبٍ واحدٍ وثيقةٌ فرديّة: الرقمُ كاملاً، والتدقيقُ ثمنُه.
    # والمقيَّدُ بجناحه يأخذه مستوراً، ويقول الأثرُ ذلك.
    log_export(
        request,
        "student_affairs.student_profile_pdf",
        rows=1,
        full_national_id=not limited,
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
            "enrollment": enrollment,
            "attendance": attendance[:15],
            "att_summary": att_summary,
            "infractions": infractions,
            "grades": grades,
            "activities": activities,
            "parent_links": parent_links,
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


@login_required
@capability_required("student_affairs.manage")
def tardiness_list(request):
    """قائمة الطلاب المتأخرين — مفلترة حسب التاريخ والصف."""
    school = request.school

    date_str = request.GET.get("date")
    if date_str:
        try:
            from datetime import date as date_type

            selected_date = date_type.fromisoformat(date_str)
        except ValueError:
            selected_date = timezone.localdate()
    else:
        selected_date = timezone.localdate()

    grade_filter = request.GET.get("grade", "")
    section_filter = request.GET.get("section", "")

    late_qs = StudentAttendance.objects.filter(
        school=school,
        status="late",
        session__date=selected_date,
    )
    if grade_filter:
        late_qs = late_qs.filter(session__class_group__grade=grade_filter)
    if section_filter:
        late_qs = late_qs.filter(session__class_group__section=section_filter)

    late_records = list(
        late_qs.select_related("student", "session__class_group", "session__subject").order_by(
            grade_order("session__class_group__grade"),
            "session__class_group__section",
            "student__full_name",
        )
    )

    total_late = len(late_records)

    # العدّ التراكمي لتأخرات كل طالب هذا العام — مُرفَق مباشرة بكل سجل
    cumulative_counts = dict(
        StudentAttendance.objects.filter(
            school=school,
            status="late",
            session__class_group__academic_year=academic_year_for(request),
        )
        .values("student_id")
        .annotate(total=Count("id"))
        .values_list("student_id", "total")
    )
    for rec in late_records:
        rec.cumulative_late = cumulative_counts.get(rec.student_id, 0)
        # خمسُ مرّاتٍ فأكثر هذا العام تُلوَّن خطراً — العتبةُ التي كانت في القالب.
        rec.cumulative_badge = "status-danger" if rec.cumulative_late >= 5 else "status-gray"
        rec.class_text = class_label(rec.session.class_group.grade, rec.session.class_group.section)

    # KPIs إضافية
    total_students_today = (
        StudentAttendance.objects.filter(
            school=school,
            session__date=selected_date,
        )
        .values("student")
        .distinct()
        .count()
    )
    late_pct = round(total_late * 100 / total_students_today) if total_students_today else 0

    # توزيع التأخر حسب الصف
    class_breakdown = (
        late_qs.values("session__class_group__grade", "session__class_group__section")
        .annotate(count=Count("id"))
        .order_by(grade_order("session__class_group__grade"), "session__class_group__section")
    )

    # التأخر هذا الأسبوع
    week_start = selected_date - timedelta(days=selected_date.weekday())
    weekly_late = StudentAttendance.objects.filter(
        school=school,
        status="late",
        session__date__gte=week_start,
        session__date__lte=selected_date,
    ).count()

    grades = ClassGroup.GRADES

    # توزيع التأخر حسب المراحل الدراسية (إعدادي / ثانوي)
    stage_raw = (
        late_qs.values("session__class_group__level_type")
        .annotate(count=Count("id"))
        .order_by("session__class_group__level_type")
    )
    level_labels = dict(ClassGroup.LEVELS)
    stage_breakdown = []
    for s in stage_raw:
        lt = s["session__class_group__level_type"]
        stage_breakdown.append({"stage_label": level_labels.get(lt, lt), "count": s["count"]})

    return render(
        request,
        "student_affairs/tardiness_list.html",
        {
            "page_subtitle": f"الطلاب المتأخرون — {date_format(selected_date, 'D، d M Y')}",
            "empty_label": f"لا يوجد طلاب متأخرون في {date_format(selected_date, 'd M Y')}",
            # صفرٌ أخضر، وحتى خمسةٍ برتقاليّ، وما فوقها أحمر — عتباتُ القالب.
            "total_late_tone": "green"
            if not total_late
            else "orange"
            if total_late <= 5
            else "red",
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
            "stage_breakdown": stage_breakdown,
            "weekly_late": weekly_late,
            "grades": grades,
            "grade_filter": grade_filter,
            "section_filter": section_filter,
            "cumulative_counts": cumulative_counts,
            "is_today": selected_date == timezone.localdate(),
        },
    )


# ═════════════════════════════════════════════════════════════════════
# تصديرات Excel إضافية — سلوك + تأخر + أنشطة
# ═════════════════════════════════════════════════════════════════════


@login_required
@capability_required("student_affairs.manage")
def behavior_export_excel(request):
    """تصدير إحصائيات السلوك — المخالفات + أكثر الطلاب."""
    import openpyxl
    from openpyxl.styles import Alignment

    school = request.school
    ctx = get_export_context(request, "تقرير السلوك الطلابي")

    # بيانات
    infractions = (
        BehaviorInfraction.objects.filter(school=school)
        .values("student__full_name", "student__national_id")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "السلوك"
    ws.sheet_view.rightToLeft = True

    headers = ["#", "اسم الطالب", "الرقم الشخصي", "عدد المخالفات"]
    num_cols = len(headers)
    data_start = add_excel_header(ws, ctx, num_cols)

    table = excel_table_styles()
    header_fill, header_font, cell_font = table.header_fill, table.header_font, table.cell_font
    thin_border, alt_fill = table.border, table.alt_fill

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=data_start, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border

    # الرقم الشخصيّ: مستور — إحصاءُ مخالفاتٍ كشفٌ جماعيّ.
    row_count = 0
    for i, rec in enumerate(infractions, 1):
        row_data = [
            i,
            rec["student__full_name"],
            mask_national_id(rec["student__national_id"]),
            rec["count"],
        ]
        for col, val in enumerate(row_data, 1):
            cell = ws.cell(row=data_start + i, column=col, value=val)
            cell.font = cell_font
            cell.border = thin_border
            if i % 2 == 0:
                cell.fill = alt_fill
        row_count = i

    for col_idx in range(1, num_cols + 1):
        max_len = 0
        for r in range(data_start, data_start + row_count + 1):
            cell = ws.cell(row=r, column=col_idx)
            max_len = max(max_len, len(str(cell.value or "")))
        ws.column_dimensions[chr(64 + col_idx)].width = min(max_len + 4, 40)

    add_excel_footer(ws, ctx, data_start + row_count, num_cols)
    log_export(
        request,
        "student_affairs.behavior_xlsx",
        rows=row_count,
        full_national_id=False,
        object_repr="إحصائيات السلوك Excel",
    )
    return excel_to_response(wb, generate_export_filename("behavior", "stats", "xlsx"))


@login_required
@capability_required("student_affairs.manage")
def tardiness_export_excel(request):
    """تصدير قائمة المتأخرين ليوم محدد."""
    import openpyxl
    from openpyxl.styles import Alignment

    school = request.school

    date_str = request.GET.get("date")
    if date_str:
        try:
            from datetime import date as date_type

            selected_date = date_type.fromisoformat(date_str)
        except ValueError:
            selected_date = timezone.localdate()
    else:
        selected_date = timezone.localdate()

    ctx = get_export_context(
        request, f"تقرير التأخر الصباحي — {selected_date.strftime('%d/%m/%Y')}"
    )

    late_records = (
        StudentAttendance.objects.filter(
            school=school,
            status="late",
            session__date=selected_date,
        )
        .select_related("student", "session__class_group", "session__subject")
        .order_by(grade_order("session__class_group__grade"), "student__full_name")
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "التأخر"
    ws.sheet_view.rightToLeft = True

    cumulative_counts = dict(
        StudentAttendance.objects.filter(
            school=school,
            status="late",
            session__class_group__academic_year=academic_year_for(request),
        )
        .values("student_id")
        .annotate(total=Count("id"))
        .values_list("student_id", "total")
    )

    headers = [
        "#",
        "اسم الطالب",
        "الصف",
        "الشعبة",
        "التكرار",
        "توقيت التسجيل",
        "الملاحظات",
        "المادة",
        "مرفق",
    ]
    num_cols = len(headers)
    data_start = add_excel_header(ws, ctx, num_cols)

    table = excel_table_styles()
    header_fill, header_font, cell_font = table.header_fill, table.header_font, table.cell_font
    thin_border, alt_fill = table.border, table.alt_fill

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=data_start, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border

    row_count = 0
    for i, rec in enumerate(late_records, 1):
        subject_name = rec.session.subject.name_ar if rec.session.subject else "—"
        recorded_time = (
            rec.tardiness_recorded_at.strftime("%H:%M") if rec.tardiness_recorded_at else "—"
        )
        has_file = "نعم" if rec.excuse_file else "—"
        row_data = [
            i,
            rec.student.full_name,
            rec.session.class_group.grade,
            rec.session.class_group.section,
            cumulative_counts.get(rec.student_id, 0),
            recorded_time,
            rec.excuse_notes or "—",
            subject_name,
            has_file,
        ]
        for col, val in enumerate(row_data, 1):
            cell = ws.cell(row=data_start + i, column=col, value=val)
            cell.font = cell_font
            cell.border = thin_border
            if i % 2 == 0:
                cell.fill = alt_fill
        row_count = i

    for col_idx in range(1, num_cols + 1):
        col_letter = (
            chr(64 + col_idx)
            if col_idx <= 26
            else chr(64 + (col_idx - 1) // 26) + chr(65 + (col_idx - 1) % 26)
        )
        max_len = 0
        for r in range(data_start, data_start + row_count + 1):
            cell = ws.cell(row=r, column=col_idx)
            max_len = max(max_len, len(str(cell.value or "")))
        ws.column_dimensions[col_letter].width = min(max_len + 4, 40)

    add_excel_footer(ws, ctx, data_start + row_count, num_cols)
    log_export(
        request,
        "student_affairs.tardiness_xlsx",
        rows=row_count,
        object_repr=f"المتأخّرون Excel — {selected_date:%Y-%m-%d}",
    )
    return excel_to_response(wb, generate_export_filename("tardiness", "daily", "xlsx"))


@login_required
@capability_required("student_affairs.activities")
def activities_export_excel(request):
    """تصدير قائمة الأنشطة والإنجازات."""
    import openpyxl
    from openpyxl.styles import Alignment

    school = request.school
    ctx = get_export_context(request, "تقرير الأنشطة والإنجازات")

    type_map = dict(StudentActivity.TYPE_CHOICES)
    scope_map = dict(StudentActivity.SCOPE_CHOICES)

    activities = (
        StudentActivity.objects.filter(school=school).select_related("student").order_by("-date")
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "الأنشطة"
    ws.sheet_view.rightToLeft = True

    headers = ["#", "اسم الطالب", "النشاط", "النوع", "النطاق", "التاريخ"]
    num_cols = len(headers)
    data_start = add_excel_header(ws, ctx, num_cols)

    table = excel_table_styles()
    header_fill, header_font, cell_font = table.header_fill, table.header_font, table.cell_font
    thin_border, alt_fill = table.border, table.alt_fill

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=data_start, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border

    row_count = 0
    for i, act in enumerate(activities, 1):
        row_data = [
            i,
            act.student.full_name,
            act.title,
            type_map.get(act.activity_type, act.activity_type),
            scope_map.get(act.scope, act.scope),
            act.date.strftime("%d/%m/%Y") if act.date else "—",
        ]
        for col, val in enumerate(row_data, 1):
            cell = ws.cell(row=data_start + i, column=col, value=val)
            cell.font = cell_font
            cell.border = thin_border
            if i % 2 == 0:
                cell.fill = alt_fill
        row_count = i

    for col_idx in range(1, num_cols + 1):
        max_len = 0
        for r in range(data_start, data_start + row_count + 1):
            cell = ws.cell(row=r, column=col_idx)
            max_len = max(max_len, len(str(cell.value or "")))
        ws.column_dimensions[chr(64 + col_idx)].width = min(max_len + 4, 40)

    add_excel_footer(ws, ctx, data_start + row_count, num_cols)
    log_export(
        request,
        "student_affairs.activities_xlsx",
        rows=row_count,
        object_repr="الأنشطة والإنجازات Excel",
    )
    return excel_to_response(wb, generate_export_filename("activities", "list", "xlsx"))


# ═════════════════════════════════════════════════════════════════════
# تصديرات PDF — حضور + سلوك + تأخر
# ═════════════════════════════════════════════════════════════════════


@login_required
@capability_required("student_affairs.manage")
def attendance_overview_pdf(request):
    """تصدير إحصائيات الحضور والغياب — PDF."""
    school = request.school
    today = timezone.localdate()

    # ── إحصائيات اليوم ──
    today_qs = StudentAttendance.objects.filter(school=school, session__date=today)
    total_today = today_qs.count()
    present = today_qs.filter(status="present").count()
    absent = today_qs.filter(status="absent").count()
    late = today_qs.filter(status="late").count()
    excused = today_qs.filter(status="excused").count()
    pct = attendance_rate(present, total_today)

    summary = {
        "present": present,
        "absent": absent,
        "late": late,
        "excused": excused,
        "total": total_today,
        "pct": pct,
    }

    # ── أكثر 20 طالب غياباً (آخر 30 يوم) ──
    thirty_days_ago = today - timedelta(days=30)
    worst_students = (
        StudentAttendance.objects.filter(
            school=school,
            status="absent",
            session__date__gte=thirty_days_ago,
        )
        .values("student__id", "student__full_name")
        .annotate(absence_count=Count("id"))
        .order_by("-absence_count")[:20]
    )

    ctx = get_export_context(request, "تقرير الحضور والغياب")
    pdf_header = get_pdf_header_html(ctx)
    pdf_footer = get_pdf_footer_html(ctx)

    html = render_to_string(
        "student_affairs/attendance_overview_pdf.html",
        {
            "summary": summary,
            "today": today,
            "worst_students": worst_students,
            "pdf_header": pdf_header,
            "pdf_footer": pdf_footer,
            **ctx,
        },
    )

    log_export(
        request,
        "student_affairs.attendance_overview_pdf",
        rows=len(worst_students),
        object_repr=f"تقرير الحضور والغياب — {today:%Y-%m-%d}",
    )
    filename = generate_export_filename("attendance", "overview", "pdf")
    return render_pdf(html, filename, paper_size="A4")


@login_required
@capability_required("student_affairs.manage")
def behavior_overview_pdf(request):
    """تصدير ملخص السلوك — PDF."""
    school = request.school
    today = timezone.localdate()

    # ── مخالفات العام الدراسي ──
    # كان الترشيح `date__year` — أي السنة الميلادية. والعام يمتدّ أغسطس–يونيو،
    # فيسقط الفصل الأول كلّه في يناير والعنوان يقول «السنة الحالية».
    _start, _end = _behaviour_window(school, today)
    year_infractions = BehaviorInfraction.objects.filter(
        school=school,
        date__gte=_start,
        date__lte=_end,
    )
    total_infractions = year_infractions.count()
    unresolved = year_infractions.filter(is_resolved=False).count()

    # ── نسبة المخالفين ──
    students_with_infractions = year_infractions.values("student").distinct().count()
    total_students = Membership.objects.filter(
        school=school,
        role__name="student",
        is_active=True,
    ).count()
    infraction_pct = (
        round(students_with_infractions * 100 / total_students) if total_students else 0
    )

    # ── توزيع حسب الدرجة — نظام النقاط ملغى ──
    degree_distribution = (
        year_infractions.values("violation_category__degree")
        .annotate(count=Count("id"))
        .order_by("violation_category__degree")
    )
    degree_rows = []
    for row in degree_distribution:
        deg = row["violation_category__degree"]
        if deg:
            degree_rows.append({"degree": deg, "count": row["count"]})

    # ── أكثر 15 طالب مخالفات — مرتبة حسب العدد ──
    worst_students = (
        year_infractions.values("student__id", "student__full_name")
        .annotate(infraction_count=Count("id"))
        .order_by("-infraction_count")[:15]
    )

    ctx = get_export_context(request, "تقرير السلوك")
    pdf_header = get_pdf_header_html(ctx)
    pdf_footer = get_pdf_footer_html(ctx)

    html = render_to_string(
        "student_affairs/behavior_overview_pdf.html",
        {
            "today": today,
            "total_infractions": total_infractions,
            "unresolved": unresolved,
            "infraction_pct": infraction_pct,
            "degree_rows": degree_rows,
            "worst_students": worst_students,
            "pdf_header": pdf_header,
            "pdf_footer": pdf_footer,
            **ctx,
        },
    )

    log_export(
        request,
        "student_affairs.behavior_overview_pdf",
        rows=len(worst_students),
        object_repr=f"تقرير السلوك — {today:%Y-%m-%d}",
    )
    filename = generate_export_filename("behavior", "overview", "pdf")
    return render_pdf(html, filename, paper_size="A4")


@login_required
@capability_required("student_affairs.manage")
def tardiness_pdf(request):
    """تصدير قائمة المتأخرين — PDF."""
    school = request.school

    date_str = request.GET.get("date")
    if date_str:
        try:
            from datetime import date as date_type

            selected_date = date_type.fromisoformat(date_str)
        except ValueError:
            selected_date = timezone.localdate()
    else:
        selected_date = timezone.localdate()

    late_records = list(
        StudentAttendance.objects.filter(
            school=school,
            status="late",
            session__date=selected_date,
        )
        .select_related("student", "session__class_group", "session__subject")
        .order_by(
            grade_order("session__class_group__grade"),
            "session__class_group__section",
            "student__full_name",
        )
    )

    total_late = len(late_records)

    cumulative_counts = dict(
        StudentAttendance.objects.filter(
            school=school,
            status="late",
            session__class_group__academic_year=academic_year_for(request),
        )
        .values("student_id")
        .annotate(total=Count("id"))
        .values_list("student_id", "total")
    )
    for rec in late_records:
        rec.cumulative = cumulative_counts.get(rec.student_id, 0)

    # نسبة التأخر
    total_students_today = (
        StudentAttendance.objects.filter(
            school=school,
            session__date=selected_date,
        )
        .values("student")
        .distinct()
        .count()
    )
    late_pct = round(total_late * 100 / total_students_today) if total_students_today else 0

    # التأخر هذا الأسبوع
    week_start = selected_date - timedelta(days=selected_date.weekday())
    weekly_late = StudentAttendance.objects.filter(
        school=school,
        status="late",
        session__date__gte=week_start,
        session__date__lte=selected_date,
    ).count()

    ctx = get_export_context(request, "تقرير التأخر الصباحي")
    pdf_header = get_pdf_header_html(ctx)
    pdf_footer = get_pdf_footer_html(ctx)

    html = render_to_string(
        "student_affairs/tardiness_pdf.html",
        {
            "selected_date": selected_date,
            "late_records": late_records,
            "total_late": total_late,
            "late_pct": late_pct,
            "weekly_late": weekly_late,
            "pdf_header": pdf_header,
            "pdf_footer": pdf_footer,
            **ctx,
        },
    )

    log_export(
        request,
        "student_affairs.tardiness_pdf",
        rows=total_late,
        object_repr=f"المتأخّرون — {selected_date:%Y-%m-%d}",
    )
    filename = generate_export_filename("tardiness", "list", "pdf")
    return render_pdf(html, filename, paper_size="A4")


# ═════════════════════════════════════════════════════════════════════
# تسجيل التأخير الصباحي — SOS-20260504-5191
# ═════════════════════════════════════════════════════════════════════


@login_required
@capability_required("student_affairs.manage")
def tardiness_search_students(request):
    """HTMX — بحث عن طلاب بالاسم لتسجيل تأخير."""
    from django.http import JsonResponse

    q = request.GET.get("q", "").strip()
    school = request.school
    today = timezone.localdate()

    if len(q) < 2:
        return JsonResponse({"results": []})

    students = (
        CustomUser.objects.filter(
            memberships__school=school,
            memberships__role__name="student",
            memberships__is_active=True,
            full_name__icontains=q,
        )
        .distinct()
        .values("id", "full_name", "national_id")[:15]
    )

    already_late_ids = set(
        StudentAttendance.objects.filter(
            school=school,
            status="late",
            session__date=today,
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


@login_required
@capability_required("student_affairs.manage")
@require_POST
def tardiness_record(request):
    """POST — تسجيل تأخير صباحي لطالب."""
    school = request.school
    today = timezone.localdate()
    now = timezone.localtime()

    student_id = request.POST.get("student_id")
    excuse_minutes = request.POST.get("excuse_minutes", "").strip()
    excuse_file = request.FILES.get("excuse_file")

    # ── File validation (قبل أي عملية DB) ──
    if excuse_file:
        allowed_ext = (".pdf", ".jpg", ".jpeg", ".png")
        allowed_ct = ("application/pdf", "image/jpeg", "image/png")
        max_size = 5 * 1024 * 1024
        ext = os.path.splitext(excuse_file.name)[1].lower()
        if ext not in allowed_ext or excuse_file.content_type not in allowed_ct:
            messages.error(request, "نوع الملف غير مسموح — يُقبل: PDF, JPG, PNG فقط.")
            return redirect("student_affairs:tardiness_list")
        if excuse_file.size > max_size:
            messages.error(request, "حجم الملف يتجاوز 5 ميغابايت.")
            return redirect("student_affairs:tardiness_list")

    student = get_object_or_404(
        CustomUser,
        pk=student_id,
        memberships__school=school,
        memberships__role__name="student",
        memberships__is_active=True,
    )

    excuse_val = int(excuse_minutes) if excuse_minutes and excuse_minutes.isdigit() else None
    excuse_notes = f"إذن تأخير {excuse_val} دقيقة" if excuse_val else ""

    session = (
        Session.objects.filter(
            school=school,
            date=today,
            class_group__enrollments__student=student,
            class_group__enrollments__is_active=True,
        )
        .order_by("start_time")
        .first()
    )

    if not session:
        session = (
            Session.objects.filter(
                school=school,
                date=today,
            )
            .order_by("start_time")
            .first()
        )

    if not session:
        messages.error(request, "لا توجد حصة مجدولة اليوم لتسجيل التأخير.")
        return redirect("student_affairs:tardiness_list")

    attendance, created = StudentAttendance.objects.get_or_create(
        session=session,
        student=student,
        school=school,
        defaults={
            "status": "late",
            "tardiness_minutes": excuse_val,
            "excuse_notes": excuse_notes,
            "tardiness_recorded_at": now,
            "marked_by": request.user,
        },
    )

    if not created:
        attendance.status = "late"
        attendance.tardiness_minutes = excuse_val
        attendance.excuse_notes = excuse_notes
        attendance.tardiness_recorded_at = now
        attendance.marked_by = request.user
        attendance.save(
            update_fields=[
                "status",
                "tardiness_minutes",
                "excuse_notes",
                "tardiness_recorded_at",
                "marked_by",
                "updated_at",
            ]
        )

    if excuse_file:
        attendance.excuse_file = excuse_file
        attendance.save(update_fields=["excuse_file"])

    # ── Audit Trail (PDPPL) ──
    AuditLog.objects.create(
        user=request.user,
        school=school,
        action="create",
        model_name="other",
        object_id=str(attendance.pk),
        object_repr=f"تسجيل تأخير {student.full_name}",
        ip_address=request.META.get("REMOTE_ADDR"),
    )

    time_str = now.strftime("%H:%M")
    messages.success(request, f"تم تسجيل تأخير {student.full_name} — الساعة {time_str}")
    return redirect("student_affairs:tardiness_list")


@login_required
@capability_required("student_affairs.manage")
@require_POST
def tardiness_delete(request, pk):
    """حذف سجل تأخير (إعادته لحاضر)."""
    school = request.school
    rec = get_object_or_404(StudentAttendance, pk=pk, school=school, status="late")
    rec.status = "present"
    rec.tardiness_minutes = None
    rec.excuse_notes = ""
    rec.tardiness_recorded_at = None
    if rec.excuse_file:
        rec.excuse_file.delete(save=False)
    rec.excuse_file = ""
    rec.save(
        update_fields=[
            "status",
            "tardiness_minutes",
            "excuse_notes",
            "tardiness_recorded_at",
            "excuse_file",
            "updated_at",
        ]
    )

    # ── Audit Trail (PDPPL) ──
    AuditLog.objects.create(
        user=request.user,
        school=school,
        action="delete",
        model_name="other",
        object_id=str(rec.pk),
        object_repr=f"إلغاء تأخير {rec.student.full_name}",
        ip_address=request.META.get("REMOTE_ADDR"),
    )

    messages.success(request, f"تم إلغاء تأخير {rec.student.full_name}")
    return redirect("student_affairs:tardiness_list")
