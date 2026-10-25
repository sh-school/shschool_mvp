"""أساسُ سجلّ القدرات: النوعُ ومصنعُه والمنحُ المشتركُ (W-20261019-007)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Any

from core.permissions import expand_roles

#: الأساسُ حين لا نصَّ ولا قرار — القدرةُ كما في الشيفرة، تنتظر المراجعة.
PLATFORM_ASSUMPTION = "افتراضُ المنصّة — لم يُراجَع مقابل نصّ"


@dataclass(frozen=True)
class Capability:
    key: str
    label: str
    roles: frozenset
    scope: str = "المدرسة"
    basis: str = PLATFORM_ASSUMPTION
    #: منحٌ لا يقرؤه الدور: ``grant(user) -> bool``. لقدرةٍ يملكها المستخدمُ بتكليفٍ ساري
    #: لا بمسمّاه — كبديل الجناح من ملاحظي الطلبة وعمّال الخدمات.
    grant: Callable | None = None
    #: أدوارٌ لا تَرِث هذه القدرةَ من أصلها في ``ROLE_INHERITS`` — تحملها إن ذُكرت في ``roles`` صراحةً فقط.
    not_inherited_by: frozenset = frozenset()

    @property
    def expanded_roles(self) -> frozenset:
        """الأدوارُ بعد الوراثة — ما يفحصه الحارسُ فعلاً."""
        return frozenset(expand_roles(set(self.roles), not_inherited_by=self.not_inherited_by))

    def granted(self, user) -> bool:
        return self.grant is not None and bool(self.grant(user))


def _cap(
    key: str,
    label: str,
    roles: Iterable[str],
    scope: str = "المدرسة",
    basis: str = PLATFORM_ASSUMPTION,
    grant: Callable | None = None,
    not_inherited_by: Iterable[str] = (),
) -> Capability:
    return Capability(
        key, label, frozenset(roles), scope, basis, grant, frozenset(not_inherited_by)
    )


def _holds_a_wing(user) -> bool:
    from core.models.academic import Wing

    return Wing.is_held_by(user)


def _delegated(key: str) -> Callable:
    """منحٌ لا يقرؤه الدور: القدرةُ المفوَّضةُ باسم مستخدمٍ بمنحٍ فعّال (`core/capability_grants.py`)."""

    def check(user: Any) -> bool:
        from core.capability_grants import holds

        return holds(user, key)

    return check


@dataclass(frozen=True)
class Shared:
    """مجموعاتٌ تشترك فيها أكثرُ من قدرةٍ في أكثر من مجال — تعريفٌ واحدٌ فلا تنجرف إحداها."""

    leadership: AbstractSet[Any]
    followup_writers: AbstractSet[Any]
    followup_columns: AbstractSet[Any]
    family_callers: AbstractSet[Any]
