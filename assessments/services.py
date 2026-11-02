"""
assessments/services.py
محرك حساب الدرجات — معادلة وزارة التعليم القطرية الصحيحة

الفصل الأول  = 40 درجة من 100
الفصل الثاني = 60 درجة من 100
المجموع السنوي = S1 + S2 (من 100)
النجاح = 50 فأكثر
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Avg, Count, Q, QuerySet
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.domain.grades import GRADE_BANDS, PASS_MARK, band_of
from core.models import StudentEnrollment
from core.models.academic import grade_order
from core.verdict_read import (
    failing_statuses,
    passing_statuses,
    pending_statuses,
    verdict_engine_enabled,
)

from .excuse_service import (  # noqa: F401  (EXCUSE_GRACE_DAYS يُستورد من هنا)
    EXCUSE_GRACE_DAYS,
    ExcuseServiceMixin,
)
from .models import (
    AnnualSubjectResult,
    Assessment,
    AssessmentPackage,
    StudentAssessmentGrade,
    StudentSubjectResult,
    SubjectClassSetup,
)
from .verdict_engine import VerdictEngine, ensure_open_year

if TYPE_CHECKING:
    from core.models import CustomUser, School


logger = logging.getLogger(__name__)

_ROW_KEYS = ("grade_", "absent_", "notes_")

_SEMESTER_WRITE_FIELDS = (
    "school",
    "p1_score",
    "p2_score",
    "p3_score",
    "p4_score",
    "p_aw_score",
    "total",
    "semester_max",
)
_ANNUAL_WRITE_FIELDS = ("school", "s1_total", "s2_total", "annual_total", "status")
_GRADE_WRITE_FIELDS = ("school", "grade", "is_absent", "notes", "entered_by", "entered_at")


def _audit_row_factory():
    """مصنعُ صفوف `AuditLog` بمحتوى إشارة `core.signals._log` نفسِه، للكتابة الدفعيّة.

    `bulk_create` لا يُطلق `post_save` فيسقط أثرُ التدقيق (PDPPL)، فتُبنى الصفوفُ هنا صفّاً بصفٍّ
    كما تبنيها الإشارةُ وتُكتب دفعةً واحدة (`_bulk_audit`). والمستخدمُ والعنوانُ والمتصفّحُ تُقرأ مرّةً.
    ويثبّت `tests/test_hot_paths_queries_w008.py` تساوي الصفوف ومحتواها مع المسار المفرد.
    """
    from core.audit_repr import masked_repr
    from core.middleware import get_current_request, get_current_user
    from core.models import AuditLog
    from core.request_utils import get_client_ip

    user = get_current_user()
    request = get_current_request()
    ip = ua = ""
    if request:
        ip = get_client_ip(request)
        ua = request.META.get("HTTP_USER_AGENT", "")[:300]

    def make(model_name: str, instance: Any, created: bool, changes: dict | None):
        return AuditLog(
            user=user,
            action="create" if created else "update",
            model_name=model_name,
            object_id=str(instance.pk),
            object_repr=masked_repr(instance),
            changes=changes,
            school=instance.school if hasattr(instance, "school_id") else None,
            ip_address=ip or None,
            user_agent=ua,
        )

    return make


def _bulk_audit(rows: list) -> None:
    if rows:
        from core.models import AuditLog

        AuditLog.objects.bulk_create(rows)


def _subject_result_changes(instance: Any) -> dict:
    """محتوى `changes` كما تكتبه إشارةُ `audit_subject_result` تماماً."""
    return {
        "semester": instance.semester,
        "total": str(getattr(instance, "total_score", "")),
        "status": getattr(instance, "status", ""),
    }


class AssessmentClosedError(ValidationError):
    """تقييمٌ مغلق: لا درجةَ تُكتب بعد الإقفال (W-20261101-007)."""

    def __init__(self, assessment):
        super().__init__(f"التقييم «{assessment.title}» مغلق — لا تُعدَّل درجاتُه.")


def ensure_assessment_open(assessment) -> None:
    if assessment.status == "closed":
        raise AssessmentClosedError(assessment)


class GradeService(ExcuseServiceMixin):
    # ── من تُحفظ له الدرجة ─────────────────────────────────

    @staticmethod
    def enrolled_student_or_404(assessment: Assessment, student_id: Any) -> CustomUser:
        """الطالبُ المقيَّدُ الآن في شعبة هذا التقييم، وإلّا 404.

        كان `save_single_grade` يقبل أيَّ معرّفِ مستخدمٍ فتُكتب له درجةٌ في ورقةٍ لا تخصّه — من مدرسةٍ أخرى أو من شعبةٍ أخرى.
        و`save_all_from_post` يمرّ على المقيَّدين وحدَهم أصلاً؛ فهذا يوحّد البابَين.
        """
        from django.core.exceptions import ValidationError
        from django.http import Http404

        try:
            enrollment = (
                StudentEnrollment.objects.filter(
                    class_group=assessment.class_group, is_active=True, student_id=student_id
                )
                .select_related("student")
                .first()
            )
        except (ValidationError, ValueError, TypeError):
            enrollment = None
        if enrollment is None:
            raise Http404("الطالبُ غيرُ مقيَّدٍ في شعبة هذا التقييم")
        return enrollment.student

    # ── حفظ درجة طالب ──────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def save_grade(
        assessment: Assessment,
        student: CustomUser,
        grade: Decimal | None = None,
        is_absent: bool = False,
        is_excused: bool | None = None,
        notes: str = "",
        entered_by: CustomUser | None = None,
        recalc: bool = True,
    ) -> tuple:
        """
        حفظ درجة طالب، ثم:
        1. إعادة حساب نتيجة الفصل
        2. إعادة حساب النتيجة السنوية

        العذرُ لا يُثبَّت من هنا (D-402م): `is_excused=None` يُبقي ما هو محفوظٌ كما هو، والصفُّ المعذور
        مقفلٌ على راصد الدرجات فيُرجَع كما هو. وتثبيتُ العذر في `decide_excuse` وحدَه، لحامل القدرة.

        Uses select_for_update() to prevent race conditions when two
        teachers attempt to record the same student's grade simultaneously.
        """
        ensure_assessment_open(assessment)
        engine = verdict_engine_enabled()
        if engine:
            # الأعوامُ المغلقة مجمَّدة — رفضٌ صريحٌ قبل أيّ كتابة (محرّك الحكم الواحد).
            ensure_open_year(assessment.package.setup)
        if grade is not None:
            grade = Decimal(str(grade))
            grade = max(Decimal("0"), min(grade, assessment.max_grade))

        # Lock existing row (if any) to prevent concurrent writes
        existing = (
            StudentAssessmentGrade.objects.select_for_update()
            .filter(assessment=assessment, student=student)
            .first()
        )

        if existing and existing.is_excused and is_excused is None:
            return existing, False  # عذرٌ مقرَّر: لا يغيّره راصدُ الدرجات (لا غيابَه ولا درجتَه)

        if existing:
            existing.school = assessment.school
            existing.grade = grade
            existing.is_absent = is_absent
            if is_excused is not None:
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
                is_excused=bool(is_excused),
                notes=notes,
                entered_by=entered_by,
            )
            created = True

        # [PERF-02] عند الحفظ الجماعي نُمرِّر recalc=False ونعيد الحساب دفعةً واحدة بعد الحلقة
        if recalc:
            GradeService._recalculate_student(assessment, student, entered_by, "save_grade")

        return obj, created

    @staticmethod
    def _recalculate_student(
        assessment: Assessment, student: CustomUser, actor: CustomUser | None, trigger: str
    ) -> None:
        """إعادةُ حساب نتيجة طالبٍ بعد تغيّر صفّ درجته (محرّكُ الحكم أو المسارُ القديم)."""
        setup = assessment.package.setup
        if verdict_engine_enabled():
            VerdictEngine.recalculate_students(
                setup.class_group,
                setup.academic_year,
                [student],
                setup,
                actor=actor,
                trigger=f"{trigger}:{assessment.pk}",
            )
        else:
            # 1. نتيجة الفصل
            GradeService.recalculate_semester_result(student, setup, assessment.package.semester)
            # 2. النتيجة السنوية
            GradeService.recalculate_annual_result(student, setup)

    # ── حساب درجات الباقات دفعة واحدة (Batch) ──────────────

    @staticmethod
    def calc_package_scores_batch(
        student_ids: list,
        packages: list[AssessmentPackage],
        assessments_by_package: dict | None = None,
    ) -> dict:
        """
        يحسب درجات كل الطلاب في كل الباقات بـ استعلام واحد بدل N×M.

        `assessments_by_package` (اختياريّ): {pkg.pk: [Assessment منشورة]} جُلبت دفعةً لكلّ باقات الشعبة،
        فلا يُستعلم عنها باقةً باقة (إعادةُ حساب الفصل تحسبُ الفصلين معاً).

        Returns: {(student_id, package_type): Decimal | None}
        """
        if not student_ids or not packages:
            return {}

        # 1. جمع كل التقييمات المنشورة لكل الباقات
        pkg_assessments: dict[str, list] = {}  # package_type → [Assessment]
        all_assessment_ids = []
        for pkg in packages:
            if assessments_by_package is not None:
                assessments = assessments_by_package.get(pkg.pk, [])
            else:
                assessments = list(
                    pkg.assessments.filter(status__in=["published", "graded", "closed"])
                )
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
        if verdict_engine_enabled():
            # نتيجةُ الفصل بعد الحكم على الطالب في موادّه كلِّها.
            VerdictEngine.recalculate_students(
                setup.class_group, setup.academic_year, [student], setup
            )
            return StudentSubjectResult.objects.get(student=student, setup=setup, semester=semester)

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

        if verdict_engine_enabled():
            # الحالةُ والمجموعُ والموضعُ من `judge_student` لا من هنا.
            VerdictEngine.recalculate_students(setup.class_group, year, [student], setup)
            return AnnualSubjectResult.objects.get(student=student, setup=setup, academic_year=year)

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

        # Lock existing row to prevent concurrent recalculation races
        existing = (
            AnnualSubjectResult.objects.select_for_update()
            .filter(student=student, setup=setup, academic_year=year)
            .first()
        )
        annual_total, status = GradeService._annual_values(
            s1_total, s2_total, existing.pass_grade if existing else PASS_MARK
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
    def _semester_defaults(setup, semester, packages, scores) -> dict:
        """قيمُ صفّ `StudentSubjectResult` من درجات الباقات — دالةٌ نقيّةٌ تشاركها الكتابةُ المفردةُ والدفعيّة."""
        total = Decimal("0")
        semester_max = AssessmentPackage.SEMESTER_MAX.get(semester, Decimal("40"))
        has_score = False
        for pkg in packages:
            score = scores.get(pkg.package_type)
            if score is not None:
                total += score
                has_score = True
                semester_max = pkg.semester_max_grade
        return {
            "school": setup.school,
            "p1_score": scores.get("P1"),
            "p2_score": scores.get("P2"),
            "p3_score": scores.get("P3"),
            "p4_score": scores.get("P4"),
            "p_aw_score": scores.get("AW"),
            "total": total if has_score else None,
            "semester_max": semester_max,
        }

    @staticmethod
    @transaction.atomic
    def _write_semester_result(student, setup, semester, packages, scores):
        """[PERF-01] يكتب StudentSubjectResult من قاموس درجات الباقات.
        منطق الكتابة مطابق تماماً لـ recalculate_semester_result لضمان تطابق النتائج
        بين المسار المفرد (calc_package_score) والمسار الدُّفعي (calc_package_scores_batch)."""
        defaults = GradeService._semester_defaults(setup, semester, packages, scores)
        existing = (
            StudentSubjectResult.objects.select_for_update()
            .filter(student=student, setup=setup, semester=semester)
            .first()
        )
        if existing:
            for attr, val in defaults.items():
                setattr(existing, attr, val)
            existing.save()
            return existing
        return StudentSubjectResult.objects.create(
            student=student, setup=setup, semester=semester, **defaults
        )

    @staticmethod
    def _annual_values(s1_total, s2_total, pass_mark: Decimal = PASS_MARK) -> tuple:
        """(المجموعُ السنويّ، الحالة) من مجموعَي الفصلين — الحسابُ القديمُ نفسُه للمسارين.

        عتبةُ النجاح `pass_mark` من `AnnualSubjectResult.pass_grade` للصفّ لا ثابتٌ في الشيفرة."""
        # نحسب السنوي فقط لو عندنا نتيجة واحدة على الأقل
        if s1_total is None and s2_total is None:
            return None, "incomplete"
        annual_total = ((s1_total or Decimal("0")) + (s2_total or Decimal("0"))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if s1_total is None or s2_total is None:
            return annual_total, "incomplete"
        return annual_total, ("pass" if annual_total >= pass_mark else "fail")

    @staticmethod
    def _grade_from_post(
        post: Any,
        sid: str,
        current: StudentAssessmentGrade | None,
        is_absent: bool,
        notes: str,
    ) -> tuple[Decimal | None, bool]:
        """(الدرجة، تخطٍّ؟) لصفٍّ واحد من نموذج الحفظ الجماعيّ — منطقُ التخطّي الدفاعيّ."""
        if is_absent:
            return None, False
        grade = None
        if f"grade_{sid}" in post:
            raw = post[f"grade_{sid}"].strip()
            if raw:
                try:
                    grade = Decimal(raw)
                    if not grade.is_finite():  # «nan» و«inf» يُقبلان decimal فيسقط الحفظُ بـ500
                        raise ValueError(raw)
                except (ValueError, TypeError, ArithmeticError) as e:
                    logger.warning("فشل تحويل درجة الطالب %s إلى Decimal: %r — %s", sid, raw, e)
                    return None, True
            # raw فارغ مع وجود المفتاح = مسحٌ صريحٌ من المستخدم (grade=None)
        elif current is not None:
            grade = current.grade  # المفتاحُ غائبٌ: أبقِ الدرجةَ المحفوظة
        # صفٌّ فارغٌ بلا سجلٍّ سابق: لا تُنشئ سجلاً خاوياً
        return grade, grade is None and current is None and not notes.strip()

    @staticmethod
    def save_all_from_post(assessment: Assessment, post: Any, entered_by: CustomUser | None) -> int:
        """حفظ كل درجات تقييمٍ دفعةً واحدة من POST، ثمّ إعادة الحساب مرّةً وتحديث الحالة.

        صفٌّ لم يُرسَل منه شيءٌ لا يُلمس أبداً — الغيابُ ليس «مسحاً». يُرجع عددَ المحفوظ.
        المحرّكُ مطفأ (الافتراضيّ): كتابةٌ دفعيّةٌ بعددِ استعلاماتٍ ثابت؛ ومرفوعاً: المسارُ الصفّيّ."""
        if verdict_engine_enabled():
            return GradeService._save_all_rowwise(assessment, post, entered_by)
        return GradeService._save_all_batched(assessment, post, entered_by)

    @staticmethod
    @transaction.atomic
    def _save_all_batched(assessment: Assessment, post: Any, entered_by: CustomUser | None) -> int:
        """نفسُ حكم `save_grade` لكلّ صفّ (قصُّ الدرجة على [0، الأقصى]، العذرُ المقرَّر مقفل) لكنّ الصفوف
        القائمةَ تُقفل وتُجلب دفعةً وتُكتب بـ`bulk_create`/`bulk_update`، وأثرُ التدقيق صفٌّ بصفٍّ دفعةً."""
        enrollments = list(
            StudentEnrollment.objects.filter(
                class_group=assessment.class_group, is_active=True
            ).select_related("student")
        )
        existing = {
            g.student_id: g
            for g in StudentAssessmentGrade.objects.select_for_update().filter(
                assessment=assessment
            )
        }
        now = timezone.now()
        to_create: list = []
        to_update: list = []
        for enr in enrollments:
            sid = str(enr.student.id)
            if not any(f"{p}{sid}" in post for p in _ROW_KEYS):
                continue
            current = existing.get(enr.student.id)
            is_absent = post.get(f"absent_{sid}") == "1"
            if current is not None and current.is_excused:
                continue  # عذرٌ مقرَّر: الصفُّ مقفلٌ على راصد الدرجات
            notes = post.get(f"notes_{sid}", "")
            grade, skip = GradeService._grade_from_post(post, sid, current, is_absent, notes)
            if skip:
                continue
            if grade is not None:
                grade = max(Decimal("0"), min(Decimal(str(grade)), assessment.max_grade))
            if current is not None:
                current.school = assessment.school
                current.grade = grade
                current.is_absent = is_absent
                current.notes = notes
                current.entered_by = entered_by
                current.entered_at = now
                to_update.append(current)
            else:
                to_create.append(
                    StudentAssessmentGrade(
                        assessment=assessment,
                        student=enr.student,
                        school=assessment.school,
                        grade=grade,
                        is_absent=is_absent,
                        is_excused=False,
                        notes=notes,
                        entered_by=entered_by,
                    )
                )
        StudentAssessmentGrade.objects.bulk_create(to_create)
        if to_update:
            StudentAssessmentGrade.objects.bulk_update(to_update, list(_GRADE_WRITE_FIELDS))
        make_audit = _audit_row_factory()
        audit_rows = []
        for created, rows in ((True, to_create), (False, to_update)):
            audit_rows += [
                make_audit(
                    "StudentAssessmentGrade", r, created, {"grade": str(getattr(r, "grade", ""))}
                )
                for r in rows
            ]
        _bulk_audit(audit_rows)
        # [PERF-02] إعادة حساب الفصل كاملاً مرة واحدة (batch) بدل مرة لكل طالب
        GradeService.recalculate_full_class(
            assessment.package.setup, students=[enr.student for enr in enrollments]
        )
        assessment.status = "graded"
        assessment.save(update_fields=["status"])
        return len(to_create) + len(to_update)

    @staticmethod
    def _save_all_rowwise(assessment: Assessment, post: Any, entered_by: CustomUser | None) -> int:
        """المسارُ الصفّيُّ (محرّكُ الحكم مرفوع): `save_grade` لكلّ صفّ ثمّ إعادةُ حسابٍ واحدة.

        صفٌّ لم يُرسَل منه شيءٌ لا يُلمس أبداً — الغيابُ ليس «مسحاً». يُرجع عددَ المحفوظ."""
        ensure_assessment_open(assessment)  # وإلا أعاد آخرُ السطور حالتَه «graded» فيفتح المغلق
        enrollments = StudentEnrollment.objects.filter(
            class_group=assessment.class_group, is_active=True
        ).select_related("student")
        existing = {
            g.student_id: g for g in StudentAssessmentGrade.objects.filter(assessment=assessment)
        }
        saved = 0
        for enr in enrollments:
            sid = str(enr.student.id)
            if not any(f"{p}{sid}" in post for p in _ROW_KEYS):
                continue
            current = existing.get(enr.student.id)
            is_absent = post.get(f"absent_{sid}") == "1"
            if current is not None and current.is_excused:
                continue  # عذرٌ مقرَّر: الصفُّ مقفلٌ على راصد الدرجات
            notes = post.get(f"notes_{sid}", "")
            grade, skip = GradeService._grade_from_post(post, sid, current, is_absent, notes)
            if skip:
                continue
            GradeService.save_grade(
                assessment=assessment,
                student=enr.student,
                grade=grade,
                is_absent=is_absent,
                notes=notes,
                entered_by=entered_by,
                recalc=False,  # [PERF-02] يُعاد الحساب دفعةً واحدة بعد الحلقة
            )
            saved += 1
        # [PERF-02] إعادة حساب الفصل كاملاً مرة واحدة (batch) بدل مرة لكل طالب
        GradeService.recalculate_full_class(assessment.package.setup)
        assessment.status = "graded"
        assessment.save(update_fields=["status"])
        return saved

    @staticmethod
    def recalculate_full_class(
        setup: SubjectClassSetup,
        actor: CustomUser | None = None,
        students: list | None = None,
    ) -> None:
        """إعادة حساب كامل — كل طلاب الفصل، كلا الفصلين، والسنوي.
        [PERF-01] يستخدم calc_package_scores_batch (استعلام واحد للدرجات لكل فصل) بدل
        الحساب لكل طالب × باقة — نفس النتائج بعدد استعلامات ثابت مهما زاد عدد الطلاب.

        بمحرّك الحكم الواحد (راية `VERDICT_ENGINE_ENABLED`): الحكمُ على كلّ طلبة الشعبة في
        موادّها كلِّها لأنّه عابرٌ للموادّ، بسجلّ مراجعةٍ بما تغيّر."""
        if verdict_engine_enabled():
            ensure_open_year(setup)
            VerdictEngine.recalculate_students(
                setup.class_group,
                setup.academic_year,
                VerdictEngine.class_students(setup.class_group),
                setup,
                actor=actor,
                trigger=f"recalculate_full_class:{setup.pk}",
            )
            return
        if students is None:  # المستدعي الذي جلب طلبةَ الشعبة لتوّه يمرّرهم فلا يُجلبون ثانيةً
            students = [
                e.student
                for e in StudentEnrollment.objects.filter(
                    class_group=setup.class_group, is_active=True
                ).select_related("student")
            ]
        if not students:
            return

        GradeService._recalculate_class_batched(setup, students)

    @staticmethod
    @transaction.atomic
    def _recalculate_class_batched(setup: SubjectClassSetup, students: list) -> None:
        """المسارُ القديم (المحرّكُ مطفأ) بعددِ استعلاماتٍ ثابت: الصفوفُ القائمةُ تُجلب وتُقفل دفعةً،
        وتُكتب بـ`bulk_create`/`bulk_update`، وأثرُ التدقيق صفٌّ بصفٍّ بمحتوى الإشارة نفسِه (`_bulk_audit`)."""
        # قفلٌ واحدٌ على إسناد المادّة قبل قراءة أيّ درجة: حفظان متزامنان لشعبةٍ واحدة يتسلسلان،
        # فلا يحسب أحدُهما من درجاتٍ سبقه الآخر بتعديلها (كان القفلُ لكلّ طالبٍ في المسار المفرد).
        list(SubjectClassSetup.objects.select_for_update().filter(pk=setup.pk).values_list("pk"))
        student_ids = [s.id for s in students]
        quantum = Decimal("0.01")
        totals: dict = {"S1": {}, "S2": {}}
        audit_rows: list = []
        make_audit = _audit_row_factory()
        now = timezone.now()

        # باقاتُ الفصلين وتقييماتُها المنشورة دفعةً واحدة بدل استعلامٍ لكلّ فصلٍ وباقة
        all_packages = list(AssessmentPackage.objects.filter(setup=setup, is_active=True))
        assessments_by_package: dict = {pkg.pk: [] for pkg in all_packages}
        for assessment in Assessment.objects.filter(
            package__in=all_packages, status__in=["published", "graded", "closed"]
        ):
            assessments_by_package[assessment.package_id].append(assessment)

        for sem in ("S1", "S2"):
            packages = [pkg for pkg in all_packages if pkg.semester == sem]
            batch = GradeService.calc_package_scores_batch(
                student_ids, packages, assessments_by_package
            )
            existing = {
                r.student_id: r
                for r in StudentSubjectResult.objects.select_for_update().filter(
                    setup=setup, semester=sem, student_id__in=student_ids
                )
            }
            to_create: list = []
            to_update: list = []
            for student in students:
                scores = {
                    pkg.package_type: batch.get((student.id, pkg.package_type)) for pkg in packages
                }
                defaults = GradeService._semester_defaults(setup, sem, packages, scores)
                row = existing.get(student.id)
                if row is None:
                    row = StudentSubjectResult(
                        student=student, setup=setup, semester=sem, **defaults
                    )
                    to_create.append(row)
                else:
                    for attr, val in defaults.items():
                        setattr(row, attr, val)
                    row.updated_at = now
                    to_update.append(row)
                # كما يقرؤه المسارُ المفرد من القاعدة: numeric(5,2) يقرّب نصفاً للأعلى
                total = defaults["total"]
                totals[sem][student.id] = (
                    total.quantize(quantum, rounding=ROUND_HALF_UP) if total is not None else None
                )
            StudentSubjectResult.objects.bulk_create(to_create)
            if to_update:
                StudentSubjectResult.objects.bulk_update(
                    to_update, [*_SEMESTER_WRITE_FIELDS, "updated_at"]
                )
            for created, rows in ((True, to_create), (False, to_update)):
                audit_rows += [
                    make_audit("StudentSubjectResult", r, created, _subject_result_changes(r))
                    for r in rows
                ]

        year = setup.academic_year
        existing_annual = {
            a.student_id: a
            for a in AnnualSubjectResult.objects.select_for_update().filter(
                setup=setup, academic_year=year, student_id__in=student_ids
            )
        }
        annual_create: list = []
        annual_update: list = []
        for student in students:
            s1_total = totals["S1"][student.id]
            s2_total = totals["S2"][student.id]
            row = existing_annual.get(student.id)
            annual_total, status = GradeService._annual_values(
                s1_total, s2_total, row.pass_grade if row else PASS_MARK
            )
            values = {
                "school": setup.school,
                "s1_total": s1_total,
                "s2_total": s2_total,
                "annual_total": annual_total,
                "status": status,
            }
            if row is None:
                annual_create.append(
                    AnnualSubjectResult(student=student, setup=setup, academic_year=year, **values)
                )
            else:
                for attr, val in values.items():
                    setattr(row, attr, val)
                row.updated_at = now
                annual_update.append(row)
        AnnualSubjectResult.objects.bulk_create(annual_create)
        if annual_update:
            AnnualSubjectResult.objects.bulk_update(
                annual_update, [*_ANNUAL_WRITE_FIELDS, "updated_at"]
            )
        _bulk_audit(audit_rows)

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
            passed=Count("id", filter=Q(status__in=passing_statuses())),
            failed=Count("id", filter=Q(status__in=failing_statuses())),
            incomplete=Count("id", filter=Q(status__in=pending_statuses())),
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
            AnnualSubjectResult.objects.filter(
                school=school, academic_year=year, status__in=failing_statuses()
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
            AnnualSubjectResult.objects.filter(school=school, academic_year=year)
            .values("setup__subject__name_ar")
            .annotate(
                avg=Avg("annual_total"),
                fail_count=Count("id", filter=Q(status__in=failing_statuses())),
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
