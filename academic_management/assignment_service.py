"""خدمةُ الإسناد — المسارُ الوحيدُ الذي تُكتب منه حقيقةُ «من يدرّس ماذا».

    Screen → check() → apply()
    Import → check() → apply()
    Command → check() → apply()

ولا يكتب أحدٌ في `SubjectClassAssignment` أو `CoursePreparation` من خارجها.
فكانت شاشةُ التوزيعات تكتب في النموذج مباشرةً بلا تحقّق، وتقبل أيَّ معلّمٍ
لأيّ مادّةٍ بأيّ عددِ حصص، ويُكتشف الخطأُ بعد شهرٍ في شاشةٍ أخرى.

## ثلاثُ درجاتٍ لا حكمٌ واحد

    BLOCK   مانعٌ — يُرفض الحفظ، ويُقال لماذا
    WARN    تحذيرٌ — يُحفظ ويُسجَّل في التدقيق أنّه حُفظ رغمه
    INFO    معلومةٌ — تُعرض ولا تؤثّر

و«الإسنادُ غيرُ صالح» جملةٌ لا تُصلح شيئاً؛ أمّا «المعلّمُ على 18 وهدفُه 16»
فتقول للمُدخِل أين يذهب. والمدرسةُ ترفع ما تشاء من التحذيرات إلى المنع من
`WorkloadGovernance.strict_codes` بلا نشر.

## التزامنُ يُحرَس هنا

كلُّ `apply` يحمل الطابعَ الذي رآه المُدخِل (`expected_updated_at`)، فإن كتب
غيرُه قبله رُفض التعديلُ بـ`StaleWriteError` بدل أن يُطمَس. فآخرُ من يضغط
«حفظ» ليس أحقَّ بالحقيقة من زميلٍ سبقه.

## والتدقيقُ بالقيم قبل وبعد

كلُّ كتابةٍ تُسجَّل في `AuditLog` بما كان وما صار — لا «تعديل» مجرّداً. فسؤالُ
النائب في نوفمبر ليس «هل تغيّر؟» بل «من نقل رياضياتَ 8/2 من أحمد إلى خالد
ومتى ولماذا؟».
"""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from academic_management import curriculum_service as curriculum
from academic_management import load as loads
from academic_management.models import CoursePreparation, WorkloadGovernance

BLOCK = "block"
WARN = "warn"
INFO = "info"

# ── رموزُ النتائج — ثابتةٌ كي تُرفع في الحوكمة وتُختبر بالاسم ─────────
NOT_IN_PLAN = "not_in_plan"
OWN_TIMETABLE = "own_timetable"
PERIODS_MISMATCH = "periods_mismatch"
PERIODS_MISMATCH_NO_REASON = "periods_mismatch_no_reason"
OVER_TARGET = "over_target"
OVER_CAPACITY = "over_capacity"
COORDINATOR_BELOW_MIN = "coordinator_below_min"
NEW_TEACHER_TRANSITION_GRADE = "new_teacher_transition_grade"
RESOURCE_NEAR_CAP = "resource_near_cap"
PARALLEL_WITHOUT_PARTNER = "parallel_without_partner"
TEACHER_OUTSIDE_SCHOOL = "teacher_outside_school"
PREPARER_DOES_NOT_TEACH = "preparer_does_not_teach"
COURSE_ALREADY_PREPARED = "course_already_prepared"
SUBJECT_HELD_BY_OTHER = "subject_held_by_other"
STALE_WRITE = "stale_write"

#: الصفوفُ الانتقاليّة التي تنصح الوزارةُ بألّا يُكلَّف بها معلّمٌ في عامه الأوّل
#: (توجيهات التوجيه التربويّ 2025-2026). معلومةٌ لا منع.
TRANSITION_GRADES = ("G9", "G12")

#: نصابُ المنسّق الأدنى (توجيهات التوجيه التربويّ 2025-2026): ثلاثٌ، وأربعٌ
#: لمنسّقي التقنية والفنون والبدنيّة. تحذيرٌ لا منع — «يتحمّل نصاباً أعلى عند
#: الشواغر وفق ما تقدّره إدارةُ المدرسة».
COORDINATOR_MIN = 3
COORDINATOR_MIN_PRACTICAL = 4
PRACTICAL_CODES = {"TECH", "IT", "CS", "ART", "PE"}


