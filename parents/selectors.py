"""قراءاتُ تطبيق الأولياء — بلا ORM في العروض (سقّاطة الطبقات)."""

from __future__ import annotations

from typing import Any

from core.models.user import CustomUser
from core.phone_search import phone_holder_ids


def parent_ids_by_phone(links: Any, term: str) -> list:
    """معرّفاتُ أولياء الأمر في هذه الروابط ممّن يحوي جوّالُه الأرقامَ المكتوبة (بلا العمود الصريح)."""
    parents = CustomUser.objects.filter(pk__in=links.values("parent_id"))
    return list(phone_holder_ids(parents, term))
