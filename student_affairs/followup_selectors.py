"""قراءةُ جداول المتابعة (W-20261109-006): الحضورُ والسلوكُ والتأخّرُ والأنشطةُ والتحرّكات.

لكلّ جدولٍ **محدِّدٌ واحدٌ** `(user, params) -> list[dict]` تقرأ به الصفحةُ ويقرأ به Excel وPDF: نطاقُ الدور (جناحُ المشرف)
ثمّ الفلترُ كاملاً — لا صفحةَ الترقيم وحدَها — وفرزُ الجناح؛ والعمودُ «م» والأعمدةُ المخفيّةُ يتولّاها العقد (`table_rows`).
الأرقامُ الشخصيّةُ لا تدخل الصفوف: كشوفٌ جماعيّةٌ بالأسماء. والمواصفاتُ في `followup_tables.py`.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.db.models import Count
from django.utils import timezone

from core.academic_calendar import academic_year_for_school, academic_year_window
from core.exports.contract import wing_rank, wing_sorted
from core.labels import class_label
from core.models.academic import StudentEnrollment, grade_order
from wings.scope import StudentScope, student_scope

#: أكثرُ الطلاب غياباً: النافذةُ بالأيّام والاقتطاعُ كما كانت الشاشةُ تعرضهما.
ABSENCE_WINDOW_DAYS = 30
WORST_ABSENT_LIMIT = 20
WORST_BEHAVIOR_LIMIT = 15
#: الأنشطةُ المعروضةُ في الصفحة الواحدة — التصديرُ يأخذ كلَّ ما يطابق الفلتر.
ACTIVITY_PAGE_LIMIT = 200


def _scope_and_school(user: Any) -> tuple[StudentScope, Any]:
    school = user.get_school()
    return student_scope(user, school), school


def class_info(school: Any, year: str, student_ids: set[Any]) -> dict[Any, tuple[str, Any]]:
    """`{student_id: (الصفّ والشعبة، ترتيبُ الجناح)}` من القيد النشط الأحدث في العام — استعلامٌ واحدٌ للصفوف كلِّها."""
    found: dict[Any, tuple[str, Any]] = {}
    rows = (
        StudentEnrollment.objects.filter(
            student_id__in=student_ids,
            is_active=True,
            class_group__school=school,
            class_group__academic_year=year,
        )
        .newest_first()
        .values_list(
            "student_id", "class_group__grade", "class_group__section", "class_group__wing__order"
        )
    )
    for student_id, grade, section, wing_order in rows:
        found.setdefault(student_id, (class_label(grade, section), wing_order))
    return found


def _with_class(rows: list[dict[str, Any]], school: Any, year: str) -> list[dict[str, Any]]:
    """يضيف `class_label` و`wing_order` لكلّ صفٍّ بمعرّف طالبه ثمّ يفرزه بالجناح."""
    info = class_info(school, year, {row["id"] for row in rows})
    for row in rows:
        row["class_label"], row["wing_order"] = info.get(row["id"], ("—", None))
    return wing_sorted(rows)


def absence_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    """أكثرُ الطلاب غياباً (آخر 30 يوماً، بأيّام الغياب لا بسجلّات الحصص) داخل نطاق الدور."""
    from operations.models import StudentAttendance

    scope, school = _scope_and_school(user)
    since = timezone.localdate() - timedelta(days=ABSENCE_WINDOW_DAYS)
    worst = (
        scope.narrow(
            StudentAttendance.objects.filter(
                school=school, status="absent", session__date__gte=since
            )
        )
        .values("student__id", "student__full_name")
        .annotate(absence_count=Count("session__date", distinct=True))
        .order_by("-absence_count")[:WORST_ABSENT_LIMIT]
    )
    rows = [
        {
            "id": r["student__id"],
            "full_name": r["student__full_name"],
            "absence_count": r["absence_count"],
        }
        for r in worst
    ]
    return _with_class(rows, school, academic_year_for_school(school))


def behavior_window(school: Any, today: date) -> tuple[date, date]:
    """نافذةُ العام الدراسيّ للسلوك — وترتدّ إلى السنة الميلاديّة إن لم يُبذر تقويم."""
    window = academic_year_window(school)
    return window if window is not None else (date(today.year, 1, 1), date(today.year, 12, 31))


def behavior_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    """أكثرُ الطلاب مخالفاتٍ في العام الدراسيّ داخل نطاق الدور، مرتَّبين بالعدد."""
    from behavior.models import BehaviorInfraction

    scope, school = _scope_and_school(user)
    start, end = behavior_window(school, timezone.localdate())
    worst = (
        scope.narrow(
            BehaviorInfraction.objects.filter(school=school, date__gte=start, date__lte=end)
        )
        .values("student__id", "student__full_name")
        .annotate(infraction_count=Count("id"))
        .order_by("-infraction_count")[:WORST_BEHAVIOR_LIMIT]
    )
    rows = [
        {
            "id": r["student__id"],
            "full_name": r["student__full_name"],
            "infraction_count": r["infraction_count"],
        }
        for r in worst
    ]
    return _with_class(rows, school, academic_year_for_school(school))


def tardiness_day(params: Any) -> date:
    """اليومُ المختار من `?date=` — واليومُ إن غاب أو فسد."""
    try:
        return date.fromisoformat(params.get("date") or "")
    except ValueError:
        return timezone.localdate()


def tardiness_queryset(scope: StudentScope, school: Any, params: Any) -> Any:
    """سجلّاتُ تأخّر اليوم المختار داخل النطاق بمرشِّحَي الصفّ والشعبة — قبل الفرز.

    فشعبةُ جناحٍ آخر مكتوبةٌ باليد في `?section=` تعطي قائمةً فارغةً لا صفوفَه.
    """
    from operations.models import StudentAttendance

    late = scope.narrow(
        StudentAttendance.objects.filter(
            school=school, status="late", session__date=tardiness_day(params)
        )
    )
    if params.get("grade"):
        late = late.filter(session__class_group__grade=params["grade"])
    if params.get("section"):
        late = late.filter(session__class_group__section=params["section"])
    return late


def ordered_late_records(late: Any) -> list[Any]:
    """سجلّاتُ التأخّر مرتّبةً بالصفّ فالشعبة فالاسم ثمّ بالجناح (فرزٌ مستقرّ) — ترتيبُ الصفحة والملفّ معاً."""
    records = late.select_related(
        "student", "session__class_group__wing", "session__subject"
    ).order_by(
        grade_order("session__class_group__grade"),
        "session__class_group__section",
        "student__full_name",
    )

    def wing_of(rec: Any) -> int:
        wing = rec.session.class_group.wing
        return wing_rank(wing.order if wing else None)

    return sorted(records, key=wing_of)


def tardiness_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    """متأخّرو اليوم المختار بمرشِّحَي الصفّ والشعبة داخل نطاق الدور، مع عدّ تأخّراتهم التراكميّ هذا العام."""
    from operations.models import StudentAttendance

    scope, school = _scope_and_school(user)
    year = academic_year_for_school(school)
    records = ordered_late_records(tardiness_queryset(scope, school, params))
    cumulative = dict(
        scope.narrow(
            StudentAttendance.objects.filter(
                school=school, status="late", session__class_group__academic_year=year
            )
        )
        .values("student_id")
        .annotate(total=Count("id"))
        .values_list("student_id", "total")
    )
    rows = [
        {
            "id": rec.student_id,
            "full_name": rec.student.full_name,
            "class_label": class_label(
                rec.session.class_group.grade, rec.session.class_group.section
            ),
            "cumulative_late": cumulative.get(rec.student_id, 0),
            "recorded_at": rec.tardiness_recorded_at.strftime("%H:%M")
            if rec.tardiness_recorded_at
            else "—",
            "notes": rec.excuse_notes or "—",
            "subject": rec.session.subject.name_ar if rec.session.subject_id else "—",
            "has_file": "نعم" if rec.excuse_file else "—",
            "wing_order": rec.session.class_group.wing.order
            if rec.session.class_group.wing_id
            else None,
        }
        for rec in records
    ]
    return wing_sorted(rows)


def activity_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    """الأنشطةُ والإنجازاتُ بمرشِّحات العام والنوع والنطاق داخل نطاق الدور، الأحدثُ أوّلاً."""
    from .models import StudentActivity

    scope, school = _scope_and_school(user)
    year = params.get("year") or academic_year_for_school(school)
    found = scope.narrow(
        StudentActivity.objects.filter(school=school, academic_year=year)
        .select_related("student")
        .order_by("-date")
    )
    if params.get("type"):
        found = found.filter(activity_type=params["type"])
    if params.get("scope"):
        found = found.filter(scope=params["scope"])
    types = dict(StudentActivity.TYPE_CHOICES)
    scopes = dict(StudentActivity.SCOPE_CHOICES)
    rows = [
        {
            "id": act.student_id,
            "pk": act.pk,
            "full_name": act.student.full_name,
            "title": act.title,
            "type_label": types.get(act.activity_type, act.activity_type),
            "scope": act.scope,
            "scope_label": scopes.get(act.scope, act.scope),
            "date_value": act.date,
            "date": act.date.strftime("%d/%m/%Y") if act.date else "—",
        }
        for act in found
    ]
    return _with_class(rows, school, year)


def movement_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    """تحرّكاتُ الطلبة بمرشِّحات الشعبة والفترة والنوع داخل نطاق الدور، الأحدثُ أوّلاً."""
    from .selectors import enrolment_movements, movement_filters

    scope, school = _scope_and_school(user)
    year = academic_year_for_school(school)
    events = enrolment_movements(school, year, **movement_filters(params))
    if scope.is_wing_bound:
        mine = scope.student_ids()
        events = [e for e in events if e["student"].pk in mine]
    rows = [
        {
            "id": e["student"].pk,
            "date": e["date"].isoformat(),
            "full_name": e["student"].full_name,
            "kind_label": e["kind_label"],
            "class_text": e["class_text"],
            "from_text": e["from_text"],
            "detail": e["detail"],
        }
        for e in events
    ]
    return _with_class(rows, school, year)
