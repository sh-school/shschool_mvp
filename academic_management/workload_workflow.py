"""دورةُ خطّة النصاب: مسودّةٌ ← تحقّقٌ ← مراجعةٌ ← اعتماد.

    Approval ≠ save(status="APPROVED")

فالاعتمادُ فعلٌ إداريٌّ يُوقَّع، لا حقلٌ يُكتب. ولذلك تعيش الانتقالاتُ هنا في
خدمةٍ تُشغّل البوّابةَ داخل معاملةٍ واحدة، وتختم من فعل وماذا ومتى. ولو تُرك
الأمرُ لـ`save()` لأمكن أن تصير خطّةٌ معتمَدةً من `admin` أو من سكربتٍ بلا
بوّابةٍ ولا توقيع.

وثلاثةُ مبادئَ تحكم هذه الوحدة:

    ١. القدرةُ لا المسمّى: من يعتمد يُعرَف بـ`WORKLOAD_APPROVE` لا باسم وظيفة.
    ٢. المراجعُ غيرُ المعتمِد افتراضاً — والجمعُ تجاوزٌ مسجَّل لا سلوكٌ صامت.
    ٣. كلُّ رقمٍ يعرف من أين جاء — وإلّا لم تُعتمد الخطّة.
"""

import hashlib

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core import permissions as perms
from core.models.academic import ClassGroup

from .models import (
    APPROVED,
    DRAFT,
    EDITABLE_STATUSES,
    FORWARD,
    FROM_PREVIOUS_PLAN,
    LOCKED,
    REVIEWED,
    SUBMITTED,
    TeacherWorkloadPlan,
    WorkloadGovernance,
)

EDIT = "edit"
REVIEW = "review"
APPROVE = "approve"

#: الافتراضُ الموصى به — تُبدّله المدرسةُ من `WorkloadGovernance`.
_DEFAULT_ROLES = {
    EDIT: perms.WORKLOAD_EDIT,
    REVIEW: perms.WORKLOAD_REVIEW,
    APPROVE: perms.WORKLOAD_APPROVE,
}

_GOVERNANCE_FIELD = {EDIT: "edit_roles", REVIEW: "review_roles", APPROVE: "approve_roles"}


class WorkflowError(Exception):
    """انتقالٌ غيرُ مشروعٍ في دورة الخطّة."""


# ══════════════════════════════════════════════════════════════════════
#  القدرات
# ══════════════════════════════════════════════════════════════════════


def capability_roles(school, capability):
    """أدوارُ هذه القدرة في هذه المدرسة — وفراغُ التهيئة يعني الافتراض."""
    configured = getattr(WorkloadGovernance.for_school(school), _GOVERNANCE_FIELD[capability], [])
    return set(configured) if configured else set(_DEFAULT_ROLES[capability])


def has_capability(user, school, capability):
    if user is None or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.get_role() in capability_roles(school, capability)


def require(user, school, capability):
    if not has_capability(user, school, capability):
        raise PermissionDenied(f"لا تملك قدرةَ «{capability}» على أنصبة هذه المدرسة.")


# ══════════════════════════════════════════════════════════════════════
#  البوّابة — بنودٌ لا يمرّ الاعتمادُ بسقوطِ واحدٍ منها
# ══════════════════════════════════════════════════════════════════════


def _assignment_rows(plan):
    from operations.models import SubjectClassAssignment

    return SubjectClassAssignment.objects.filter(
        school=plan.school,
        academic_year=plan.academic_year,
        teacher=plan.teacher,
        is_active=True,
    )


def assigned_periods(plan):
    """الحصصُ التدريسيّةُ المُسنَدةُ فعلاً لهذا المعلّم في هذا العام."""
    return sum(r.weekly_periods for r in _assignment_rows(plan))


def fingerprint_of(rows):
    """بصمةُ مجموعةِ إسنادات — تُحسب من صفوفٍ في اليد بلا استعلامٍ ثانٍ.

    العددُ والمجموعُ يقرؤهما إنسانٌ في التقرير، والتجزئةُ تكشف ما لا يكشفانه:
    إسنادٌ نُقل من شعبةٍ إلى أخرى بالحصص نفسها لا يغيّر رقماً ويغيّر الحقيقة.
    """
    items = sorted(
        (str(r.subject_id), str(r.class_group_id), r.weekly_periods) for r in rows
    )
    payload = "|".join(f"{s}:{c}:{p}" for s, c, p in items)
    return {
        "count": len(items),
        "periods": sum(p for _, _, p in items),
        "digest": hashlib.sha256(payload.encode()).hexdigest(),
    }


