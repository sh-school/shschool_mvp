"""مجموعاتُ الحالات التي تقرؤها المستهلكات (`assessments/verdict_read.py`) — مطفأةً وموقدة.

مطفأةً (`VERDICT_ENGINE_ENABLED=False`) تطابق المجموعاتُ حالتَي `pass` و`fail` القديمتين حرفيّاً
فلا يتغيّر عدٌّ. وموقدةً تشمل «مُرفَّع» في النجاح، و«دورٌ ثانٍ» و«ملغي» في الرسوب، و«معذور» و«محروم»
و«الملحق» فيما لم يُحسم. والمستهلكاتُ كلُّها تقرؤها من هنا — فيُختبر عيّنةٌ منها بالعدّ.
"""

from __future__ import annotations

import pytest

from assessments.models import AnnualSubjectResult, SubjectClassSetup
from assessments.services import GradeService
from core.domain.grades import (
    FAILING_STATUSES,
    PASSING_STATUSES,
    PENDING_STATUSES,
    RESULT_STATUSES,
)
from core.verdict_read import (
    failing_statuses,
    passing_statuses,
    pending_statuses,
    result_statuses,
)
from operations.models import Subject
from parents.services import ParentService
from tests.conftest import ClassGroupFactory, UserFactory

pytestmark = pytest.mark.django_db

#: حالةٌ لكلّ طالبٍ في مادّةٍ واحدة.
STATUSES = ("pass", "promoted", "fail", "second_round", "cancelled", "incomplete", "excused")


def test_sets_match_the_legacy_ones_while_the_flag_is_off(settings):
    settings.VERDICT_ENGINE_ENABLED = False
    assert passing_statuses() == ("pass",)
    assert failing_statuses() == ("fail",)
    assert pending_statuses() == ("incomplete",)
    assert set(result_statuses()) == {"pass", "fail", "incomplete", "second_round"}


def test_sets_are_the_domain_ones_when_the_flag_is_on(settings):
    settings.VERDICT_ENGINE_ENABLED = True
    assert passing_statuses() == PASSING_STATUSES
    assert failing_statuses() == FAILING_STATUSES
    assert pending_statuses() == PENDING_STATUSES
    assert result_statuses() == RESULT_STATUSES


@pytest.fixture
def rows(school, seeded_calendar):
    """سبعةُ طلبةٍ في مادّةٍ واحدة، لكلٍّ حالةٌ من `STATUSES`."""
    teacher = UserFactory()
    group = ClassGroupFactory(school=school, grade="G8", academic_year=seeded_calendar)
    subject = Subject.objects.create(school=school, name_ar="مادة", code="VR1")
    setup = SubjectClassSetup.objects.create(
        school=school,
        subject=subject,
        class_group=group,
        teacher=teacher,
        academic_year=seeded_calendar,
    )
    students = []
    for status in STATUSES:
        student = UserFactory()
        AnnualSubjectResult.objects.create(
            student=student,
            setup=setup,
            school=school,
            academic_year=seeded_calendar,
            status=status,
        )
        students.append(student)
    return {"setup": setup, "school": school, "year": seeded_calendar, "students": students}


def test_class_summary_counts_legacy_statuses_only_while_off(rows, settings):
    settings.VERDICT_ENGINE_ENABLED = False
    summary = GradeService.get_class_results_summary(rows["setup"], rows["year"])
    assert (summary["passed"], summary["failed"], summary["incomplete"]) == (1, 1, 1)


def test_class_summary_uses_the_full_sets_when_on(rows, settings):
    settings.VERDICT_ENGINE_ENABLED = True
    summary = GradeService.get_class_results_summary(rows["setup"], rows["year"])
    assert summary["passed"] == 2  # pass + promoted
    assert summary["failed"] == 3  # fail + second_round + cancelled
    assert summary["incomplete"] == 2  # incomplete + excused


@pytest.mark.parametrize(("flag", "passed", "failed"), [(False, 1, 1), (True, 2, 3)])
def test_queryset_helpers_follow_the_flag(rows, settings, flag, passed, failed):
    settings.VERDICT_ENGINE_ENABLED = flag
    qs = AnnualSubjectResult.objects.filter(school=rows["school"])
    assert qs.passed().count() == passed
    assert qs.failed().count() == failed


def test_parent_grades_summary_follows_the_flag(rows, settings):
    student = rows["students"][1]  # مُرفَّع
    settings.VERDICT_ENGINE_ENABLED = False
    off = ParentService.get_student_grades(student, rows["school"], rows["year"])
    settings.VERDICT_ENGINE_ENABLED = True
    on = ParentService.get_student_grades(student, rows["school"], rows["year"])
    assert (off["passed"], off["failed"]) == (0, 0)  # حالةٌ لا تعرفها القراءةُ القديمة
    assert (on["passed"], on["failed"]) == (1, 0)