class AssignmentError(Exception):
    """رُفض الحفظُ بمانعٍ أو أكثر — و`findings` تحمل الأسباب."""

    def __init__(self, findings):
        self.findings = findings
        super().__init__("؛ ".join(f.message for f in findings if f.level == BLOCK))


class StaleWriteError(Exception):
    """كُتب فوق نسخةٍ رآها المُدخِلُ ثمّ تغيّرت."""


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    message: str

    @property
    def blocks(self):
        return self.level == BLOCK


def _f(level, code, message):
    return Finding(level, code, message)


def _apply_strictness(findings, school):
    """ما رفعته المدرسةُ من تحذيرٍ إلى منع — يُرفع هنا لا في كلّ فحص."""
    strict = set(WorkloadGovernance.for_school(school).strict_codes or [])
    if not strict:
        return findings
    return [
        Finding(BLOCK, f.code, f.message) if f.level == WARN and f.code in strict else f
        for f in findings
    ]


def blocking(findings):
    return [f for f in findings if f.blocks]


# ══════════════════════════════════════════════════════════════════════
#  فحصُ الإسناد
# ══════════════════════════════════════════════════════════════════════


def _teaches_in_school(teacher, school):
    from core.models import Membership

    return Membership.objects.filter(user=teacher, school=school, is_active=True).exists()


def _is_coordinator(teacher, school):
    from core.models import Membership

    return Membership.objects.filter(
        user=teacher, school=school, is_active=True, role__name="coordinator"
    ).exists()


def _joined_this_year(teacher, school, academic_year):
    """معلّمٌ في عامه الأوّل — بدأت عضويّتُه بعد بدء العام الدراسيّ.

    والنافذةُ من التقويم لا من اسم العام: مدرسةٌ بلا تقويمٍ مبذورٍ ترتدّ إلى
    سبتمبر–يونيو، ومن لا نافذةَ له لا يُوصف بأنّه جديدٌ ولا قديم.
    """
    from core.academic_calendar import academic_year_window
    from core.models import Membership

    window = academic_year_window(school)
    if not window:
        return False
    start, _end = window
    return Membership.objects.filter(
        user=teacher, school=school, is_active=True, joined_at__gte=start
    ).exists()


def _capacity_for(teacher, school, academic_year, level_type):
    """كم خانةً تسعها أيّامُ المعلّم بعد تفريغاته — الصيغةُ نفسُها في خطّة النصاب."""
    from operations.models import TeacherExemption
    from operations.scheduler_constraints import get_max_periods_for_day

    rows = TeacherExemption.objects.filter(
        school=school, teacher=teacher, academic_year=academic_year, is_active=True
    )
    days_off, blocked = set(), 0
    for row in rows:
        if row.exemption_type == "full_day":
            days_off.add(row.day_of_week)
        else:
            blocked += 1
    return (
        sum(get_max_periods_for_day(d, level_type) for d in range(5) if d not in days_off) - blocked
    )


def _resource_pressure(subject, school, academic_year, added_periods):
    """موردٌ محدودٌ (معملٌ، ملعبٌ) يقترب من سقفه بمجموع الحصص التي تستهلكه."""
    from operations.models import SchedulingResource, SubjectClassAssignment

    out = []
    for resource in SchedulingResource.objects.filter(
        school=school, is_active=True, subjects=subject
    ).prefetch_related("subjects"):
        subject_ids = [s.id for s in resource.subjects.all()]
        demand = sum(
            SubjectClassAssignment.objects.live(school, year=academic_year)
            .filter(subject_id__in=subject_ids)
            .values_list("weekly_periods", flat=True)
        )
        # 35 خانةً في الأسبوع × السعة = ما يتّسع له المورد.
        ceiling = 35 * resource.capacity
        if demand + added_periods > ceiling * 0.9:
            out.append(
                _f(
                    INFO,
                    RESOURCE_NEAR_CAP,
                    f"«{resource.name}» يقترب من سقفه: {demand + added_periods} حصّةً من {ceiling}.",
                )
            )
    return out