def assignment_fingerprint(plan):
    """بصمةُ إسنادات هذه الخطّة — تُقرأ من القاعدة."""
    return fingerprint_of(_assignment_rows(plan))


def has_diverged(plan, rows=None):
    """هل تباعد الإسنادُ عمّا فُحص لحظةَ الاعتماد؟

    وهذا سؤالٌ عن الزمن لا عن الصواب: خطّةٌ صحّت ثمّ تباعد عنها الواقعُ ليست
    خطّةً وُلدت خاطئة. و`rows` تُمرَّر حين تكون الشاشةُ قد قرأتها، فلا تُقرأ
    مرّتين ولا تصير الصفحةُ استعلاماً لكلّ بطاقة.
    """
    if not plan.validation_fingerprint:
        return None
    digest = (fingerprint_of(rows) if rows is not None else assignment_fingerprint(plan))["digest"]
    return digest != plan.validation_fingerprint


def _assignment_scopes(plan):
    """كلُّ (مادّة، مرحلة) أُسنِدت إليه — ومنها تُعرف مرحلتُه لحساب سعة أيّامه.

    فالخميسُ ستُّ حصصٍ في الإعداديّ وسبعٌ في الثانويّ، ومن يعمل في المرحلتين
    يُقاس بالأشدّ.
    """
    from operations.models import SubjectClassAssignment

    rows = SubjectClassAssignment.objects.filter(
        school=plan.school,
        academic_year=plan.academic_year,
        teacher=plan.teacher,
        is_active=True,
    ).select_related("subject", "class_group")
    levels = dict(
        ClassGroup.objects.filter(school=plan.school, academic_year=plan.academic_year).values_list(
            "id", "level_type"
        )
    )
    seen = {}
    for r in rows:
        level = levels.get(r.class_group_id, "")
        seen[(r.subject_id, level)] = (r.subject, level)
    return list(seen.values())


#: أسماءُ الأيّام كما في `ScheduleSlot.DAYS` — الأحدُ أوّلُ الأسبوع.
DAY_NAMES = {0: "الأحد", 1: "الاثنين", 2: "الثلاثاء", 3: "الأربعاء", 4: "الخميس"}


def available_capacity(plan):
    """كم خانةً تسعها أيّامُ المعلّم المتاحة بعد تفريغاته؟

    والتفريغُ **لا يُخفّف النصاب**: من فُرّغ يومَ الأحد لدورةٍ خارج المدرسة
    يبقى نصابُه كما هو ويُحشر في بقيّة الأيّام. ولذلك لزمت هذه المقابلة: ما
    دام الرقمُ لا ينقص، فليس بديهيّاً أنّ الأيّامَ الباقيةَ تسعه.

    وبثلاثة تفريغاتٍ يصير ثمانيةَ عشرَ نصاباً مستحيلاً — ولا يظهر استحالتُه
    إلّا يومَ يعجز المولّد، بعد أن تكون الخطّةُ قد اعتُمدت ووُقّعت.
    """
    from operations.models import TeacherExemption
    from operations.scheduler_constraints import get_max_periods_for_day

    levels = {level for _, level in _assignment_scopes(plan) if level}
    #: الأشدُّ تقييداً هو الحاكم — والخميسُ ستٌّ للإعداديّ وسبعٌ للثانويّ.
    level = "sec" if levels == {"sec"} else "prep"

    rows = TeacherExemption.objects.filter(
        school=plan.school,
        teacher=plan.teacher,
        academic_year=plan.academic_year,
        is_active=True,
    )
    days_off, blocked_periods = {}, 0
    for row in rows:
        if row.exemption_type == "full_day":
            days_off[row.day_of_week] = row.reason
        else:
            blocked_periods += 1

    capacity = (
        sum(get_max_periods_for_day(day, level) for day in DAY_NAMES if day not in days_off)
        - blocked_periods
    )

    return {
        "level": level,
        "days_off": [DAY_NAMES[d] for d in sorted(days_off)],
        "reasons": {DAY_NAMES[d]: reason for d, reason in sorted(days_off.items())},
        "blocked_periods": blocked_periods,
        "capacity": capacity,
        "target": plan.teaching_target,
        "fits": plan.teaching_target <= capacity,
    }


