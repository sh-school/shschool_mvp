"""
assessments/verdict_engine.py
محرّكُ الحكم الواحد — يجمع وقائعَ الطالب من القاعدة، ويحكم بـ`core.domain.grades.judge_student`،
ويخزّن الحكمَ في `StudentSubjectResult` و`AnnualSubjectResult` مع سجلّ مراجعةٍ بما تغيّر.

**خلف راية**: `settings.VERDICT_ENGINE_ENABLED` (الافتراضُ False). ما دامت مطفأةً يبقى
`GradeService` على حسابه القديم حرفيّاً، فلا يتغيّر حكمٌ ولا شهادة. والراية تُرفع مع الطلب الذي
يحوّل المستهلكين (الشهادة وملفّ الطالب وبوّابة وليّ الأمر…) لقراءة الحكم المخزَّن — فالحالاتُ
الجديدة («مُرفَّع»، «دور ثانٍ»، «معذور»…) لا تفهمها المستهلكات القديمة التي تعدّ `fail` و`pass`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.domain.grades import (
    ABSENT,
    EXCUSED_MARK,
    PRESENT,
    SEMESTER_MAX,
    VERDICT_RULESET,
    ExamFacts,
    MakeupFacts,
    SecondRoundFacts,
    SubjectFacts,
    is_additional_subject,
    judge_student,
    package_out_of,
    package_score,
    package_weights,
)
from core.models import AuditLog, StudentEnrollment
from core.models.academic import grade_number

from .models import (
    AnnualSubjectResult,
    Assessment,
    AssessmentPackage,
    ExamDeprivation,
    ExamMisconduct,
    StudentAssessmentGrade,
    StudentSubjectResult,
    SubjectClassSetup,
)

if TYPE_CHECKING:
    from core.models import ClassGroup, CustomUser, School


def verdict_engine_enabled() -> bool:
    """أيُحسب الحكمُ الواحد ويُخزَّن؟ — راية `VERDICT_ENGINE_ENABLED` (مطفأةٌ افتراضاً)."""
    return bool(getattr(settings, "VERDICT_ENGINE_ENABLED", False))


#: حالاتُ التقييم التي تُحسب — ما سواها مسودّة.
COUNTED_STATUSES = ("published", "graded", "closed")


class ClosedYearError(Exception):
    """كتابةٌ على درجات عامٍ دراسيٍّ غيرِ الجاري أو إعادةُ حساب نتائجه."""


def is_open_year(setup: SubjectClassSetup) -> bool:
    return setup.academic_year == academic_year_for_school(setup.school)


def ensure_open_year(setup: SubjectClassSetup) -> None:
    """الأعوامُ المغلقة مجمَّدة — لا درجةَ تُكتب ولا نتيجةَ يُعاد حسابُها من أيّ مسار.

    على قاعدة «لا حصّةَ نشطةٌ خارجَ العام الجاري»: ما خرج من العام الجاري اعتُمد
    وطُبع، فتعديلُه رفضٌ صريح لا إعادةُ حسابٍ صامتة بقاعدةٍ أحدث.
    """
    if not is_open_year(setup):
        raise ClosedYearError(
            f"العامُ الدراسيّ {setup.academic_year} مغلق — لا تُعدَّل درجاتُه ولا نتائجُه."
        )


MakeupKey = tuple[Any, Any]


def package_facts(
    packages: list[AssessmentPackage], student_ids: list[Any]
) -> tuple[dict[tuple[Any, Any], ExamFacts], dict[MakeupKey, MakeupFacts]]:
    """وقائعُ الباقات لكلّ (طالب، باقة)، والملحقُ لكلّ (طالب، إعداد) — باستعلامين.

    درجةُ الباقة كسرٌ دقيق: أداءُ الطالب في تقييماتها موزوناً بـ`weight_in_package`،
    مضروباً في درجة الباقة من القرار (`package_out_of`: 15، 20، 40 …) — لا في الوزن المخزَّن
    (قرار 14/2018 م5: التوزيعُ للقطاع لا للمدرسة). وباقةٌ خارج البنية تُعطى `out_of=0` فيراها
    الحكمُ ولا يجمعها، ودرجتُها `None` (لا «0» في السجلّ).
    والغائبُ عن تقييمٍ جزءٌ صفرٌ فيها، وحصّتُه تُعدّ بعذرٍ أو بغيره — والحكمُ بها في
    `judge_student`. وتقييمُ الملحق (`Assessment.MAKEUP`) لا يدخل درجةَ باقته.

    والباقةُ **مرصودةٌ** لطالبٍ فقط إن كان لكلّ تقييمٍ منشورٍ فيها مدخلٌ محدَّدٌ له — درجةٌ
    أو غياب؛ فتقييمٌ واحدٌ لم يُرصد بعدُ (خانةٌ فارغة، أو `StudentAssessmentGrade` بلا درجةٍ
    ولا غياب، أو لا صفَّ له إطلاقاً) يجعل الباقةَ كلَّها «غير مرصودة» لذلك الطالب — لا نسبةً
    محسوبةً من الموجود وحدَه كأنّ الباقي صفر. وإلّا فإنشاءَ تقييمٍ جديدٍ في باقةٍ (`AW` عادةً)
    كان يخفض فوراً درجةَ كلّ من أُنجزت باقيةُ تقييماته (وزنُه يدخل المقام قبل أن يُرصد لأحد)،
    وخانةً فارغةً تُحفظ بلا قيمةٍ لغير طالبٍ («حفظ الكلّ») كانت تُحسب صفراً مرصوداً لا خانةً
    لم تُملأ بعد. (جولة 9، عيبٌ عالي الخطورة.)
    """
    if not packages or not student_ids:
        return {}, {}
    pkg_by_id = {p.id: p for p in packages}
    rows = list(
        Assessment.objects.filter(
            package_id__in=pkg_by_id, status__in=COUNTED_STATUSES
        ).values_list("id", "package_id", "max_grade", "weight_in_package", "assessment_type")
    )
    if not rows:
        return {}, {}
    index = _entries_index([r[0] for r in rows], student_ids)
    regular, makeups = _split_regular_and_makeup(rows, pkg_by_id)
    exams: dict[tuple[Any, Any], ExamFacts] = {}
    for pkg_id, items in regular.items():
        exams.update(_package_exams(pkg_by_id[pkg_id], items, student_ids, index))
    return exams, _makeup_facts(makeups, student_ids, index)


#: (طالب، تقييم) → (الدرجة الخام، غائب بعذرٍ أو بغيره، معذور).
_Entry = tuple[Decimal | None, bool, bool]
_Items = list[tuple[Any, Fraction, Fraction]]


def _entries_index(
    assessment_ids: list[Any], student_ids: list[Any]
) -> dict[tuple[Any, Any], _Entry]:
    """ما رُصد لكلّ (طالب، تقييم) — باستعلامٍ واحد."""
    index: dict[tuple[Any, Any], _Entry] = {}
    for sid, aid, raw_grade, was_absent, was_excused in StudentAssessmentGrade.objects.filter(
        assessment_id__in=assessment_ids, student_id__in=student_ids
    ).values_list("student_id", "assessment_id", "grade", "is_absent", "is_excused"):
        index[(sid, aid)] = (raw_grade, bool(was_absent or was_excused), bool(was_excused))
    return index


def _split_regular_and_makeup(
    rows: list[Any], pkg_by_id: dict[Any, AssessmentPackage]
) -> tuple[dict[Any, _Items], dict[Any, _Items]]:
    """تقييماتُ كلّ باقةٍ عاديّة، وتقييماتُ الملحق لكلّ إعدادٍ — لا يدخل الملحقُ درجةَ باقته."""
    regular: dict[Any, _Items] = {}
    makeups: dict[Any, _Items] = {}
    for aid, pkg_id, row_max, row_weight, atype in rows:
        item = (aid, Fraction(row_max), Fraction(row_weight))
        if atype == Assessment.MAKEUP:
            makeups.setdefault(pkg_by_id[pkg_id].setup_id, []).append(item)
        else:
            regular.setdefault(pkg_id, []).append(item)
    return regular, makeups


def _package_exams(
    pkg: AssessmentPackage,
    items: _Items,
    student_ids: list[Any],
    index: dict[tuple[Any, Any], _Entry],
) -> dict[tuple[Any, Any], ExamFacts]:
    """وقائعُ باقةٍ واحدة لكلّ طالبٍ رُصدت له كاملةً (وإلّا فلا مدخلَ له)."""
    total_w = sum((w for _, _, w in items), Fraction(0))
    if not total_w:
        return {}
    out_of = package_out_of(
        grade_number(pkg.setup.class_group.grade), pkg.semester, pkg.package_type
    ) or Fraction(0)
    exams: dict[tuple[Any, Any], ExamFacts] = {}
    for sid in student_ids:
        pct, excused, absent = Fraction(0), Fraction(0), Fraction(0)
        complete = True
        for aid, item_max, w in items:
            entry = index.get((sid, aid))
            if entry is None:
                complete = False
                continue
            value, is_absent, is_excused = entry
            share = w / total_w
            if is_absent:
                if is_excused:
                    excused += share
                else:
                    absent += share
            elif value is not None:
                if item_max:
                    pct += Fraction(value) / item_max * share
            else:
                # صفٌّ محفوظٌ بلا درجةٍ ولا غياب — خانةٌ فارغة، لا صفرٌ مرصود.
                complete = False
        if complete:
            score = pct * out_of if out_of else None
            exams[(sid, pkg.id)] = ExamFacts(score, out_of, excused, absent)
    return exams


def _makeup_facts(
    makeups: dict[Any, _Items],
    student_ids: list[Any],
    index: dict[tuple[Any, Any], _Entry],
) -> dict[MakeupKey, MakeupFacts]:
    """اختبارُ الملحق لكلّ (طالب، إعداد): حضرَه بنسبته، أو غاب بعذرٍ أو بغيره."""
    makeup_facts: dict[MakeupKey, MakeupFacts] = {}
    for setup_id, items in makeups.items():
        for sid in student_ids:
            taken = [
                (index[(sid, aid)], max_grade, w)
                for aid, max_grade, w in items
                if (sid, aid) in index
                and (index[(sid, aid)][1] or index[(sid, aid)][0] is not None)
            ]
            if not taken:
                continue
            sat = [(e, mx, w) for e, mx, w in taken if not e[1]]
            if not sat:
                excused_any = any(e[2] for e, _, _ in taken)
                makeup_facts[(sid, setup_id)] = MakeupFacts(EXCUSED_MARK if excused_any else ABSENT)
                continue
            all_w = sum((w for _, _, w in taken), Fraction(0))
            earned = sum(
                (Fraction(e[0]) / mx * w for e, mx, w in sat if e[0] is not None and mx),
                Fraction(0),
            )
            makeup_facts[(sid, setup_id)] = MakeupFacts(PRESENT, earned / all_w if all_w else None)
    return makeup_facts


#: ما يُقارن قبل/بعد في كلّ صفّ — الحكمُ كلُّه لا الحالةُ وحدَها.
ANNUAL_AUDIT_FIELDS: tuple[str, ...] = (
    "status",
    "standing",
    "annual_total",
    "s1_total",
    "s2_total",
    "mark",
    "article",
    "review",
    "second_round_max",
)
SEMESTER_AUDIT_FIELDS: tuple[str, ...] = (
    "p1_score",
    "p2_score",
    "p3_score",
    "p4_score",
    "p_aw_score",
    "total",
    "semester_max",
)
VERDICT_AUDIT_OP = "verdict_recalculated"


def _audit_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.01")))
    return str(value)


@dataclass
class VerdictPlan:
    """حكمٌ محسوبٌ لم يُكتب: الصفوفُ المعدَّلة والجديدة، وما تغيّر فيها بقيمتيه.

    `changes` صفٌّ لكلّ (طالب، إعداد، «annual»|«S1»|«S2») تغيّر فيه حقلٌ من حقول
    المقارنة: `{"student", "setup", "row", "before", "after"}` — `before` لا شيء لصفٍّ جديد.

    `deferred`: نتائجُ الشعبة في العام مكتوبةٌ بقواعد أقدم (`ruleset` < `VERDICT_RULESET`)،
    فلا يُكتب شيءٌ جزئيّاً حتّى يُعاد الحكمُ عليها كلِّها بالأمر. و`stale` عددُ الصفوف القديمة
    في الخطّة — تُكتب بالإصدار الجاري ولو لم يتغيّر فيها حقل. و`trigger` ما أطلق الحساب.
    """

    school: School | None
    students: int
    changes: list[dict[str, Any]] = field(default_factory=list)
    sem_rows: list[tuple[Any, bool]] = field(default_factory=list)
    annual_rows: list[tuple[Any, bool]] = field(default_factory=list)
    deferred: bool = False
    stale: int = 0
    trigger: str = ""

    def stage(
        self,
        existing: StudentSubjectResult | AnnualSubjectResult | None,
        blank: StudentSubjectResult | AnnualSubjectResult,
        values: dict[str, Any],
        ident: tuple[str, str, str],
        now: Any,
    ) -> None:
        annual = isinstance(blank, AnnualSubjectResult)
        fields = ANNUAL_AUDIT_FIELDS if annual else SEMESTER_AUDIT_FIELDS
        after = {f: _audit_value(values[f]) for f in fields}
        before = None
        if existing is not None:
            before = {f: _audit_value(getattr(existing, f)) for f in fields}
            if annual and getattr(existing, "ruleset", VERDICT_RULESET) != VERDICT_RULESET:
                self.stale += 1
        if before != after:
            self.changes.append(
                {
                    "student": ident[0],
                    "setup": ident[1],
                    "row": ident[2],
                    "before": before,
                    "after": after,
                }
            )
        target = existing if existing is not None else blank
        for attr, val in {**values, "updated_at": now}.items():
            setattr(target, attr, val)
        created = existing is None
        if annual:
            self.annual_rows.append((target, created))
        else:
            self.sem_rows.append((target, created))

    def write(self, actor: CustomUser | None = None, audit: bool = True) -> None:
        """يكتب السجلَّ أوّلاً (إن تغيّر شيء) ثمّ النتائج — في معاملةٍ واحدة."""
        if self.deferred:
            return
        with transaction.atomic():
            if audit and self.changes:
                AuditLog.objects.create(
                    school=self.school,
                    user=actor,
                    action="update",
                    model_name="other",
                    object_id=str(self.school.pk) if self.school else "",
                    object_repr="إعادةُ الحكم على نتائج الطلبة",
                    changes={
                        "op": VERDICT_AUDIT_OP,
                        "trigger": self.trigger,
                        "changed": len(self.changes),
                        "rows": self.changes,
                    },
                )
            sem_fields = ["school_id", *SEMESTER_AUDIT_FIELDS, "updated_at"]
            annual_fields = ["school_id", *ANNUAL_AUDIT_FIELDS, "ruleset", "updated_at"]
            StudentSubjectResult.objects.bulk_update(
                [r for r, c in self.sem_rows if not c], sem_fields, batch_size=500
            )
            StudentSubjectResult.objects.bulk_create(
                [r for r, c in self.sem_rows if c], batch_size=500
            )
            AnnualSubjectResult.objects.bulk_update(
                [r for r, c in self.annual_rows if not c], annual_fields, batch_size=500
            )
            AnnualSubjectResult.objects.bulk_create(
                [r for r, c in self.annual_rows if c], batch_size=500
            )


def _structure_note(
    grade: int,
    setup: SubjectClassSetup,
    by_setup_sem: dict[tuple[Any, str], list[AssessmentPackage]],
) -> str:
    """باقاتٌ من بنية القرار 14/2018 م3 غائبةٌ عن فصلٍ له باقات — نصُّ التنبيه، أو "".

    قاعدةٌ بُذرت بالجدول القديم (الفصل الأول P1 وP4 بلا P2) كان يُجمع فيها الموجودُ ويُحسم
    بالناقص ضدّ الطالب؛ فالمادّةُ «غير مكتمل» حتّى تُصحَّح بنيتُها.
    """
    missing = []
    for sem in ("S1", "S2"):
        present = {p.package_type for p in by_setup_sem.get((setup.id, sem), [])}
        if present:
            missing += [f"{sem}/{k}" for k in package_weights(grade, sem) if k not in present]
    if not missing:
        return ""
    return "بنيةُ الباقات ناقصةٌ عن القرار 14/2018 م3 — لا يُحكم في المادّة حتّى تُصحَّح: " + (
        "، ".join(missing)
    )


class VerdictEngine:
    """حكمُ الطلبة وتخزينُه — `plan_students` يحسب، و`VerdictPlan.write` يكتب."""

    @staticmethod
    @transaction.atomic
    def recalculate_students(
        class_group: ClassGroup,
        year: str,
        students: list[CustomUser],
        include: SubjectClassSetup | None = None,
        actor: CustomUser | None = None,
        trigger: str = "",
    ) -> int:
        """يحكم على طلبةٍ في موادّ شعبتهم كلِّها ويخزّن الحكم — ويسجّل ما تغيّر قبل كتابته.

        `plan_students` ثمّ `VerdictPlan.write`: كلُّ مسارٍ يعيد الحساب (حفظُ درجة، حفظُ الكلّ،
        الزرّ، قرارُ فريق السلوك، ترحيلُ الثاني عشر) يكتب في `AuditLog` قائمةَ ما تغيّر بقيمتيه
        قبل/بعد وفاعلَه وما أطلقه (`trigger`)، ولا سجلَّ لإعادة حسابٍ لم تغيّر شيئاً.

        ونتائجُ الشعبة المكتوبةُ بقواعد أقدم (`is_deferred`) لا تُرجئ الكتابة: يُعاد الحكمُ على
        الشعبة كلِّها بالإصدار الجاري (`restamp`) ويُسجَّل ما تغيّر — فلا يُحفظ رصدٌ بلا أثرٍ حتّى
        يُشغَّل الأمر، ولا تُخرج الشعبةُ طلبةً متساوين بقاعدتين. (جولة 7، 2026-09-17: كان يُرجئ
        بصمتٍ كلَّ شعبةٍ بعد النشر إلى أن يُشغَّل الأمرُ يدويّاً.)

        ويُرجع عددَ من حُكم عليهم.
        """
        plan = VerdictEngine.plan_students(class_group, year, students, include)
        if plan.deferred:
            plan = VerdictEngine.plan_students(
                class_group,
                year,
                VerdictEngine.class_students(class_group, students),
                include,
                restamp=True,
            )
            trigger = f"{trigger}:restamp" if trigger else "restamp"
        plan.trigger = trigger
        plan.write(actor=actor)
        return plan.students

    @staticmethod
    def class_students(
        class_group: ClassGroup, extra: list[CustomUser] | tuple[CustomUser, ...] = ()
    ) -> list[CustomUser]:
        """طلبةُ الشعبة المقيَّدون — ومعهم من طُلب الحكمُ عليه ولو لم يُقيَّد (للترحيل)."""
        students = [
            e.student
            for e in StudentEnrollment.objects.filter(
                class_group=class_group, is_active=True
            ).select_related("student")
        ]
        known = {s.id for s in students}
        return students + [s for s in extra if s.id not in known]

    @staticmethod
    def is_deferred(class_group: ClassGroup, year: str) -> bool:
        """نتائجُ الشعبة في العام مكتوبةٌ بقواعد حكمٍ أقدم — تنتظر `recalculate_grade_results`.

        إلى أن يُشغَّل الأمرُ لا يُعاد حسابُ أحدٍ فيها جزئيّاً: حفظُ درجةٍ واحدةٍ كان يكتب نتيجةَ
        طالبٍ بالقواعد الجديدة وزميلُه صاحبُ الدرجات نفسِها باقٍ على القديمة. والنطاقُ ما يُعيد
        الأمرُ حسابَه بعينه (طلبةُ الشعبة المقيَّدون في إعداداتها النشطة) — فلا يعلق الإرجاءُ بصفٍّ
        لطالبٍ غادر لا يمسّه الأمر.
        """
        return AnnualSubjectResult.objects.filter(
            academic_year=year,
            ruleset__lt=VERDICT_RULESET,
            setup__class_group=class_group,
            setup__is_active=True,
            student__enrollments__class_group=class_group,
            student__enrollments__is_active=True,
        ).exists()

    @staticmethod
    def plan_students(
        class_group: ClassGroup,
        year: str,
        students: list[CustomUser],
        include: SubjectClassSetup | None = None,
        restamp: bool = False,
    ) -> VerdictPlan:
        """الحكمُ على طلبةٍ في موادّ شعبتهم كلِّها بـ`judge_student` — محسوباً لا مكتوباً.

        الحكمُ عابرٌ للموادّ (م13، م23، م29، م50) فلا يُحسب لمادّةٍ وحدَها: تُقرأ وقائعُ
        الطالب في كلّ إعدادات الشعبة النشطة (باستعلاماتٍ ثابتة العدد) تحت القفل — فيُستدعى
        داخل معاملة. ومدخلاتُ الدور الثاني (`second_round_score`/`second_round_absent`)
        تُقرأ ولا تُكتب، وكذلك قراراتُ الحرمان (`ExamDeprivation`) ووقائعُ الانضباط
        (`ExamMisconduct`: الغشُّ لمادّةٍ واختبار، والإلغاءُ لكلّ الموادّ).

        `restamp=True` يحسب ولو كانت نتائجُ الشعبة بقواعد أقدم (فيُحدّثها)؛ وغيرُه يُعلِم بها
        (`VerdictPlan.deferred`) فيُعيد `recalculate_students` الحكمَ على الشعبة كلِّها.
        """
        plan = VerdictPlan(school=None, students=len(students))
        if not students:
            return plan
        grade = grade_number(class_group.grade)
        setups = VerdictEngine._eligible_setups(class_group, year, include, grade)
        if not setups:
            plan.students = 0
            return plan
        for setup in setups:
            ensure_open_year(setup)
        school = setups[0].school
        plan.school = school
        if not restamp and VerdictEngine.is_deferred(class_group, year):
            plan.deferred = True
            return plan
        sids = [s.id for s in students]
        inputs = _load_inputs(setups, sids, year, school, grade)
        now = timezone.now()
        for student in students:
            subjects = [_subject_facts(setup, student.id, inputs) for setup in setups]
            verdict = judge_student(
                grade,
                subjects,
                frozenset(inputs.gates.get(student.id, ())),
                inputs.cancelled.get(student.id, ""),
            )
            _stage_verdict(plan, student, setups, verdict, inputs, year, now)
        return plan

    @staticmethod
    def _eligible_setups(
        class_group: ClassGroup, year: str, include: SubjectClassSetup | None, grade: int
    ) -> list[SubjectClassSetup]:
        """إعداداتُ الشعبة النشطة في العام (ومعها `include`) — بلا المادّة الإضافيّة الاختياريّة.

        المادّةُ الإضافيّةُ الاختياريّة لا تُنشأ لها سجلّاتُ درجاتٍ إطلاقاً — غيابٌ كلّيٌّ
        عن محرّك التقييم، لا حالةُ «ليست مادة نجاح ورسوب» (`has_pass_mark`). (جولة 9، §2.)
        """
        setup_filter = Q(class_group=class_group, academic_year=year, is_active=True)
        if include is not None:
            setup_filter |= Q(id=include.id)
        setups = list(
            SubjectClassSetup.objects.filter(setup_filter).select_related(
                "school", "class_group", "subject"
            )
        )
        return [s for s in setups if not is_additional_subject(grade, s.subject.name_ar)]


@dataclass
class _Inputs:
    """كلُّ ما يحتاجه الحكمُ على طلبةِ شعبةٍ من القاعدة — تُقرأ مرّةً بعددِ استعلاماتٍ ثابت."""

    exams: dict[tuple[Any, Any], ExamFacts]
    makeups: dict[MakeupKey, MakeupFacts]
    by_setup_sem: dict[tuple[Any, str], list[AssessmentPackage]]
    structure: dict[Any, str]
    annual_rows: dict[tuple[Any, Any], AnnualSubjectResult]
    sem_rows: dict[tuple[Any, Any, str], StudentSubjectResult]
    gates: dict[Any, set[str]]
    cheats: dict[tuple[Any, Any], set[str]]
    cancelled: dict[Any, str]


def _load_inputs(
    setups: list[SubjectClassSetup], sids: list[Any], year: str, school: School, grade: int
) -> _Inputs:
    packages = list(
        AssessmentPackage.objects.filter(setup__in=setups, is_active=True).select_related(
            "setup__class_group"
        )
    )
    exams, makeups = package_facts(packages, sids)
    by_setup_sem: dict[tuple[Any, str], list[AssessmentPackage]] = {}
    for pkg in packages:
        by_setup_sem.setdefault((pkg.setup_id, pkg.semester), []).append(pkg)
    structure = {setup.id: _structure_note(grade, setup, by_setup_sem) for setup in setups}

    annual_rows = {
        (r.student_id, r.setup_id): r
        for r in AnnualSubjectResult.objects.select_for_update().filter(
            setup__in=setups, student_id__in=sids, academic_year=year
        )
    }
    sem_rows = {
        (r.student_id, r.setup_id, r.semester): r
        for r in StudentSubjectResult.objects.select_for_update().filter(
            setup__in=setups, student_id__in=sids
        )
    }
    gates: dict[Any, set[str]] = {}
    for sid, gate in ExamDeprivation.objects.filter(
        student_id__in=sids, academic_year=year, school=school, deprived=True
    ).values_list("student_id", "gate"):
        gates.setdefault(sid, set()).add(gate)
    cheats: dict[tuple[Any, Any], set[str]] = {}
    cancelled: dict[Any, str] = {}
    for sid, kind, setup_id, exam, basis in ExamMisconduct.objects.filter(
        student_id__in=sids, academic_year=year, school=school
    ).values_list("student_id", "kind", "setup_id", "exam", "basis"):
        if kind == ExamMisconduct.KIND_CANCELLED:
            cancelled[sid] = basis
        else:
            cheats.setdefault((sid, setup_id), set()).add(exam)
    return _Inputs(
        exams, makeups, by_setup_sem, structure, annual_rows, sem_rows, gates, cheats, cancelled
    )


def _subject_facts(setup: SubjectClassSetup, sid: Any, inputs: _Inputs) -> SubjectFacts:
    """وقائعُ طالبٍ في مادّةٍ واحدة — درجاتُ باقاتها والملحقُ والدورُ الثاني والغشُّ."""
    sems = {
        sem: {
            p.package_type: inputs.exams[(sid, p.id)]
            for p in inputs.by_setup_sem.get((setup.id, sem), [])
            if (sid, p.id) in inputs.exams
        }
        for sem in ("S1", "S2")
    }
    row = inputs.annual_rows.get((sid, setup.id))
    second = None
    if row is not None and (row.second_round_absent or row.second_round_score is not None):
        second = SecondRoundFacts(
            None if row.second_round_score is None else Fraction(row.second_round_score),
            row.second_round_absent,
        )
    return SubjectFacts(
        str(setup.id),
        sems["S1"],
        sems["S2"],
        inputs.makeups.get((sid, setup.id)),
        second,
        has_pass_mark=setup.counts_pass_mark,
        cheated=frozenset(inputs.cheats.get((sid, setup.id), ())),
        structure=inputs.structure[setup.id],
    )


def _stage_verdict(
    plan: VerdictPlan,
    student: CustomUser,
    setups: list[SubjectClassSetup],
    verdict: Any,
    inputs: _Inputs,
    year: str,
    now: Any,
) -> None:
    """يضع صفوفَ الفصلين والسنويّ لطالبٍ في الخطّة (`plan.stage`) من حكمه."""
    sid = student.id
    verdicts = verdict.by_key()
    for setup in setups:
        v = verdicts[str(setup.id)]
        for sem, total in (("S1", v.s1_total), ("S2", v.s2_total)):
            scores: dict[str, Decimal] = {}
            for p in inputs.by_setup_sem.get((setup.id, sem), []):
                raw_score = inputs.exams[(sid, p.id)].score if (sid, p.id) in inputs.exams else None
                if raw_score is not None:
                    scores[p.package_type] = package_score(p.package_type, raw_score)
            plan.stage(
                inputs.sem_rows.get((sid, setup.id, sem)),
                StudentSubjectResult(student=student, setup=setup, semester=sem),
                {
                    "school_id": setup.school_id,
                    "p1_score": scores.get("P1"),
                    "p2_score": scores.get("P2"),
                    "p3_score": scores.get("P3"),
                    "p4_score": scores.get("P4"),
                    "p_aw_score": scores.get("AW"),
                    "total": total,
                    "semester_max": SEMESTER_MAX.get(sem, Decimal("40")),
                },
                (str(sid), str(setup.id), sem),
                now,
            )
        plan.stage(
            inputs.annual_rows.get((sid, setup.id)),
            AnnualSubjectResult(student=student, setup=setup, academic_year=year),
            {
                "school_id": setup.school_id,
                "s1_total": v.s1_total,
                "s2_total": v.s2_total,
                "annual_total": v.annual_total,
                "status": v.status,
                "standing": verdict.standing,
                "mark": v.mark,
                "article": v.article[:40],
                "review": v.review[:500],
                "second_round_max": v.second_round_max,
                "ruleset": VERDICT_RULESET,
            },
            (str(sid), str(setup.id), "annual"),
            now,
        )
