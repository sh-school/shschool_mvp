"""[STAFF] المغادرةُ تاريخٌ لا محو — من كان هنا أمس كان هنا.

كان في `Membership` تاريخُ التحاقٍ بلا نظير، وبوليانٌ واحدٌ `is_active`. فمن
نُقل إلى مدرسةٍ أخرى لا يُقال عنه إلّا «غيرُ نشط» — وذلك يمحو السؤالَ لا
يجيبه:

    هل كان في كادر 2025-2026؟   نعم
    هل هو في كادر 2026-2027؟    لا

وبوليانٌ واحدٌ لا يحمل الجوابين معاً. وثمانيةٌ من معلّمي الشحانية نُقلوا فبقوا
في القوائم بأصفارٍ في كلّ عمود، وأحدُهم له خمسٌ وعشرون حصّةً في تاريخ العام
الماضي — فمحوُ عضويّته يقطع تلك الحصص عن صاحبها.

فصار للمغادرة تاريخُها وسببُها ومرجعُها، و`is_active` يُطفأ معها: فكلُّ
استعلامٍ قائمٍ يسأل عن النشطين — واثنان ومئةُ موضعٍ في المستودع — يصير صحيحاً
بلا تعديلِ سطرٍ فيه، ويبقى التاريخُ محفوظاً لمن يسأل عنه.
"""

from datetime import date

import pytest

from core.models import Membership
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

JOINED = date(2025, 9, 1)
LEFT = date(2026, 8, 1)


@pytest.fixture
def member(school):
    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(full_name="معلّمٌ منقول")
    return MembershipFactory(user=user, school=school, role=role, joined_at=JOINED)


# ── التسجيل ──────────────────────────────────────────────────────────


def test_recording_a_departure_stamps_the_date_and_stands_him_down(member):
    member.record_departure(
        on=LEFT, reason="transfer", reference="قرار نقل 44", note="نُقل إلى مدرسةٍ أخرى"
    )

    member.refresh_from_db()
    assert member.left_at == LEFT
    assert member.is_active is False, "فيخرج من كلّ استعلامٍ يسأل عن النشطين"
    assert (member.departure_reason, member.departure_reference) == ("transfer", "قرار نقل 44")


def test_a_departure_without_a_reference_is_refused(member):
    """النقلُ قرارٌ إداريّ — كالتفريغ وكالنصاب، لا يُقبل بلا مرجع."""
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        member.record_departure(on=LEFT, reason="transfer", reference="")


def test_a_departure_before_joining_is_refused(member):
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        member.record_departure(on=date(2000, 1, 1), reason="transfer", reference="قرار 1")


# ── السؤالُ عن زمنٍ بعينه ────────────────────────────────────────────


def test_he_was_here_before_he_left(member):
    """وهذا هو بيتُ القصيد: الماضي يبقى صادقاً."""
    member.record_departure(on=LEFT, reason="transfer", reference="قرار نقل 44")

    assert member.was_member_on(date(2026, 5, 1)) is True
    assert member.was_member_on(LEFT) is False, "يومُ المغادرة أوّلُ أيّام الغياب"
    assert member.was_member_on(date(2026, 9, 1)) is False


def test_a_standing_member_is_here_today_and_was_here_yesterday(member):
    assert member.left_at is None
    assert member.was_member_on(date(2026, 9, 1)) is True


def test_the_queryset_separates_the_present_from_the_departed(school, member):
    role = RoleFactory(school=school, name="teacher")
    staying = MembershipFactory(
        user=UserFactory(full_name="معلّمٌ باقٍ"), school=school, role=role, joined_at=JOINED
    )
    member.record_departure(on=LEFT, reason="transfer", reference="قرار نقل 44")

    current = set(Membership.objects.current().values_list("pk", flat=True))

    assert staying.pk in current
    assert member.pk not in current

    past = set(Membership.objects.active_on(date(2026, 5, 1)).values_list("pk", flat=True))
    assert member.pk in past, "وكان في الكادر يومَها"
