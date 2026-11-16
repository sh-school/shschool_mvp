"""behavior/edit_services.py — تعديلُ مخالفةٍ مسجَّلة (بلاغ 5D5D، قرار المالك 2026-11-11).

وحدةٌ مستقلّةٌ لأنّ `behavior/services.py` بلغ سقفَ الحجم. القاعدةُ هنا لا في القالب:
من سجّل المخالفةَ يعدّلها؛ وغيرُه من القائمة المغلقة `BEHAVIOR_EDIT`، والمشرفُ لجناحه وحدَه.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied
from django.db import transaction

from behavior.models import BehaviorInfraction
from core.permissions import BEHAVIOR_EDIT

if TYPE_CHECKING:
    from django.http import HttpRequest

    from core.models import CustomUser

_TEXT_FIELDS = ("description", "violation_description")
_LOCKED = "صدر قرارُ اللجنة في هذه المخالفة، فلا تتغيّر درجتُها من التعديل."


def can_edit_infraction(user: CustomUser, infraction: BehaviorInfraction, scope: Any) -> bool:
    """من سجّل المخالفةَ يعدّلها؛ وغيرُه من القائمة المغلقة، والمشرفُ لطلبة جناحه وحدَهم."""
    if infraction.reported_by_id == user.pk:
        return True
    if user.get_role() not in BEHAVIOR_EDIT:
        return False
    return bool(scope.covers_student(infraction.student_id))


def editable_infraction_ids(user: CustomUser, infractions: Any, scope: Any) -> set[Any]:
    """معرّفاتُ الصفوف التي يحقّ لهذا المستخدم تعديلُها — لرابط «تعديل» في ملفّ الطالب."""
    return {i.pk for i in infractions if can_edit_infraction(user, i, scope)}


def level_locked_by_committee(infraction: BehaviorInfraction) -> bool:
    """مخالفةٌ محالةٌ للجنة (الدرجة 3 و4) صدر فيها قرارٌ: لا تتغيّر درجتُها من التعديل."""
    return infraction.level >= 3 and (infraction.is_resolved or infraction.committee_votes.exists())


def save_infraction_edit(
    *,
    infraction: BehaviorInfraction,
    editor: CustomUser,
    scope: Any,
    data: dict[str, Any],
    categories: list[Any],
    request: HttpRequest | None = None,
) -> tuple[bool, str]:
    """يحفظ تعديلَ النموذج المُتحقَّق منه؛ ويُرجع (نجح؟، رسالةً للمستخدم)."""
    wanted = data.get("violation_category")
    category = next((c for c in categories if c.pk == wanted), None)
    if wanted and category is None:
        return False, "فئة المخالفة غير متاحة لهذه المخالفة."
    try:
        changed = update_infraction(
            infraction=infraction,
            editor=editor,
            scope=scope,
            data=data,
            violation_category=category,
            request=request,
        )
    except ValueError as exc:
        return False, str(exc)
    return True, "تم حفظ التعديل." if changed else "لا تغييرَ لحفظه."


@transaction.atomic
def update_infraction(
    *,
    infraction: BehaviorInfraction,
    editor: CustomUser,
    scope: Any,
    data: dict[str, Any],
    violation_category: Any = None,
    request: HttpRequest | None = None,
) -> list[str]:
    """يعدّل الوصفَ والمخالفةَ والإجراءَ والتاريخ، ويسجّل في التدقيق الحقولَ المتغيّرة قبلُ وبعد.

    ترجع أسماءَ الحقول التي تغيّرت. وفي التدقيق نصوصُ الوصف أطوالُها لا محتواها (PDPPL).
    Raises:
        PermissionDenied: من لا يحقّ له التعديل.
        ValueError: تغييرُ درجةِ مخالفةٍ صدر فيها قرارُ اللجنة.
    """
    from core.models import AuditLog

    if not can_edit_infraction(editor, infraction, scope):
        raise PermissionDenied("لا يحقّ لك تعديل هذه المخالفة.")
    level = violation_category.degree if violation_category else infraction.level
    if level != infraction.level and level_locked_by_committee(infraction):
        raise ValueError(_LOCKED)

    action_type = data["disciplinary_action_type"]
    new = {
        "violation_category_id": violation_category.pk if violation_category else None,
        "level": level,
        "description": data["description"],
        "disciplinary_action_type": action_type,
        "violation_description": data.get("violation_description", ""),
        "date": data["date"],
    }
    old_code = infraction.violation_category.code if infraction.violation_category_id else ""
    new_code = violation_category.code if violation_category else ""
    changes: dict[str, Any] = {}
    fields: list[str] = []
    for name, value in new.items():
        before = getattr(infraction, name)
        if before == value:
            continue
        fields.append(name)
        if name == "violation_category_id":
            changes["violation_category"] = {"before": old_code, "after": new_code}
        elif name in _TEXT_FIELDS:
            changes[name] = {"before": len(before or ""), "after": len(value or "")}
        else:
            changes[name] = {"before": str(before), "after": str(value)}
        setattr(infraction, name, value)
    if not changes:
        return []
    if "disciplinary_action_type" in changes:
        labels = dict(BehaviorInfraction.DISCIPLINARY_ACTION_CHOICES)
        infraction.action_taken = labels.get(action_type, "")
        fields.append("action_taken")
    infraction.save(update_fields=fields)
    AuditLog.log(
        user=editor,
        action="update",
        model_name="BehaviorInfraction",
        object_id=infraction.pk,
        object_repr="مخالفة سلوكية — تعديل",
        changes=changes,
        school=infraction.school,
        request=request,
    )
    return list(changes)