def is_editable(plan):
    """هل يُحرَّر محتوى الخطّة الآن؟ — المسودّةُ وحدَها تُحرَّر.

    وما رُفع للمراجعة لا يُعدَّل من تحت المراجع؛ يُردّ إلى المسودّة أوّلاً.
    """
    return plan.status in EDITABLE_STATUSES


def _check(label, passed, detail=""):
    return {"label": label, "passed": passed, "detail": detail}


def validate(plan):
    """تُعيد بنودَ البوّابة موصوفةً — ولا تغيّر شيئاً.

    وهي زرٌّ مستقلٌّ في الشاشة عمداً: على المُدخِل أن يعرف أين يقف قبل أن
    يرفعها، لا أن يكتشف النقصَ من رفضٍ عند الاعتماد.
    """
    checks = []

    gaps = plan.provenance_gaps()
    checks.append(
        _check(
            "كلُّ رقمٍ يعرف من أين جاء",
            not gaps,
            "؛ ".join(gaps) or "النصابُ والتخفيضُ لهما منبعٌ موثَّق.",
        )
    )

    checks.append(
        _check(
            "التخفيضُ ضمن النصاب",
            plan.reduction_periods <= plan.required_weekly_periods,
            f"{plan.reduction_periods} من {plan.required_weekly_periods}",
        )
    )

    rows = list(plan.allocations.all())
    total = sum(a.target_periods for a in rows)
    checks.append(
        _check(
            "التوزيعُ حسب المرحلة يبلغ الهدف",
            plan.allocations_balanced,
            (
                "لا تفصيلَ — والخطّةُ متوازنةٌ بحكم التعريف"
                if not rows
                else f"{total} مقابل {plan.teaching_target}"
            ),
        )
    )

    assigned = assigned_periods(plan)
    checks.append(
        _check(
            "المُسنَدُ فعلاً يساوي الهدفَ التدريسيّ",
            assigned == plan.teaching_target,
            f"{assigned} مقابل {plan.teaching_target}",
        )
    )

    room = available_capacity(plan)
    checks.append(
        _check(
            "الأيّامُ المتاحةُ تسع الهدفَ التدريسيّ",
            room["fits"],
            (
                f"{room['target']} في {room['capacity']} خانة"
                + (f" — مفرَّغٌ: {'، '.join(room['days_off'])}" if room["days_off"] else "")
            ),
        )
    )

    return checks


def blocking(checks):
    return [c["label"] for c in checks if not c["passed"]]


# ══════════════════════════════════════════════════════════════════════
#  الانتقالات
# ══════════════════════════════════════════════════════════════════════


def _move(plan, to_status):
    if to_status not in FORWARD[plan.status]:
        raise WorkflowError(
            f"لا انتقالَ من «{plan.get_status_display()}» إلى «{to_status}» — "
            "والدورةُ لا تُقفز فوق مراحلها."
        )


@transaction.atomic
def open_draft(school, teacher, academic_year, *, by, **fields):
    """مسودّةٌ جديدةٌ بإصدارٍ يلي أعلى إصدارٍ قائم."""
    require(by, school, EDIT)
    latest = (
        TeacherWorkloadPlan.objects.filter(
            school=school, teacher=teacher, academic_year=academic_year
        )
        .order_by("-plan_version")
        .first()
    )
    plan = TeacherWorkloadPlan(
        school=school,
        teacher=teacher,
        academic_year=academic_year,
        plan_version=(latest.plan_version + 1) if latest else 1,
        status=DRAFT,
        created_by=by,
        updated_by=by,
        **fields,
    )
    plan.full_clean(exclude=["created_by", "updated_by"])
    plan.save()
    return plan