def check_assignment(
    *,
    school,
    academic_year,
    class_group,
    subject,
    teacher,
    weekly_periods,
    override_reason="",
    parallel_group="",
    current=None,
):
    """يصف ما سيحدث إن حُفظ هذا الإسناد — ولا يكتب شيئاً.

    `current` هو السجلُّ القائمُ إن كان تعديلاً، كي لا يُحسب حملُه مرّتين.
    """
    findings = []

    if class_group.has_own_timetable:
        findings.append(
            _f(BLOCK, OWN_TIMETABLE, f"شعبة {class_group} جدولُها مستقلّ — لا تُسنَد من هنا.")
        )
        return _apply_strictness(findings, school)

    # بلا خطّةٍ مبذورةٍ لا يُقاس شيء — ولا تُمنع الكتابةُ لغيابِ مرجعٍ لم يُبذر
    # بعد. فمنعُ كلّ إسنادٍ يومَ النشر يُعطّل الشاشةَ حتى يُشغَّل أمرُ البذر،
    # وهذه بوّابةٌ تحرس ما لا وجودَ له.
    scope_rows = curriculum.demand_for(class_group)
    if not scope_rows:
        findings.append(
            _f(
                INFO,
                NOT_IN_PLAN,
                "لا خطّةَ دراسيّةً لهذا الصفّ بعد — فلا يُقاس عددُ الحصص على مرجع.",
            )
        )
        row = None
    else:
        row = next((r for r in scope_rows if r.subject_id == subject.id), None)

    if scope_rows and row is None:
        findings.append(
            _f(
                BLOCK,
                NOT_IN_PLAN,
                f"{subject.name_ar} ليست في الخطّة الدراسيّة لصفّ {class_group.get_grade_display()}"
                f"{' — ' + class_group.get_track_display() if class_group.track else ''}.",
            )
        )
    elif row is not None and weekly_periods != row.weekly_periods:
        if override_reason.strip():
            findings.append(
                _f(
                    WARN,
                    PERIODS_MISMATCH,
                    f"{weekly_periods} حصصٍ والخطّةُ تقول {row.weekly_periods} — بسببٍ مسجَّل.",
                )
            )
        else:
            findings.append(
                _f(
                    BLOCK,
                    PERIODS_MISMATCH_NO_REASON,
                    f"{weekly_periods} حصصٍ والخطّةُ تقول {row.weekly_periods} — "
                    "المخالفةُ تحتاج سبباً يُحفظ معها.",
                )
            )

    if row is not None and row.elective_group and not parallel_group:
        siblings = [
            r
            for r in scope_rows
            if r.elective_group == row.elective_group and r.subject_id != subject.id
        ]
        if siblings:
            from operations.models import SubjectClassAssignment

            partner_assigned = (
                SubjectClassAssignment.objects.live(school, year=academic_year)
                .filter(class_group=class_group, subject_id__in=[s.subject_id for s in siblings])
                .exists()
            )
            if partner_assigned:
                findings.append(
                    _f(
                        WARN,
                        PARALLEL_WITHOUT_PARTNER,
                        "بديلٌ اختياريٌّ آخر مُسنَدٌ للشعبة نفسها — فاذكر مجموعةَ التوازي ليُجدولا معاً.",
                    )
                )

    if teacher is None:
        return _apply_strictness(findings, school)

    if not _teaches_in_school(teacher, school):
        findings.append(
            _f(BLOCK, TEACHER_OUTSIDE_SCHOOL, "المعلّمُ المختار ليس من أعضاء هذه المدرسة.")
        )
        return _apply_strictness(findings, school)

    load = loads.load_for(school, academic_year, teacher.id)
    current_periods = current.weekly_periods if current and current.teacher_id == teacher.id else 0
    projected_teaching = load.teaching - current_periods + weekly_periods

    if load.target is not None and projected_teaching > load.target:
        source = (
            "هدفِه المعتمَد" if load.target_source == loads.FROM_APPROVED_PLAN else "النصابِ المرجعيّ"
        )
        findings.append(
            _f(
                WARN,
                OVER_TARGET,
                f"{teacher.full_name}: {projected_teaching} تدريس تتجاوز {source} {load.target}.",
            )
        )

    capacity = _capacity_for(teacher, school, academic_year, class_group.level_type)
    if projected_teaching > capacity:
        findings.append(
            _f(
                WARN,
                OVER_CAPACITY,
                f"أيّامُ {teacher.full_name} بعد تفريغاته تسع {capacity} حصّةً"
                f" و{projected_teaching} لا تسعها.",
            )
        )

    if _is_coordinator(teacher, school):
        minimum = (
            COORDINATOR_MIN_PRACTICAL
            if (subject.code or "").upper() in PRACTICAL_CODES
            else COORDINATOR_MIN
        )
        if projected_teaching < minimum:
            findings.append(
                _f(
                    WARN,
                    COORDINATOR_BELOW_MIN,
                    f"نصابُ المنسّق {projected_teaching} دون الحدّ الأدنى {minimum}"
                    " (توجيهات التوجيه التربويّ 2025-2026).",
                )
            )

    if class_group.grade in TRANSITION_GRADES and _joined_this_year(teacher, school, academic_year):
        findings.append(
            _f(
                INFO,
                NEW_TEACHER_TRANSITION_GRADE,
                f"{teacher.full_name} في عامه الأوّل على صفٍّ انتقاليّ"
                f" ({class_group.get_grade_display()}) — تنصح الوزارةُ بتجنّبه ما أمكن.",
            )
        )

    findings.extend(
        _resource_pressure(subject, school, academic_year, weekly_periods - current_periods)
    )
    return _apply_strictness(findings, school)


