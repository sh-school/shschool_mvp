"""DBT-11 — بريدٌ لا مزوّدَ له: يُوسَم `undeliverable` ولا يُعاد ولا يدخل DLQ ولا يبلغ Sentry، وحمولةُ DLQ قائمةٌ بيضاء.

تعريفُ المالك (2026-09-26): بريدٌ لا يُسلَّم في غياب مزوّدٍ فعليّ (`UndeliveredEmailBackend`) **ليس عطلاً**. فكان يمرّ في مسار
الأعطال كلِّه: `logger.error` ثمّ `logger.exception` (حدثان في Sentry) ثمّ ثلاثُ إعاداتٍ ثمّ صفُّ DLQ — لرسالةٍ لن تُسلَّم
مهما أُعيدت. والإعادةُ وDLQ وSentry لأعطال مزوّدٍ **حقيقيّ** وحدَها. والرسائلُ الموسومةُ لا تُعاد بعد شراء المزوّد (قرارُ المالك).

وقاعدةٌ ثانية هنا: حمولةُ DLQ **تشخيصٌ لا محتوى** — معرّفاتٌ ونوعٌ وسببٌ فقط، فلا بريدَ ولا هاتفَ ولا موضوعَ ولا نصّاً أبداً
(المستودعُ عامّ، والحمولةُ تُقرأ في الإدارة). فالقائمةُ البيضاءُ `DLQ_PAYLOAD_KEYS` هي المرجعُ الوحيد، و`_to_dlq` تُنقّي بها ما يُكتب،
وحارسٌ بنيويٌّ (tests/test_dlq_payload_whitelist.py) يمنع أن يُضيف كاتبٌ مفتاحاً خارجها.
"""

from __future__ import annotations

import logging
from typing import Any

from notifications.delivery_state import mark_undeliverable

logger = logging.getLogger(__name__)

#: مفاتيحُ حمولة DLQ المسموحة — معرّفاتٌ وتصنيفاتٌ فقط. **لا مفتاحَ محتوىً**: لا بريد ولا هاتف ولا موضوع ولا نصّ ولا اسم.
DLQ_PAYLOAD_KEYS = frozenset(
    {"student_id", "user_id", "sent_by_id", "dispatch_id", "notif_type", "reason"}
)


def clean_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """يُبقي مفاتيحَ القائمة البيضاء وحدَها؛ وما سواها يُسقط (تُذكر **أسماءُ** المفاتيح المُسقَطة لا قيمُها)."""
    payload = payload or {}
    dropped = sorted(str(key) for key in payload if key not in DLQ_PAYLOAD_KEYS)
    if dropped:
        logger.warning("DLQ: مفاتيحُ خارج القائمة البيضاء أُسقطت: %s", ", ".join(dropped))
    return {key: value for key, value in payload.items() if key in DLQ_PAYLOAD_KEYS}


def drop_undelivered(delivery: Any, school: Any, **message: Any) -> dict[str, str]:
    """بريدٌ لا مزوّدَ له: يُوسَم تسليمُه `undeliverable` ويُسجَّل «لم يُسلَّم» — بلا استحواذٍ ولا إعادةٍ ولا DLQ.

    `mark_undeliverable` القائمُ يُنهي تسليماً لم تبدأ له منطقةُ مزوّدٍ أصلاً (`pending` أو `retry_wait`) — وهذا حالُه، فلا
    يمرّ بـ`in_progress` (ادّعاءُ تنفيذٍ لم يقع). ثمّ تمرّ الرسالةُ بـ`send_email` مرّةً واحدةً ليبقى لها سطرٌ في `NotificationLog`
    بحالة «failed» وسببِها؛ والـbackend يكتب التحذيرَ الوحيدَ ولا يكتب `send_email` خطأً (انظر `send_email`).
    `message`: وسائطُ `send_email` (المستلمُ والموضوعُ والنصّ…) — تمرّ ولا تُخزَّن.
    """
    from notifications.services import NotificationService

    if delivery is not None and not mark_undeliverable(  # type: ignore[no-untyped-call]  # delivery_state غيرُ مُنوَّع
        delivery.id, school.id
    ):
        # انتهى التسليمُ أو يملكه تنفيذٌ آخر (رسالةٌ مكرَّرةٌ في الطابور): لا سجلَّ ثانياً ولا تحذيراً ثانياً.
        return {"status": "not_claimed"}
    NotificationService.send_email(school=school, delivery=delivery, **message)
    return {"status": "undeliverable"}
