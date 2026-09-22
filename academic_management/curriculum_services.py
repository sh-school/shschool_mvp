"""الطلبُ التعليميُّ مقروءاً من الخطّة الدراسيّة — ومقيساً بما أُسنِد فعلاً.

    CurriculumDemand ≠ ObservedAssignment

فالخطّةُ تقول ماذا **ينبغي**، والإسنادُ يقول ماذا **جرى**، والفرقُ بينهما هو
كلُّ ما تفيده هذه الوحدة. وقبلها لم يكن للفرق موضعٌ يُقاس فيه أصلاً: عددُ
الحصص يُكتب يدويّاً في كلٍّ من مئتين وخمسين خليّة، فمن كتب واحدةً بدل اثنتين
لم يخالف شيئاً في النظام.

## الاختياريّةُ تُقاس على المجموعة لا على البديل

في الحادي عشر والثاني عشر «مادّةٌ اختياريّة» بحصّتين تُختار من قائمة، فبدائلُها
سجلّاتٌ تتقاسم `elective_group` واحدة. ولو جُمع طلبُها جمعَ الإلزاميّ لظهرت
المدرسةُ مطالَبةً بتدريس الفنونِ وإدارةِ الأعمالِ والحوسبةِ معاً في الشعبة
الواحدة.

وبديلان في شعبةٍ واحدةٍ حالةٌ صحيحة لا خطأ: طلّابُ 11/4 ينقسمون بين الفنون
والكيمياء في التوقيت نفسه، فتُجدول أربعُ حصصٍ ويأخذ الطالبُ اثنتين:

    InstructionalPeriods ≠ StudentPeriods

## ولا يُقاس ما لا جدولَ له

شُعبُ التربية الخاصّة جدولُها مستقلّ (`ClassGroup.has_own_timetable`)، فتخرج من
الطلب والتغطية معاً. واستثناؤها مكتوبٌ في البيانات لا مسكوتٌ عنه في الكود.
"""

from collections import defaultdict

from academic_management.models import (
    FROZEN_STATUSES,
    CurriculumPlan,
    TeacherWorkloadPlan,
    WorkloadGovernance,
)
from core.models.academic import ClassGroup, grade_number

# ── حالاتُ الخليّة في فحص التغطية ────────────────────────────────────
MATCH = "MATCH"
UNDER = "UNDER"
OVER = "OVER"
MISSING = "MISSING"
EXTRA = "EXTRA"
UNCOVERED_ELECTIVE = "UNCOVERED_ELECTIVE"
NO_TRACK = "NO_TRACK"

STATUS_LABELS = {
    MATCH: "مطابق",
    UNDER: "أقلُّ من الخطّة",
    OVER: "أكثرُ من الخطّة",
    MISSING: "غيرُ مُسنَد",
    EXTRA: "خارج الخطّة",
    UNCOVERED_ELECTIVE: "اختياريّةٌ بلا تغطية",
    NO_TRACK: "شعبةٌ بلا مسار",
}

#: ما يستوجب عملاً — و`MATCH` وحدَه ليس منها.
PROBLEM_STATUSES = (UNDER, OVER, MISSING, EXTRA, UNCOVERED_ELECTIVE, NO_TRACK)


# ══════════════════════════════════════════════════════════════════════
#  الطلبُ من الخطّة
# ══════════════════════════════════════════════════════════════════════


def plan_rows(school, academic_year):
    """صفوفُ الخطّة كلُّها لهذا العام — تُقرأ مرّةً وتُمرَّر.

    فكلُّ دالّةٍ هنا تعمل على بياناتٍ محمَّلةٍ سلفاً، لا تستعلم بنفسها: ثلاثُ
    دوالَّ تستعلم كلُّ واحدةٍ منها عن الخطّة نفسها تعني ثلاثةَ استعلاماتٍ لجوابٍ
    واحد، ويصعب اختبارُ أيٍّ منها بمعزلٍ عن قاعدة.
    """
    return list(
        CurriculumPlan.objects.live(school, year=academic_year)
        .select_related("subject", "department")
        .order_by("grade", "track", "subject__name_ar")
    )


