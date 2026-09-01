"""
أساسُ إسناد الأنصبة — ما هو قائمٌ اليوم، لا ما ينبغي أن يكون.

الشاشةُ في مرحلتها الأولى **قراءةٌ محضة**: تجيب عن سؤالٍ واحدٍ بوضوح —
*مَن يُدرّس ماذا، ولأيّ شعبة، وكم حصّة؟* — وتترك السؤالَ الرابع مفتوحاً:
*وما الفرقُ بين المرصود والمعتمد؟* لأنّ المعتمَدَ ليس في القاعدة بعد.

    ObservedScheduledWorkload ≠ ApprovedWorkload

ولذلك لا يُملأ «النصابُ المعتمد» من الـ870 حصّة. التاريخُ مصدرُ اقتراحٍ لا
مصدرُ سياسة:

    HistoricalAssignment → Proposal        (وليس → Truth)

وكلُّ دالّةٍ هنا تأخذ `academic_year` صراحةً. فالشاشةُ ليست عن «الحالة
الحاليّة» بلا تاريخ: هي عن عامٍ بعينه، وستأخذ نسخةَ خطّةٍ بعينها حين تُبنى
`TeacherWorkloadPlan`. و`plan_context` يحمل اليومَ نسخةً فارغةً مُسمّاةً كي
لا تُضاف بأثرٍ رجعيّ على تصميمٍ لم يحسب لها حساباً.
"""

from collections import defaultdict

from academic_management.models import (
    APPROVED,
    DRAFT,
    FROZEN_STATUSES,
    LOCKED,
    REVIEWED,
    SUBMITTED,
    TeacherSubjectQualification,
    TeacherWorkloadPlan,
)
from operations import schedule_profile as base
from operations import workload_profile as wl

#: ما تستطيع الشاشةُ التحقّقَ منه اليومَ من البيانات القائمة.
ENFORCEABLE = "CURRENTLY_ENFORCEABLE"
#: ما يعتمد على الخطّة المعتمَدة والمؤهّلات — يُقاس متى وُجدت، ويُقال «لا جوابَ
#: بعد» متى غابت. وكان اسمُه «موقوفٌ حتى تُبنى النماذج» فبقي بعد أن بُنيت،
#: يقول للمستخدم إنّ النظامَ ناقصٌ وقد اكتمل.
NEEDS_MODELS = "REQUIRES_APPROVED_PLAN"

#: الحقولُ التي لا مصدرَ لها بعد — تُعرض «غير محدَّدة» ولا تُشتقّ من الجدول.
UNKNOWN = "غير محدَّد"


#: عناوينُ حالة الخطّة كما تُعرض في الشاشة.
STATUS_LABELS = {
    DRAFT: "مسوّدة",
    SUBMITTED: "قيد المراجعة",
    REVIEWED: "روجعت — بانتظار الاعتماد",
    APPROVED: "معتمدة",
    LOCKED: "مقفلة",
}


def plan_context(school, academic_year):
    """سياقُ الخطّة: عامٌ ونسخة. وتُسمّى النسخةُ الغائبةُ غيابَها صراحةً."""
    plans = (
        TeacherWorkloadPlan.objects.filter(school=school, academic_year=academic_year)
        if school
        else TeacherWorkloadPlan.objects.none()
    )
    approved = plans.filter(status__in=FROZEN_STATUSES)
    latest = approved.order_by("-plan_version").first()
    return {
        "school": school,
        "academic_year": academic_year,
        "plan_version": latest.plan_version if latest else None,
        "plan_status": (
            f"خطّةُ النصاب: نسخة {latest.plan_version} — {STATUS_LABELS[latest.status]}"
            f" · {approved.count()} معلّماً معتمَداً"
            if latest
            else "لا توجد نسخةُ خطّةٍ معتمدة"
        ),
        "drafts": plans.filter(status__in=(DRAFT, SUBMITTED, REVIEWED)).count(),
        "approved_teachers": approved.count(),
        "is_read_only": True,
    }


