"""الإنابة: قدراتُ الوظيفة المُنَابة بتكليفٍ ساري (W-20261019-007، نُقلت حرفاً من السجلّ)."""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from django.core.signals import request_finished, request_started

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


#: الوظائفُ المُنَابةُ التي مرّ بها فحصُ القدرة في الطلب الحاليّ (W-20261107-002) — يقرؤها ``AuditLog.save``
#: فيَسِمُ الصفَّ بـ``acting_for``. ``None`` = لم يمرّ فعلٌ بالإنابة في هذا الطلب.
_acting_for: ContextVar[frozenset[str] | None] = ContextVar("acting_for", default=None)


def current_acting_for() -> str | None:
    """الوظائفُ المُنَابةُ في الطلب الحاليّ نصّاً مرتَّباً (``None`` إن لم تُستعمل الإنابة)."""
    roles = _acting_for.get()
    return ",".join(sorted(roles)) if roles else None


def _mark_acting(roles: frozenset[str]) -> None:
    _acting_for.set((_acting_for.get() or frozenset()) | roles)


def _reset_acting(**_: Any) -> None:
    """يصفّر الوسمَ عند بدء الطلب وعند انتهائه فلا يتسرّب سياقُ الإنابة إلى طلبٍ لاحق."""
    _acting_for.set(None)


request_started.connect(_reset_acting, dispatch_uid="acting_audit_reset_started")
request_finished.connect(_reset_acting, dispatch_uid="acting_audit_reset_finished")


def acting_holds(user: Any, cap: Capability, *, mark: bool = True) -> bool:
    """أيحمل المستخدمُ ``cap`` اليومَ بتكليفٍ ساري بأعباء وظيفةٍ تحملها؟

    يُقرأ ``StaffAssignment`` (استعلامٌ واحدٌ للطلب) فلا يمسّ ``Capability.granted`` — فذاك منحٌ
    صريحٌ باسم الشخص يقرؤه ``is_operator`` بحرفه، والتكليفُ مؤقّتٌ بوظيفة.

    وعند النجاح يُعلَّم سياقُ الطلب بالوظيفة المُنَابة ليَسِمَ ``AuditLog`` أفعالَه؛ و``mark=False``
    للعرض (القائمةُ الجانبيّة) فلا يُوسَم فعلٌ أصليٌّ لمجرّد ظهور عنصرِ قائمة.
    """
    if not acting_transferable(cap) or _acting_roles_provider is None:
        return False
    matched = _acting_roles_provider(user) & cap.expanded_roles
    if matched and mark:
        _mark_acting(frozenset(matched))
    return bool(matched)


def _grant_or_acting(cap: Capability) -> Callable | None:
    """``_grant`` الحارس: المنحُ الصريحُ، ثمّ التكليفُ — لتعدّه القائمةُ الجانبيّةُ كما يمرّره الحارس."""
    if not acting_transferable(cap):
        return cap.grant

    def check(user: Any) -> bool:
        return cap.granted(user) or acting_holds(user, cap, mark=False)

    return check
