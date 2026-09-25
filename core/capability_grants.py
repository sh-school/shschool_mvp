"""منحُ القدرات المفوَّضة وسحبُها — الكاتبُ الوحيد في `CapabilityGrant` (التذكرة SOS-20260924-1CFE، الجزء أ).

القدرةُ المفوَّضةُ (`schedule.operator`) يحملها شخصٌ بعينه بلا أن يتغيّر دورُه. والمنحُ والسحبُ قراران إداريّان:

* **من يمنح ويسحب:** المديرُ والنائبُ الأكاديميّ ومطوّرُ المنصّة وحدَهم (`can_manage`).
* **السببُ إلزاميّ** في المنح والسحب، وكلُّ منهما يُدقَّق: `PermissionAuditLog` (سجلُّ تغيير الصلاحيّات، من ولمن ومتى)
  و`AuditLog` (السجلُّ العامّ المحميُّ من الحذف) — كما يُدقَّق تعيينُ الأدوار.
* **لا مسحَ:** المنحُ يُسحب (`revoked_at`) فيبقى أثرُه؛ ومنحٌ فعّالٌ واحدٌ لكلّ (مدرسة، مستخدم، قدرة).
* **يُمنح لكادرٍ فعّالٍ فقط** — لا لطالبٍ ولا لوليّ أمر، ولا لمن ليست له عضويّةٌ نشطةٌ في المدرسة.

والقراءةُ (`holds`) تُحفظ على كائن المستخدم للطلب الواحد فلا يُسأل عنها كلَّ حارس؛ والمنحُ والسحبُ يُبطلانها.
ولا رقمَ وظيفيّاً ولا اسماً هنا: الأشخاصُ يُعيَّنون وقتَ التشغيل (`grant_capability`).
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.developer_access import is_platform_developer
from core.models import ALL_STAFF_ROLES, AuditLog, PermissionAuditLog
from core.models.capability_grant import DELEGABLE_CAPABILITIES, CapabilityGrant

#: من يمنح القدرةَ المفوَّضةَ ويسحبها (قرارُ المالك 2026-09-25). المطوّرُ بمعيار `is_platform_developer` أيضاً.
GRANTER_ROLES = frozenset({"principal", "vice_academic", "platform_developer"})

#: أقصرُ سببٍ يُقبل — يمنع «-» و«.» ويترك الحرّيّةَ لما فوقه.
MIN_REASON_LENGTH = 5

_CACHE_ATTR = "_capability_grant_keys"


class GrantError(Exception):
    """رفضُ منحٍ أو سحبٍ — الرسالةُ للمنفِّذ."""


def can_manage(user: Any) -> bool:
    """أيمنح هذا المستخدمُ القدراتِ المفوَّضةَ ويسحبها؟"""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return bool(
        user.is_superuser or user.get_role() in GRANTER_ROLES or is_platform_developer(user)
    )


def active_keys(user: Any) -> frozenset[str]:
    """القدراتُ المفوَّضةُ الفعّالةُ لهذا المستخدم — استعلامٌ واحدٌ يُحفظ على الكائن للطلب."""
    if user is None or not getattr(user, "is_authenticated", False):
        return frozenset()
    cached = user.__dict__.get(_CACHE_ATTR)
    if cached is None:
        cached = frozenset(
            CapabilityGrant.objects.filter(user=user, revoked_at__isnull=True).values_list(
                "capability", flat=True
            )
        )
        user.__dict__[_CACHE_ATTR] = cached
    return cached  # type: ignore[no-any-return]


def holds(user: Any, capability: str) -> bool:
    """أيحمل هذا المستخدمُ القدرةَ المفوَّضةَ بمنحٍ فعّال؟ (لا بدوره — راجع `core/capabilities.py`)."""
    return capability in active_keys(user)


def _forget(user: Any) -> None:
    user.__dict__.pop(_CACHE_ATTR, None)


def _clean_reason(reason: str, *, what: str) -> str:
    cleaned = (reason or "").strip()
    if len(cleaned) < MIN_REASON_LENGTH:
        raise GrantError(f"سببُ {what} إلزاميٌّ ({MIN_REASON_LENGTH} أحرفٍ فأكثر).")
    return cleaned


def _require_manager(by: Any) -> None:
    if not can_manage(by):
        raise GrantError("المنحُ والسحبُ للمدير والنائب الأكاديميّ ومطوّر المنصّة وحدَهم.")


def _require_delegable(capability: str) -> None:
    if capability not in DELEGABLE_CAPABILITIES:
        known = "، ".join(sorted(DELEGABLE_CAPABILITIES))
        raise GrantError(f"«{capability}» ليست قدرةً مفوَّضة — المفوَّضةُ: {known}.")


def _audit(
    *,
    by: Any,
    target: Any,
    school: Any,
    action: str,
    grant: CapabilityGrant,
    reason: str,
    request: Any,
) -> None:
    label = DELEGABLE_CAPABILITIES[grant.capability]
    granted = action == "capability_granted"
    details = {"capability": grant.capability, "reason": reason, "grant": str(grant.pk)}
    PermissionAuditLog.log(
        actor=by, target=target, action=action, school=school, details=details, request=request
    )
    AuditLog.log(
        user=by,
        action="create" if granted else "update",
        model_name="other",
        object_id=str(grant.pk),
        object_repr=f"{'منح' if granted else 'سحب'} قدرة «{label}»",
        changes={**details, "target": str(target.pk)},
        school=school,
        request=request,
    )


def grant(
    *, user: Any, capability: str, by: Any, reason: str, request: Any = None
) -> tuple[CapabilityGrant, bool]:
    """يمنح `user` القدرةَ المفوَّضة — يُعيد (المنح، أأُنشئ الآن؟)؛ ومنحٌ فعّالٌ قائمٌ يُعاد كما هو بلا تدقيقٍ مكرَّر."""
    _require_delegable(capability)
    _require_manager(by)
    reason = _clean_reason(reason, what="المنح")
    school = user.get_school()
    if school is None or user.get_role() not in ALL_STAFF_ROLES:
        raise GrantError("تُمنح القدرةُ لكادرٍ له عضويّةٌ نشطةٌ في مدرسته — لا لطالبٍ ولا لوليّ أمر.")
    if by.get_school() != school and not is_platform_developer(by):
        raise GrantError("لا يمنح مديرُ مدرسةٍ قدرةً في مدرسةٍ أخرى.")

    existing = CapabilityGrant.objects.filter(
        school=school, user=user, capability=capability, revoked_at__isnull=True
    ).first()
    if existing is not None:
        return existing, False
    try:
        with transaction.atomic():
            created = CapabilityGrant.objects.create(
                school=school, user=user, capability=capability, reason=reason, granted_by=by
            )
            _audit(
                by=by,
                target=user,
                school=school,
                action="capability_granted",
                grant=created,
                reason=reason,
                request=request,
            )
    except IntegrityError:  # سباقٌ مع منحٍ متزامن — الفريدُ الجزئيّ يحسمه، والسابقُ هو الفعّال
        return (
            CapabilityGrant.objects.get(
                school=school, user=user, capability=capability, revoked_at__isnull=True
            ),
            False,
        )
    _forget(user)
    return created, True


def revoke(
    *, user: Any, capability: str, by: Any, reason: str, request: Any = None
) -> CapabilityGrant | None:
    """يسحب منحَ `user` الفعّالَ لهذه القدرة — `None` إن لم يكن له منحٌ فعّال."""
    _require_delegable(capability)
    _require_manager(by)
    reason = _clean_reason(reason, what="السحب")
    current = (
        CapabilityGrant.objects.filter(user=user, capability=capability, revoked_at__isnull=True)
        .select_related("school")
        .first()
    )
    if current is None:
        return None
    if by.get_school() != current.school and not is_platform_developer(by):
        raise GrantError("لا يسحب مديرُ مدرسةٍ منحاً في مدرسةٍ أخرى.")
    with transaction.atomic():
        current.revoked_at = timezone.now()
        current.revoked_by = by
        current.revoke_reason = reason
        current.save(update_fields=["revoked_at", "revoked_by", "revoke_reason", "updated_at"])
        _audit(
            by=by,
            target=user,
            school=current.school,
            action="capability_revoked",
            grant=current,
            reason=reason,
            request=request,
        )
    _forget(user)
    return current