def plans_by_teacher(school, academic_year):
    """أحدثُ نسخةٍ لكلّ معلّم — المعتمدةُ إن وُجدت، وإلّا فالمسوّدةُ موسومةً.

    والمسوّدةُ **لا تُعرض رقماً معتمَداً**: تُعرض بوصفها مسوّدةً كي لا يُقرأ
    ما لم يُوقَّع بعدُ على أنّه قرار.
    """
    if not school:
        return {}
    out = {}
    for row in (
        TeacherWorkloadPlan.objects.filter(school=school, academic_year=academic_year)
        .select_related("teacher")
        .prefetch_related("allocations")
        .order_by("plan_version")
    ):
        key = str(row.teacher_id)
        current = out.get(key)
        if current is None or _rank(row) >= _rank(current):
            out[key] = row
    return out


def _rank(plan):
    """المعتمَدةُ تسبق المسوّدة، ثمّ الأحدثُ نسخةً."""
    return (1 if plan.status in FROZEN_STATUSES else 0, plan.plan_version)


def plan_display(plan, observed):
    """ما يُعرض في خانة «المعتمَد» — ولا يُملأ من المرصود أبداً."""
    if plan is None:
        return {
            "state": "none",
            "label": UNKNOWN,
            "approved": None,
            "reductions": None,
            "required": None,
            "delta": None,
            "version": None,
            "source": None,
            "note": "لا خطّةَ لهذا المعلّم في هذا العام.",
        }
    if plan.status not in FROZEN_STATUSES:
        return {
            "state": "draft",
            "label": f"{STATUS_LABELS[plan.status]} (نسخة {plan.plan_version})",
            "approved": None,
            "reductions": None,
            "required": None,
            "delta": None,
            "version": plan.plan_version,
            "source": None,
            "note": "مسوّدةٌ لم تُعتمد — لا تُقرأ رقماً معتمَداً.",
        }
    gap = plan.discrepancy(observed)
    return {
        "state": "approved",
        "label": f"{plan.teaching_target}",
        "approved": plan.teaching_target,
        "required": plan.required_weekly_periods,
        "reductions": plan.reduction_periods,
        "reduction_reason": plan.reduction_reason,
        "delta": gap["delta"],
        "is_error": gap["is_error"],
        "version": plan.plan_version,
        # مصدرُ كلِّ رقمٍ على حدة — فالنصابُ قد يأتي من تعميمٍ والتخفيضُ من قرارٍ آخر.
        "required_source": plan.get_required_source_kind_display(),
        "required_source_reference": (
            plan.required_source_reference or plan.required_policy_key
        ),
        "reduction_source": plan.get_reduction_source_display() if plan.reduction_source else "",
        "reduction_source_reference": plan.reduction_source_reference,
        "allocations": [
            {"level": a.get_level_type_display(), "periods": a.target_periods}
            for a in plan.allocations.all()
        ],
        "note": gap["note"],
    }


def load(school, academic_year):
    """يقرأ الجدولَ والإسنادات مرّةً واحدةً — ولا يكتب."""
    lessons = base.load_lessons(school, academic_year)
    rows = wl.assignment_rows(school, academic_year)
    return lessons, rows


# ══════════════════════════════════════════════════════════════════════
#  المناظير الثلاثة
# ══════════════════════════════════════════════════════════════════════


