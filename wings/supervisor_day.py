"""غيابُ اليوم في لوحة مشرف الجناح وبديله (W-20261008-00x، D-249م القسم 8 وD-251م).

**المُجمِّعُ نفسُه** (`operations/day_selectors.py`) لا استعلاماتٌ ثانية: الملخّصُ المخزَّنُ للمدرسة كلِّها 20 ث في الذاكرة المشتركة يُقتطع هنا لأجنحة
المستخدم وحدَها بعد القراءة. والجناحُ من `wings_of(user)` لا من الطلب. أرقامٌ بلا أسماءِ طلبة (D-171م). وبديلُ الجناح يصل هنا بالدالّة نفسِها:
فلا مواصفةَ ثانيةً ولا لوحةً ثانية، وتنتهي لوحتُه بانتهاء تكليفه (`wings_of` ترجع فارغةً).
"""

from __future__ import annotations

import datetime as dt
from typing import Any


def supervisor_day_payload(user: Any, school: Any, day: dt.date) -> dict[str, Any] | None:
    """حمولةُ المشرف لأجنحته اليوم، أو `None` لمن لا يحمل جناحاً (بديلٌ انتهى تكليفُه) أو حاصرٍ عامٍّ لا لوحةَ أجنحةٍ له."""
    from core.academic_calendar import academic_year_for_school
    from operations.day_selectors import live_payload, scope_to_wings
    from wings.services import holds_school_wide, wings_of

    if holds_school_wide(user):
        return None
    wings = wings_of(user, school, academic_year_for_school(school))
    if not wings:
        return None
    return scope_to_wings(live_payload(school, day), {str(wing.id) for wing in wings})


def supervisor_day_section(user: Any, school: Any, today: dt.date) -> dict[str, Any]:
    """قسمُ «sup_day» في سياق لوحة المشرف — يسجّله `WingsConfig.ready` فلا تستورد النواةُ هذه الوحدة (سقّاطةُ الطبقات)."""
    payload = supervisor_day_payload(user, school, today)
    if payload is None:
        return {}
    return {
        "sup_day": payload,
        "sup_final": payload["phase"] == "final",
        "sup_open": payload["phase"] != "closed",
        # حالةُ كلّ شعبةٍ بمعرّفها: تقرؤها رقاقةُ الشعبة في لوح الجناح (`record_panel.html`) فلا جدولَ مكرَّراً (D-16: مصدرٌ واحدٌ للشعبة).
        "sup_sections": {row["id"]: row for row in payload["sections"]},
    }
