"""
نصابُ المعلّم كما هو **مرصودٌ في الجدول** — لا كما هو معتمَدٌ إداريّاً.

    ObservedScheduledWorkload ≠ ApprovedWorkload

وهذا الفرقُ هو كلُّ شيء. فمعلّمٌ ظهر في الجدول بثماني حصصٍ قد يكون نصابُه
الرسميُّ ثمانيةَ عشرَ وله تخفيضُ منسّقِ مادّة، وقد يكون نصابُه ثمانياً فعلاً،
وقد يكون نقصاً في الإسناد لم ينتبه له أحد. **والجدولُ وحده لا يعرف** — ليس
فيه حقلٌ للنصاب المطلوب ولا للتخفيض ولا لمن اعتمده.

    RequiredLoad = TeachingLoad + ApprovedReductions

ولا يُحسب الطرفُ الأيسرُ من الجدول. فما هنا مصدرُ **اقتراحٍ** لخطّة النصاب،
لا مصدرُ حقيقةٍ عنها:

    HistoricalAssignment → Proposal        (وليس → Truth)

وثلاثةُ أشياء لا تُخلط:

    CanTeach ≠ AssignedToTeach ≠ ActuallyScheduled

وهذه الوحدةُ تقيس الأخيرَ، وتقارنه بالثاني (`SubjectClassAssignment`).
والأوّلُ — المؤهّلُ — ليس في القاعدة أصلاً، فيُذكر أنّه غيرُ معلومٍ ولا
يُستنتج من ظهور المعلّم في مادّة.

ولا تكتب هذه الوحدةُ شيئاً في القاعدة.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from core.models.academic import grade_order
from operations.schedule_profile import DAY_NAMES

MATCH = "MATCH"
SCHEDULE_ONLY = "SCHEDULE_ONLY"  # في الجدول ولا إسنادَ له
ASSIGNMENT_ONLY = "ASSIGNMENT_ONLY"  # إسنادٌ لم يُجدوَل
DIFFERENT_COUNT = "DIFFERENT_COUNT"
DIFFERENT_TEACHER = "DIFFERENT_TEACHER"


# ══════════════════════════════════════════════════════════════════════
#  ١. النصابُ المرصود في الجدول
# ══════════════════════════════════════════════════════════════════════


@dataclass
class TeacherWorkload:
    """ما ظهر في الجدول لمعلّمٍ واحد — مرصودٌ لا معتمَد."""

    teacher_id: str
    name: str
    observed_weekly: int = 0
    subjects: dict = field(default_factory=dict)  # subject_id ← {code, name, periods}
    grades: dict = field(default_factory=dict)
    sections: dict = field(default_factory=dict)
    per_subject_class: dict = field(default_factory=dict)  # «MATH·7/1» ← عدد
    per_day: dict = field(default_factory=dict)
    levels: dict = field(default_factory=dict)
    split_periods: int = 0  # حصصٌ تنقسم فيها الشعبةُ بين مادّتين

    @property
    def multi_subject(self):
        return len(self.subjects) > 1

    @property
    def multi_level(self):
        return len(self.levels) > 1

    @property
    def sections_per_subject(self):
        counts = defaultdict(set)
        for key in self.per_subject_class:
            code, section = key.split("·", 1)
            counts[code].add(section)
        return {code: len(sections) for code, sections in sorted(counts.items())}


def observed_workload(lessons):
    """لكلّ معلّم: موادُّه وصفوفُه وشعبُه وحصصُه — كما هي في الجدول.

    والحصّةُ المنقسمة تُعدّ حصّةً كاملةً لكلّ معلّمٍ فيها: خانةٌ واحدةٌ تحمل
    مجموعتين من الطلاب في مادّتين، وكلاهما يعمل. فلا يُنقَص نصابُ أحدهما
    لأنّ زميلَه يشاركه التوقيت.
    """
    split_slots = {
        key
        for key, count in Counter((x.class_id, x.day, x.period) for x in lessons).items()
        if count > 1
    }

    rows = {}
    for x in lessons:
        row = rows.setdefault(
            x.teacher_id, TeacherWorkload(teacher_id=x.teacher_id, name=x.teacher_name)
        )
        row.observed_weekly += 1

        entry = row.subjects.setdefault(
            x.subject_id, {"code": x.subject_code, "name": x.subject_name, "periods": 0}
        )
        entry["periods"] += 1

        section = x.class_label or x.class_name
        key = f"{x.subject_code or x.subject_id[:6]}·{section}"
        row.per_subject_class[key] = row.per_subject_class.get(key, 0) + 1

        for bucket, value in (
            (row.grades, x.grade or "—"),
            (row.sections, section),
            (row.levels, x.level_type or "—"),
            (row.per_day, DAY_NAMES.get(x.day, str(x.day))),
        ):
            bucket[value] = bucket.get(value, 0) + 1

        if (x.class_id, x.day, x.period) in split_slots:
            row.split_periods += 1

    for row in rows.values():
        row.subjects = dict(sorted(row.subjects.items(), key=lambda kv: -kv[1]["periods"]))
        row.per_subject_class = dict(sorted(row.per_subject_class.items()))
    return dict(sorted(rows.items(), key=lambda kv: -kv[1].observed_weekly))


# ══════════════════════════════════════════════════════════════════════
#  ٢. النصابُ المُسنَد في `SubjectClassAssignment`
# ══════════════════════════════════════════════════════════════════════


def assignment_rows(school, academic_year):
    """يقرأ الإسنادات النشطة — بمعرّفاتها لا بأسمائها."""
    from operations.models import SubjectClassAssignment

    rows = (
        SubjectClassAssignment.objects.filter(
            school=school, academic_year=academic_year, is_active=True
        )
        .select_related("teacher", "class_group", "subject")
        .order_by(grade_order("class_group__grade"), "class_group__section")
    )
    out = []
    for r in rows:
        grade = (r.class_group.grade or "").removeprefix("G")
        out.append(
            {
                "teacher_id": str(r.teacher_id) if r.teacher_id else "",
                "teacher_name": r.teacher.full_name if r.teacher else "— بلا معلّم —",
                "class_id": str(r.class_group_id),
                "section": f"{grade}/{r.class_group.section}",
                "grade": r.class_group.grade or "—",
                "subject_id": str(r.subject_id),
                "code": r.subject.code or "",
                "name": r.subject.name_ar,
                "weekly_periods": r.weekly_periods,
            }
        )
    return out


def assigned_workload(rows):
    """مجموعُ `weekly_periods` لكلّ معلّم — وما بلا معلّمٍ يُجمَع تحت «—»."""
    totals = defaultdict(lambda: {"name": "", "weekly": 0, "cells": 0, "subjects": set()})
    for r in rows:
        key = r["teacher_id"] or "—"
        bucket = totals[key]
        bucket["name"] = r["teacher_name"]
        bucket["weekly"] += r["weekly_periods"]
        bucket["cells"] += 1
        bucket["subjects"].add(r["subject_id"])
    return {
        k: {**v, "subjects": len(v["subjects"])}
        for k, v in sorted(totals.items(), key=lambda kv: -kv[1]["weekly"])
    }


# ══════════════════════════════════════════════════════════════════════
#  ٣. المطابقة: الجدولُ مقابل الإسناد
# ══════════════════════════════════════════════════════════════════════


def reconcile_cells(lessons, rows):
    """يقارن خليّةً بخليّة: (شعبة × مادّة) ← كم حصّةً، ومن المعلّم.

    والمقارنةُ على مستوى الخليّة لا المجموع: معلّمان تبادلا شعبتين يظهر
    مجموعُ كلٍّ منهما سليماً وهما مخطئان في الاثنتين.
    """
    scheduled = defaultdict(lambda: {"periods": 0, "teachers": Counter()})
    meta = {}
    for x in lessons:
        key = (x.class_id, x.subject_id)
        scheduled[key]["periods"] += 1
        scheduled[key]["teachers"][x.teacher_name] += 1
        meta[key] = (x.class_label or x.class_name, x.subject_code, x.subject_name)

    assigned = {(r["class_id"], r["subject_id"]): r for r in rows}

    out = []
    for key in sorted(set(scheduled) | set(assigned), key=str):
        sch = scheduled.get(key)
        asg = assigned.get(key)
        if sch and not asg:
            status, delta = SCHEDULE_ONLY, sch["periods"]
        elif asg and not sch:
            status, delta = ASSIGNMENT_ONLY, -asg["weekly_periods"]
        else:
            delta = sch["periods"] - asg["weekly_periods"]
            top = sch["teachers"].most_common(1)[0][0]
            if delta:
                status = DIFFERENT_COUNT
            elif asg["teacher_name"] != top:
                status = DIFFERENT_TEACHER
            else:
                status = MATCH
        if key in meta:
            section, code, name = meta[key]
        else:
            section, code, name = asg["section"], asg["code"], asg["name"]
        out.append(
            {
                "section": section,
                "code": code,
                "name": name,
                "scheduled": sch["periods"] if sch else 0,
                "assigned": asg["weekly_periods"] if asg else 0,
                "delta": delta,
                "scheduled_teacher": sch["teachers"].most_common(1)[0][0] if sch else "—",
                "assigned_teacher": asg["teacher_name"] if asg else "—",
                "status": status,
            }
        )
    return out


def reconcile_teachers(observed, rows):
    """مجموعُ كلِّ معلّمٍ في الجدول مقابل مجموعه في الإسناد."""
    assigned = assigned_workload(rows)
    out = {}
    for teacher_id in set(observed) | set(assigned):
        obs = observed.get(teacher_id)
        asg = assigned.get(teacher_id)
        scheduled = obs.observed_weekly if obs else 0
        planned = asg["weekly"] if asg else 0
        if scheduled == planned:
            status = MATCH
        elif not planned:
            status = SCHEDULE_ONLY
        elif not scheduled:
            status = ASSIGNMENT_ONLY
        else:
            status = DIFFERENT_COUNT
        out[teacher_id] = {
            "name": obs.name if obs else asg["name"],
            "scheduled": scheduled,
            "assigned": planned,
            "delta": scheduled - planned,
            "status": status,
        }
    return dict(sorted(out.items(), key=lambda kv: (-abs(kv[1]["delta"]), -kv[1]["scheduled"])))


def demand_coverage(lessons, rows):
    """ميزانيّةُ الحصص لكلّ (صفّ × مادّة): المطلوبُ مقابل المُسنَد والمُجدوَل.

    فلا يكفي أن يتوازن نصابُ المعلّمين: أربعُ شعبٍ في السابع × خمسِ حصصِ
    رياضيّاتٍ = عشرون حصّةً يجب أن تُسنَد كلُّها. فإن كان مجموعُ إسنادات
    معلّمي الرياضيّات تسعةَ عشرَ، فثمّةَ حصّةٌ بلا معلّم.
    """
    scheduled = Counter((x.grade or "—", x.subject_id) for x in lessons)
    meta = {(x.grade or "—", x.subject_id): (x.subject_code, x.subject_name) for x in lessons}
    assigned = Counter()
    sections = defaultdict(set)
    unstaffed = Counter()
    for r in rows:
        key = (r["grade"], r["subject_id"])
        assigned[key] += r["weekly_periods"]
        sections[key].add(r["section"])
        meta.setdefault(key, (r["code"], r["name"]))
        if not r["teacher_id"]:
            unstaffed[key] += r["weekly_periods"]

    out = []
    for key in sorted(set(scheduled) | set(assigned), key=lambda k: (k[0], str(meta.get(k)))):
        code, name = meta.get(key, ("—", "—"))
        out.append(
            {
                "grade": key[0],
                "code": code,
                "name": name,
                "sections": len(sections.get(key, ())),
                "scheduled": scheduled.get(key, 0),
                "assigned": assigned.get(key, 0),
                "delta": scheduled.get(key, 0) - assigned.get(key, 0),
                "unstaffed": unstaffed.get(key, 0),
            }
        )
    return out


def summary(cells, teachers):
    return {
        "cells": dict(Counter(c["status"] for c in cells)),
        "teachers": dict(Counter(t["status"] for t in teachers.values())),
        "scheduled_total": sum(c["scheduled"] for c in cells),
        "assigned_total": sum(c["assigned"] for c in cells),
    }