# ══════════════════════════════════════════════════════════════════════
#  تطبيقُ الإسناد
# ══════════════════════════════════════════════════════════════════════


def _guard_stale(instance, expected_updated_at):
    if expected_updated_at is None or instance is None:
        return
    if instance.updated_at.isoformat() != str(expected_updated_at):
        raise StaleWriteError(
            "عُدِّل هذا الإسنادُ من مكانٍ آخر بعد أن فتحتَه — أعِد التحميلَ لترى ما تغيّر قبل أن تكتب فوقه."
        )


def _snapshot(a):
    return {
        "teacher": str(a.teacher_id) if a.teacher_id else None,
        "weekly_periods": a.weekly_periods,
        "requires_lab": a.requires_lab,
        "parallel_group": a.parallel_group,
        "periods_override_reason": a.periods_override_reason,
        "is_active": a.is_active,
    }


def _audit(instance, action, before, after, findings=()):
    from core.signals import _log

    warned = [f.code for f in findings if f.level == WARN]
    _log(
        "SubjectClassAssignment",
        action,
        instance,
        changes={"before": before, "after": after, "saved_despite": warned},
    )


@transaction.atomic
def apply_assignment(
    *,
    school,
    academic_year,
    class_group,
    subject,
    teacher,
    weekly_periods,
    by,
    override_reason="",
    parallel_group="",
    requires_lab=False,
    expected_updated_at=None,
    confirm_transfer=False,
):
    """يفحص ثمّ يكتب في معاملةٍ واحدة — ويرفع `AssignmentError` عند أيّ مانع.

    يُنشئ السجلَّ إن لم يوجد لهذه (الشعبة، المادّة، العام)، ويعدّله إن وُجد.

    ## نقلُ المادّة من معلّمٍ إلى آخر يُؤكَّد

    المادّةُ في الشعبة لمعلّمٍ واحد، فإسنادُها إلى ثانٍ **يُسقطها عن الأوّل**.
    وكان ذلك يقع صامتاً: منسّقٌ يُسند بالخطأ فيخسر زميلُه حصصَه ولا يعلم
    أحدُهما. فصار النقلُ يحتاج `confirm_transfer=True` — ومن لم يؤكّد رُدَّ
    بمانعٍ يسمّي صاحبَ المادّة الحاليَّ ليقرّر المنسّقُ على بيّنة.
    """
    from operations.models import SubjectClassAssignment

    current = (
        SubjectClassAssignment.objects.filter(
            school=school, academic_year=academic_year, class_group=class_group, subject=subject
        )
        .select_for_update()
        .first()
    )
    _guard_stale(current, expected_updated_at)

    findings = check_assignment(
        school=school,
        academic_year=academic_year,
        class_group=class_group,
        subject=subject,
        teacher=teacher,
        weekly_periods=weekly_periods,
        override_reason=override_reason,
        parallel_group=parallel_group,
        current=current,
    )

    holder = current.teacher if current and current.is_active else None
    transferring = bool(holder and teacher and holder.id != teacher.id)
    if transferring and not confirm_transfer:
        findings.append(
            _f(
                BLOCK,
                SUBJECT_HELD_BY_OTHER,
                f"{subject.name_ar} في {class_group} مُسنَدةٌ إلى {holder.full_name} — "
                f"وإسنادُها إلى {teacher.full_name} يُسقطها عنه. أكِّد النقل.",
            )
        )

    if blocking(findings):
        raise AssignmentError(findings)

    before = _snapshot(current) if current else None
    if current is None:
        current = SubjectClassAssignment(
            school=school,
            academic_year=academic_year,
            class_group=class_group,
            subject=subject,
            created_by=by,
        )
    previous_teacher_id = current.teacher_id
    current.teacher = teacher
    current.weekly_periods = weekly_periods
    current.requires_lab = requires_lab
    current.parallel_group = (parallel_group or "").strip()[:40]
    current.periods_override_reason = (override_reason or "").strip()[:200]
    current.is_active = True
    current.deleted_by = None
    current.deleted_at = None
    current.deletion_reason = ""
    current.updated_by = by
    current.save()

    _audit(current, "create" if before is None else "update", before, _snapshot(current), findings)

    # سقوطُ شرط التدريس عن المحضِّر السابق — يُحرَس هنا لا يُترك للمصادفة.
    if previous_teacher_id and previous_teacher_id != (teacher.id if teacher else None):
        _drop_orphaned_preparation(
            school, academic_year, class_group, subject, previous_teacher_id, by
        )

    return current, findings


