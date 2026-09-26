"""قراءاتُ شؤون الموظفين — بلا ORM في العروض (سقّاطة الطبقات)."""

from __future__ import annotations

import re
from collections.abc import Iterable

from core.models.crypto import decrypt_field

#: أقلُّ عددٍ من الأرقام يُفعِّل البحثَ بالهاتف — دونه اسمٌ أو رقمٌ وظيفيّ لا جوّال،
#: ولا يستأهل فكَّ الأرقام كلِّها.
MIN_PHONE_DIGITS = 4


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