def teacher_view(lessons, rows, plans=None):
    """منظورُ المعلّم: موادُّه وشعبُه وحصصُه لكلّ شعبة وتوزيعُه اليوميّ."""
    observed = wl.observed_workload(lessons)
    reconciled = wl.reconcile_teachers(observed, rows)
    plans = plans or {}

    out = []
    for teacher_id, row in observed.items():
        check = reconciled.get(teacher_id, {})
        cells = []
        for key, periods in row.per_subject_class.items():
            code, section = key.split("·", 1)
            cells.append({"code": code, "section": section, "periods": periods})
        cells.sort(key=lambda c: (c["code"], c["section"]))
        out.append(
            {
                "teacher_id": teacher_id,
                "name": row.name,
                "observed_weekly": row.observed_weekly,
                "assigned_weekly": check.get("assigned", 0),
                "delta": check.get("delta", 0),
                "status": check.get("status", ""),
                "subjects": list(row.subjects.values()),
                "sections": sorted(row.sections),
                "grades": sorted(row.grades),
                "per_day": row.per_day,
                "cells": cells,
                "multi_subject": row.multi_subject,
                "multi_level": row.multi_level,
                "split_periods": row.split_periods,
                # طبقةُ النصاب المعتمد — مصدرُها الخطّةُ وحدَها.
                "plan": plan_display(plans.get(teacher_id), row.observed_weekly),
                "approved_weekly": None,
                "reductions": None,
                "required_teaching": None,
                "qualifications": None,
            }
        )
    return sorted(out, key=lambda t: -t["observed_weekly"])


def subject_view(lessons, rows):
    """منظورُ المادّة: الطلبُ موزَّعاً على الشُّعب، ومن يغطّيه — Coverage Matrix."""
    scheduled = defaultdict(int)
    teachers = defaultdict(set)
    meta = {}
    for x in lessons:
        key = (x.subject_id, x.grade or "—", x.class_label or x.class_name)
        scheduled[key] += 1
        teachers[key].add(x.teacher_name)
        meta[(x.subject_id, x.grade or "—")] = (x.subject_code, x.subject_name)

    assigned = {}
    for r in rows:
        assigned[(r["subject_id"], r["grade"], r["section"])] = r
        meta.setdefault((r["subject_id"], r["grade"]), (r["code"], r["name"]))

    groups = defaultdict(list)
    for key in sorted(set(scheduled) | set(assigned), key=lambda k: (k[1], k[2])):
        subject_id, grade, section = key
        asg = assigned.get(key)
        groups[(subject_id, grade)].append(
            {
                "section": section,
                "scheduled": scheduled.get(key, 0),
                "assigned": asg["weekly_periods"] if asg else 0,
                "teacher": ("، ".join(sorted(teachers[key])) if key in teachers else UNKNOWN),
                "assigned_teacher": asg["teacher_name"] if asg else UNKNOWN,
            }
        )

    out = []
    for (subject_id, grade), sections in groups.items():
        code, name = meta.get((subject_id, grade), ("", "—"))
        demand = sum(s["scheduled"] for s in sections)
        covered = sum(s["assigned"] for s in sections)
        out.append(
            {
                "subject_id": subject_id,
                "code": code,
                "name": name,
                "grade": grade,
                "sections": sections,
                "demand": demand,
                "covered": covered,
                "delta": demand - covered,
                "unstaffed": sum(1 for s in sections if s["assigned_teacher"] == UNKNOWN),
            }
        )
    return sorted(out, key=lambda s: (s["grade"], -s["demand"]))


