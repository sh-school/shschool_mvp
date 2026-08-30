"""[SECURITY] دورُ مطوّر المنصّة يعمل بذاته لا بصفةٍ أخرى.

`platform_developer` كان خارج `ALL_STAFF_ROLES`، فيُردّ صاحبُه عن لوحة
التحكّم نفسها: «ليس لديك صلاحية الوصول — دورك: platform_developer».

ولم يظهر ذلك لأنّ حساب المطوّر `superuser`، و`role_required` يُمرّر
الـsuperuser دائماً — فالدور معطَّلٌ في ذاته ويعمل بصفةٍ أخرى. وظهر حين
حمل حسابٌ غيرُ superuser هذا الدور.

والصفتان يجب أن تفترقا: من يملك مفاتيح النظام شيء، ومن دورُه في المدرسة
«مطوّر المنصّة» شيءٌ آخر.
"""

import pytest

from core.models import CustomUser
from core.models.access import (
    ALL_STAFF_ROLES,
    TIER_5_BENEFICIARIES,
    TIER_SYSTEM,
    Membership,
    Role,
)


def test_the_developer_role_counts_as_staff():
    assert TIER_SYSTEM <= ALL_STAFF_ROLES


@pytest.mark.parametrize("role", sorted(TIER_5_BENEFICIARIES))
def test_beneficiaries_are_not_staff(role):
    """الطالب ووليّ الأمر خارجها — وإلّا فتح توسيعُها بابهما على الطاقم."""
    assert role not in ALL_STAFF_ROLES


@pytest.mark.django_db
def test_a_developer_who_is_not_a_superuser_reaches_the_dashboard(client, school):
    """الدعوى على الشاشة: حسابٌ بدور المطوّر وحده — بلا مفاتيح النظام."""
    user = CustomUser.objects.create(national_id="28700000001", full_name="مطوّر")
    user.set_password("Aa!23456789")
    user.save()
    role, _ = Role.objects.get_or_create(school=school, name="platform_developer")
    Membership.objects.create(user=user, school=school, role=role)
    client.force_login(user)

    resp = client.get("/dashboard/")

    assert resp.status_code != 403, "الدور يعمل بذاته لا بصفة superuser"