def index_by_scope(rows):
    """الخطّةُ مفهرسةً بـ(صفّ، مسار) — وهو مفتاحُ الشعبة إلى طلبها."""
    out = defaultdict(list)
    for row in rows:
        out[(row.grade, row.track)].append(row)
    return out


def demand_for(class_group, rows=None):
    """صفوفُ الخطّة التي تخصّ هذه الشعبة — وفارغةٌ لمن جدولُه مستقلّ."""
    if class_group.has_own_timetable:
        return []
    rows = plan_rows(class_group.school, class_group.academic_year) if rows is None else rows
    return index_by_scope(rows).get((class_group.grade, class_group.track), [])


def split_electives(scope_rows):
    """يفصل الإلزاميَّ عن مجموعات الاختيار — والمجموعةُ تُقاس مرّةً واحدة."""
    mandatory = [r for r in scope_rows if not r.elective_group]
    groups = defaultdict(list)
    for row in scope_rows:
        if row.elective_group:
            groups[row.elective_group].append(row)
    return mandatory, dict(groups)


def expected_total(scope_rows):
    """مجموعُ حصص الطالب في الأسبوع: الإلزاميُّ + حصّةُ كلّ مجموعةِ اختيارٍ مرّة.

    وبدائلُ المجموعة الواحدة يجب أن تتساوى حصصُها — وإلّا فالمجموعُ يعتمد على
    ما يختاره الطالب، وهذا لا يكون في خطّةٍ وزاريّة. فتُعاد أكبرُها ويُبلَّغ
    عن التفاوت في `scope_issues`.
    """
    mandatory, groups = split_electives(scope_rows)
    total = sum(r.weekly_periods for r in mandatory)
    total += sum(max(r.weekly_periods for r in alts) for alts in groups.values())
    return total


def scope_issues(scope_rows):
    """خللٌ في الخطّة نفسها — لا في الإسناد."""
    issues = []
    _, groups = split_electives(scope_rows)
    for name, alts in groups.items():
        periods = {r.weekly_periods for r in alts}
        if len(periods) > 1:
            issues.append(
                f"بدائلُ مجموعة «{name}» تختلف حصصُها ({'، '.join(str(p) for p in sorted(periods))})"
            )
    return issues


# ══════════════════════════════════════════════════════════════════════
#  التغطية: الخطّةُ مقابل الإسناد
# ══════════════════════════════════════════════════════════════════════


def _sections(school, academic_year):
    """الشُّعبُ التي يقيسها هذا النظام — ومن له جدولٌ مستقلٌّ خارجَها."""
    return list(
        ClassGroup.objects.filter(
            school=school, academic_year=academic_year, is_active=True, has_own_timetable=False
        ).order_by("grade", "section")
    )


def _assignments_by_section(school, academic_year):
    from operations.models import SubjectClassAssignment

    out = defaultdict(dict)
    rows = SubjectClassAssignment.objects.live(school, year=academic_year).select_related(
        "subject", "teacher"
    )
    for a in rows:
        out[a.class_group_id][a.subject_id] = a
    return out


def _cell(section, row, assignment):
    """خليّةٌ واحدة: ما تطلبه الخطّةُ وما أُسنِد فعلاً."""
    planned = row.weekly_periods
    assigned = assignment.weekly_periods if assignment else 0
    if assignment is None:
        status = MISSING
    elif assigned == planned:
        status = MATCH
    else:
        status = UNDER if assigned < planned else OVER
    return {
        "section": str(section),
        "section_id": section.id,
        "grade": section.grade,
        "grade_order": grade_number(section.grade),
        "track": section.track,
        "subject": row.subject.name_ar,
        "subject_id": row.subject_id,
        "code": row.subject.code,
        "department": row.department.name if row.department else "",
        "elective_group": row.elective_group,
        "planned": planned,
        "assigned": assigned,
        "delta": assigned - planned,
        "teacher": assignment.teacher.full_name if assignment and assignment.teacher else "",
        "is_pilot": row.is_pilot,
        "status": status,
    }


