"""[CORE] عددُ الطلاب المعروض في صفحة الاستيراد/التصدير — مقيَّدٌ بعامٍ لا بالدهر.

بلاغُ المالك 2026-10-01: الرقمُ ٨٩٢ «مضلِّل». السببُ: `count_active_students`
تعدّ `Membership.is_active` بلا بُعد عام — وقيدٌ قديمٌ لم تُغلق عضويّتُه صراحةً
يبقى محسوباً إلى الأبد. والعدّ الصحيح `StudentEnrollment` مقيَّداً بشعبةٍ من
العام نفسِه، لأنّ الطالب يحمل قيداً نشطاً واحداً لكلّ عامٍ شارك فيه معاً.
"""

import pytest

from core.models import ClassGroup
from core.services import count_active_students, count_students_enrolled_in_year
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory

THIS_YEAR = "2026-2027"
LAST_YEAR = "2025-2026"


@pytest.mark.django_db
def test_a_student_enrolled_only_last_year_is_not_counted_this_year(school):
    group = ClassGroupFactory(school=school, academic_year=LAST_YEAR)
    StudentEnrollmentFactory(class_group=group, student=UserFactory())

    assert count_students_enrolled_in_year(school, THIS_YEAR) == 0
    assert count_students_enrolled_in_year(school, LAST_YEAR) == 1


@pytest.mark.django_db
def test_a_student_with_two_years_of_active_enrollment_counts_once_per_year(school):
    """القيدُ القديمُ لا يُغلق عند بداية العام — فيحمل الطالبُ قيدَين نشطَين معاً."""
    student = UserFactory()
    old_group = ClassGroupFactory(school=school, academic_year=LAST_YEAR, grade="G8")
    new_group = ClassGroupFactory(school=school, academic_year=THIS_YEAR, grade="G9")
    StudentEnrollmentFactory(class_group=old_group, student=student, is_active=True)
    StudentEnrollmentFactory(class_group=new_group, student=student, is_active=True)

    assert count_students_enrolled_in_year(school, THIS_YEAR) == 1
    assert count_students_enrolled_in_year(school, LAST_YEAR) == 1


@pytest.mark.django_db
def test_an_inactive_enrollment_this_year_is_not_counted(school):
    group = ClassGroupFactory(school=school, academic_year=THIS_YEAR)
    StudentEnrollmentFactory(class_group=group, student=UserFactory(), is_active=False)

    assert count_students_enrolled_in_year(school, THIS_YEAR) == 0


@pytest.mark.django_db
def test_two_students_in_the_same_class_group_count_separately(school):
    group = ClassGroupFactory(school=school, academic_year=THIS_YEAR)
    StudentEnrollmentFactory(class_group=group, student=UserFactory())
    StudentEnrollmentFactory(class_group=group, student=UserFactory())

    assert count_students_enrolled_in_year(school, THIS_YEAR) == 2


@pytest.mark.django_db
def test_without_a_year_or_school_the_count_is_zero_not_an_error(school):
    assert count_students_enrolled_in_year(None, THIS_YEAR) == 0
    assert count_students_enrolled_in_year(school, "") == 0


@pytest.mark.django_db
def test_the_old_count_is_the_misleading_one_the_new_count_fixes(school):
    """المقارنةُ المباشرة: نفسُ المعطى، رقمان مختلفان — هذا هو عينُ البلاغ."""
    student = UserFactory()
    old_group = ClassGroupFactory(school=school, academic_year=LAST_YEAR)
    StudentEnrollmentFactory(class_group=old_group, student=student)
    # عضويّةُ الطالب (لا قيدُه) لم تُغلق صراحةً — ما زال `is_active=True` فيها.
    from core.models.access import Membership, Role

    role, _ = Role.objects.get_or_create(school=school, name="student")
    Membership.objects.create(user=student, school=school, role=role, is_active=True)

    assert count_active_students(school) == 1, "القديمُ يعدّ طالبَ العام الماضي"
    assert count_students_enrolled_in_year(school, THIS_YEAR) == 0, "الجديدُ لا يعدّه"


def test_class_group_field_still_named_academic_year():
    """حارسٌ ساذج: لو تغيّر اسمُ الحقل يفشل هذا قبل أن يفشل الاستعلامُ صامتاً بنتيجةٍ فارغة."""
    assert "academic_year" in [f.name for f in ClassGroup._meta.get_fields()]
