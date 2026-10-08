"""البحثُ بالهاتف والعمودُ الصريحُ — حتّى لا تحتاج الشاشاتُ إلى `phone` الخام (PDPPL، المرحلة 1 من محو العمود).

الجوّالُ مخزَّنٌ في ثلاثة أعمدة (`phone` صريحٌ و`phone_encrypted` و`phone_hmac`)، والصريحُ لا يُقرأ منه ولا يُبحث فيه
بعد اليوم: القراءةُ بـ`CustomUser.get_phone_decrypted()`، والبحثُ هنا. فحين يُفرَّغ الصريحُ في المرحلة 2
(`docs/privacy/pdppl_audit_2026-10-05.md`) لا تنكسر شاشةٌ.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from core.models.crypto import decrypt_field

#: أقلُّ عددٍ من الأرقام يُفعِّل البحثَ بالهاتف — دونه اسمٌ أو رقمٌ وظيفيّ لا جوّال،
#: ولا يستأهل فكَّ الأرقام كلِّها.
MIN_PHONE_DIGITS = 4


def digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def phone_holder_ids(people: Any, term: str) -> Iterable:
    """معرّفاتُ من يحوي جوّالُه الأرقامَ المكتوبة في البحث.

    الجوّالُ مخزَّنٌ مشفَّراً، فلا `icontains` عليه في القاعدة. والقائمةُ في نطاق
    مدرسةٍ واحدة (بضع مئاتٍ على الأكثر)، فيُفكّ التشفيرُ ويُطابَق في الذاكرة —
    على الأرقام وحدَها كي لا تفرّق المسافةُ ولا الرمزُ `+` بين `55001122`
    و`+974 5500 1122`. ومن لا نسخةَ مشفَّرةَ له بعدُ (صفٌّ قديمٌ لم يُحفظ) يُطابَق على الصريح.
    """
    wanted = digits(term)
    if len(wanted) < MIN_PHONE_DIGITS:
        return []
    rows = people.order_by().values_list("pk", "phone_encrypted", "phone")
    return [
        pk
        for pk, encrypted, plain in rows
        if wanted in digits(decrypt_field(encrypted) if encrypted else plain)
    ]