def _elective_cells(section, alts, section_assignments):
    """مجموعةُ اختيارٍ واحدة: بديلٌ مختارٌ أو بديلان متوازيان أو لا شيء.

    ولا تُجمع حصصُ البديلين: كلٌّ منهما يبلغ حصصَ المجموعة كاملةً لقسمٍ من
    الطلاب، فالجمعُ يقول إنّ الطالبَ يأخذ أربعاً وهو يأخذ اثنتين.
    """
    chosen = [(r, section_assignments.get(r.subject_id)) for r in alts]
    chosen = [(r, a) for r, a in chosen if a is not None]
    if not chosen:
        row = alts[0]
        cell = _cell(section, row, None)
        cell.update(
            {
                "status": UNCOVERED_ELECTIVE,
                "subject": "· أو ·".join(r.subject.name_ar for r in alts),
                "code": "",
            }
        )
        return [cell]
    return [_cell(section, row, assignment) for row, assignment in chosen]


def coverage(school, academic_year, rows=None):
    """كلُّ (شعبة × مادّة) موصوفةً: مطابقةٌ أو ناقصةٌ أو زائدةٌ أو خارج الخطّة.

    وثلاثةُ استعلاماتٍ لا أكثر مهما كثرت الشُّعب: الخطّةُ والشُّعبُ والإسنادات.
    """
    rows = plan_rows(school, academic_year) if rows is None else rows
    by_scope = index_by_scope(rows)
    sections = _sections(school, academic_year)
    assignments = _assignments_by_section(school, academic_year)

    cells = []
    for section in sections:
        section_assignments = assignments.get(section.id, {})
        scope_rows = by_scope.get((section.grade, section.track), [])

        if not scope_rows:
            cells.append(
                {
                    "section": str(section),
                    "section_id": section.id,
                    "grade": section.grade,
                    "grade_order": grade_number(section.grade),
                    "track": section.track,
                    "subject": "—",
                    "subject_id": None,
                    "code": "",
                    "department": "",
                    "elective_group": "",
                    "planned": 0,
                    "assigned": sum(a.weekly_periods for a in section_assignments.values()),
                    "delta": 0,
                    "teacher": "",
                    "is_pilot": False,
                    "status": NO_TRACK,
                }
            )
            continue

        mandatory, groups = split_electives(scope_rows)
        planned_subjects = set()

        for row in mandatory:
            planned_subjects.add(row.subject_id)
            cells.append(_cell(section, row, section_assignments.get(row.subject_id)))

        for alts in groups.values():
            planned_subjects.update(r.subject_id for r in alts)
            cells.extend(_elective_cells(section, alts, section_assignments))

        # إسنادٌ لا يقابله صفٌّ في الخطّة — يُقال ولا يُحذف.
        for subject_id, assignment in section_assignments.items():
            if subject_id in planned_subjects:
                continue
            cells.append(
                {
                    "section": str(section),
                    "section_id": section.id,
                    "grade": section.grade,
                    "grade_order": grade_number(section.grade),
                    "track": section.track,
                    "subject": assignment.subject.name_ar,
                    "subject_id": subject_id,
                    "code": assignment.subject.code,
                    "department": "",
                    "elective_group": "",
                    "planned": 0,
                    "assigned": assignment.weekly_periods,
                    "delta": assignment.weekly_periods,
                    "teacher": assignment.teacher.full_name if assignment.teacher else "",
                    "is_pilot": False,
                    "status": EXTRA,
                }
            )

    for cell in cells:
        cell["status_label"] = STATUS_LABELS[cell["status"]]
    cells.sort(key=lambda c: (c["grade_order"], c["section"], c["subject"]))
    return cells


def coverage_summary(cells, sections_count=None):
    """ملخّصٌ يقرؤه الرأس: كم خليّةً وكم شعبةً سليمة."""
    counts = defaultdict(int)
    bad_sections = set()
    all_sections = set()
    for c in cells:
        counts[c["status"]] += 1
        all_sections.add(c["section"])
        if c["status"] in PROBLEM_STATUSES:
            bad_sections.add(c["section"])
    total_sections = sections_count if sections_count is not None else len(all_sections)
    return {
        "counts": dict(counts),
        "cells": len(cells),
        "matched": counts[MATCH],
        "problems": sum(counts[s] for s in PROBLEM_STATUSES),
        "sections": total_sections,
        "clean_sections": total_sections - len(bad_sections),
    }