@transaction.atomic
def remove_assignment(*, assignment, by, reason, expected_updated_at=None):
    """حذفٌ ناعمٌ بأثره — من حذف ومتى ولماذا. والسببُ لا يُترك فارغاً."""
    if not (reason or "").strip():
        raise ValidationError({"reason": "الحذفُ قرارٌ إداريّ — ويُكتب سببُه."})
    _guard_stale(assignment, expected_updated_at)

    before = _snapshot(assignment)
    assignment.is_active = False
    assignment.deleted_by = by
    assignment.deleted_at = timezone.now()
    assignment.deletion_reason = reason.strip()[:200]
    assignment.updated_by = by
    assignment.save()
    _audit(assignment, "delete", before, _snapshot(assignment))

    if assignment.teacher_id:
        _drop_orphaned_preparation(
            assignment.school,
            assignment.academic_year,
            assignment.class_group,
            assignment.subject,
            assignment.teacher_id,
            by,
        )
    return assignment


# ══════════════════════════════════════════════════════════════════════
#  إسنادُ التحضير
# ══════════════════════════════════════════════════════════════════════


def _teaches_course(teacher_id, school, academic_year, grade, track, subject):
    from operations.models import SubjectClassAssignment

    return (
        SubjectClassAssignment.objects.live(school, year=academic_year)
        .filter(
            teacher_id=teacher_id,
            subject=subject,
            class_group__grade=grade,
            class_group__track=track,
            class_group__has_own_timetable=False,
        )
        .exists()
    )


