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

DashboardProvider = Callable[[Any, Any, date], dict[str, Any]]

_PROVIDERS: dict[str, DashboardProvider] = {}


def register_role_dashboard(role: str, provider: DashboardProvider) -> None:
    _PROVIDERS[role] = provider


def role_dashboard_provider(role: str) -> DashboardProvider | None:
    return _PROVIDERS.get(role)