def section_totals(school, academic_year, rows=None):
    """مجموعُ حصص الطالب لكلّ شعبة: المخطَّطُ والمُسنَد.

    والمُسنَدُ قد يتجاوز المخطَّط بحصص التوازي، وهذا صحيحٌ لا خطأ — فيُعرض
    عددُ الحصص المزدوجة على حدة كي لا يُقرأ فائضاً.
    """
    rows = plan_rows(school, academic_year) if rows is None else rows
    by_scope = index_by_scope(rows)
    assignments = _assignments_by_section(school, academic_year)
    out = []
    for section in _sections(school, academic_year):
        scope_rows = by_scope.get((section.grade, section.track), [])
        section_assignments = assignments.get(section.id, {})
        planned = expected_total(scope_rows) if scope_rows else None
        assigned = sum(a.weekly_periods for a in section_assignments.values())
        _, groups = split_electives(scope_rows)
        parallel = 0
        for alts in groups.values():
            picked = [r for r in alts if r.subject_id in section_assignments]
            if len(picked) > 1:
                parallel += sum(
                    section_assignments[r.subject_id].weekly_periods for r in picked[1:]
                )
        out.append(
            {
                "section": str(section),
                "grade": section.grade,
                "grade_order": grade_number(section.grade),
                "track": section.get_track_display() if section.track else "",
                "planned": planned,
                "assigned": assigned,
                "parallel": parallel,
                "balanced": planned is not None and assigned - parallel == planned,
            }
        )
    return sorted(out, key=lambda s: (s["grade_order"], s["section"]))


# ══════════════════════════════════════════════════════════════════════
#  ميزانُ القسم: الطلبُ مقابل العرض
# ══════════════════════════════════════════════════════════════════════


def _section_counts(school, academic_year):
    """عددُ الشُّعب لكلّ (صفّ، مسار) — مقامُ ضربِ الطلب."""
    counts = defaultdict(int)
    for section in _sections(school, academic_year):
        counts[(section.grade, section.track)] += 1
    return counts


def _teacher_targets(school, academic_year):
    """هدفُ كلّ معلّمٍ إن كان له، وإلّا `None` — والصمتُ لا يصير صفراً.

    فمعلّمٌ بلا خطّةٍ معتمَدةٍ ولا نصابٍ مرجعيٍّ في الحوكمة **غيرُ معلوم**، ولو
    عُدّ صفراً لظهر القسمُ عاجزاً عن تغطية نفسه وهو مكتمل.
    """
    governance = WorkloadGovernance.for_school(school)
    fallback = governance.reference_load
    targets = {}
    approved = (
        TeacherWorkloadPlan.objects.filter(
            school=school, academic_year=academic_year, status__in=FROZEN_STATUSES
        )
        .order_by("teacher_id", "-plan_version")
        .select_related("teacher")
    )
    for plan in approved:
        targets.setdefault(plan.teacher_id, plan.teaching_target)
    return targets, fallback