def check_preparation(*, school, academic_year, grade, track, subject, teacher):
    """هل يجوز أن يحضّر هذا المعلّمُ هذا المقرّر؟ — ولا يكتب."""
    findings = []

    if not _teaches_course(teacher.id, school, academic_year, grade, track, subject):
        findings.append(
            _f(
                BLOCK,
                PREPARER_DOES_NOT_TEACH,
                f"{teacher.full_name} لا يدرّس {subject.name_ar} في هذا الصفّ — والمحضِّرُ من مدرّسي المقرّر حصراً.",
            )
        )
        return _apply_strictness(findings, school)

    existing = (
        CoursePreparation.objects.live(school, year=academic_year)
        .filter(grade=grade, track=track, subject=subject)
        .exclude(teacher=teacher)
        .first()
    )
    if existing:
        findings.append(
            _f(
                BLOCK,
                COURSE_ALREADY_PREPARED,
                f"المقرّرُ يحضّره {existing.teacher.full_name} — أزِل مسؤوليّتَه أوّلاً ثمّ أسنِدها.",
            )
        )
        return _apply_strictness(findings, school)

    # قرارُ الإدارة (2026-09-06): حصّتا التحضير عرفاً لا تُسجَّلان في النصاب،
    # فلا تجاوزَ يُحذَّر منه هنا. والمسؤوليّةُ تُسجَّل وتظهر في الكشف كما هي.
    return _apply_strictness(findings, school)


@transaction.atomic
def apply_preparation(*, school, academic_year, grade, track, subject, teacher, by):
    """يعيّن المحضِّرَ — أو يستبدله إن كان المقرّرُ بلا محضِّرٍ نشط."""
    findings = check_preparation(
        school=school,
        academic_year=academic_year,
        grade=grade,
        track=track,
        subject=subject,
        teacher=teacher,
    )
    if blocking(findings):
        raise AssignmentError(findings)

    row, created = CoursePreparation.objects.update_or_create(
        school=school,
        academic_year=academic_year,
        grade=grade,
        track=track,
        subject=subject,
        defaults={"teacher": teacher, "is_active": True, "updated_by": by},
    )
    if created:
        row.created_by = by
        row.save(update_fields=["created_by"])

    from core.signals import _log

    _log(
        "CoursePreparation",
        "create" if created else "update",
        row,
        changes={
            "teacher": str(teacher.id),
            "saved_despite": [f.code for f in findings if f.level == WARN],
        },
    )
    return row, findings


@transaction.atomic
def remove_preparation(*, preparation, by, reason):
    """يُسقط مسؤوليّةَ التحضير ناعماً بسبب."""
    if not (reason or "").strip():
        raise ValidationError({"reason": "إسقاطُ التحضير قرارٌ — ويُكتب سببُه."})
    from core.signals import _log

    preparation.is_active = False
    preparation.updated_by = by
    preparation.save()
    _log(
        "CoursePreparation",
        "delete",
        preparation,
        changes={"teacher": str(preparation.teacher_id), "reason": reason.strip()[:200]},
    )
    return preparation


def _drop_orphaned_preparation(school, academic_year, class_group, subject, teacher_id, by):
    """سقط آخرُ إسنادٍ تدريسيٍّ للمعلّم في المقرّر — فتسقط مسؤوليّةُ تحضيره معه.

    ويُسجَّل السببُ صراحةً: «سقط شرطُ التدريس». فمقرّرٌ صار بلا محضِّرٍ بصمتٍ
    يُقرأ بعد شهرٍ خللاً، وبهذا السبب يُقرأ نتيجةَ نقلٍ معلوم.
    """
    if _teaches_course(
        teacher_id, school, academic_year, class_group.grade, class_group.track, subject
    ):
        return
    for prep in CoursePreparation.objects.live(school, year=academic_year).filter(
        grade=class_group.grade, track=class_group.track, subject=subject, teacher_id=teacher_id
    ):
        remove_preparation(preparation=prep, by=by, reason="سقط شرطُ التدريس — أُزيل إسنادُه للمقرّر")


__all__ = [
    "BLOCK",
    "INFO",
    "WARN",
    "AssignmentError",
    "Finding",
    "StaleWriteError",
    "apply_assignment",
    "apply_preparation",
    "blocking",
    "check_assignment",
    "check_preparation",
    "remove_assignment",
    "remove_preparation",
]
