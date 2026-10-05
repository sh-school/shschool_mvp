"""قراءاتُ شؤون الموظفين — بلا ORM في العروض (سقّاطة الطبقات)."""

from __future__ import annotations

from core.models.access import Membership
from core.phone_search import MIN_PHONE_DIGITS, phone_holder_ids  # noqa: F401  (يُعاد تصديرُهما)

#: أدوارٌ ليست كادراً: الطالبُ ووليُّ الأمر لهما عضويّةٌ في المدرسة ولا يظهران في سجلّ الكادر.
NON_STAFF_ROLES = ("student", "parent")


def staff_memberships(school, *, departed: bool = False):
    """عضويّاتُ الكادر: النشطةُ، أو — لـ«المغادرين» — المنتهيةُ لمن لا عضويّةَ كادرٍ نشطةً له.

    «المغادر» من لا يعمل الآن، لا من له صفٌّ منتهٍ قديم: من غادر ثمّ أُعيد تعيينُه (أو عُطّلت له
    عضويّةٌ قديمة) على رأس عمله ولا يُعدّ مغادراً (W-20261002-043).
    """
    staff = Membership.objects.filter(school=school).exclude(role__name__in=NON_STAFF_ROLES)
    if not departed:
        return staff.filter(is_active=True)
    return staff.filter(is_active=False).exclude(
        user_id__in=staff.filter(is_active=True).values("user_id")
    )


def active_staff_memberships(user, school):
    """عضويّاتُ الكادر النشطةُ لشخصٍ في مدرسة — لمغادرةٍ بدورٍ محدَّد."""
    return (
        Membership.objects.filter(user=user, school=school, is_active=True)
        .exclude(role__name__in=NON_STAFF_ROLES)
        .select_related("role")
    )