def department_balance(school, academic_year, rows=None):
    """لكلّ قسمٍ: كم حصّةً يطلبها منه المنهجُ، وكم يملك من نصابِ معلّميه.

    والطلبُ يُحسب من الخطّة مضروبةً في عدد الشُّعب، إلّا الاختياريّةَ فتُحسب
    بما اختارته الشُّعبُ فعلاً — لأنّ اختيارَ الشعبة بين الفنون وإدارة الأعمال
    قرارُ مدرسةٍ لا يحمله الدليلُ الوزاريّ، وقسماهما مختلفان.

    والعرضُ تقديريّ: يُجمع من عضويّة المعلّمين في الأقسام، ومعلّمٌ يدرّس في
    قسمين (كمعلّم الفيزياء الذي يدرّس علومَ العاشر) يُحسب نصابُه في قسمه
    الإداريّ وحدَه. فالميزانُ مؤشّرٌ للتخطيط لا حسابٌ مغلق.
    """
    from core.models import Membership

    rows = plan_rows(school, academic_year) if rows is None else rows
    counts = _section_counts(school, academic_year)
    assignments = _assignments_by_section(school, academic_year)
    chosen_electives = defaultdict(int)
    for section_assignments in assignments.values():
        for subject_id, assignment in section_assignments.items():
            chosen_electives[subject_id] += 1

    demand = defaultdict(int)
    names = {}
    for row in rows:
        key = row.department_id
        names[key] = row.department.name if row.department else "بلا قسم"
        sections = counts.get((row.grade, row.track), 0)
        if not sections:
            continue
        if row.elective_group:
            # الشُّعبُ التي اختارت هذا البديل فعلاً — لا كلُّ شُعب الصفّ.
            picked = min(chosen_electives.get(row.subject_id, 0), sections)
            demand[key] += row.weekly_periods * picked
        else:
            demand[key] += row.weekly_periods * sections

    targets, fallback = _teacher_targets(school, academic_year)
    supply = defaultdict(int)
    unknown = defaultdict(int)
    staff = defaultdict(int)
    memberships = Membership.objects.filter(
        school=school, is_active=True, department_obj__isnull=False
    ).select_related("department_obj")
    for m in memberships:
        key = m.department_obj_id
        names.setdefault(key, m.department_obj.name)
        staff[key] += 1
        target = targets.get(m.user_id, fallback)
        if target is None:
            unknown[key] += 1
        else:
            supply[key] += target

    out = []
    for key in set(demand) | set(supply) | set(unknown) | set(staff):
        # العرضُ معلومٌ حين يوجد معلّمون ولكلٍّ منهم هدفٌ — وإلّا فالفرقُ لا
        # يُحسب. وقسمٌ بلا معلّمين مسجَّلين يظهر عجزُه كاملاً وهو مجهولٌ لا عاجز.
        countable = bool(staff[key]) and not unknown[key]
        out.append(
            {
                "department_id": key,
                "name": names.get(key, "بلا قسم"),
                "demand": demand[key],
                "supply": supply[key] if countable else None,
                "teachers": staff[key],
                "unknown_targets": unknown[key],
                "delta": (supply[key] - demand[key]) if countable else None,
            }
        )
    return sorted(out, key=lambda d: (-d["demand"], d["name"]))


# ══════════════════════════════════════════════════════════════════════
#  عرضُ الخطّة نفسها
# ══════════════════════════════════════════════════════════════════════


def plan_view(school, academic_year, rows=None):
    """الخطّةُ مجموعةً بـ(صفّ، مسار) — كما تُقرأ في الدليل الوزاريّ."""
    rows = plan_rows(school, academic_year) if rows is None else rows
    counts = _section_counts(school, academic_year)
    groups = index_by_scope(rows)
    out = []
    for (grade, track), scope_rows in groups.items():
        label = dict(ClassGroup.TRACKS).get(track, "") if track else ""
        out.append(
            {
                "grade": grade,
                "grade_order": grade_number(grade),
                "grade_label": dict(ClassGroup.GRADES).get(grade, grade),
                "track": track,
                "track_label": label,
                "sections": counts.get((grade, track), 0),
                "total": expected_total(scope_rows),
                "issues": scope_issues(scope_rows),
                "pilot": any(r.is_pilot for r in scope_rows),
                "rows": [
                    {
                        "subject": r.subject.name_ar,
                        "code": r.subject.code,
                        "periods": r.weekly_periods,
                        "department": r.department.name if r.department else "—",
                        "elective_group": r.elective_group,
                        "source": r.get_source_kind_display(),
                        "reference": r.source_reference,
                        "is_pilot": r.is_pilot,
                    }
                    for r in scope_rows
                ],
            }
        )
    return sorted(out, key=lambda g: (g["grade_order"], g["track"]))


__all__ = [
    "MATCH",
    "MISSING",
    "PROBLEM_STATUSES",
    "STATUS_LABELS",
    "coverage",
    "coverage_summary",
    "demand_for",
    "department_balance",
    "expected_total",
    "plan_rows",
    "plan_view",
    "scope_issues",
    "section_totals",
    "split_electives",
]
