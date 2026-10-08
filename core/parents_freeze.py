"""تجميدُ التواصل مع أولياء الأمور — المفتاحُ المركزيّ الوحيد (W-20261008-013، D-268م وD-272م).

قرارُ المالك: «تجميد وإخفاء، لا حذف». مفتاحٌ واحدٌ `PARENTS_FROZEN` **مجمَّدٌ افتراضاً**، وفي إعدادات الاختبار False.
لا يقرأ أيُّ كودٍ `settings.PARENTS_FROZEN` مباشرةً: يمرّ عبر `parents_frozen()` وحدَها (حارسُ
`tests/test_parents_freeze_flag_guard.py`)، فيبقى موضعُ الفكّ والقراءة واحداً.

هذه الوحدةُ لا تحذف شيئاً ولا تمسّ جدولاً: التجميدُ سلوكٌ يتخطّى الإرسال ولا يُغيّر حالةَ أيّ سجلّ.
"""

from collections.abc import Iterable
from typing import Any

from django.conf import settings

#: الدورُ الذي يمثّل وليَّ الأمر في المنصّة.
PARENT_ROLE = "parent"

#: ما يُسجَّل في سجلّ الإشعار/الحدث حين يُتخطّى إرسالٌ لوليّ أمر.
FROZEN_MESSAGE = "مجمَّد بقرار تجميد التواصل مع أولياء الأمور"


def parents_frozen() -> bool:
    """هل التواصل مع أولياء الأمور مجمَّد؟ — الافتراضُ الآمنُ عند غياب الإعداد: مجمَّد."""
    return bool(getattr(settings, "PARENTS_FROZEN", True))


def is_parent_only(user: Any) -> bool:
    """أوليُّ أمرٍ لا غير؟ — له عضويّةُ parent نشطةٌ وليس له دورٌ آخر نشط.

    معلّمٌ هو وليُّ أمرٍ أيضاً كادرٌ: لا يُحجب عنه إشعارُ عمله. أمّا إشعارٌ يُرسل إليه **بصفته وليّاً**
    (عبر رابط `ParentStudentLink`) فتحجبه نقطةُ إرسالٍ تعرف أنّها تخاطب الأهل، لا هذه الدالّة.
    """
    roles = {m.role.name for m in user.active_memberships}
    return PARENT_ROLE in roles and roles <= {PARENT_ROLE}


def without_frozen_parents(users: Iterable[Any]) -> list[Any]:
    """المستلمون بعد استبعاد أولياء الأمور الخُلَّص عند التجميد؛ وبلا تجميدٍ كما هم."""
    users = list(users)
    if not parents_frozen():
        return users
    return [u for u in users if not is_parent_only(u)]


def frozen_recipient(*, email: str | None = None, phone: str | None = None) -> bool:
    """هل عنوانُ التسليم (بريدٌ أو هاتف) لوليّ أمرٍ خالصٍ والتواصلُ مجمَّد؟

    حارسٌ لمهامّ القنوات (send_email/sms/whatsapp) التي تستلم عنواناً لا مستخدماً: تُجمَّد
    رسالةٌ وُضعت في الطابور قبل التجميد ثمّ وصلت بعده. لا تمسّ حالةَ أيّ سجلّ.
    """
    if not parents_frozen():
        return False
    from core.models import CustomUser
    from core.models.crypto import hmac_field

    users = CustomUser.objects.none()
    if email:
        users = CustomUser.objects.filter(email__iexact=email)
    elif phone:
        users = CustomUser.objects.filter(phone_hmac=hmac_field(phone))
    return any(is_parent_only(u) for u in users[:20])
