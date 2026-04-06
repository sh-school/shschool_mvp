"""
assessments/services.py
محرك حساب الدرجات — معادلة وزارة التعليم القطرية الصحيحة

الفصل الأول  = 40 درجة من 100
الفصل الثاني = 60 درجة من 100
المجموع السنوي = S1 + S2 (من 100)
النجاح = 50 فأكثر
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import transaction
from django.db.models import Avg, Count, Q, QuerySet

from core.models import StudentEnrollment

from .models import (
    AnnualSubjectResult,
    Assessment,
    AssessmentPackage,
    StudentAssessmentGrade,
    StudentSubjectResult,
    SubjectClassSetup,
)

if TYPE_CHECKING:
    from core.models import CustomUser, School


class GradeService:
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
    ) -> dict:
        """
        يحسب درجات كل الطلاب في كل الباقات بـ استعلام واحد بدل N×M.

        Returns: {(student_id, package_type): Decimal | None}
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
                    results[(sid, pkg.package_type)] = actual.quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )

        return results

    # ── حساب درجة الباقة الواحدة ───────────────────────────

    @staticmethod
    def calc_package_score(student: CustomUser, package: AssessmentPackage) -> Decimal | None:
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
        return actual_score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

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

        scores: dict = {}
        total = Decimal("0")
        semester_max = AssessmentPackage.SEMESTER_MAX.get(semester, Decimal("40"))
        has_score = False

        for pkg in packages:
            score = GradeService.calc_package_score(student, pkg)
            scores[pkg.package_type] = score
            if score is not None:
                total += score
                has_score = True
                # semester_max من أول باقة لها بيانات
                semester_max = pkg.semester_max_grade

        # Lock existing row to prevent concurrent recalculation races
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
            "total": total if has_score else None,
            "semester_max": semester_max,
        }
        if existing:
            for attr, val in defaults.items():
                setattr(existing, attr, val)
            existing.save()
            result = existing
        else:
            result = StudentSubjectResult.objects.create(
                student=student, setup=setup, semester=semester, **defaults
            )
        return result

    # ── النتيجة السنوية ─────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def recalculate_annual_result(
        student: CustomUser, setup: SubjectClassSetup
    ) -> AnnualSubjectResult:
        """
        يجمع نتائج الفصلين ويحسب المجموع السنوي من 100.

        المعادلة: annual_total = s1_total + s2_total
        حيث s1_total ∈ [0,40] و s2_total ∈ [0,60]
        """
        year = setup.academic_year

        try:
            s1_result = StudentSubjectResult.objects.get(
                student=student, setup=setup, semester="S1"
            )
            s1_total = s1_result.total
        except StudentSubjectResult.DoesNotExist:
            s1_total = None

        try:
            s2_result = StudentSubjectResult.objects.get(
                student=student, setup=setup, semester="S2"
            )
            s2_total = s2_result.total
        except StudentSubjectResult.DoesNotExist:
            s2_total = None

        # نحسب السنوي فقط لو عندنا نتيجة واحدة على الأقل
        if s1_total is None and s2_total is None:
            annual_total = None
            status = "incomplete"
        else:
            annual_total = (s1_total or Decimal("0")) + (s2_total or Decimal("0"))
            annual_total = annual_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            if s1_total is None or s2_total is None:
                status = "incomplete"
            elif annual_total >= Decimal("50"):
                status = "pass"
            else:
                status = "fail"

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
    def recalculate_full_class(setup: SubjectClassSetup) -> None:
        """إعادة حساب كامل — كل طلاب الفصل، كلا الفصلين، والسنوي"""
        enrollments = StudentEnrollment.objects.filter(
            class_group=setup.class_group, is_active=True
        ).select_related("student")

        for enr in enrollments:
            for sem in ("S1", "S2"):
                GradeService.recalculate_semester_result(enr.student, setup, sem)
            GradeService.recalculate_annual_result(enr.student, setup)

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
    def get_class_results_summary(
        setup: SubjectClassSetup, year: str = settings.CURRENT_ACADEMIC_YEAR
    ) -> dict:
        """ملخص النتائج السنوية للفصل في مادة — استعلام واحد"""
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
        year: str = settings.CURRENT_ACADEMIC_YEAR,
    ) -> QuerySet:
        """كشف الدرجات السنوية الكامل للطالب"""
        return (
            AnnualSubjectResult.objects.filter(student=student, school=school, academic_year=year)
            .select_related("setup__subject", "setup__class_group")
            .order_by("setup__subject__name_ar")
        )

    @staticmethod
    def get_failing_students(
        school: School, year: str = settings.CURRENT_ACADEMIC_YEAR
    ) -> QuerySet:
        """الطلاب الراسبون سنوياً"""
        return (
            AnnualSubjectResult.objects.filter(school=school, academic_year=year, status="fail")
            .select_related("student", "setup__subject", "setup__class_group")
            .order_by("setup__class_group__grade", "student__full_name")
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

        bands = [0] * 6  # <50, 50-59, 60-69, 70-79, 80-89, 90-100
        for r in results_values:
            if r is None:
                continue
            t = float(r)
            if t >= 90:
                bands[5] += 1
            elif t >= 80:
                bands[4] += 1
            elif t >= 70:
                bands[3] += 1
            elif t >= 60:
                bands[2] += 1
            elif t >= 50:
                bands[1] += 1
            else:
                bands[0] += 1

        # ── Class comparison — 2 queries ──
        classes = list(
            ClassGroup.objects.filter(school=school, academic_year=year).order_by(
                "grade", "section"
            )[:15]
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