def section_view(lessons, rows):
    """منظورُ الشعبة: كلُّ موادّها ومعلّميها وعددُ حصصها."""
    scheduled = defaultdict(int)
    teachers = {}
    meta = {}
    for x in lessons:
        key = (x.class_id, x.subject_id)
        scheduled[key] += 1
        teachers[key] = x.teacher_name
        meta[x.class_id] = (x.class_label or x.class_name, x.grade or "—", x.level_type or "—")
        meta[(x.class_id, x.subject_id)] = (x.subject_code, x.subject_name)

    assigned = {(r["class_id"], r["subject_id"]): r for r in rows}

    groups = defaultdict(list)
    for key in sorted(set(scheduled) | set(assigned), key=str):
        class_id, subject_id = key
        asg = assigned.get(key)
        if key in meta:
            code, name = meta[key]
        else:
            code, name = asg["code"], asg["name"]
        groups[class_id].append(
            {
                "code": code,
                "name": name,
                "scheduled": scheduled.get(key, 0),
                "assigned": asg["weekly_periods"] if asg else 0,
                "teacher": teachers.get(key) or (asg["teacher_name"] if asg else UNKNOWN),
            }
        )
        if class_id not in meta and asg:
            meta[class_id] = (asg["section"], asg["grade"], "—")

    out = []
    for class_id, subjects in groups.items():
        label, grade, level = meta.get(class_id, ("—", "—", "—"))
        out.append(
            {
                "class_id": class_id,
                "label": label,
                "grade": grade,
                "level": level,
                "subjects": sorted(subjects, key=lambda s: -s["scheduled"]),
                "weekly": sum(s["scheduled"] for s in subjects),
                "teachers": len({s["teacher"] for s in subjects}),
            }
        )
    return sorted(out, key=lambda s: (s["grade"], s["label"]))


# ══════════════════════════════════════════════════════════════════════
#  البوّابة — مرحلتان لا واحدة
# ══════════════════════════════════════════════════════════════════════


def permitting_pairs(school):
    """أزواجُ (معلّم · مادّة) التي يُجيزها مؤهّلٌ سارٍ — تُقرأ مرّةً وتُمرَّر.

    وتُقرأ هنا لا داخل `gate`: البوّابةُ دالّةٌ على بياناتٍ محمَّلةٍ سلفاً، ولو
    استعلمت بنفسها لصارت تعتمد على قاعدةٍ لا على وسائطها — فيصعب اختبارُها
    ويتضاعف الاستعلامُ مع كلّ منظور.
    """
    rows = TeacherSubjectQualification.objects.filter(school=school)
    return {
        (str(q.teacher_id), str(q.subject_id))
        for q in rows
        if q.permits_teaching and q.is_valid_on()
    }


