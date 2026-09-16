"""
assessments/services.py
محرك حساب الدرجات — معادلة وزارة التعليم القطرية الصحيحة

الفصل الأول  = 40 درجة من 100
الفصل الثاني = 60 درجة من 100
المجموع السنوي = S1 + S2 (من 100)
النجاح = 50 فأكثر
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models import Avg, Count, Q, QuerySet
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.domain.grades import (
    ABSENT,
    EXCUSED_MARK,
    FAILING_STATUSES,
    GRADE_BANDS,
    PASSING_STATUSES,
    PENDING_STATUSES,
    PRESENT,
    RESULT_STATUSES,
    SEMESTER_MAX,
    SITTING_STATUSES,
    STANDING_INCOMPLETE,
    STANDING_LABELS,
    STANDING_SECOND_ROUND,
    STANDING_TONES,
    STATUS_PROMOTED,
    VERDICT_RULESET,
    ExamFacts,
    MakeupFacts,
    SecondRoundFacts,
    SubjectFacts,
    band_of,
    judge_student,
    package_out_of,
    package_score,
    package_weights,
)
from core.models import AuditLog, StudentEnrollment
from core.models.academic import grade_number, grade_order

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
    index: dict[tuple[Any, Any], tuple[Decimal | None, bool, bool]] = {}
    for sid, aid, raw_grade, was_absent, was_excused in StudentAssessmentGrade.objects.filter(
        assessment_id__in=[r[0] for r in rows], student_id__in=student_ids
    ).values_list("student_id", "assessment_id", "grade", "is_absent", "is_excused"):
        index[(sid, aid)] = (raw_grade, bool(was_absent or was_excused), bool(was_excused))

    regular: dict[Any, list[tuple[Any, Fraction, Fraction]]] = {}
    makeups: dict[Any, list[tuple[Any, Fraction, Fraction]]] = {}
    for aid, pkg_id, row_max, row_weight, atype in rows:
        item = (aid, Fraction(row_max), Fraction(row_weight))
        if atype == Assessment.MAKEUP:
            makeups.setdefault(pkg_by_id[pkg_id].setup_id, []).append(item)
        else:
            regular.setdefault(pkg_id, []).append(item)

    exams: dict[tuple[Any, Any], ExamFacts] = {}
    for pkg_id, items in regular.items():
        pkg = pkg_by_id[pkg_id]
        total_w = sum((w for _, _, w in items), Fraction(0))
        if not total_w:
            continue
        out_of = package_out_of(
            grade_number(pkg.setup.class_group.grade), pkg.semester, pkg.package_type
        ) or Fraction(0)
        for sid in student_ids:
            pct, excused, absent, seen = Fraction(0), Fraction(0), Fraction(0), False
            for aid, item_max, w in items:
                entry = index.get((sid, aid))
                if entry is None:
                    continue
                seen = True
                value, is_absent, is_excused = entry
                share = w / total_w
                if is_absent:
                    if is_excused:
                        excused += share
                    else:
                        absent += share
                elif value is not None and item_max:
                    pct += Fraction(value) / item_max * share
            if seen:
                score = pct * out_of if out_of else None
                exams[(sid, pkg_id)] = ExamFacts(score, out_of, excused, absent)

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
    return exams, makeup_facts


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


class GradeService:
    # ── إنشاء باقات الفصل ───────────────────────────────────

    @staticmethod
    @transaction.atomic
    def ensure_packages(setup: SubjectClassSetup, semester: str) -> list[AssessmentPackage]:
        """ينشئ باقاتِ الفصل الناقصة بأوزانها الافتراضيّة، ولا يمسّ القائمة.

        ما يُنشأ يأتي من `package_weights` وحدَه: شعبةُ الثاني عشر تنال P2 في
        الفصل الأول وP4 في الثاني لا غير (القرار 14/2018، المادّة 3 «ثالثاً»،
        2018/06/06) — فلا P1/P3/AW بوزن صفر. متكرّرُ الاستدعاء بلا أثرٍ زائد.
        """
        grade = grade_number(setup.class_group.grade)
        semester_max = SEMESTER_MAX.get(semester, Decimal("40"))
        for ptype, weight in package_weights(grade, semester).items():
            AssessmentPackage.objects.get_or_create(
                setup=setup,
                package_type=ptype,
                semester=semester,
                defaults={
                    "school": setup.school,
                    "weight": weight,
                    "semester_max_grade": semester_max,
                    "is_active": True,
                },
            )
        return list(AssessmentPackage.objects.filter(setup=setup, semester=semester))

    @staticmethod
    @transaction.atomic
    def align_packages(setup: SubjectClassSetup, semester: str) -> list[AssessmentPackage]:
        """للبذر: يطابق باقاتِ الفصل بجدول `package_weights` — أو يتوقّف.

        `ensure_packages` يُكمل ولا يمسّ القائم (قد تكون أوزانُه قرارَ مدرسة). والبذرُ على
        قاعدةٍ بُذرت بالجدول القديم (P1 وP4 بخمسين في الفصل الأول) كان يُضيف فوقها
        فيبلغ مجموعُ الأوزان 162.5٪. فهنا: إن لم تُرصد في الفصل درجةٌ حُذف الزائدُ وأُعيد
        الوزنُ إلى الجدول؛ وإن رُصدت فلا يُمسّ شيء ويُرفع `PackageStructureError`.
        """
        grade = grade_number(setup.class_group.grade)
        table = package_weights(grade, semester)
        semester_max = SEMESTER_MAX.get(semester, Decimal("40"))
        existing = list(
            AssessmentPackage.objects.select_for_update().filter(setup=setup, semester=semester)
        )
        wrong = [
            p
            for p in existing
            if table.get(p.package_type) != p.weight or p.semester_max_grade != semester_max
        ]
        if wrong:
            graded = StudentAssessmentGrade.objects.filter(
                assessment__package__in=existing
            ).exists()
            if graded:
                raise PackageStructureError(
                    f"{setup} ({semester}): بنيةُ باقاتٍ تخالف الجدول وعليها درجات — "
                    "لا تُمسّ آليّاً (fix_grade12_packages للثاني عشر، أو full_seed --reset)."
                )
            for p in wrong:
                if p.package_type in table:
                    p.weight = table[p.package_type]
                    p.semester_max_grade = semester_max
                    p.save(update_fields=["weight", "semester_max_grade"])
                else:
                    p.delete()
        return GradeService.ensure_packages(setup, semester)

    # ── حفظ درجة طالب ──────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def save_grade(
        assessment: Assessment,
        student: CustomUser,
        grade: Decimal | None = None,
        is_absent: bool = False,
        is_excused: bool = False,
        notes: str = "",
        entered_by: CustomUser | None = None,
        recalc: bool = True,
    ) -> tuple[StudentAssessmentGrade, bool]:
        """
        حفظ درجة طالب، ثم إعادةُ الحكم على الطالب في موادّه (`recalculate_students`).

        يرفض عاماً مغلقاً (`ClosedYearError`) قبل أيّ كتابة. ويقفل صفَّ الدرجة
        (`select_for_update`) فلا يتسابق معلّمان على درجة الطالب نفسها.
        """
        setup = assessment.package.setup
        ensure_open_year(setup)
        if grade is not None:
            grade = Decimal(str(grade))
            grade = max(Decimal("0"), min(grade, assessment.max_grade))

        existing = (
            StudentAssessmentGrade.objects.select_for_update()
            .filter(assessment=assessment, student=student)
            .first()
        )

        if existing:
            existing.school = assessment.school
            existing.grade = grade
            existing.is_absent = is_absent
            existing.is_excused = is_excused
            existing.notes = notes
            existing.entered_by = entered_by
            existing.save()
            obj, created = existing, False
        else:
            obj = StudentAssessmentGrade.objects.create(
                assessment=assessment,
                student=student,
                school=assessment.school,
                grade=grade,
                is_absent=is_absent,
                is_excused=is_excused,
                notes=notes,
                entered_by=entered_by,
            )
            created = True

        # [PERF-02] عند الحفظ الجماعي نُمرِّر recalc=False ونعيد الحساب دفعةً واحدة بعد الحلقة
        if recalc:
            GradeService.recalculate_students(
                setup.class_group,
                setup.academic_year,
                [student],
                setup,
                actor=entered_by,
                trigger=f"save_grade:{assessment.pk}",
            )

        return obj, created

    # ── درجات الباقات للعرض ────────────────────────────────

    @staticmethod
    def calc_package_scores_batch(
        student_ids: list[Any],
        packages: list[AssessmentPackage],
        raw: bool = False,
    ) -> dict[tuple[Any, str], Any]:
        """{(طالب، نوع الباقة): درجة} — `raw=True` الكسرُ الدقيق، وإلّا درجةُ العرض.

        درجةُ العرض `package_score`: منتصفُ الفصل مجبور (م8) وغيرُه إلى 0.01. والمجموعُ
        والحكمُ لا يُبنيان من هذه — بل من `judge_student` عبر `recalculate_students`.
        """
        exams, _ = package_facts(list(packages), list(student_ids))
        results: dict[tuple[Any, str], Any] = {}
        for pkg in packages:
            for sid in student_ids:
                facts = exams.get((sid, pkg.id))
                if pkg.weight == 0:
                    results[(sid, pkg.package_type)] = Decimal("0")
                elif facts is None or facts.score is None:
                    results[(sid, pkg.package_type)] = None
                else:
                    results[(sid, pkg.package_type)] = (
                        facts.score if raw else package_score(pkg.package_type, facts.score)
                    )
        return results

    @staticmethod
    def calc_package_score(
        student: CustomUser, package: AssessmentPackage, raw: bool = False
    ) -> Any:
        """درجةُ الطالب في باقةٍ واحدة — `calc_package_scores_batch` لطالبٍ وباقة."""
        return GradeService.calc_package_scores_batch([student.id], [package], raw=raw).get(
            (student.id, package.package_type)
        )

    # ── الحكمُ الواحد وتخزينُه ─────────────────────────────

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

        ويُرجع عددَ من حُكم عليهم — وصفراً إن أُرجئ (نتائجُ الشعبة بقواعد أقدم، `is_deferred`).
        """
        plan = GradeService.plan_students(class_group, year, students, include)
        plan.trigger = trigger
        plan.write(actor=actor)
        return 0 if plan.deferred else plan.students

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

        `restamp=True` للأمر وحدَه: يحسب ولو كانت نتائجُ المدرسة بقواعد أقدم (فيُحدّثها)؛
        وغيرُه يُرجئ (`VerdictPlan.deferred`).
        """
        plan = VerdictPlan(school=None, students=len(students))
        if not students:
            return plan
        setup_filter = Q(class_group=class_group, academic_year=year, is_active=True)
        if include is not None:
            setup_filter |= Q(id=include.id)
        setups = list(
            SubjectClassSetup.objects.filter(setup_filter).select_related(
                "school", "class_group", "subject"
            )
        )
        if not setups:
            plan.students = 0
            return plan
        for setup in setups:
            ensure_open_year(setup)
        school = setups[0].school
        plan.school = school
        if not restamp and GradeService.is_deferred(class_group, year):
            plan.deferred = True
            return plan
        grade = grade_number(class_group.grade)
        sids = [s.id for s in students]

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

        now = timezone.now()
        for student in students:
            sid = student.id
            subjects = []
            for setup in setups:
                sems = {
                    sem: {
                        p.package_type: exams[(sid, p.id)]
                        for p in by_setup_sem.get((setup.id, sem), [])
                        if (sid, p.id) in exams
                    }
                    for sem in ("S1", "S2")
                }
                row = annual_rows.get((sid, setup.id))
                second = None
                if row is not None and (
                    row.second_round_absent or row.second_round_score is not None
                ):
                    second = SecondRoundFacts(
                        None
                        if row.second_round_score is None
                        else Fraction(row.second_round_score),
                        row.second_round_absent,
                    )
                subjects.append(
                    SubjectFacts(
                        str(setup.id),
                        sems["S1"],
                        sems["S2"],
                        makeups.get((sid, setup.id)),
                        second,
                        has_pass_mark=setup.counts_pass_mark,
                        cheated=frozenset(cheats.get((sid, setup.id), ())),
                        structure=structure[setup.id],
                    )
                )
            verdict = judge_student(
                grade, subjects, frozenset(gates.get(sid, ())), cancelled.get(sid, "")
            )
            verdicts = verdict.by_key()

            for setup in setups:
                v = verdicts[str(setup.id)]
                for sem, total in (("S1", v.s1_total), ("S2", v.s2_total)):
                    scores: dict[str, Decimal] = {}
                    for p in by_setup_sem.get((setup.id, sem), []):
                        raw_score = exams[(sid, p.id)].score if (sid, p.id) in exams else None
                        if raw_score is not None:
                            scores[p.package_type] = package_score(p.package_type, raw_score)
                    plan.stage(
                        sem_rows.get((sid, setup.id, sem)),
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
                    annual_rows.get((sid, setup.id)),
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
                        "review": v.review[:300],
                        "second_round_max": v.second_round_max,
                        "ruleset": VERDICT_RULESET,
                    },
                    (str(sid), str(setup.id), "annual"),
                    now,
                )
        return plan

    @staticmethod
    def recalculate_semester_result(
        student: CustomUser,
        setup: SubjectClassSetup,
        semester: str,
    ) -> StudentSubjectResult:
        """نتيجةُ فصلٍ لطالبٍ في مادّة — بعد الحكم عليه في موادّه كلِّها."""
        GradeService.recalculate_students(setup.class_group, setup.academic_year, [student], setup)
        return StudentSubjectResult.objects.get(student=student, setup=setup, semester=semester)

    @staticmethod
    def recalculate_annual_result(
        student: CustomUser, setup: SubjectClassSetup
    ) -> AnnualSubjectResult:
        """النتيجةُ السنويّة لطالبٍ في مادّة — بعد الحكم عليه في موادّه كلِّها.

        الحالةُ والمجموعُ والكلمةُ والموضعُ من `judge_student` لا من هنا: غائبٌ بلا عذرٍ عن
        نهاية الثاني «غائب» (م27)، والمعذورُ ينتظر ملحقَه (م18–م19) أو دورَه (م21، م25، م26)،
        والمحرومُ بقرارٍ مسجَّل (م29، م30)، والمُرفَّعُ بقاعدة (م50).
        """
        GradeService.recalculate_students(setup.class_group, setup.academic_year, [student], setup)
        return AnnualSubjectResult.objects.get(
            student=student, setup=setup, academic_year=setup.academic_year
        )

    @staticmethod
    def recalculate_full_class(setup: SubjectClassSetup, actor: CustomUser | None = None) -> int:
        """إعادةُ الحكم على كلّ طلبة الشعبة — في موادّها كلِّها لأنّ الحكمَ عابرٌ للموادّ."""
        ensure_open_year(setup)
        students = [
            e.student
            for e in StudentEnrollment.objects.filter(
                class_group=setup.class_group, is_active=True
            ).select_related("student")
        ]
        return GradeService.recalculate_students(
            setup.class_group,
            setup.academic_year,
            students,
            setup,
            actor=actor,
            trigger=f"recalculate_full_class:{setup.pk}",
        )

    # ── إحصائيات ───────────────────────────────────────────

    # ── إنشاء تقييم جديد ──────────────────────────────────

    @staticmethod
    @transaction.atomic
    def create_assessment(
        package: AssessmentPackage,
        title: str,
        assessment_type: str = "exam",
        date=None,
        max_grade: Decimal = Decimal("100"),
        weight_in_package: Decimal = Decimal("100"),
        description: str = "",
        created_by=None,
    ) -> Assessment:
        """إنشاء تقييم جديد في باقة مع validation."""
        if not title or not title.strip():
            raise ValueError("عنوان التقييم مطلوب")

        return Assessment.objects.create(
            package=package,
            school=package.school,
            title=title.strip(),
            assessment_type=assessment_type,
            date=date,
            max_grade=max_grade,
            weight_in_package=weight_in_package,
            description=description,
            status="published",
            created_by=created_by,
        )

    # ── إحصائيات ───────────────────────────────────────────

    @staticmethod
    def get_assessment_stats(assessment: Assessment) -> dict:
        """إحصائيات تقييم: متوسط، أعلى، أدنى، نسبة النجاح"""
        # Single query — fetch all grades for this assessment
        all_grades = list(
            StudentAssessmentGrade.objects.filter(assessment=assessment).values_list(
                "grade", "is_absent"
            )
        )
        total = len(all_grades)
        absent = sum(1 for _, is_abs in all_grades if is_abs)
        vals = [float(g) for g, is_abs in all_grades if not is_abs and g is not None]
        entered = len(vals)

        if not entered:
            return {
                "total": total,
                "entered": entered,
                "absent": absent,
                "avg": None,
                "max": None,
                "min": None,
                "pass_pct": None,
            }

        avg = round(sum(vals) / len(vals), 2)
        pass_th = float(assessment.max_grade) * 0.5
        pass_pct = round(sum(1 for v in vals if v >= pass_th) / len(vals) * 100)

        return {
            "total": total,
            "entered": entered,
            "absent": absent,
            "avg": avg,
            "max": max(vals),
            "min": min(vals),
            "pass_pct": pass_pct,
        }

    @staticmethod
    def get_class_results_summary(setup: SubjectClassSetup, year: str | None = None) -> dict:
        """ملخص النتائج السنوية للفصل في مادة — استعلام واحد"""
        year = year or academic_year_for_school(setup.school)
        counted = Q(status__in=RESULT_STATUSES)
        stats = AnnualSubjectResult.objects.filter(setup=setup, academic_year=year).aggregate(
            total=Count("id", filter=counted),
            passed=Count("id", filter=Q(status__in=PASSING_STATUSES)),
            failed=Count("id", filter=Q(status__in=FAILING_STATUSES)),
            incomplete=Count("id", filter=Q(status__in=PENDING_STATUSES)),
            avg=Avg("annual_total", filter=counted),
        )
        total = stats["total"]
        passed = stats["passed"]
        avg = round(float(stats["avg"]), 2) if stats["avg"] is not None else None

        return {
            "total": total,
            "passed": passed,
            "failed": stats["failed"],
            "incomplete": stats["incomplete"],
            "pass_pct": round(passed / total * 100) if total else 0,
            "avg": avg,
        }

    @staticmethod
    def get_student_annual_report(
        student: CustomUser,
        school: School,
        year: str | None = None,
    ) -> QuerySet:
        """كشف الدرجات السنوية الكامل للطالب"""
        year = year or academic_year_for_school(school)
        return (
            AnnualSubjectResult.objects.filter(student=student, school=school, academic_year=year)
            .select_related("setup__subject", "setup__class_group")
            .order_by("setup__subject__name_ar")
        )

    @staticmethod
    def get_failing_students(school: School, year: str | None = None) -> QuerySet:
        """الموادُّ الراسبة سنوياً — `FAILING_STATUSES`: الراسبُ نهائيّاً ومن يُعيدها في الدور الثاني."""
        year = year or academic_year_for_school(school)
        return (
            AnnualSubjectResult.objects.filter(
                school=school, academic_year=year, status__in=FAILING_STATUSES
            )
            .select_related("student", "setup__subject", "setup__class_group")
            .order_by(grade_order("setup__class_group__grade"), "student__full_name")
        )

    @staticmethod
    def get_semester_summary_for_class(setup: SubjectClassSetup, semester: str) -> dict:
        """ملخص درجات الفصل في مادة (لعرض الجدول)"""
        results = StudentSubjectResult.objects.filter(setup=setup, semester=semester)
        total = results.count()
        grades = [float(r.total) for r in results if r.total is not None]
        avg = round(sum(grades) / len(grades), 2) if grades else None
        s_max = float(AssessmentPackage.SEMESTER_MAX.get(semester, Decimal("40")))
        pass_th = s_max * 0.5
        passed = sum(1 for g in grades if g >= pass_th)

        return {
            "total": total,
            "avg": avg,
            "passed": passed,
            "pass_pct": round(passed / len(grades) * 100) if grades else 0,
            "semester_max": s_max,
        }

    @staticmethod
    def get_chart_data(school, year: str) -> dict:
        """
        بيانات الرسوم البيانية للتقييمات — توزيع الدرجات + مقارنة الفصول + المواد.

        ✅ v5.4: ينقل business logic من api_assessment_charts view إلى service layer.
        يستخدم 3 استعلامات DB بدل N+1 (استعلام per فصل).

        Args:
            school: كائن المدرسة
            year: العام الدراسي

        Returns:
            dict يحتوي: grade_distribution, class_comparison, subject_comparison
        """
        from collections import defaultdict

        from django.db.models import Avg, Count, Q

        from core.models import ClassGroup, StudentEnrollment

        from .models import AnnualSubjectResult

        # ── Grade distribution bands ──
        results_values = AnnualSubjectResult.objects.filter(
            school=school, academic_year=year
        ).values_list("annual_total", flat=True)

        # من الأدنى إلى الأعلى: <50, 50-59, 60-69, 70-79, 80-89, 90-100 — رتبةُ الشريحة.
        bands = [0] * len(GRADE_BANDS)
        for r in results_values:
            band = band_of(r)
            if band is not None:
                bands[band.rank] += 1

        # ── Class comparison — 2 queries ──
        classes = list(
            ClassGroup.objects.filter(school=school, academic_year=year).in_school_order()[:15]
        )
        class_ids = [cg.pk for cg in classes]

        student_to_class: dict = {}
        for student_id, class_group_id in StudentEnrollment.objects.filter(
            class_group_id__in=class_ids, is_active=True
        ).values_list("student_id", "class_group_id"):
            student_to_class[student_id] = class_group_id

        class_sums: dict = defaultdict(lambda: [0.0, 0])
        for student_id, annual_total in AnnualSubjectResult.objects.filter(
            student_id__in=student_to_class.keys(),
            school=school,
            academic_year=year,
            annual_total__isnull=False,
        ).values_list("student_id", "annual_total"):
            cg_id = student_to_class.get(student_id)
            if cg_id:
                class_sums[cg_id][0] += float(annual_total)
                class_sums[cg_id][1] += 1

        class_labels, class_avgs = [], []
        for cg in classes:
            data = class_sums.get(cg.pk)
            if data and data[1] > 0:
                class_labels.append(str(cg))
                class_avgs.append(round(data[0] / data[1], 1))

        # ── Subject comparison — setup__subject بدل subject مباشرةً ──
        subj_data = (
            AnnualSubjectResult.objects.filter(
                school=school, academic_year=year, status__in=RESULT_STATUSES
            )
            .values("setup__subject__name_ar")
            .annotate(
                avg=Avg("annual_total"),
                fail_count=Count("id", filter=Q(status__in=FAILING_STATUSES)),
                total=Count("id"),
            )
            .order_by("-avg")[:10]
        )
        subj_labels = [s["setup__subject__name_ar"] or "" for s in subj_data]
        subj_avgs = [round(float(s["avg"]), 1) if s["avg"] else 0 for s in subj_data]
        subj_fail_rates = [
            round(s["fail_count"] / s["total"] * 100, 1) if s["total"] else 0 for s in subj_data
        ]

        return {
            "grade_distribution": {
                "labels": ["أقل من 50", "50-59", "60-69", "70-79", "80-89", "90-100"],
                "data": bands,
            },
            "class_comparison": {
                "labels": class_labels,
                "data": class_avgs,
            },
            "subject_comparison": {
                "labels": subj_labels,
                "avgs": subj_avgs,
                "fail_rates": subj_fail_rates,
            },
        }


# ─────────────────────────────────────────────────────────────
# الدورُ الثاني (البند 2.2) — الشاشةُ تقرأ الحكمَ المخزَّن ولا تحكم
# ─────────────────────────────────────────────────────────────


@dataclass
class SecondRoundRow:
    student: CustomUser
    standing: str
    article: str
    results: list[AnnualSubjectResult]
    #: تنبيهاتٌ لا أحكام: عتبةُ حرمانٍ بُلغت ولا قرارَ مسجَّلاً للفريق.
    warnings: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return STANDING_LABELS.get(self.standing, "")

    @property
    def tone(self) -> str:
        return STANDING_TONES.get(self.standing, "warning")

    @property
    def sits_second_round(self) -> bool:
        return self.standing == STANDING_SECOND_ROUND

    def _names(self, statuses: tuple[str, ...]) -> list[str]:
        return [r.setup.subject.name_ar for r in self.results if r.status in statuses]

    @property
    def retake(self) -> list[str]:
        return self._names(SITTING_STATUSES)

    @property
    def failed(self) -> list[str]:
        return self._names(FAILING_STATUSES)

    @property
    def promoted(self) -> list[str]:
        return self._names((STATUS_PROMOTED,))

    @property
    def reviews(self) -> list[str]:
        """تنبيهاتُ المراجعة المخزَّنة (م50-الأولى) — «المادّة: التنبيه»."""
        return [f"{r.setup.subject.name_ar}: {r.review}" for r in self.results if r.review]


class SecondRoundService:
    """طلبةُ شعبةٍ بعد الدور الأول — **من الحكم المخزَّن** (`AnnualSubjectResult`).

    الحكمُ واحدٌ يُحسب في `judge_student` ويُكتب عند كلّ إعادة حساب؛ فالشاشةُ وقائمةُ
    الراسبين والكشفُ والشهادةُ ولوحةُ المدير تقرأ الشيءَ نفسَه ولا تتناقض.

    وما تضيفه الشاشةُ تنبيهاتٌ لا أحكام: من تجاوز عتبةَ حرمانٍ في سجلّ الحضور حتّى عشيّة
    اختبارها (م29؛ «تُطبَّق أحكام السياسة قبل كل اختبار على حدة» —
    `08_conduct_policy_2026.md:162`) ولم يُسجَّل لفريق السلوك قرارٌ فيه (`ExamDeprivation`)،
    والعشيّةُ التي لا تُعرف: «غير محدَّد — يحتاج تاريخ الاختبار».
    """

    #: الباقةُ التي هي اختبارُ كلّ عتبة، وفصلُها ونوعُ حدثها في التقويم.
    GATE_EXAMS: dict[str, tuple[str, str, str]] = {
        "s1_midterm": ("P1", "S1", "midterm_exam"),
        "s1_final": ("P2", "S1", "final_exam"),
        "s2_midterm": ("P3", "S2", "midterm_exam"),
        "s2_final": ("P4", "S2", "final_exam"),
    }

    @staticmethod
    def exam_eve(
        class_group: ClassGroup,
        year: str,
        gate: str,
        setups: list[SubjectClassSetup] | tuple[SubjectClassSetup, ...] = (),
    ) -> date | None:
        """عشيّةُ اختبار العتبة لصفّ الشعبة في العام المعروض — أو `None` إن لم تُعرف.

        من تقويم الوزارة (`CalendarEvent` بنوع الاختبار ونطاق الصفّ)، ثمّ من أوّل تاريخٍ
        لتقييمات باقته في موادّ الشعبة. ولا ارتدادَ إلى «اليوم»: عشيّةٌ مجهولةٌ تُعدّ فيها
        أيّامُ فصلٍ آخر على عتبةِ هذا، فيُوسم الطالبُ قبل أن يبلغها. (تصحيح 2026-09-15.)
        """
        from datetime import timedelta

        from core.academic_calendar import _scope_for
        from core.models import AcademicYear, CalendarEvent

        ptype, semester, event_type = SecondRoundService.GATE_EXAMS[gate]
        year_obj = AcademicYear.objects.filter(school=class_group.school, name=year).first()
        if year_obj is not None:
            event = (
                CalendarEvent.objects.filter(
                    academic_year=year_obj,
                    event_type=event_type,
                    semester__code=semester,
                    grade_scope__in=("all", _scope_for(class_group.grade)),
                )
                .order_by("start_date")
                .first()
            )
            if event is not None:
                return event.start_date - timedelta(days=1)
        first_exam = (
            Assessment.objects.filter(
                package__setup__in=setups,
                package__package_type=ptype,
                package__semester=semester,
                date__isnull=False,
            )
            .exclude(assessment_type=Assessment.MAKEUP)
            .order_by("date")
            .values_list("date", flat=True)
            .first()
        )
        if first_exam is not None:
            return first_exam - timedelta(days=1)
        return None

    @staticmethod
    def roster(
        class_group: ClassGroup, year: str | None = None
    ) -> tuple[list[SecondRoundRow], list[str]]:
        """(صفوفُ الطلبة من الحكم المخزَّن، تنبيهاتُ الشعبة)."""
        from operations.absence_policy import gates_for
        from operations.absence_standing import unexcused_days_for_class

        school = class_group.school
        year = year or academic_year_for_school(school)
        setups = list(
            SubjectClassSetup.objects.filter(
                class_group=class_group, academic_year=year, is_active=True
            ).select_related("subject")
        )
        students = [
            e.student
            for e in StudentEnrollment.objects.filter(class_group=class_group, is_active=True)
            .select_related("student")
            .order_by("student__full_name")
        ]
        results: dict[Any, list[AnnualSubjectResult]] = {}
        for r in (
            AnnualSubjectResult.objects.filter(setup__in=setups, academic_year=year)
            .select_related("setup__subject")
            .order_by("setup__subject__name_ar")
        ):
            results.setdefault(r.student_id, []).append(r)

        decided: set[tuple[Any, str]] = set(
            ExamDeprivation.objects.filter(
                school=school, academic_year=year, student__in=students
            ).values_list("student_id", "gate")
        )
        class_warnings: list[str] = []
        if GradeService.is_deferred(class_group, year):
            class_warnings.append(
                "نتائجُ الشعبة مكتوبةٌ بقواعد حكمٍ أقدم — لا تُعتمد حتّى يُشغَّل "
                "recalculate_grade_results --apply"
            )
        breaches: dict[Any, list[str]] = {}
        for gate in gates_for(class_group.grade):
            eve = SecondRoundService.exam_eve(class_group, year, gate.key, setups)
            if eve is None:
                class_warnings.append(f"{gate.label}: غير محدَّد — يحتاج تاريخ الاختبار")
                continue
            days = unexcused_days_for_class(class_group, school, on=eve)
            for student in students:
                if (
                    days.get(student.id, 0) > gate.max_days
                    and (student.id, gate.key) not in decided
                ):
                    breaches.setdefault(student.id, []).append(
                        f"تجاوز عتبةَ {gate.label} ({days[student.id]} يوماً) — لم يُسجَّل قرارُ فريق السلوك"
                    )

        rows = []
        for student in students:
            own = results.get(student.id, [])
            standing = own[0].standing if own else STANDING_INCOMPLETE
            article = next((r.article for r in own if r.status in SITTING_STATUSES), "")
            rows.append(
                SecondRoundRow(student, standing, article, own, breaches.get(student.id, []))
            )
        return rows, class_warnings


# ─────────────────────────────────────────────────────────────
# قراراتُ الأهليّة ووقائعُ الانضباط — كتابتُها مسارٌ واحد
# ─────────────────────────────────────────────────────────────

DECISION_AUDIT_OP = "exam_decision"


class ExamDecisionService:
    """كتابةُ قرارات فريق السلوك (`ExamDeprivation`) ووقائع لجان الاختبار (`ExamMisconduct`).

    القرارُ يحدّد أهليّةَ الطالب للاختبار والدور الثاني، فكلُّ كتابةٍ أو حذفٍ هنا، في معاملةٍ
    واحدة: يُرفض العامُ المغلق؛ ويُملأ `decided_by` بالفاعل لا بيدٍ حرّة؛ ويُكتب في `AuditLog`
    القيمُ قبل/بعد والفاعل؛ ثمّ يُعاد الحكمُ على الطالب (والطالبِ السابق إن تبدّل) في شعبته —
    فلا يبقى الحكمُ المخزَّن على ما قبل القرار وتنبيهُ العتبة قد سقط.
    """

    FIELDS: dict[type, tuple[str, ...]] = {
        ExamDeprivation: (
            "student_id",
            "academic_year",
            "gate",
            "deprived",
            "decided_on",
            "decided_by_id",
            "note",
        ),
        ExamMisconduct: (
            "student_id",
            "academic_year",
            "kind",
            "setup_id",
            "exam",
            "basis",
            "report_ref",
            "decided_on",
            "decided_by_id",
            "note",
        ),
    }

    @staticmethod
    def _snapshot(obj: ExamDeprivation | ExamMisconduct) -> dict[str, str]:
        return {f: _audit_value(getattr(obj, f)) for f in ExamDecisionService.FIELDS[type(obj)]}

    @staticmethod
    def ensure_open(school: School, year: str) -> None:
        if year != academic_year_for_school(school):
            raise ClosedYearError(f"العامُ الدراسيّ {year} مغلق — لا تُسجَّل فيه قرارات.")

    @staticmethod
    def _log(
        obj: ExamDeprivation | ExamMisconduct,
        actor: CustomUser | None,
        action: str,
        before: dict[str, str] | None,
        after: dict[str, str] | None,
    ) -> None:
        AuditLog.objects.create(
            school=obj.school,
            user=actor,
            action=action,
            model_name="other",
            object_id=str(obj.pk),
            object_repr=str(obj)[:300],
            changes={
                "op": DECISION_AUDIT_OP,
                "model": type(obj).__name__,
                "before": before,
                "after": after,
            },
        )

    @staticmethod
    def _rejudge(
        obj: ExamDeprivation | ExamMisconduct,
        student_ids: set[Any],
        actor: CustomUser | None,
        trigger: str,
    ) -> bool:
        """يُعيد الحكمَ على الطلبة في شعبتهم للعام — `False` إن أُرجئ (قواعدُ أقدم)."""
        applied = True
        for sid in student_ids:
            enrollment = (
                StudentEnrollment.objects.filter(
                    student_id=sid,
                    is_active=True,
                    class_group__school=obj.school,
                    class_group__academic_year=obj.academic_year,
                )
                .select_related("class_group", "student")
                .newest_first()
                .first()
            )
            if enrollment is None:
                continue
            done = GradeService.recalculate_students(
                enrollment.class_group,
                obj.academic_year,
                [enrollment.student],
                actor=actor,
                trigger=trigger,
            )
            applied = applied and bool(done)
        return applied

    @staticmethod
    @transaction.atomic
    def save(obj: ExamDeprivation | ExamMisconduct, actor: CustomUser) -> bool:
        """يحفظ القرار ويسجّله ويعيد الحكم — `False` إن أُرجئ الحكم (`is_deferred`)."""
        model = type(obj)
        ExamDecisionService.ensure_open(obj.school, obj.academic_year)
        old = model.objects.select_for_update().filter(pk=obj.pk).first()
        before = None
        students = {obj.student_id}
        if old is not None:
            ExamDecisionService.ensure_open(old.school, old.academic_year)
            before = ExamDecisionService._snapshot(old)
            students.add(old.student_id)
        obj.decided_by = actor
        obj.clean()
        obj.save()
        ExamDecisionService._log(
            obj,
            actor,
            "create" if old is None else "update",
            before,
            ExamDecisionService._snapshot(obj),
        )
        return ExamDecisionService._rejudge(
            obj, students, actor, f"{DECISION_AUDIT_OP}:{model.__name__}:{obj.pk}"
        )

    @staticmethod
    @transaction.atomic
    def delete(obj: ExamDeprivation | ExamMisconduct, actor: CustomUser) -> bool:
        ExamDecisionService.ensure_open(obj.school, obj.academic_year)
        before = ExamDecisionService._snapshot(obj)
        pk, students = obj.pk, {obj.student_id}
        ExamDecisionService._log(obj, actor, "delete", before, None)
        obj.delete()
        obj.pk = pk
        return ExamDecisionService._rejudge(
            obj, students, actor, f"{DECISION_AUDIT_OP}:{type(obj).__name__}:{pk}"
        )


# ─────────────────────────────────────────────────────────────
# ترحيلُ باقات الثاني عشر القائمة إلى بنيتها (البند 0.1)
# ─────────────────────────────────────────────────────────────


class PackageStructureError(Exception):
    """بنيةُ باقاتٍ تخالف الجدول وعليها درجات — لا تُطابَق آليّاً."""


class Grade12BlockedError(Exception):
    """إعدادٌ لا يُمسّ: عليه تقييماتٌ أو درجاتٌ مرصودة."""


@dataclass
class Grade12SetupPlan:
    """ما سيتغيّر في إعداد مادّةٍ واحدٍ من الثاني عشر."""

    setup: SubjectClassSetup
    #: باقاتٌ لا وجودَ لها في بنية الثاني عشر (P1/P3/AW) — تُحذف إن كانت فارغة.
    extra: list[AssessmentPackage] = field(default_factory=list)
    #: P2/P4 بوزنٍ أو قصوى غيرِ بنيتها — (الباقة، الوزنُ الصحيح).
    reweight: list[tuple[AssessmentPackage, Decimal]] = field(default_factory=list)
    #: تقييماتٌ ودرجاتٌ مرصودة على الباقات الزائدة — إن وُجدت فلا يُمسّ الإعداد.
    blocking_assessments: int = 0
    blocking_grades: int = 0

    @property
    def changes(self) -> bool:
        return bool(self.extra or self.reweight)

    @property
    def blocked(self) -> bool:
        return self.blocking_assessments > 0


class Grade12PackageFix:
    """يطابق باقاتِ شعب الثاني عشر القائمة بجدول `package_weights(12, …)`.

    لماذا أمرُ إدارةٍ لا هجرةُ بيانات: الهجرةُ تجري آليّاً عند النشر، والعملُ هنا
    **يجب أن يتوقّف** إن وُجدت درجاتٌ مرصودة على P1/P3/AW — حذفُها قرارُ مالكٍ لا
    آلة. والأمرُ يعرض العددَ أوّلاً (`--dry-run` افتراضاً)، ويُطبَّق صراحةً
    (`--apply`)، ويُتراجَع عنه (`--revert`)، ويُكتب في سجلّ المراجعة بفاعله.

    **ونطاقُه العامُ الجاري لكلّ مدرسة وحدَه**: نتائجُ عامٍ مُغلق لا يُعاد وزنُها ولا
    حسابُها (طلبتُه المتخرّجون تسجيلاتُهم غيرُ نشطة فلا يُعاد حسابُهم أصلاً).
    والتطبيقُ يعيد بناء خطّة الإعداد **داخل المعاملة وتحت قفل باقاته**: إدراجُ تقييمٍ
    على باقةٍ مقفولة ينتظر القفل، فلا يمحو الحذفُ المتتالي درجةً رُصدت بعد العرض.
    والتراجعُ يستعيد **ما سجّله التطبيقُ نفسُه** في AuditLog لا بنيةً عامّة، ويقف إن
    رُصدت درجاتٌ بعده.
    """

    APPLY = "grade12_fix_apply"
    REVERT = "grade12_fix_revert"

    @staticmethod
    def setups(school: School | None = None) -> list[SubjectClassSetup]:
        qs = SubjectClassSetup.objects.filter(class_group__grade="G12").select_related(
            "class_group", "subject", "school"
        )
        if school is not None:
            qs = qs.filter(school=school)
        current: dict = {}
        out = []
        for setup in qs:
            if setup.school_id not in current:
                current[setup.school_id] = academic_year_for_school(setup.school)
            if setup.academic_year == current[setup.school_id]:
                out.append(setup)
        return out

    @staticmethod
    def _plan_for(setup: SubjectClassSetup, packages: list[AssessmentPackage]) -> Grade12SetupPlan:
        plan = Grade12SetupPlan(setup=setup)
        for pkg in packages:
            weight = package_weights(12, pkg.semester).get(pkg.package_type)
            if weight is None:
                plan.extra.append(pkg)
            elif pkg.weight != weight or pkg.semester_max_grade != SEMESTER_MAX[pkg.semester]:
                plan.reweight.append((pkg, weight))
        if plan.extra:
            ids = [p.id for p in plan.extra]
            plan.blocking_assessments = Assessment.objects.filter(package_id__in=ids).count()
            plan.blocking_grades = StudentAssessmentGrade.objects.filter(
                assessment__package_id__in=ids
            ).count()
        return plan

    @staticmethod
    def plan(setups: list[SubjectClassSetup] | None = None) -> list[Grade12SetupPlan]:
        setups = Grade12PackageFix.setups() if setups is None else setups
        by_setup: dict = {}
        for pkg in AssessmentPackage.objects.filter(setup__in=setups):
            by_setup.setdefault(pkg.setup_id, []).append(pkg)
        return [Grade12PackageFix._plan_for(s, by_setup.get(s.id, [])) for s in setups]

    @staticmethod
    @transaction.atomic
    def apply(setup: SubjectClassSetup, actor: CustomUser) -> Grade12SetupPlan:
        """يطبّق خطّةَ الإعداد مبنيّةً من جديد تحت القفل، ويعيد حسابَه، ويسجّل ما كان."""
        packages = list(AssessmentPackage.objects.select_for_update().filter(setup=setup))
        plan = Grade12PackageFix._plan_for(setup, packages)
        if plan.blocked:
            raise Grade12BlockedError(
                f"{setup}: {plan.blocking_assessments} تقييماً و{plan.blocking_grades} درجةً"
            )
        if not plan.changes:
            return plan
        deleted = [
            {
                "semester": p.semester,
                "package_type": p.package_type,
                "weight": str(p.weight),
                "semester_max_grade": str(p.semester_max_grade),
                "is_active": p.is_active,
            }
            for p in plan.extra
        ]
        reweighted = [
            {
                "semester": p.semester,
                "package_type": p.package_type,
                "old_weight": str(p.weight),
                "old_semester_max_grade": str(p.semester_max_grade),
                "weight": str(w),
                "semester_max_grade": str(SEMESTER_MAX[p.semester]),
            }
            for p, w in plan.reweight
        ]
        AssessmentPackage.objects.filter(id__in=[p.id for p in plan.extra]).delete()
        for pkg, weight in plan.reweight:
            pkg.weight = weight
            pkg.semester_max_grade = SEMESTER_MAX[pkg.semester]
            pkg.save(update_fields=["weight", "semester_max_grade"])
        students = GradeService.recalculate_full_class(setup, actor=actor)
        AuditLog.objects.create(
            school=setup.school,
            user=actor,
            action="update",
            model_name="other",
            object_id=str(setup.id),
            object_repr=f"باقات الثاني عشر (0.1): {setup}"[:300],
            changes={
                "op": Grade12PackageFix.APPLY,
                "academic_year": setup.academic_year,
                "deleted": deleted,
                "reweighted": reweighted,
                "recalculated_students": students,
            },
        )
        return plan

    @staticmethod
    def pending_revert(setup: SubjectClassSetup) -> AuditLog | None:
        """آخرُ تطبيقٍ على الإعداد لم يُتراجَع عنه — أو لا شيء."""
        logs = list(
            AuditLog.objects.filter(object_id=str(setup.id), model_name="other").order_by(
                "-timestamp"
            )
        )
        reverted = {
            (log.changes or {}).get("reverts")
            for log in logs
            if (log.changes or {}).get("op") == Grade12PackageFix.REVERT
        }
        for log in logs:
            op = (log.changes or {}).get("op")
            if op == Grade12PackageFix.APPLY and str(log.id) not in reverted:
                return log
        return None

    @staticmethod
    @transaction.atomic
    def revert(setup: SubjectClassSetup, actor: CustomUser) -> list[str]:
        """يستعيد ما سجّله آخرُ `apply` على هذا الإعداد — أوزانَه وقُصواه وباقاتِه المحذوفة."""
        log = Grade12PackageFix.pending_revert(setup)
        if log is None:
            return []
        list(AssessmentPackage.objects.select_for_update().filter(setup=setup))
        after = StudentAssessmentGrade.objects.filter(
            assessment__package__setup=setup, entered_at__gt=log.timestamp
        ).count()
        if after:
            raise Grade12BlockedError(f"{setup}: {after} درجةً رُصدت بعد التطبيق")
        changes = log.changes or {}
        touched = []
        for d in changes.get("deleted", []):
            _, created = AssessmentPackage.objects.get_or_create(
                setup=setup,
                package_type=d["package_type"],
                semester=d["semester"],
                defaults={
                    "school": setup.school,
                    "weight": Decimal(d["weight"]),
                    "semester_max_grade": Decimal(d["semester_max_grade"]),
                    "is_active": d["is_active"],
                },
            )
            if created:
                touched.append(f"+{d['semester']}/{d['package_type']}")
        for r in changes.get("reweighted", []):
            AssessmentPackage.objects.filter(
                setup=setup, package_type=r["package_type"], semester=r["semester"]
            ).update(
                weight=Decimal(r["old_weight"]),
                semester_max_grade=Decimal(r["old_semester_max_grade"]),
            )
            touched.append(f"{r['semester']}/{r['package_type']}→{r['old_weight']}")
        students = GradeService.recalculate_full_class(setup, actor=actor)
        AuditLog.objects.create(
            school=setup.school,
            user=actor,
            action="update",
            model_name="other",
            object_id=str(setup.id),
            object_repr=f"تراجعُ باقات الثاني عشر (0.1): {setup}"[:300],
            changes={
                "op": Grade12PackageFix.REVERT,
                "reverts": str(log.id),
                "restored": touched,
                "recalculated_students": students,
            },
        )
        return touched
