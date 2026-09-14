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
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Avg, Count, Q, QuerySet

from core.academic_calendar import academic_year_for_school
from core.domain.grades import (
    GRADE_BANDS,
    SEMESTER_MAX,
    FirstRoundDecision,
    SubjectOutcome,
    band_of,
    classify_first_round,
    package_score,
    package_weights,
    semester_total,
)
from core.models import AuditLog, StudentEnrollment
from core.models.academic import grade_number, grade_order

from .models import (
    AnnualSubjectResult,
    Assessment,
    AssessmentPackage,
    StudentAssessmentGrade,
    StudentSubjectResult,
    SubjectClassSetup,
)

if TYPE_CHECKING:
    from core.models import ClassGroup, CustomUser, School


#: حالاتُ التقييم التي تُحسب — ما سواها مسودّة.
COUNTED_STATUSES = ("published", "graded", "closed")

#: اختباراتُ الغياب المحكوم به، وفصلُ كلٍّ منها: منتصفُ الأول ونهايتُه، ونهايةُ الثاني.
EXAM_PACKAGES = {"P1": "S1", "P2": "S1", "P4": "S2"}

ABSENT = "absent"
EXCUSED_ABSENCE = "excused"


def exam_absences(setup_ids, student_ids=None) -> dict:
    """{(طالب، إعداد): {باقة: "absent" | "excused"}} — الغيابُ عن الاختبار **كلِّه**.

    الطالبُ غائبٌ عن اختبارٍ إن غاب عن **كلّ** تقييماته المحسوبة في باقته. فمن غاب
    عن جزءٍ وحضر آخر لم يغب عن الاختبار: م24 «ثالثاً» (ص21) — «الطالب المتغيب عن
    أي من الجزء العملي أو النظري (وليس كلاهما) في اختبار نهاية الفصل الدراسي
    الثاني - سواء أكان الغياب بعذر مقبول أم بدون عذر- تجمع الدرجات … فإن أدى ذلك
    إلى حصوله على النهاية الصغرى للمادة اعتبر ناجحا»؛ و«ثانياً» لنهاية الأول:
    «فتحسب درجة الطالب على الجزء الذي حضره فقط». فالجزءُ الغائبُ صفرٌ في المجموع
    (`calc_package_score`) والحكمُ بالمجموع. وم22: الفصلُ الأول «بكامله (منتصف
    الفصل ونهايته)».

    ويُعدّ الغيابُ كلُّه «معذوراً» إن كان في أجزائه عذرٌ — حالٌ لا يسمّيها النصّ،
    والعذرُ يُحيل إلى ملحقٍ أو دورٍ ثانٍ يُختبر فيه لا إلى رسوب.
    """
    counts: dict = {}
    by_package = Q()
    for ptype, sem in EXAM_PACKAGES.items():
        by_package |= Q(package__package_type=ptype, package__semester=sem)
    for setup_id, ptype, n in (
        Assessment.objects.filter(
            by_package,
            package__setup_id__in=setup_ids,
            package__is_active=True,
            status__in=COUNTED_STATUSES,
        )
        .values("package__setup_id", "package__package_type")
        .annotate(n=Count("id"))
        .values_list("package__setup_id", "package__package_type", "n")
    ):
        counts[(setup_id, ptype)] = n
    if not counts:
        return {}

    grades = StudentAssessmentGrade.objects.filter(
        Q(is_absent=True) | Q(is_excused=True),
        assessment__package__setup_id__in=setup_ids,
        assessment__package__is_active=True,
        assessment__status__in=COUNTED_STATUSES,
    )
    if student_ids is not None:
        grades = grades.filter(student_id__in=student_ids)
    tally: dict = {}
    for sid, setup_id, ptype, sem, is_excused in grades.values_list(
        "student_id",
        "assessment__package__setup_id",
        "assessment__package__package_type",
        "assessment__package__semester",
        "is_excused",
    ):
        if EXAM_PACKAGES.get(ptype) != sem:
            continue
        t = tally.setdefault((sid, setup_id, ptype), [0, 0])
        t[0] += 1
        t[1] += bool(is_excused)

    result: dict = {}
    for (sid, setup_id, ptype), (absent, excused) in tally.items():
        if absent == counts.get((setup_id, ptype)):
            result.setdefault((sid, setup_id), {})[ptype] = EXCUSED_ABSENCE if excused else ABSENT
    return result