@transaction.atomic
def new_version_from(plan, *, by):
    """تعديلُ خطّةٍ معتمَدةٍ = إصدارٌ جديد، والقديمُ يبقى قائماً كما اعتُمد."""
    require(by, plan.school, EDIT)
    if plan.status not in (APPROVED, LOCKED):
        raise WorkflowError("الإصدارُ الجديدُ يُشتقّ من نسخةٍ معتمَدة — وهذه لم تُعتمد بعد.")
    return open_draft(
        plan.school,
        plan.teacher,
        plan.academic_year,
        by=by,
        required_weekly_periods=plan.required_weekly_periods,
        required_source_kind=FROM_PREVIOUS_PLAN,
        required_source_plan=plan,
        reduction_periods=plan.reduction_periods,
        reduction_reason=plan.reduction_reason,
        reduction_source=plan.reduction_source,
        reduction_source_reference=plan.reduction_source_reference,
    )


@transaction.atomic
def submit_for_review(plan, *, by):
    require(by, plan.school, EDIT)
    _move(plan, SUBMITTED)
    plan.status = SUBMITTED
    plan.submitted_by = by
    plan.submitted_at = timezone.now()
    plan.updated_by = by
    plan.save()
    return plan


@transaction.atomic
def record_review(plan, *, by, comment=""):
    """المراجعةُ ختمٌ باسمٍ ووقت — لا مجرّدُ حالةٍ تتغيّر."""
    require(by, plan.school, REVIEW)
    _move(plan, REVIEWED)
    plan.status = REVIEWED
    plan.reviewed_by = by
    plan.reviewed_at = timezone.now()
    plan.review_comment = comment
    plan.updated_by = by
    plan.save()
    return plan


@transaction.atomic
def return_to_draft(plan, *, by, comment=""):
    """الردُّ إلى المُدخِل رجوعٌ مشروع — والمسودّةُ تُحرَّر من جديد."""
    require(by, plan.school, REVIEW)
    _move(plan, DRAFT)
    plan.status = DRAFT
    plan.review_comment = comment
    plan.updated_by = by
    plan.save()
    return plan


@transaction.atomic
def approve(plan, *, by):
    """الاعتمادُ: بوّابةٌ كاملةٌ ثمّ توقيع — وسقوطُ بندٍ يمنعه.

    وتُعاد البوّابةُ هنا ولو شُغِّلت قبل قليلٍ بزرّ التحقّق، لأنّ الإسنادَ قد
    يتغيّر تحت الخطّة بين اللحظتين.
    """
    require(by, plan.school, APPROVE)
    _move(plan, APPROVED)

    failed = blocking(validate(plan))
    if failed:
        raise ValidationError("لا تُعتمد الخطّةُ وفيها بنودٌ غيرُ مثبتة: " + "، ".join(failed))

    governance = WorkloadGovernance.for_school(plan.school)
    self_approval = plan.reviewed_by_id == by.id
    if self_approval and not governance.allow_self_approval:
        raise PermissionDenied(
            "من راجع الخطّةَ لا يعتمدها — وإلّا فُقدت المراجعةُ المستقلّة. "
            "وإن أرادت المدرسةُ الجمعَ فبتهيئةٍ صريحةٍ تُسجَّل."
        )

    stamp = assignment_fingerprint(plan)
    plan.status = APPROVED
    plan.approved_by = by
    plan.approved_at = timezone.now()
    plan.self_approval_override = self_approval
    plan.validated_at = timezone.now()
    plan.validated_assignment_count = stamp["count"]
    plan.validated_assignment_periods = stamp["periods"]
    plan.validation_fingerprint = stamp["digest"]
    plan.updated_by = by
    plan.save()

    if self_approval:
        _audit_self_approval(plan, by)
    return plan


@transaction.atomic
def lock(plan, *, by):
    """القفلُ للجدولة — آخرُ انتقالٍ، وبعده لا شيء."""
    require(by, plan.school, APPROVE)
    _move(plan, LOCKED)
    plan.status = LOCKED
    plan.updated_by = by
    plan.save()
    return plan


def _audit_self_approval(plan, by):
    """التجاوزُ يُكتب في سجلّ التدقيق — فالصمتُ عنه يُلغي معناه."""
    from core.signals import _log

    _log(
        "other",
        "update",
        plan,
        changes={
            "event": "workload_self_approval_override",
            "plan": str(plan.pk),
            "actor": str(by.pk),
            "note": "راجع الخطّةَ واعتمدها الشخصُ نفسُه بتهيئةٍ صريحةٍ للمدرسة.",
        },
    )
