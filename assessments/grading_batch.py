"""الكتابةُ الدفعيّةُ للدرجات ونتائجِ الفصل والسنة (W-20261101-008).

استُخرجت من `services.py` لتبقى الخدمةُ دون الحدّ؛ `GradeService` يفوّض إليها. المسارُ الصفّيُّ
(`save_grade`) باقٍ مرجعاً، ويثبّت `tests/test_hot_paths_queries_w008.py` تساويَ المخرجات وأثرِ التدقيق.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

from core.domain.grades import PASS_MARK
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
    from core.models import CustomUser

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


@transaction.atomic
def save_all_batched(assessment: Assessment, post: Any, entered_by: CustomUser | None) -> int:
    """نفسُ حكم `save_grade` لكلّ صفّ (قصُّ الدرجة على [0، الأقصى]، العذرُ المقرَّر مقفل) لكنّ الصفوف
    القائمةَ تُقفل وتُجلب دفعةً وتُكتب بـ`bulk_create`/`bulk_update`، وأثرُ التدقيق صفٌّ بصفٍّ دفعةً."""
    from .services import GradeService

    enrollments = list(
        StudentEnrollment.objects.filter(
            class_group=assessment.class_group, is_active=True
        ).select_related("student")
    )
    existing = {
        g.student_id: g
        for g in StudentAssessmentGrade.objects.select_for_update().filter(assessment=assessment)
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


@transaction.atomic
def recalculate_class_batched(setup: SubjectClassSetup, students: list) -> None:
    """المسارُ القديم (المحرّكُ مطفأ) بعددِ استعلاماتٍ ثابت: الصفوفُ القائمةُ تُجلب وتُقفل دفعةً،
    وتُكتب بـ`bulk_create`/`bulk_update`، وأثرُ التدقيق صفٌّ بصفٍّ بمحتوى الإشارة نفسِه (`_bulk_audit`)."""
    from .services import GradeService

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
                row = StudentSubjectResult(student=student, setup=setup, semester=sem, **defaults)
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
