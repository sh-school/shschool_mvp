"""الإنابة: قدراتُ الوظيفة المُنَابة بتكليفٍ ساري (W-20261019-007، نُقلت حرفاً من السجلّ)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.capabilities.base import Capability
from core.permissions import SYSTEM_ADMIN, USER_MANAGE

# ── الإنابة: قدراتُ الوظيفة المُنَابة بتكليفٍ ساري (W-20261001-021، م-43 من النظام الوظيفيّ) ──────
#: قدرةٌ أعضاؤها هم USER_MANAGE وحدَهم أو SYSTEM_ADMIN وحدَهم — إدارةُ المستخدمين وإدارةُ النظام —
#: لا تنتقل بالتكليف أبداً (قرارُ المالك 2026-10-04). وما سواها من قدرات الوظيفة المُنَابة ينتقل
#: مدّةَ التكليف وحدَها، بالمعيار نفسِه الذي يفحص به الحارسُ دورَ صاحبها (``expanded_roles``).
ACTING_NEVER_TRANSFERS: tuple[frozenset[str], ...] = (
    frozenset(USER_MANAGE),
    frozenset(SYSTEM_ADMIN),
)
#: وقدرتان بالمفتاح لا تنتقلان كذلك (قرارُ المالك D-413م بعد حكم 0104): بياناتُ الخرق وسجلُّ الصلاحيّات.
#: دورُهما يضمّ النائبين فكان المُنَابُ يرثهما، وهما من أحسّ ما في المنصّة — فلا تُنَابان إلا بقرارٍ لاحقٍ صريح.
ACTING_NEVER_KEYS: frozenset[str] = frozenset({"breach.manage", "audit.permissions_log"})


def acting_transferable(cap: Capability) -> bool:
    """أتنتقل هذه القدرةُ بالتكليف؟ — القائمةُ المعلنةُ الواحدة: كلُّ قدرات السجلّ عدا ``ACTING_NEVER_TRANSFERS``
    و``ACTING_NEVER_KEYS``."""
    return cap.key not in ACTING_NEVER_KEYS and cap.roles not in ACTING_NEVER_TRANSFERS


def acting_capabilities() -> frozenset[str]:
    """مفاتيحُ القدرات التي تنتقل بالتكليف — للاختبار والعرض."""
    from core.capabilities.registry import registry

    return frozenset(key for key, cap in registry().items() if acting_transferable(cap))


#: قارئُ الوظائف المكلَّفة اليومَ — تسجّله وحدةُ شؤون الموظفين في ``ready()`` فلا تستورد النواةُ منها
#: استيراداً نازلاً (حارس الطبقات)، على نمط ``register_role_dashboard``.
_acting_roles_provider: Callable[[Any], frozenset[str]] | None = None


def register_acting_roles_provider(provider: Callable[[Any], frozenset[str]]) -> None:
    """يسجّل دالةَ قراءة الوظائف التي يقوم المستخدمُ بأعبائها بتكليفٍ ساري."""
    global _acting_roles_provider
    _acting_roles_provider = provider


def acting_holds(user: Any, cap: Capability) -> bool:
    """أيحمل المستخدمُ ``cap`` اليومَ بتكليفٍ ساري بأعباء وظيفةٍ تحملها؟

    يُقرأ ``StaffAssignment`` (استعلامٌ واحدٌ للطلب) فلا يمسّ ``Capability.granted`` — فذاك منحٌ
    صريحٌ باسم الشخص يقرؤه ``is_operator`` بحرفه، والتكليفُ مؤقّتٌ بوظيفة.
    """
    if not acting_transferable(cap) or _acting_roles_provider is None:
        return False
    return bool(_acting_roles_provider(user) & cap.expanded_roles)


def _grant_or_acting(cap: Capability) -> Callable | None:
    """``_grant`` الحارس: المنحُ الصريحُ، ثمّ التكليفُ — لتعدّه القائمةُ الجانبيّةُ كما يمرّره الحارس."""
    if not acting_transferable(cap):
        return cap.grant

    def check(user: Any) -> bool:
        return cap.granted(user) or acting_holds(user, cap)

    return check
