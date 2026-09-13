"""قيدُ الطالب القائم — الأحدثُ عاماً لا ما تُرجعه القاعدةُ أوّلاً.

الطالبُ يحمل قيدَين نشطَين معاً حين يبدأ عامٌ جديدٌ ولا يُغلق قيدُ الماضي:
القيدُ الفريدُ مفروضٌ على الزوج (طالب، شعبة) وهما شعبتان، فيمرّ. و`.first()`
بلا `order_by` تُرجع صفّاً عشوائيّاً يتقلّب مع ترتيب صفوف القاعدة.
"""

import pytest

from core.models import StudentEnrollment
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory

pytestmark = pytest.mark.django_db


def _two_years(school, student):
    """قيدان نشطان: العامُ الماضي والعامُ الجاري."""
    old = ClassGroupFactory(school=school, grade="G7", section="1", academic_year="2025-2026")
    new = ClassGroupFactory(school=school, grade="G8", section="4", academic_year="2026-2027")
    StudentEnrollmentFactory(student=student, class_group=old)
    StudentEnrollmentFactory(student=student, class_group=new)
    return old, new


def test_current_of_returns_the_newest_year(school, student_user):
    _, new = _two_years(school, student_user)

    assert StudentEnrollment.objects.current_of(student_user).class_group == new


def test_current_of_is_stable_whatever_the_row_order(school, student_user):
    """الترتيبُ في القاعدة يتقلّب — والجوابُ لا يتقلّب معه."""
    _, new = _two_years(school, student_user)

    seen = {StudentEnrollment.objects.current_of(student_user).class_group_id for _ in range(5)}
    assert seen == {new.id}


def test_current_of_ignores_inactive_enrollments(school, student_user):
    old, new = _two_years(school, student_user)
    StudentEnrollment.objects.filter(class_group=new).update(is_active=False)

    assert StudentEnrollment.objects.current_of(student_user).class_group == old


def test_current_of_scopes_to_school_when_asked(school, student_user, django_user_model):
    from tests.conftest import SchoolFactory

    other = SchoolFactory()
    mine = ClassGroupFactory(school=school, academic_year="2025-2026")
    theirs = ClassGroupFactory(school=other, academic_year="2026-2027")
    StudentEnrollmentFactory(student=student_user, class_group=mine)
    StudentEnrollmentFactory(student=student_user, class_group=theirs)

    assert StudentEnrollment.objects.current_of(student_user, school=school).class_group == mine
    assert StudentEnrollment.objects.current_of(student_user).class_group == theirs


def test_current_of_returns_none_without_enrollment(school, student_user):
    assert StudentEnrollment.objects.current_of(student_user) is None
