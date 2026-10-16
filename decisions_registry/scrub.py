"""حجبُ الأسماء والأرقام الشخصيّة من نصّ القرار قبل تخزينه (PDPPL) — W-20260928-019.

الأرقامُ والبريدُ تُحجب بالنمط. والأسماءُ لا نمطَ لها فتُحجب من قائمةٍ تُسلَّم مع الملف خارجَ git (`--names-file`)؛
قائمةٌ فارغةٌ تعني أن لا أسماءَ مُعرَّفةً للحجب، وتُبلَّغ في ناتج الاستيراد.
"""

from __future__ import annotations

import re

MASK = "[محجوب]"
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# رقمٌ شخصيٌّ أو هاتف: 8 خاناتٍ فأكثر متّصلة (يشمل الهويّة 11 خانة)، مع +974 اختياريّاً.
_LONG_NUMBER = re.compile(r"(?<![\w-])(?:\+?974[\s-]?)?\d{8,}(?![\w-])")


def mask_personal(text: str, names: tuple[str, ...] = ()) -> str:
    masked = _EMAIL.sub(MASK, text or "")
    masked = _LONG_NUMBER.sub(MASK, masked)
    for name in sorted({n.strip() for n in names if n and n.strip()}, key=len, reverse=True):
        masked = masked.replace(name, MASK)
    return masked
