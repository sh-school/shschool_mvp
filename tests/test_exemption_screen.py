"""[SCHEDULE] شاشةُ التفريغات: التفريغُ غيابٌ، والقيدُ الدائمُ صفةٌ لازمة.

    «لا أولى ولا سابعة» ليس تفريغاً.

التفريغُ غيابٌ لسببٍ خارجيٍّ له مرجعٌ وتاريخ — دورةٌ في الوزارة، أو اجتماعُ
منسّقين. والمنعُ الدائمُ صفةٌ لازمةٌ لصاحبها لا تنقضي. وقد سكن الاثنان جدولاً
واحداً لأنّ المولّدَ لا يقرأ غيرَه، فامتلأت شاشةُ «تفريغات المعلمين» بعشرة
صفوفٍ لرجلٍ واحدٍ ليس مفرَّغاً في شيء.

فصارت الشاشةُ تعرض التفريغاتِ وحدَها، ويبقى أثرُ القيد في الجدول كاملاً:
`TeacherExemption.objects` هي مصدرُ المولّد، ولم يُمَسّ.
"""

import pytest

from operations.models import TeacherExemption
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


def exempt(school, teacher, *, day, period, reason):
    return TeacherExemption.objects.create(
        school=school,
        teacher=teacher,
        academic_year=YEAR,
        exemption_type="specific_period",
        day_of_week=day,
        period_number=period,
        reason=reason,
        source="school",
        is_active=True,
    )


@pytest.fixture
def teacher(school):
    user = UserFactory(full_name="معلّمٌ مقيَّد")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


def test_a_personal_rule_is_not_listed_as_a_release(school, teacher):
    exempt(school, teacher, day=0, period=1, reason="قرار إدارة المدرسة — لا أولى ولا سابعة")

    assert TeacherExemption.objects.count() == 1
    assert TeacherExemption.objects.releases().count() == 0


def test_a_real_release_is_still_listed(school, teacher):
    exempt(school, teacher, day=0, period=1, reason="اجتماعُ منسّقي المواد بالنائب الأكاديميّ")

    assert TeacherExemption.objects.releases().count() == 1


def test_the_generator_still_sees_the_personal_rule(school, teacher):
    """الحاسمُ: الإخفاءُ من الشاشة لا يرفع القيدَ عن الجدول."""
    row = exempt(school, teacher, day=0, period=7, reason="قرار إدارة المدرسة — لا أولى ولا سابعة")

    #: `objects` بلا `releases()` هو ما يقرؤه المولّد.
    assert row in TeacherExemption.objects.filter(school=school, academic_year=YEAR)