@dataclass(frozen=True)
class AbsenceFlags:
    excused: bool = False
    unexcused_final: bool = False
    unexcused_first_semester: bool = False


def subject_absence_flags(statuses: dict, grade: int) -> AbsenceFlags:
    """أثرُ غياب الاختبارات على مادّة — بحسب سياسة الصفّ.

    4–11:  نهايةُ الثاني بلا عذر → رسوب (م27). الفصلُ الأول بكامله بلا عذر → رسوب
           (م22). والعذرُ يُحيل إلى الدور الثاني عن نهاية الثاني (م25–26) أو عن الفصل
           الأول بكامله (م21). أمّا العذرُ عن نهاية الأول وحدَها فيسبقه الملحق (م19)،
           ومن غاب عنه «تكون درجته في الفصل الأول هي الدرجة التي حصل عليها في اختبار
           منتصف الفصل الأول وأعمال الفصل الأول» ويُحكم بمجموعه (م20 ص20) — فلا عذرَ
           يُعلَّم له، والدرجةُ الغائبةُ صفر.
    الثاني عشر: نهايةُ الثاني بلا عذر → رسوب (م17)؛ نهايةُ الأول بلا عذر → رسوب (م14)؛
           والعذرُ عن نهاية أيّ فصلٍ يُحيل إلى الدور الثاني مباشرة (م13-ت، م16 ص10).
    """
    p1, p2, p4 = statuses.get("P1"), statuses.get("P2"), statuses.get("P4")
    if grade == 12:
        excused = EXCUSED_ABSENCE in (p2, p4)
        unexcused_s1 = p2 == ABSENT
    else:
        excused = p4 == EXCUSED_ABSENCE or (p1 == p2 == EXCUSED_ABSENCE)
        unexcused_s1 = p1 == p2 == ABSENT
    return AbsenceFlags(
        excused=excused, unexcused_final=p4 == ABSENT, unexcused_first_semester=unexcused_s1
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
    ) -> tuple:
        """
        حفظ درجة طالب، ثم:
        1. إعادة حساب نتيجة الفصل
        2. إعادة حساب النتيجة السنوية

        Uses select_for_update() to prevent race conditions when two
        teachers attempt to record the same student's grade simultaneously.
        """
        if grade is not None:
            grade = Decimal(str(grade))
            grade = max(Decimal("0"), min(grade, assessment.max_grade))

        # Lock existing row (if any) to prevent concurrent writes
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

        setup = assessment.package.setup
        semester = assessment.package.semester

        # [PERF-02] عند الحفظ الجماعي نُمرِّر recalc=False ونعيد الحساب دفعةً واحدة بعد الحلقة
        if recalc:
            # 1. نتيجة الفصل
            GradeService.recalculate_semester_result(student, setup, semester)
            # 2. النتيجة السنوية
            GradeService.recalculate_annual_result(student, setup)

        return obj, created

    # ── حساب درجات الباقات دفعة واحدة (Batch) ──────────────

    @staticmethod
    def calc_package_scores_batch(
        student_ids: list,
        packages: list[AssessmentPackage],
        raw: bool = False,
    ) -> dict:
        """
        يحسب درجات كل الطلاب في كل الباقات بـ استعلام واحد بدل N×M.

        Returns: {(student_id, package_type): Decimal | None}
        `raw=True` يُعيد الدرجةَ الخامَ التي يُبنى منها مجموعُ الفصل (`semester_total`)،
        وإلّا فدرجةَ العرض (`package_score`: منتصفُ الفصل مجبور وحدَه — م8).
        """
        if not student_ids or not packages:
            return {}

        # 1. جمع كل التقييمات المنشورة لكل الباقات
        pkg_assessments: dict[str, list] = {}  # package_type → [Assessment]
        all_assessment_ids = []
        for pkg in packages:
            assessments = list(pkg.assessments.filter(status__in=["published", "graded", "closed"]))
            pkg_assessments[pkg.package_type] = assessments
            all_assessment_ids.extend(a.id for a in assessments)

        if not all_assessment_ids:
            return {}

        # 2. استعلام واحد لكل الدرجات
        all_grades = StudentAssessmentGrade.objects.filter(
            assessment_id__in=all_assessment_ids,
            student_id__in=student_ids,
        ).values_list("student_id", "assessment_id", "grade", "is_absent")

        # index: (student_id, assessment_id) → (grade, is_absent)
        grades_index: dict = {}
        for sid, aid, grade, is_abs in all_grades:
            grades_index[(sid, aid)] = (grade, is_abs)

        # 3. حساب الدرجة لكل طالب × باقة
        results: dict = {}
        for pkg in packages:
            assessments = pkg_assessments.get(pkg.package_type, [])
            if not assessments or pkg.weight == 0:
                for sid in student_ids:
                    results[(sid, pkg.package_type)] = Decimal("0") if pkg.weight == 0 else None
                continue

            total_weight = sum(float(a.weight_in_package) for a in assessments)
            if total_weight == 0:
                for sid in student_ids:
                    results[(sid, pkg.package_type)] = None
                continue

            for sid in student_ids:
                weighted_pct = Decimal("0")
                has_grade = False

                for asmnt in assessments:
                    entry = grades_index.get((sid, asmnt.id))
                    if entry is None:
                        continue

                    grade, is_abs = entry
                    has_grade = True
                    if is_abs or grade is None:
                        pct = Decimal("0")
                    else:
                        pct = Decimal(str(grade)) / asmnt.max_grade * Decimal("100")

                    w = Decimal(str(asmnt.weight_in_package)) / Decimal(str(total_weight))
                    weighted_pct += pct * w

                if not has_grade:
                    results[(sid, pkg.package_type)] = None
                else:
                    actual = weighted_pct * pkg.weight * pkg.semester_max_grade / Decimal("10000")
                    results[(sid, pkg.package_type)] = (
                        actual if raw else package_score(pkg.package_type, actual)
                    )

        return results

    # ── حساب درجة الباقة الواحدة ───────────────────────────

    @staticmethod
    def calc_package_score(
        student: CustomUser, package: AssessmentPackage, raw: bool = False
    ) -> Decimal | None:
        """
        يحسب درجة الطالب الفعلية في الباقة من مجموع الفصل.

        المعادلة:
          أداء_الطالب_في_الباقة (0–100%) × وزن_الباقة_من_الفصل% × درجة_الفصل_القصوى / 100

        مثال — الباقة P4 في الفصل الثاني:
          weight = 50%, semester_max = 60
          → درجة قصوى للباقة = 50% × 60 = 30 درجة
          → لو الطالب حصل 80% في تقييمات الباقة:
          → درجته = 80% × 30 = 24 من 30
        """
        if package.weight == 0:
            return Decimal("0")

        assessments = package.assessments.filter(status__in=["published", "graded", "closed"])
        if not assessments.exists():
            return None

        total_weight = sum(float(a.weight_in_package) for a in assessments)
        if total_weight == 0:
            return None

        # ── Batch-fetch student grades to avoid N+1 queries ──
        assessment_ids = [a.id for a in assessments]
        grades_map = {
            g.assessment_id: g
            for g in StudentAssessmentGrade.objects.filter(
                assessment_id__in=assessment_ids, student=student
            )
        }

        # حساب أداء الطالب % في هذه الباقة
        weighted_pct = Decimal("0")
        has_grade = False

        for asmnt in assessments:
            g = grades_map.get(asmnt.id)
            if g is None:
                continue

            has_grade = True
            if g.is_absent or g.grade is None:
                pct = Decimal("0")
            else:
                pct = g.grade / asmnt.max_grade * Decimal("100")

            w = Decimal(str(asmnt.weight_in_package)) / Decimal(str(total_weight))
            weighted_pct += pct * w

        if not has_grade:
            return None

        # تحويل إلى الدرجة الفعلية من مجموع الفصل
        # = أداء% × وزن_الباقة% × درجة_الفصل_القصوى / 100 / 100
        actual_score = weighted_pct * package.weight * package.semester_max_grade / Decimal("10000")
        return actual_score if raw else package_score(package.package_type, actual_score)

    # ── نتيجة الفصل ────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def recalculate_semester_result(
        student: CustomUser,
        setup: SubjectClassSetup,
        semester: str,
    ) -> StudentSubjectResult:
        """
        يحسب ويخزن مجموع درجات الطالب في مادة للفصل المحدد.
        الناتج: total ∈ [0, semester_max] (40 أو 60)
        """
        packages = AssessmentPackage.objects.filter(setup=setup, semester=semester, is_active=True)

        packages = list(packages)
        raws = {
            pkg.package_type: GradeService.calc_package_score(student, pkg, raw=True)
            for pkg in packages
        }
        return GradeService._write_semester_result(student, setup, semester, packages, raws)

    # ── النتيجة السنوية ─────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def recalculate_annual_result(
        student: CustomUser, setup: SubjectClassSetup, absences: dict | None = None
    ) -> AnnualSubjectResult:
        """
        يجمع نتائج الفصلين ويحسب المجموع السنوي من 100، ويحكم بالحالة.

        المعادلة: annual_total = s1_total + s2_total — وكلاهما مجبورٌ عند كتابته (م8)،
        فلا يُجبر المجموعُ ثانيةً: جبرُه كان يُنصف مجموعاً قديماً خُزّن قبل الجبر
        كلّما أُعيد حسابُ طالبٍ واحد، فتختلط في الشعبة قاعدتان.

        والحالةُ تقرأ الغيابَ عن الاختبارات (`exam_absences`) كما تقرؤه شاشةُ الدور
        الثاني، فلا يتناقضان:
          «fail» والمجموعُ «غائب» (None) — الغائبُ بلا عذر عن نهاية الفصل الثاني:
              «تكون الدرجة النهائية للمادة (مجموع الفصلين) "غائب" أي لا يحتسب له
              درجات الفصل الأول، وتحسب المادة ضمن مواد الرسوب» (4–11 م27 ص22؛
              والثاني عشر م17 ص11).
          «fail» — الغائبُ بلا عذر عن الفصل الأول بكامله: «وتحسب ضمن مواد الرسوب»
              (م22 ص21؛ والثاني عشر م14 ص10).
          «second_round» — المعذورُ المُحال إلى الدور الثاني (م12-ب؛ `excused_final_absence`).
        """
        year = setup.academic_year

        try:
            s1_total = StudentSubjectResult.objects.get(
                student=student, setup=setup, semester="S1"
            ).total
        except StudentSubjectResult.DoesNotExist:
            s1_total = None

        try:
            s2_total = StudentSubjectResult.objects.get(
                student=student, setup=setup, semester="S2"
            ).total
        except StudentSubjectResult.DoesNotExist:
            s2_total = None

        if absences is None:
            absences = exam_absences([setup.id], [student.id])
        flags = subject_absence_flags(
            absences.get((student.id, setup.id), {}), grade_number(setup.class_group.grade)
        )

        if s1_total is None and s2_total is None:
            annual_total = None
            status = "incomplete"
        else:
            annual_total = (s1_total or Decimal("0")) + (s2_total or Decimal("0"))
            if s1_total is None or s2_total is None:
                status = "incomplete"
            elif annual_total >= Decimal("50"):
                status = "pass"
            else:
                status = "fail"

        if flags.unexcused_final:
            annual_total, status = None, "fail"
        elif flags.unexcused_first_semester:
            status = "fail"
        elif flags.excused:
            status = "second_round"

        # Lock existing row to prevent concurrent recalculation races
        existing = (
            AnnualSubjectResult.objects.select_for_update()
            .filter(student=student, setup=setup, academic_year=year)
            .first()
        )
        defaults = {
            "school": setup.school,
            "s1_total": s1_total,
            "s2_total": s2_total,
            "annual_total": annual_total,
            "status": status,
        }
        if existing:
            for attr, val in defaults.items():
                setattr(existing, attr, val)
            existing.save()
            annual = existing
        else:
            annual = AnnualSubjectResult.objects.create(
                student=student, setup=setup, academic_year=year, **defaults
            )
        return annual

    @staticmethod
    @transaction.atomic
    def _write_semester_result(student, setup, semester, packages, scores):
        """[PERF-01] يكتب StudentSubjectResult من قاموس درجات الباقات **الخام**.
        المسارُ الوحيد للكتابة — يمرّ به المفرد (calc_package_score) والدُّفعي
        (calc_package_scores_batch) فلا تفترق نتائجهما. والمجموعُ `semester_total`:
        جبرٌ واحدٌ لمجموع الفصل بعد جبر منتصفه (م8)، لا جبرٌ لكلّ باقة."""
        semester_max = AssessmentPackage.SEMESTER_MAX.get(semester, Decimal("40"))
        raws = {pkg.package_type: scores.get(pkg.package_type) for pkg in packages}
        for pkg in packages:
            if raws[pkg.package_type] is not None:
                semester_max = pkg.semester_max_grade
        total = semester_total(raws)
        scores = {k: (None if v is None else package_score(k, v)) for k, v in raws.items()}

        existing = (
            StudentSubjectResult.objects.select_for_update()
            .filter(student=student, setup=setup, semester=semester)
            .first()
        )
        defaults = {
            "school": setup.school,
            "p1_score": scores.get("P1"),
            "p2_score": scores.get("P2"),
            "p3_score": scores.get("P3"),
            "p4_score": scores.get("P4"),
            "p_aw_score": scores.get("AW"),
            "total": total,
            "semester_max": semester_max,
        }
        if existing:
            for attr, val in defaults.items():
                setattr(existing, attr, val)
            existing.save()
            return existing
        return StudentSubjectResult.objects.create(
            student=student, setup=setup, semester=semester, **defaults
        )

    @staticmethod
    def recalculate_full_class(setup: SubjectClassSetup) -> int:
        """إعادة حساب كامل — كل طلاب الفصل، كلا الفصلين، والسنوي.
        [PERF-01] يستخدم calc_package_scores_batch (استعلام واحد للدرجات لكل فصل) بدل
        الحساب لكل طالب × باقة — نفس النتائج بعدد استعلامات ثابت مهما زاد عدد الطلاب."""
        enrollments = list(
            StudentEnrollment.objects.filter(
                class_group=setup.class_group, is_active=True
            ).select_related("student")
        )
        students = [e.student for e in enrollments]
        student_ids = [s.id for s in students]
        if not student_ids:
            return 0

        for sem in ("S1", "S2"):
            packages = list(
                AssessmentPackage.objects.filter(setup=setup, semester=sem, is_active=True)
            )
            batch = GradeService.calc_package_scores_batch(student_ids, packages, raw=True)
            for student in students:
                scores = {
                    pkg.package_type: batch.get((student.id, pkg.package_type)) for pkg in packages
                }
                GradeService._write_semester_result(student, setup, sem, packages, scores)

        absences = exam_absences([setup.id], student_ids)
        for student in students:
            GradeService.recalculate_annual_result(student, setup, absences=absences)
        return len(students)

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
        stats = AnnualSubjectResult.objects.filter(setup=setup, academic_year=year).aggregate(
            total=Count("id"),
            passed=Count("id", filter=Q(status="pass")),
            failed=Count("id", filter=Q(status="fail")),
            incomplete=Count("id", filter=Q(status="incomplete")),
            avg=Avg("annual_total"),
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
        """الطلاب الراسبون سنوياً"""
        year = year or academic_year_for_school(school)
        return (
            AnnualSubjectResult.objects.filter(school=school, academic_year=year, status="fail")
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
            AnnualSubjectResult.objects.filter(school=school, academic_year=year)
            .values("setup__subject__name_ar")
            .annotate(
                avg=Avg("annual_total"),
                fail_count=Count("id", filter=Q(status="fail")),
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
# الدورُ الثاني (البند 2.2) — القواعدُ في core.domain.grades، وهنا جمعُ المدخلات
# ─────────────────────────────────────────────────────────────


@dataclass
class SecondRoundRow:
    student: CustomUser
    decision: FirstRoundDecision


class SecondRoundService:
    """يصنّف طلبةَ شعبةٍ بعد الدور الأول بـ`classify_first_round` (م12/13/16/29/50).

    المدخلاتُ من القاعدة: المجموعُ السنويّ لكلّ مادّةٍ نشطة، والغيابُ عن الاختبارات
    كلِّها لا عن جزءٍ منها (`exam_absences`)، وأيّامُ الغياب بلا عذر (`absence_standing`).

    والحرمانُ هنا **تجاوزُ عتبة الاختبار في يومه**: «إذا تجاوزت مدة الغياب … اعتباراً
    من بداية العام الدراسي» (م29 ص22–23؛ والثاني عشر م19 ص11)، و«تُطبَّق أحكام
    السياسة قبل كل اختبار على حدة» (`08_conduct_policy_2026.md:162`). فالأيّامُ تُعدّ
    في العام المعروض حتّى عشيّة اختبار نهاية الفصل (`exam_eve`) لا حتّى اليوم. وقرارُه
    الرسميّ لفريق إدارة سلوك الطلبة، فالشاشةُ تعرض بلوغَ العتبة ولا تُصدره. ولا يُقرأ
    بعدُ حرمانُ العذر الطبيّ المزوَّر ومخالفاتِ التنمّر الحمراء الثلاث
    (`08_conduct_policy_2026.md:173-174`)، ولا «ملغي» (م45 مكرر) من محاضر
    `exam_control.ExamIncident` — فالمحضرُ لا يميّز الفعلَ الذي يُلغي كلَّ الموادّ.
    """

    @staticmethod
    def exam_eve(class_group: ClassGroup, year: str, semester: str, setups=()) -> date | None:
        """عشيّةُ اختبار نهاية الفصل لصفّ الشعبة في العام المعروض — آخرُ يومٍ يُعدّ غيابُه.

        من تقويم الوزارة (`CalendarEvent` «final_exam» بنطاق الصفّ)، ثمّ من أوّل تاريخٍ
        لاختبار نهاية الفصل في موادّ الشعبة، ثمّ نهايةُ العام أو اليوم أيُّهما أسبق.
        """
        from datetime import timedelta

        from django.utils import timezone

        from core.academic_calendar import _scope_for
        from core.models import AcademicYear, CalendarEvent

        school = class_group.school
        year_obj = AcademicYear.objects.filter(school=school, name=year).first()
        if year_obj is not None:
            event = (
                CalendarEvent.objects.filter(
                    academic_year=year_obj,
                    event_type="final_exam",
                    semester__code=semester,
                    grade_scope__in=("all", _scope_for(class_group.grade)),
                )
                .order_by("start_date")
                .first()
            )
            if event is not None:
                return event.start_date - timedelta(days=1)
        ptype = "P2" if semester == "S1" else "P4"
        first_exam = (
            Assessment.objects.filter(
                package__setup__in=setups,
                package__package_type=ptype,
                package__semester=semester,
                date__isnull=False,
            )
            .order_by("date")
            .values_list("date", flat=True)
            .first()
        )
        if first_exam is not None:
            return first_exam - timedelta(days=1)
        if year_obj is None:
            return None
        return min(year_obj.end_date, timezone.localdate())

    @staticmethod
    def roster(class_group: ClassGroup, year: str | None = None) -> list[SecondRoundRow]:
        from operations.absence_policy import breached
        from operations.absence_standing import unexcused_days_for_class

        school = class_group.school
        year = year or academic_year_for_school(school)
        grade = grade_number(class_group.grade)
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
        totals = {
            (r.student_id, r.setup_id): (r.annual_total if r.status != "incomplete" else None)
            for r in AnnualSubjectResult.objects.filter(setup__in=setups, academic_year=year)
        }
        absences = exam_absences([s.id for s in setups])

        # م29 (الصفّ الأخير): حرمانُ الدور الأول = عتبةُ نهاية الفصل الثاني عند اختباره.
        # والثاني عشر م19-1: عتبةُ نهاية الفصل الأول عند اختباره تحرم أيضاً.
        finals = ("s1_final", "s2_final") if grade == 12 else ("s2_final",)
        days_at = {}
        for key in finals:
            eve = SecondRoundService.exam_eve(
                class_group, year, "S1" if key == "s1_final" else "S2", setups
            )
            days_at[key] = unexcused_days_for_class(class_group, school, on=eve) if eve else {}

        rows = []
        for student in students:
            outcomes = []
            for setup in setups:
                flags = subject_absence_flags(absences.get((student.id, setup.id), {}), grade)
                outcomes.append(
                    SubjectOutcome(
                        subject=setup.subject.name_ar,
                        annual_total=totals.get((student.id, setup.id)),
                        excused_final_absence=flags.excused,
                        unexcused_final_absence=flags.unexcused_final,
                        unexcused_first_semester_absence=flags.unexcused_first_semester,
                    )
                )
            hit = {
                key
                for key in finals
                if any(
                    g.key == key
                    for g in breached(class_group.grade, days_at[key].get(student.id, 0))
                )
            }
            decision = classify_first_round(
                outcomes,
                grade,
                deprived=bool(hit),
                deprived_before_first_final="s1_final" in hit,
            )
            rows.append(SecondRoundRow(student, decision))
        return rows


# ─────────────────────────────────────────────────────────────
# ترحيلُ باقات الثاني عشر القائمة إلى بنيتها (البند 0.1)
# ─────────────────────────────────────────────────────────────


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
    def _plan_for(setup: SubjectClassSetup, packages) -> Grade12SetupPlan:
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
    def plan(setups=None) -> list[Grade12SetupPlan]:
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
        students = GradeService.recalculate_full_class(setup)
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
        students = GradeService.recalculate_full_class(setup)
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
