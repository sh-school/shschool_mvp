"""قراءاتُ شؤون الموظفين — بلا ORM في العروض (سقّاطة الطبقات)."""

from __future__ import annotations

import re
from collections.abc import Iterable

from core.models.access import Membership
from core.models.crypto import decrypt_field

#: أقلُّ عددٍ من الأرقام يُفعِّل البحثَ بالهاتف — دونه اسمٌ أو رقمٌ وظيفيّ لا جوّال،
#: ولا يستأهل فكَّ الأرقام كلِّها.
MIN_PHONE_DIGITS = 4


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


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def phone_holder_ids(people, term: str) -> Iterable:
    """معرّفاتُ من يحوي جوّالُه الأرقامَ المكتوبة في البحث.

    الجوّالُ مخزَّنٌ مشفَّراً، فلا `icontains` عليه في القاعدة. والقائمةُ في نطاق
    مدرسةٍ واحدة (بضع مئاتٍ على الأكثر)، فيُفكّ التشفيرُ ويُطابَق في الذاكرة —
    على الأرقام وحدَها كي لا تفرّق المسافةُ ولا الرمزُ `+` بين `55001122`
    و`+974 5500 1122`.
    """
    wanted = _digits(term)
    if len(wanted) < MIN_PHONE_DIGITS:
        return []
    rows = people.exclude(phone_encrypted="").order_by().values_list("pk", "phone_encrypted")
    return [pk for pk, encrypted in rows if wanted in _digits(decrypt_field(encrypted))]
