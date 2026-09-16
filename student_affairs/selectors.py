"""قراءاتُ شؤون الطلاب — دوالُّ تُرجع QuerySet أو قاموساً، ولا تكتب شيئاً.

كانت هذه الاستعلاماتُ في العروض نفسِها: `student_list` مئتا سطرٍ بخمسةٍ
وثلاثين استدعاءَ ORM، و`tardiness_list` و`tardiness_pdf` و`tardiness_export_excel`
تكتب استعلامَ التأخّر التراكميّ ثلاثَ مرّاتٍ بحروفه. فالعرضُ الآن يقرأ الطلبَ
ويختار القالب، والقراءةُ هنا مرّةً واحدة — تُختبر بلا طلبٍ ولا قالب
(`tests/test_student_affairs_selectors.py`).

والكتابةُ ليست هنا: `services.py` بـ`transaction.atomic`. انظر
`docs/architecture/layering.md`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, TypeVar

from django.db.models import (
    CharField,
    Count,
    Exists,
    F,
    Func,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Value,
)

from assessments.models import AnnualSubjectResult
from behavior.models import BehaviorInfraction
from clinic.models import ClinicVisit, HealthRecord
from core import academic_calendar, sorting
from core.domain.attendance import attendance_rate, percent
from core.models.academic import (
    ClassGroup,
    ParentStudentLink,
    StudentEnrollment,
    Wing,
    grade_number,
    grade_order,
)
from core.models.access import Membership
from core.models.school import School
from core.models.user import CustomUser
from core.sorting import blank_as_null, normalise_arabic
from library.models import BookBorrowing
from operations.models import Session, StudentAttendance

from .models import StudentActivity, StudentTransfer

if TYPE_CHECKING:
    from wings.scope import StudentScope

#: دالّتان في النواة بلا أنواع — تُقرآن هنا بتوقيعٍ صريح فيبقى هذا الملفُّ صفراً في mypy
#: دون أن يُمسّ عددُ أخطاء `core/` في سقّاطة الأنواع.
academic_year_window: Callable[[School], tuple[date, date] | None] = (
    academic_calendar.academic_year_window
)
arabic_key: Callable[[F], Any] = sorting.arabic_key

_Q = TypeVar("_Q", bound=QuerySet)


# ─── نطاقُ صاحب الطلب ──────────────────────────────────────────────────────
#
# المشرفُ الإداريُّ يقرأ طلبةَ جناحه وحدَهم (قرارا المستخدم 2026-09-14 و2026-09-15).
# والسؤالُ «من في نطاقه؟» في `wings/scope.py` وحدَه: القراءةُ هنا تأخذ نطاقاً اختياريّاً
# وتمرّ عليه **قبل** المرشِّحات والعدّ والاقتطاع. و`None` — أو نطاقُ القيادة — يُعيد
# الاستعلامَ كما هو بلا استعلامٍ زائد.


def _narrow(scope: StudentScope | None, qs: _Q, student_path: str = "student_id") -> _Q:
    return qs if scope is None else scope.narrow(qs, student_path)  # type: ignore[return-value]


def _narrow_classes(scope: StudentScope | None, qs: _Q, class_path: str = "class_group") -> _Q:
    return qs if scope is None else scope.narrow_classes(qs, class_path)  # type: ignore[return-value]


def _wing_bound(scope: StudentScope | None) -> bool:
    return scope is not None and scope.is_wing_bound


# ─── سجلّ الطلاب ───────────────────────────────────────────────────────────


def student_memberships(school: School) -> QuerySet[Membership]:
    """عضويّاتُ الطلبة النشطة في المدرسة — أساسُ السجلّ وعدِّ الطلبة."""
    return Membership.objects.filter(school=school, role__name="student", is_active=True)


def _enrolled_in(
    school: School, year: str, scope: StudentScope | None = None, **class_group: str
) -> Exists:
    lookups = {f"class_group__{field}": value for field, value in class_group.items()}
    return Exists(
        _narrow_classes(
            scope,
            StudentEnrollment.objects.filter(
                class_group__school=school,
                class_group__academic_year=year,
                is_active=True,
                student_id=OuterRef("user_id"),
                **lookups,
            ),
        )
    )


def _grade_sort_key() -> Func:
    """«G10» نصّاً يسبق «G7»، وعدداً يليه — فيُحشى الجزءُ الرقميُّ بصفر.

    تُنزع الحروفُ أوّلاً: `RIGHT('G7', 2)` تلتقط الحرفَ فتُعيد «G7»، و«10» أصغرُ
    من «G7» في ترتيب المحارف. ومن لا قيدَ له يبقى عَدَماً فيسقط إلى الذيل في
    الاتّجاهين لا يتصدّر التنازليّ.
    """
    digits = Func(
        F("grade_code"),
        Value(r"\D"),
        Value(""),
        Value("g"),
        function="REGEXP_REPLACE",
        output_field=CharField(),
    )
    return Func(digits, Value(2), Value("0"), function="LPAD", output_field=CharField())


def student_register(
    school: School,
    year: str,
    *,
    grade: str = "",
    section: str = "",
    parent_status: str = "",
    status: str = "enrolled",
    q: str = "",
    scope: StudentScope | None = None,
) -> QuerySet[Membership]:
    """سجلُّ الطلبة مرشَّحاً ومعلَّماً بما يُعرض ويُفرز — بلا ترتيبٍ نهائيّ.

    العضويّةُ تقول «هذا طالبُ المدرسة» والقيدُ يقول «هذا صفُّه هذا العام»، وهما
    شيئان: من نُقل هذا الصيفَ أُغلق قيدُه وبقيت عضويّتُه. فالافتراضُ المقيَّدون
    (`status="enrolled"`)، ومن لا قيدَ له يُرى بترشيحٍ صريح (`unenrolled`/`all`).

    والصفُّ والشعبةُ ووليُّ الأمر تُجلب بالاستعلام نفسِه ليصحّ الفرزُ بها على
    السجلّ كلِّه لا على الصفحة الظاهرة. والبحثُ يقع على الرقم **الكامل** لا
    على المستور.

    والنطاقُ على الاستعلام الأساسيّ **قبل** كلّ مرشِّحٍ وفرزٍ وترقيم، فالعددُ والصفحاتُ
    والبحثُ بالرقم الشخصيّ لا تبلغ طالباً خارجه؛ والصفُّ والشعبةُ من شُعب الجناح وحدها.
    """
    students = _narrow(
        scope,
        student_memberships(school)
        .select_related("user", "user__profile")
        .order_by("user__full_name"),
        "user_id",
    )
    if grade:
        students = students.filter(_enrolled_in(school, year, scope, grade=grade))
    if section:
        students = students.filter(_enrolled_in(school, year, scope, section=section))
    if parent_status in ("linked", "unlinked"):
        has_parent = Exists(
            ParentStudentLink.objects.filter(school=school, student_id=OuterRef("user_id"))
        )
        students = students.annotate(_has_parent=has_parent).filter(
            _has_parent=parent_status == "linked"
        )

    is_enrolled = _enrolled_in(school, year)
    if status == "enrolled":
        students = students.filter(is_enrolled)
    elif status == "unenrolled":
        students = students.exclude(is_enrolled)

    enrolment = _narrow_classes(
        scope,
        StudentEnrollment.objects.filter(
            student_id=OuterRef("user_id"),
            class_group__academic_year=year,
            is_active=True,
        ),
    ).order_by("-class_group__academic_year", "-enrolled_at")
    # وليُّ الأمر: الأساسيُّ أوّلاً، فإن لم يُعلَّم أحدٌ فأقدمُ ارتباط.
    guardian = ParentStudentLink.objects.filter(
        student_id=OuterRef("user_id"), school=school
    ).order_by("-is_primary", "created_at")

    students = students.annotate(
        grade_code=Subquery(enrolment.values("class_group__grade")[:1]),
        section_code=Subquery(enrolment.values("class_group__section")[:1]),
        name_key=arabic_key(F("user__full_name")),
        national_key=blank_as_null("user__national_id"),
        guardian_name=Subquery(guardian.values("parent__full_name")[:1]),
        guardian_phone=Subquery(guardian.values("parent__phone")[:1]),
        guardian_relation=Subquery(guardian.values("relationship")[:1]),
    ).annotate(
        grade_key=_grade_sort_key(),
        section_key=blank_as_null("section_code"),
        guardian_key=arabic_key(F("guardian_name")),
    )

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
    return students


def guardian_relation_labels() -> dict[str, str]:
    """الصلةُ بعنوانها العربيّ — من النموذج نفسِه فلا قاموسَ ثانٍ يتخلّف عنه."""
    return dict(ParentStudentLink.RELATIONSHIP)


def register_filter_options(
    school: School, year: str, scope: StudentScope | None = None
) -> tuple[list[str], QuerySet]:
    """(الصفوفُ بترتيبها العدديّ، الشُّعبُ بلا تكرار) — خياراتُ ترشيح السجلّ، من شُعب الجناح للمقيَّد."""
    active = _narrow_classes(
        scope, ClassGroup.objects.filter(school=school, academic_year=year, is_active=True), "pk"
    )
    grades = sorted(set(active.values_list("grade", flat=True)), key=grade_number)
    sections = active.values_list("section", flat=True).distinct().order_by("section")
    return grades, sections


def students_for_export(
    school: School, year: str, *, q: str = "", grade: str = "", section: str = ""
) -> list[tuple[Membership, dict[str, Any]]]:
    """(العضويّة، قيدُها) لتصدير السجلّ — بترشيح التصدير كما كان: الاسمُ والرقمُ حرفيّاً."""
    students = student_memberships(school).select_related("user").order_by("user__full_name")
    if q:
        students = students.filter(
            Q(user__full_name__icontains=q) | Q(user__national_id__icontains=q)
        )

    enrolments = {
        row["student_id"]: row
        for row in StudentEnrollment.objects.filter(
            class_group__school=school,
            class_group__academic_year=year,
            is_active=True,
        ).values("student_id", "class_group__grade", "class_group__section")
    }
    if grade:
        students = students.filter(
            user_id__in=[
                sid for sid, row in enrolments.items() if row["class_group__grade"] == grade
            ]
        )
    if section:
        students = students.filter(
            user_id__in=[
                sid for sid, row in enrolments.items() if row.get("class_group__section") == section
            ]
        )
    return [(m, enrolments.get(m.user_id, {})) for m in students]


# ─── ملفّ الطالب ───────────────────────────────────────────────────────────


def current_enrolment(student: CustomUser, year: str) -> StudentEnrollment | None:
    enrolment: StudentEnrollment | None = (
        StudentEnrollment.objects.filter(
            student=student, class_group__academic_year=year, is_active=True
        )
        .select_related("class_group")
        .first()
    )
    return enrolment


def guardian_links(student: CustomUser, school: School) -> QuerySet[ParentStudentLink]:
    return ParentStudentLink.objects.filter(student=student, school=school).select_related("parent")


def annual_results(student: CustomUser, school: School, year: str) -> QuerySet[AnnualSubjectResult]:
    return (
        AnnualSubjectResult.objects.filter(student=student, school=school, academic_year=year)
        .select_related("setup__subject", "setup__class_group")
        .order_by("setup__subject__name_ar")
    )


def recent_activities(
    student: CustomUser, school: School, limit: int = 10
) -> QuerySet[StudentActivity]:
    return StudentActivity.objects.filter(student=student, school=school).order_by("-date")[:limit]


def student_infractions(student: CustomUser, school: School) -> QuerySet[BehaviorInfraction]:
    return (
        BehaviorInfraction.objects.filter(student=student, school=school)
        .select_related("violation_category")
        .order_by("-date")
    )


def student_profile_records(
    student: CustomUser, school: School, year: str, scope: StudentScope | None = None
) -> dict[str, Any]:
    """ما يجمعه ملفُّ الطالب من سبعة تطبيقات — بمفاتيح سياق الصفحة نفسِها.

    الحضورُ على نافذة **العام الدراسي** لا السنة الميلادية: العامُ يمتدّ من
    أغسطس إلى يونيو، والترشيحُ بـ`session__date__year=` كان يعرض في سبتمبر
    ثلاثةَ أسابيع ويُسقط في يناير الفصلَ الأوّل كلَّه.

    وللمقيَّد بجناحه (قرارُ المستخدم 2026-09-15) لا تُحسب: الدرجاتُ، وفصيلةُ الدم
    وأسبابُ زيارات العيادة (تاريخُ الزيارة و«أُعيد إلى المنزل» وحدَهما)، والإعاراتُ،
    والأنشطةُ، والانتقالات.
    """
    window = academic_year_window(school)
    # لا نافذةَ إلّا لاسم عامٍ لا يُقرأ — وكانت الصفحةُ تسقط عندها كذلك (`window[0]`).
    assert window is not None, f"لا نافذةَ للعام الدراسي في {school}"
    attendance = StudentAttendance.objects.filter(
        student=student,
        school=school,
        session__date__gte=window[0],
        session__date__lte=window[1],
    ).aggregate(
        present=Count("id", filter=Q(status="present")),
        absent=Count("id", filter=Q(status="absent")),
        late=Count("id", filter=Q(status="late")),
        excused=Count("id", filter=Q(status="excused")),
        total=Count("id"),
    )
    # بصيغة العرض قبل الترحيل — `attendance_rate` تُقرّب الأنصافَ غيرَها (23 من 80: 28.7 لا 28.8).
    attendance["pct"] = (
        round(attendance["present"] / attendance["total"] * 100, 1) if attendance["total"] else 0
    )

    infractions = student_infractions(student, school)
    by_level = infractions.aggregate(
        total=Count("id"),
        **{f"level_{lvl}": Count("id", filter=Q(level=lvl)) for lvl in range(1, 5)},
    )
    limited = _wing_bound(scope)

    visits = ClinicVisit.objects.filter(student=student, school=school).order_by("-visit_date")
    if scope is not None and scope.clinic_summary_only:
        # التاريخُ و«أُعيد إلى المنزل» وحدَهما يبلغان القالب — لا السببُ ولا الحرارة.
        clinic: dict[str, Any] = {
            "clinic_visits": visits.values("visit_date", "is_sent_home")[:5],
            "health_record": None,
        }
    else:
        clinic = {
            "clinic_visits": visits[:5],
            "health_record": HealthRecord.objects.filter(student=student).first(),
        }

    if scope is not None and scope.hides_grades:
        grades: QuerySet[AnnualSubjectResult] = AnnualSubjectResult.objects.none()
        grades_summary: dict[str, int] = {}
    else:
        grades = annual_results(student, school, year)
        grades_summary = grades.aggregate(
            total_subjects=Count("id"),
            passed=Count("id", filter=Q(status="pass")),
            failed=Count("id", filter=Q(status="fail")),
        )

    if limited:
        # الإعاراتُ والأنشطةُ والانتقالاتُ ليست من متابعة المشرف — فلا تُحسب له.
        follow_up: dict[str, Any] = {"borrowings": [], "activities": [], "transfers": []}
    else:
        follow_up = {
            "borrowings": BookBorrowing.objects.filter(user=student)
            .select_related("book")
            .order_by("-borrow_date")[:5],
            "activities": recent_activities(student, school),
            "transfers": StudentTransfer.objects.filter(student=student, school=school).order_by(
                "-created_at"
            )[:5],
        }

    return {
        "enrollment": current_enrolment(student, year),
        "parent_links": guardian_links(student, school),
        "attendance": attendance,
        # نظامُ النقاط ملغى — الملخّصُ عددُ المخالفات وحدَه.
        "behavior": {
            "total": by_level["total"],
            "by_level": {lvl: by_level[f"level_{lvl}"] for lvl in range(1, 5)},
            "recent": infractions[:5],
        },
        **clinic,
        "grades": grades,
        "grades_summary": grades_summary,
        **follow_up,
    }


def student_profile_pdf_records(
    student: CustomUser,
    school: School,
    year: str,
    today: date,
    scope: StudentScope | None = None,
) -> dict[str, Any]:
    """ما تطبعه وثيقةُ ملفّ الطالب: حضورُ ثلاثين يوماً، وآخرُ عشرين مخالفة.

    وللمقيَّد بجناحه: لا درجاتٍ ولا أنشطة — فوثيقتُه متابعةٌ لا وثيقةٌ رسميّة.
    """
    limited = _wing_bound(scope)
    attendance = (
        StudentAttendance.objects.filter(
            school=school, student=student, session__date__gte=today - timedelta(days=30)
        )
        .select_related("session__subject")
        .order_by("-session__date")
    )
    summary = attendance.aggregate(
        total=Count("id"),
        present=Count("id", filter=Q(status="present")),
        absent=Count("id", filter=Q(status="absent")),
        late=Count("id", filter=Q(status="late")),
    )
    return {
        "enrollment": current_enrolment(student, year),
        "attendance": attendance[:15],
        "att_summary": summary,
        "infractions": student_infractions(student, school)[:20],
        "grades": (
            AnnualSubjectResult.objects.none()
            if scope is not None and scope.hides_grades
            else annual_results(student, school, year)
        ),
        "activities": (
            StudentActivity.objects.none() if limited else recent_activities(student, school)
        ),
        "parent_links": guardian_links(student, school),
    }


# ─── الحضور والغياب ────────────────────────────────────────────────────────


def absence_ranking(
    school: School, since: date, *fields: str, scope: StudentScope | None = None
) -> QuerySet:
    """الغائبون منذ `since` مرتّبين بعدد غيابهم — الحقولُ المطلوبةُ وحدها.

    والأكثرُ غياباً يُحسب داخل النطاق قبل الاقتطاع — لا عشرون المدرسةِ ثمّ يُصفّى.
    """
    ranking: QuerySet = (
        _narrow(
            scope,
            StudentAttendance.objects.filter(
                school=school, status="absent", session__date__gte=since
            ),
        )
        .values(*fields)
        .annotate(absence_count=Count("id"))
        .order_by("-absence_count")
    )
    return ranking


def attendance_by_grade_on(
    school: School, day: date, scope: StudentScope | None = None
) -> QuerySet:
    return (
        _narrow(scope, StudentAttendance.objects.filter(school=school, session__date=day))
        .values("session__class_group__grade")
        .annotate(
            total=Count("id"),
            present_count=Count("id", filter=Q(status="present")),
            absent_count=Count("id", filter=Q(status="absent")),
            late_count=Count("id", filter=Q(status="late")),
        )
        .order_by(grade_order("session__class_group__grade"))
    )


@dataclass(frozen=True)
class DailyTrend:
    labels: list[str]
    present: list[int]
    absent: list[int]


def daily_attendance_trend(
    school: School, today: date, days: int = 14, scope: StudentScope | None = None
) -> DailyTrend:
    """نسبتا الحضور والغياب لكلّ يومٍ من آخر `days` — استعلامٌ واحدٌ مجمَّعٌ باليوم."""
    start = today - timedelta(days=days - 1)
    by_day = {
        row["session__date"]: row
        for row in _narrow(
            scope,
            StudentAttendance.objects.filter(
                school=school, session__date__gte=start, session__date__lte=today
            ),
        )
        .values("session__date")
        .annotate(
            total=Count("id"),
            present=Count("id", filter=Q(status="present")),
            absent=Count("id", filter=Q(status="absent")),
        )
    }
    trend = DailyTrend([], [], [])
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        row = by_day.get(day, {"total": 0, "present": 0, "absent": 0})
        trend.labels.append(day.strftime("%m/%d"))
        trend.present.append(attendance_rate(row["present"], row["total"]))
        trend.absent.append(attendance_rate(row["absent"], row["total"]))
    return trend


def attendance_on_by_class(
    school: School, day: date, scope: StudentScope | None = None
) -> QuerySet[StudentAttendance]:
    """سجلُّ حضور يومٍ مرتّباً بالصفّ ثمّ الاسم — ورقةُ «حضور اليوم» في التصدير."""
    return (
        _narrow(scope, StudentAttendance.objects.filter(school=school, session__date=day))
        .select_related("student", "session__class_group")
        .order_by(grade_order("session__class_group__grade"), "student__full_name")
    )


# ─── السلوك ────────────────────────────────────────────────────────────────


def behaviour_window(school: School, today: date) -> tuple[date, date]:
    """نافذةُ العام الدراسي — وترتدّ إلى السنة الميلادية إن لم يُبذر تقويم."""
    window = academic_year_window(school)
    if window is not None:
        return window
    return date(today.year, 1, 1), date(today.year, 12, 31)


def behaviour_year_summary(
    school: School, today: date, scope: StudentScope | None = None
) -> dict[str, Any]:
    """مخالفاتُ العام الدراسي: العدد، وغيرُ المحلول، ونسبةُ المخالفين، والدرجات، والأكثر.

    كان الترشيحُ `date__year` — السنةَ الميلاديّة؛ والعامُ يمتدّ أغسطس–يونيو،
    فيسقط الفصلُ الأوّل كلُّه في يناير والعنوانُ يقول «السنة الحالية».

    والمقيَّدُ بجناحه: كلُّ مخالفةٍ تمرّ على نطاقه أوّلاً، والمقامُ طلبةُ جناحه — لا
    المدرسةُ فتصغر النسبةُ كذباً.
    """
    start, end = behaviour_window(school, today)
    year_infractions = _narrow(
        scope, BehaviorInfraction.objects.filter(school=school, date__gte=start, date__lte=end)
    )
    offenders = year_infractions.values("student").distinct().count()
    if scope is not None and scope.is_wing_bound:
        total_students = len(scope.student_ids())
    else:
        total_students = student_memberships(school).count()
    degrees = (
        year_infractions.values("violation_category__degree")
        .annotate(count=Count("id"))
        .order_by("violation_category__degree")
    )
    return {
        "year_infractions": year_infractions,
        "total_infractions": year_infractions.count(),
        "unresolved": year_infractions.filter(is_resolved=False).count(),
        "students_with_infractions": offenders,
        "total_students": total_students,
        "infraction_pct": percent(offenders, total_students),
        # نظامُ النقاط ملغى — الدرجةُ (1–4) وحدها، وما لا درجةَ له لا يُعدّ.
        "degree_counts": [
            (row["violation_category__degree"], row["count"])
            for row in degrees
            if row["violation_category__degree"]
        ],
        "worst_students": year_infractions.values("student__id", "student__full_name")
        .annotate(infraction_count=Count("id"))
        .order_by("-infraction_count")[:15],
    }


def monthly_infraction_trend(
    school: School, today: date, months: int = 6, scope: StudentScope | None = None
) -> tuple[list[str], list[int]]:
    """(أسماءُ الأشهر، عددُ المخالفات) لآخر `months` أشهر — الشهرُ الجاري حتى اليوم."""
    labels, counts = [], []
    for back in range(months - 1, -1, -1):
        month_start = (today.replace(day=1) - timedelta(days=30 * back)).replace(day=1)
        if back > 0:
            next_month = (month_start + timedelta(days=32)).replace(day=1)
        else:
            next_month = today + timedelta(days=1)
        labels.append(month_start.strftime("%b"))
        counts.append(
            _narrow(
                scope,
                BehaviorInfraction.objects.filter(
                    school=school, date__gte=month_start, date__lt=next_month
                ),
            ).count()
        )
    return labels, counts


def infraction_counts_by_student(school: School, scope: StudentScope | None = None) -> QuerySet:
    """كلُّ المخالفات بالطالب، الأكثرُ أوّلاً — ورقةُ تصدير السلوك، مضيَّقةً قبل التجميع."""
    return (
        _narrow(scope, BehaviorInfraction.objects.filter(school=school))
        .values("student__full_name", "student__national_id")
        .annotate(count=Count("id"))
        .order_by("-count")
    )


# ─── التأخّر الصباحي ───────────────────────────────────────────────────────


def late_arrivals(
    school: School,
    day: date,
    *,
    grade: str = "",
    section: str = "",
    scope: StudentScope | None = None,
) -> QuerySet[StudentAttendance]:
    """المتأخّرون يومَ `day` — مرشَّحين بالصفّ والشعبة إن طُلبا، بلا ترتيب.

    والنطاقُ قبل المرشِّحَين: شعبةُ جناحٍ آخر مكتوبةٌ باليد في `?section=` تعطي قائمةً
    فارغة لا صفوفَه.
    """
    late = _narrow(
        scope, StudentAttendance.objects.filter(school=school, status="late", session__date=day)
    )
    if grade:
        late = late.filter(session__class_group__grade=grade)
    if section:
        late = late.filter(session__class_group__section=section)
    return late


def late_register(
    late: QuerySet[StudentAttendance], *, by_section: bool = True
) -> QuerySet[StudentAttendance]:
    """سجلُّ المتأخّرين للعرض: الصفّ، (فالشعبة)، فالاسم."""
    order = [grade_order("session__class_group__grade")]
    if by_section:
        order.append("session__class_group__section")
    return late.select_related("student", "session__class_group", "session__subject").order_by(
        *order, "student__full_name"
    )


def cumulative_late_counts(
    school: School, year: str, scope: StudentScope | None = None
) -> dict[Any, int]:
    """الطالب ← عددُ تأخّراته هذا العام — داخل النطاق وحدَه."""
    return dict(
        _narrow(
            scope,
            StudentAttendance.objects.filter(
                school=school, status="late", session__class_group__academic_year=year
            ),
        )
        .values("student_id")
        .annotate(total=Count("id"))
        .values_list("student_id", "total")
    )


def students_marked_on(school: School, day: date, scope: StudentScope | None = None) -> int:
    """عددُ الطلبة المرصودين يومَ `day` — مقامُ نسبة التأخّر."""
    return (
        _narrow(scope, StudentAttendance.objects.filter(school=school, session__date=day))
        .values("student")
        .distinct()
        .count()
    )


def late_this_week(school: School, day: date, scope: StudentScope | None = None) -> int:
    """المتأخّرون من أوّل الأسبوع حتى `day`."""
    week_start = day - timedelta(days=day.weekday())
    return _narrow(
        scope,
        StudentAttendance.objects.filter(
            school=school, status="late", session__date__gte=week_start, session__date__lte=day
        ),
    ).count()


def cancellable_late_records(
    school: School, scope: StudentScope | None, today: date
) -> QuerySet[StudentAttendance]:
    """سجلّاتُ التأخّر التي يُلغيها صاحبُ الطلب.

    المقيَّدُ بجناحه يُلغي تأخّراً صباحيّاً رُصد اليوم لطالبٍ من جناحه، ولا شيءَ غيرَه:
    تأخّرُ الحصّة من كشف الجناح (`tardiness_recorded_at` فارغ) يُصحَّح من الكشف،
    وتأخّرُ يومٍ مضى سجلٌّ لا يُمحى — وكلاهما 404 كصفِّ جناحٍ آخر.
    """
    late = StudentAttendance.objects.filter(school=school, status="late")
    if _wing_bound(scope):
        late = _narrow(scope, late.filter(session__date=today, tardiness_recorded_at__isnull=False))
    return late


def wing_names(wing_ids: Iterable[Any]) -> list[str]:
    """أسماءُ الأجنحة بترتيبها — لعناوين ما يعرضه المقيَّدُ بجناحه ويصدّره."""
    return list(
        Wing.objects.filter(pk__in=wing_ids)
        .order_by("order", "code")
        .values_list("name", flat=True)
    )


def late_by_class(late: QuerySet[StudentAttendance]) -> QuerySet:
    return (
        late.values("session__class_group__grade", "session__class_group__section")
        .annotate(count=Count("id"))
        .order_by(grade_order("session__class_group__grade"), "session__class_group__section")
    )


def late_by_stage(late: QuerySet[StudentAttendance]) -> list[dict[str, Any]]:
    """التأخّرُ بالمرحلة (إعدادي / ثانوي) بعنوانها العربيّ."""
    labels = dict(ClassGroup.LEVELS)
    return [
        {
            "stage_label": labels.get(
                row["session__class_group__level_type"], row["session__class_group__level_type"]
            ),
            "count": row["count"],
        }
        for row in late.values("session__class_group__level_type")
        .annotate(count=Count("id"))
        .order_by("session__class_group__level_type")
    ]


def tardiness_session(
    school: School, student: CustomUser, day: date, scope: StudentScope | None = None
) -> Session | None:
    """حصّةُ تسجيل التأخّر الصباحيّ: أوّلُ حصّةٍ لشعبة الطالب يومَ `day`، وإلّا أوّلُ حصّةٍ في المدرسة.

    والمقيَّدُ بجناحه: من شُعب جناحه وحدها، ولا رجوعَ إلى «أوّل حصّةٍ في المدرسة» — يعلّق
    التأخّرَ على شعبةٍ ليست شعبتَه؛ لا حصّةَ لشعبته اليوم يعني لا رصد.
    """
    sessions = Session.objects.filter(school=school, date=day).order_by("start_time")
    own = _narrow_classes(
        scope,
        sessions.filter(
            class_group__enrollments__student=student,
            class_group__enrollments__is_active=True,
        ),
    ).first()
    if own is not None or _wing_bound(scope):
        return own
    return sessions.first()
