"""[CORE] منسوبو المدرسة: صفٌّ واحدٌ لكلّ إنسانٍ مهما تعدّدت عضويّاته.

المنسّقُ الذي هو وليُّ أمرٍ أيضاً له عضويّتان في المدرسة نفسها. و`filter`
عبر العلاقة ضمٌّ لا ترشيح، فيعود صفَّين — فيصحّ العدُّ خطأً، ويرفع `get()`
استثناءَ «أكثرَ من واحد»:

    MultipleObjectsReturned: get() returned more than one CustomUser — it returned 2!

وقد أسقط هذا صفحةَ طباعة الجدول على معلّمٍ حقيقيّ: بنجر الدوسري، منسّقُ
التربية البدنية ووليُّ أمر. وستّةُ أشخاصٍ في المدرسة على حاله، فكان العدُّ
يقول 1513 والحقيقةُ 1507.

    `distinct()` تُخفي العلّةَ ولا تُزيلها — والترشيحُ باستعلامٍ داخليٍّ يُزيلها.
"""

import pytest

from core.models import CustomUser
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def double_member(school):
    """منسّقٌ هو وليُّ أمرٍ في المدرسة نفسها."""
    user = UserFactory(full_name="منسّقٌ ووليُّ أمر")
    for name in ("coordinator", "parent"):
        MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=name))
    return user


def test_a_person_with_two_memberships_appears_once(school, double_member):
    assert CustomUser.objects.in_school(school).filter(id=double_member.id).count() == 1


def test_get_does_not_raise_on_a_double_member(school, double_member):
    """هذا هو السطرُ الذي أسقط صفحةَ الطباعة."""
    assert CustomUser.objects.in_school(school).get(id=double_member.id) == double_member


def test_the_join_is_what_duplicated_them(school, double_member):
    """توثيقُ العلّة: الضمُّ القديمُ يعدّ الشخصَ مرّتين."""
    joined = CustomUser.objects.filter(
        memberships__school=school, memberships__is_active=True, id=double_member.id
    )

    assert joined.count() == 2
    assert CustomUser.objects.in_school(school).filter(id=double_member.id).count() == 1


def test_someone_elsewhere_is_not_counted(school, double_member):
    from tests.conftest import SchoolFactory

    other = SchoolFactory()

    assert CustomUser.objects.in_school(other).filter(id=double_member.id).count() == 0
