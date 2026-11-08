"""مُنتقي الطالب في شاشة تسجيل المخالفة: الصفُّ والشعبةُ ثمّ الطالب (بلاغ المالك 2026-09-26).

كانت الشاشةُ تعرض كلَّ طلبة المدرسة (أو الجناح) في قائمةٍ واحدةٍ يُبحث فيها بالاسم وحده، ومن أراد طالباً من شعبةٍ بعينها
تصفّح مئاتِ الأسماء. فصار لها قائمتان منسدلتان — الصفُّ والشعبة — تحصران قائمةَ الطالب وبحثَها. والتصفيةُ في المتصفّح على
سمات `data-grade` و`data-section` (القائمةُ كلُّها مرسومةٌ أصلاً)، وهذا الملفُّ يشتقّ لكلّ طالبٍ صفَّه وشعبتَه **الحاليَّين**.

الحاليّان = قيدُ العام الدراسيّ الجاري، والأحدثُ إن تعدّدت قيودُه النشطةُ فيه (`newest_first`). فقيدُ العام الماضي الذي لم
يُغلق بعدُ لا يضع طالباً في صفٍّ غادره (قِيس هذا على بيانات المدرسة: أكثرُ من 200 طالبٍ بقيدَين نشطَين). ومن لا قيدَ حاليَّ له
يبقى في القائمة بلا صفٍّ ولا شعبة: يظهر حين لا يُقيَّد بصفٍّ ولا شعبة، ولا يظهر تحت أيٍّ منهما.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date

from core.academic_calendar import academic_year_for_school
from core.labels import class_label
from core.models import ClassGroup, CustomUser, StudentEnrollment, Wing
from core.permissions import get_teacher_student_ids, teacher_can_access_student
from wings.scope import student_scope, student_scope_for


def _section_key(section: str) -> tuple[int, int, str]:
    """الأرقامُ أوّلاً بقيمتها («2» قبل «10»)، ثمّ الحروف — وليس ترتيباً نصّيّاً يضع «10» قبل «2»."""
    return (0, int(section), "") if section.isdigit() else (1, 0, section)


def student_picker(students: Iterable[Any], school) -> dict[str, Any]:
    """سياقُ منتقي الطالب: الطلبةُ بصفّهم وشعبتهم الحاليَّين، وخياراتُ الصفّ والشعبة.

    يُرجع `students` (قائمةً بالعناصر نفسِها وعليها `pick_grade` و`pick_section`)، و`grade_options` (الصفوفُ التي فيها طلبةٌ
    بترتيبها الرسميّ)، و`sections_by_grade` (شُعبُ كلّ صفٍّ)، و`all_sections` (كلُّ الشعب، لمن لم يختر صفّاً).
    والخياراتُ من طلبة نطاق صاحب الطلب وحدَهم: مشرفُ الجناح لا يرى صفّاً ولا شعبةً ليست من جناحه.
    """
    people = list(students)
    current: dict[Any, tuple[str, str]] = {}
    rows = (
        StudentEnrollment.objects.filter(
            student_id__in=[person.pk for person in people],
            is_active=True,
            class_group__school=school,
            class_group__academic_year=academic_year_for_school(school),
        )
        .newest_first()
        .values_list("student_id", "class_group__grade", "class_group__section")
    )
    for student_id, grade, section in rows:
        current.setdefault(student_id, (grade, section))

    sections: dict[str, set[str]] = {}
    for person in people:
        grade, section = current.get(person.pk, ("", ""))
        person.pick_grade, person.pick_section = grade, section
        if grade and section:
            sections.setdefault(grade, set()).add(section)

    labels = dict(ClassGroup.GRADES)
    return {
        "students": people,
        "grade_options": [
            (code, labels[code]) for code, _label in ClassGroup.GRADES if code in sections
        ],
        "sections_by_grade": {
            grade: sorted(found, key=_section_key) for grade, found in sections.items()
        },
        "all_sections": sorted({s for found in sections.values() for s in found}, key=_section_key),
    }


def visible_infractions(user, school):
    """مخالفاتُ المدرسة المرئيةُ لصاحب الطلب — بنطاقِ الويب نفسِه (W-20261012-032).

    المعلّمُ والمنسّقُ ومشرفُ الجناح لطلبتهم، والقيادةُ (None) للمدرسة كلِّها. و`?student_id` و`?class_id`
    تُضيَّقان بعده فتُرجعان قائمةً فارغةً لطالبٍ خارج النطاق لا خطأً يكشف وجوده."""
    from .models import BehaviorInfraction

    qs = BehaviorInfraction.objects.filter(school=school).with_student().order_by("-date")
    visible = get_teacher_student_ids(user)
    if visible is not None:
        qs = qs.filter(student_id__in=visible)
    return qs


def recordable_student(request, school, student_id):
    """الطالبُ الذي يحقّ لصاحب الطلب أن يسجّل عليه مخالفة — وإلّا 404 موحَّد لا يكشف وجودَه.

    يجمع ثلاثةَ شروط في استعلامٍ واحد: عضويةٌ فعّالةٌ في مدرسة الطلب بدور طالب (فمستخدمٌ من مدرسةٍ أخرى
    أو غيرُ طالبٍ لا يُجلب)، ثمّ نطاقُ الدور: المشرفُ المقيَّد بجناحه، والمعلّمُ والمنسّقُ بجدولهما، والقيادةُ
    لمدرستها كلِّها. وتُمرَّر `student.id` (UUID) لا النصُّ الخام: مقارنةُ نصٍّ بمجموعة UUID تُرجع False دائماً.
    يُجلب الطالبُ بنطاقه قبل صحّة النموذج، ومعرّفٌ فارغ يُرجع None. الرفضُ 404 لا صفحةَ منع كي لا يُعرف أنّ الطالبَ موجودٌ في مدرسةٍ أخرى أو خارج جدول المعلّم."""
    if not student_id:
        return None
    try:
        sid = uuid.UUID(str(student_id))
    except ValueError:
        raise Http404("طالبٌ غير موجود") from None
    student = get_object_or_404(
        CustomUser.objects.filter(
            memberships__school=school,
            memberships__is_active=True,
            memberships__role__name="student",
        ).distinct(),
        id=sid,
    )
    scope = student_scope_for(request)
    if scope.is_wing_bound:
        scope.require_student(student.id)
    elif not teacher_can_access_student(request.user, student.id):
        raise Http404("طالبٌ غير موجود")
    return student


def escalation_preview_targets(students, student_id: str, category_id: str):
    """(الطالب، الفئة) لمعاينة التصعيد، أو None إن لم يصحّ المعرّفان أو خرج الطالب عن النطاق أو الفئةُ بلا درجة.

    `students` استعلامُ الطلبة المرئيّين لصاحب الطلب — فلا يُعرض طالبٌ خارج نطاقه.
    """
    from behavior.models import ViolationCategory

    try:
        sid, cid = uuid.UUID(student_id), uuid.UUID(category_id)
    except (ValueError, TypeError):
        return None
    student = students.filter(pk=sid).first()
    category = ViolationCategory.objects.filter(pk=cid, is_active=True).first()
    if student is None or category is None or category.degree is None:
        return None
    return student, category


def _visible_student_ids(request):
    """طلبةُ صاحب الطلب — `None` للمدرسة كلِّها، ومجموعةٌ للمقيَّد بجدولٍ أو جناح."""
    return get_teacher_student_ids(request.user, scope=student_scope_for(request))


def _get_scoped_students(request, school):
    """
    يُعيد QuerySet طلاب مرئيّ حسب دور المستخدم:
    - القيادة/الأخصائيون → كل طلاب المدرسة
    - المشرف الإداري → طلبة جناحه
    - المعلم/المنسق → طلاب فصوله فقط
    """
    student_ids = _visible_student_ids(request)
    if student_ids is None:
        # admin/leadership — all students
        return (
            CustomUser.objects.filter(
                memberships__school=school,
                memberships__role__name="student",
                memberships__is_active=True,
            )
            .order_by("full_name")
            .distinct()
        )
    return CustomUser.objects.filter(id__in=student_ids).order_by("full_name")


#: الدرجاتُ الأربع على بطاقة الشعبة (قرار المالك 10-09: النوعُ = الدرجة، واسمُ الفئة عند الضغط).
DEGREES = (1, 2, 3, 4)


def infractions_by_class(
    year_infractions, scope, school, year: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """بطاقةٌ لكلّ شعبة: عددُ المخالفين وعددُ المخالفات بالدرجات 1–4 (W-20261008-026).

    الشعبةُ = **قيدُ الطالب الجاري** في العام الجاري لا شعبتُه وقتَ المخالفة (D-201م: الطالبُ يرحّل مخالفاتِه معه)،
    والأحدثُ إن تعدّدت قيودُه النشطة. ثلاثةُ استعلاماتٍ ثابتةٌ مهما كثرت الشُّعب: الشُّعب، ومخالفاتُ الطلبة بالدرجة،
    وقيودُهم الجارية؛ و`year` عامُ الطلب يمرّره المستدعي فلا استعلامَ تقويمٍ هنا. الشعبةُ بلا مخالفاتٍ تُعرض بصفر. والمقيَّدُ بجناحه لا يرى غيرَ شُعب جناحه.
    ومخالفاتُ من لا قيدَ جاريَ له تُعاد في `unassigned` فيبقى المجموعُ مساوياً لإجمالي الشاشة.
    """
    groups = ClassGroup.objects.filter(school=school, academic_year=year, is_active=True)
    groups = scope.class_groups() if scope.is_wing_bound else groups

    per_student: dict[Any, dict[int, int]] = {}
    for row in year_infractions.values("student_id", "violation_category__degree").annotate(
        n=Count("id")
    ):
        per_student.setdefault(row["student_id"], {})[row["violation_category__degree"]] = row["n"]

    enrollments = (
        StudentEnrollment.objects.filter(
            student_id__in=per_student,
            is_active=True,
            class_group__school=school,
            class_group__academic_year=year,
        )
        .newest_first()
        .values_list("student_id", "class_group_id")
    )
    current: dict[Any, Any] = {}
    for student_id, class_id in enrollments:
        current.setdefault(student_id, class_id)

    def blank() -> dict[str, Any]:
        return {"offenders": 0, "total": 0, "degrees": dict.fromkeys(DEGREES, 0)}

    cards = {group.pk: {"group": group, **blank()} for group in groups}
    unassigned = blank()
    for student_id, degrees in per_student.items():
        card = cards.get(current.get(student_id)) or unassigned
        card["offenders"] += 1
        for degree, n in degrees.items():
            card["total"] += n
            if degree in card["degrees"]:
                card["degrees"][degree] += n
    for card in [*cards.values(), unassigned]:
        card["degree_rows"] = [(d, card["degrees"][d]) for d in DEGREES]
    ordered = sorted(cards.values(), key=lambda c: c["group"].school_order)
    return ordered, unassigned


def monthly_infraction_trend(school_infractions, today) -> tuple[list[str], list[int]]:
    """اتجاهُ المخالفات الشهريّ لآخر ستّة أشهر: (التسميات، الأعداد) — كان حلقةً داخل العرض."""
    from datetime import timedelta

    from django.utils.formats import date_format

    labels: list[str] = []
    counts: list[int] = []
    for i in range(5, -1, -1):
        month_start = (today.replace(day=1) - timedelta(days=30 * i)).replace(day=1)
        next_month = (
            (month_start + timedelta(days=32)).replace(day=1)
            if i > 0
            else today + timedelta(days=1)
        )
        labels.append(date_format(month_start, "F"))
        counts.append(school_infractions.filter(date__gte=month_start, date__lt=next_month).count())
    return labels, counts


#: حقولُ المخالفة المشفَّرة — لا يحتاجها التقريرُ اليوميّ فلا تُفكّ لكلّ صفّ ولا تخرج إلى ملفّ.
_ENCRYPTED_FIELDS = (
    "description",
    "action_taken",
    "violation_description",
    "digital_evidence_notes",
    "security_notes",
)

#: الراصدُ حين لا يدَ بشريّةً: مخالفةٌ أنشأها الرصدُ الآليّ.
AUTO_REPORTER = "الرصد الآلي"


def daily_report_day(raw: str | None):
    """اليومُ المختار من `?date=` — واليومُ إن غاب أو فسد."""
    try:
        return parse_date(raw or "") or timezone.localdate()
    except ValueError:
        return timezone.localdate()


def daily_report(school, user, params) -> dict[str, Any]:
    """التقريرُ السلوكيّ اليوميّ لصاحب الطلب: صفوفُ يومٍ واحدٍ بنطاقه، ومرشِّحا الجناح والصفّ.

    **يومُ المخالفة**: يومُ حصّتها إن كانت لها حصّة (`session__date`) وإلا `date`؛ فـ`date` يومُ الكتابة
    (`auto_now_add`) وتصحيحُ حصّةٍ مضت يُكتب اليومَ عن يومها، فلا تظهر المخالفةُ الآليّةُ في غير يوم حصّتها.
    **النطاق**: `get_teacher_student_ids` — المدرسةُ للقيادة، وطلبةُ الجدول للمعلّم، وطلبةُ الجناح للمشرف؛
    وجناحٌ خارج ما يراه يعود 404. وقيدُ الطالب الجاريُّ يعطي الشعبةَ (كما في `infractions_by_class`).
    **الاستعلامات ثابتةٌ** أمام عدد الصفوف: المخالفات بعلاقاتها، ثمّ قيودُ طلبتها.
    ولا وصفَ ولا رقمَ شخصيّاً ولا وليَّ أمرٍ في الصفوف.
    """
    from .models import BehaviorInfraction

    year = academic_year_for_school(school)
    scope = student_scope(user, school)
    day = daily_report_day(params.get("date"))

    wings = Wing.objects.filter(school=school, academic_year=year).order_by("code")
    if scope.is_wing_bound:
        wings = wings.filter(pk__in=scope.wing_ids)
    wing_options = [(str(wing.pk), wing.name) for wing in wings]
    wing = (params.get("wing") or "").strip()
    if wing and wing not in {key for key, _name in wing_options}:
        raise Http404("ليس من أجنحتك")
    grade = (params.get("grade") or "").strip()
    if grade not in dict(ClassGroup.GRADES):
        grade = ""

    infractions = (
        BehaviorInfraction.objects.filter(school=school)
        .filter(Q(session__date=day) | Q(session__isnull=True, date=day))
        .select_related("student", "violation_category", "reported_by")
        .defer(*_ENCRYPTED_FIELDS)
    )
    student_ids = get_teacher_student_ids(user, scope=scope)
    if student_ids is not None:
        infractions = infractions.filter(student_id__in=student_ids)
    found = list(infractions)

    current: dict[Any, tuple[str, str, str]] = {}
    enrollments = (
        StudentEnrollment.objects.filter(
            student_id__in={inf.student_id for inf in found},
            is_active=True,
            class_group__school=school,
            class_group__academic_year=year,
        )
        .newest_first()
        .values_list(
            "student_id", "class_group__grade", "class_group__section", "class_group__wing_id"
        )
    )
    for student_id, class_grade, section, wing_id in enrollments:
        current.setdefault(student_id, (class_grade, section, str(wing_id) if wing_id else ""))

    order = {code: index for index, (code, _label) in enumerate(ClassGroup.GRADES)}
    rows = []
    for inf in found:
        class_grade, section, wing_id = current.get(inf.student_id, ("", "", ""))
        if (wing and wing_id != wing) or (grade and class_grade != grade):
            continue
        if inf.violation_category:
            violation = inf.violation_category.name_ar
        else:
            violation = inf.get_auto_rule_display() or "—"
        if inf.reported_by:
            reporter = inf.reported_by.full_name
        else:
            reporter = AUTO_REPORTER if inf.auto_rule else "—"
        rows.append(
            {
                "sort": (
                    order.get(class_grade, len(order)),
                    _section_key(section),
                    inf.student.full_name,
                    str(inf.pk),
                ),
                "student": inf.student.full_name,
                "class_label": class_label(class_grade, section),
                "violation": violation,
                "level": inf.get_level_display(),
                "step": inf.get_escalation_step_display(),
                "reporter": reporter,
            }
        )
    rows.sort(key=lambda row: row["sort"])
    return {
        "day": day,
        "rows": rows,
        "wing": wing,
        "grade": grade,
        "wing_options": wing_options,
        "grade_options": list(ClassGroup.GRADES),
    }


# ── إجراءاتُ المخالفات المقترحة (W-20261108-007) ─────────────────────────────
def pending_actions(school: Any, scope: Any = None) -> Any:
    """مخالفاتُ المدرسة التي اقتُرح لها إجراءٌ وينتظر الاعتماد — ولمشرف الجناح طلبةُ جناحه وحدَهم عبر `scope`."""
    from behavior.models import BehaviorInfraction

    qs = (
        BehaviorInfraction.objects.filter(school=school, approval_status="pending")
        .select_related("student", "reported_by", "violation_category", "prepared_by")
        .order_by("-date", "-created_at")
    )
    return qs if scope is None else scope.narrow(qs)


def specialist_referrals(school: Any) -> Any:
    """الإحالاتُ المعتمَدةُ التي بلغت عتبةً تنصّ عليها السياسةُ — قائمةُ الاختصاصيّين الاجتماعيّ والنفسيّ."""
    from behavior.models import BehaviorInfraction

    return (
        BehaviorInfraction.objects.filter(
            school=school, approval_status="approved", proposed_specialist=True
        )
        .select_related("student", "violation_category", "approved_by")
        .order_by("-approved_at")
    )