def gate(lessons, rows, plans=None, quals=None):
    """شروطُ الإسناد الثمانية، مفصولةً بما تملك القاعدةُ اليومَ الإجابةَ عنه.

    وخلطُ الطرفين يجعل «سلامةَ الواقع القائم» رهينةً لنظامِ تخطيطٍ لم يُبنَ:
    فتظهر أربعةُ شروطٍ خضراءَ فعلاً وكأنّها ناقصة. ولذلك تُفصل الطبقتان.
    """
    cells = wl.reconcile_cells(lessons, rows)
    coverage = wl.demand_coverage(lessons, rows)
    observed = wl.observed_workload(lessons)
    teachers = wl.reconcile_teachers(observed, rows)
    plans = plans or {}
    approved = {k: p for k, p in plans.items() if p.status in FROZEN_STATUSES}

    # إسنادٌ لا يغطّيه مؤهّلٌ سارٍ — يُقاس متى وُجد مؤهّلٌ واحدٌ في المدرسة.
    permitting = quals or set()
    unqualified = [
        r
        for r in rows
        if r["teacher_id"] and (r["teacher_id"], r["subject_id"]) not in permitting
    ]

    #: خطّةٌ معتمَدةٌ ينقص رقماً من أرقامها منبعُه.
    undocumented = [p for p in approved.values() if p.provenance_gaps()]

    missing_cells = [c for c in cells if c["status"] != wl.MATCH]
    unstaffed = [r for r in rows if not r["teacher_id"]]
    zero_period = [r for r in rows if r["weekly_periods"] <= 0]
    uncovered = [r for r in coverage if r["delta"]]

    # ∑ AssignedInstructionalPeriods = TeachingTarget — بعد الاعتماد فقط.
    off_target = []
    for teacher_id, plan in approved.items():
        row = observed.get(teacher_id)
        if row and row.observed_weekly != plan.teaching_target:
            off_target.append(
                {
                    "name": plan.teacher.full_name,
                    "observed": row.observed_weekly,
                    "target": plan.teaching_target,
                    "delta": row.observed_weekly - plan.teaching_target,
                }
            )

    checks = [
        {
            "layer": ENFORCEABLE,
            "label": "لكلّ شعبة × مادّة عددُ حصصٍ مطلوب",
            "passed": not zero_period,
            "detail": f"{len(rows)} إسناداً، منها {len(zero_period)} بلا عددِ حصص",
        },
        {
            "layer": ENFORCEABLE,
            "label": "كلُّ إسنادٍ له معلّم",
            "passed": not unstaffed,
            "detail": f"{len(unstaffed)} إسناداً بلا معلّم",
        },
        {
            "layer": ENFORCEABLE,
            "label": "لا خليّةَ ناقصةً بين الإسناد والجدول",
            "passed": not missing_cells,
            "detail": f"{len(cells) - len(missing_cells)} من {len(cells)} خليّةً مطابقة",
        },
        {
            "layer": ENFORCEABLE,
            "label": "طلبُ كلّ (صفّ × مادّة) مغطّى بالكامل",
            "passed": not uncovered,
            "detail": f"{len(uncovered)} مجموعةً غيرَ مغطّاة من {len(coverage)}",
        },
        {
            "layer": NEEDS_MODELS,
            "label": "لكلّ معلّمٍ نصابٌ معتمَد",
            "passed": (len(approved) == len(observed)) if approved else None,
            "detail": (
                f"{len(approved)} من {len(observed)} معلّماً لهم خطّةٌ معتمَدة"
                if approved
                else "لا خطّةَ معتمَدةً بعد — TeacherWorkloadPlan فارغ"
            ),
        },
        {
            "layer": NEEDS_MODELS,
            "label": "مجموعُ إسنادات المعلّم يساوي هدفَه التدريسيّ",
            "passed": (not off_target) if approved else None,
            "detail": (
                f"{len(off_target)} معلّماً يخالف هدفَه من {len(approved)} معتمَداً"
                if approved
                else "لا يصير شرطاً حتى تُعتمد خطّةُ المعلّم"
            ),
        },
        {
            "layer": NEEDS_MODELS,
            "label": "لا مادّةَ مُسنَدةً لمعلّمٍ غير مؤهَّل",
            "passed": (not unqualified) if quals else None,
            "detail": (
                f"{len(unqualified)} إسناداً بلا مؤهّلٍ سارٍ من {len(rows)}"
                if quals
                else "لا مؤهّلَ مسجَّلٌ بعد — وغيابُ السجلّ ليس إذناً بالتدريس"
            ),
        },
        {
            "layer": NEEDS_MODELS,
            "label": "كلُّ تخفيضٍ له سببُه ومرجعُه",
            "passed": (not undocumented) if approved else None,
            "detail": (
                f"{len(undocumented)} خطّةً معتمَدةً ينقصها مصدرُ رقمٍ من {len(approved)}"
                if approved
                else "لا يصير شرطاً حتى تُعتمد خطّةُ المعلّم"
            ),
        },
    ]
    return {
        "checks": checks,
        "enforceable_passed": sum(1 for c in checks if c["layer"] == ENFORCEABLE and c["passed"]),
        "enforceable_total": sum(1 for c in checks if c["layer"] == ENFORCEABLE),
        "blocked_total": sum(1 for c in checks if c["layer"] == NEEDS_MODELS),
        "off_target": off_target[:50],
        "issues": missing_cells[:50],
        "teacher_issues": [t for t in teachers.values() if t["status"] != wl.MATCH][:50],
    }


def totals(lessons, rows):
    return {
        "lessons": len(lessons),
        "assigned": sum(r["weekly_periods"] for r in rows),
        "teachers": len({x.teacher_id for x in lessons}),
        "sections": len({x.class_id for x in lessons}),
        "subjects": len({x.subject_id for x in lessons}),
        "cells": len(rows),
    }
