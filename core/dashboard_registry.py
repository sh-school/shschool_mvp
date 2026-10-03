"""سجلُّ لوحات الأدوار التي تملكها وحداتٌ أخرى — النواةُ تُرسل، والوحدةُ تقرأ بياناتِها.

`core` لا يستورد وحدةً نازلة (سقّاطةُ الطبقات، القاعدة 2)، فلوحةُ السكرتير — وكلُّ ما بياناتُه
في `staff_affairs` — لا يجوز أن يستعلم عنها `core/dashboard_selectors.py`. فتسجّل الوحدةُ مزوِّدَها
عند الإقلاع (`AppConfig.ready`) وتقرؤه النواةُ بالاسم: `provider(user, school, today) -> dict`
يتضمّن مفتاحَ `view_type` الذي يختار قالبَ الدور في `dashboard/main.html`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from django.core.exceptions import ImproperlyConfigured

DashboardProvider = Callable[[Any, Any, date], dict[str, Any]]

_PROVIDERS: dict[str, DashboardProvider] = {}


def register_role_dashboard(role: str, provider: DashboardProvider) -> None:
    """يسجّل مزوِّدَ لوحةِ دور — والتسجيلُ المكرَّر بمزوِّدٍ آخر خطأٌ لا فوزٌ صامتٌ للأخير بترتيب الإقلاع."""
    existing = _PROVIDERS.get(role)
    if existing is not None and existing is not provider:
        raise ImproperlyConfigured(f"للدور «{role}» مزوِّدُ لوحةٍ مسجَّلٌ سلفاً.")
    _PROVIDERS[role] = provider


def registered_roles() -> frozenset[str]:
    return frozenset(_PROVIDERS)


def role_dashboard_provider(role: str) -> DashboardProvider | None:
    return _PROVIDERS.get(role)


def role_dashboard_context(
    role: str, base: dict[str, Any], user: Any, school: Any, today: date
) -> dict[str, Any]:
    """سياقُ لوحة الدور من مزوِّده — ولا يكتب فوق مفاتيح النواة (مراجعةُ 0105)."""
    extra = _PROVIDERS[role](user, school, today)
    if clash := extra.keys() & base.keys():
        raise ImproperlyConfigured(f"مزوِّدُ لوحة «{role}» يكتب فوق مفاتيحَ النواة: {sorted(clash)}")
    return extra
