"""
core/module_registry.py — سجل مركزي لوحدات المنصة
═══════════════════════════════════════════════════
كل تطبيق يسجّل نفسه في ready() → يُبنى:
  • قاموس المسارات المحمية للـ Middleware
  • قائمة الوحدات المتاحة لكل دور (sidebar)

Usage:
    # في apps.py
    from core.module_registry import register_module
    class MyConfig(AppConfig):
        def ready(self):
            register_module(
                name="assessments",
                label="التقييمات والدرجات",
                url_prefix="/assessments/",
                icon="bi-journal-check",
                allowed_roles={"principal", "vice_academic", ...},
                sort_order=10,
            )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
# Dataclass لبيانات كل وحدة
# ══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ModuleInfo:
    """بيانات وحدة مسجّلة."""

    name: str  # مفتاح فريد (e.g. "assessments")
    label: str  # عنوان عربي
    url_prefix: str  # مسار الـ URL (e.g. "/assessments/")
    icon: str  # Bootstrap Icons class
    allowed_roles: frozenset  # الأدوار المسموح لها
    sidebar_roles: frozenset  # الأدوار التي ترى الوحدة في القائمة الجانبية
    sort_order: int  # ترتيب العرض
    parent: str  # وحدة أب (للـ sub-modules)


# ══════════════════════════════════════════════════════════════════
# السجل الداخلي
# ══════════════════════════════════════════════════════════════════

_MODULES: dict[str, ModuleInfo] = {}


def register_module(
    *,
    name: str,
    label: str,
    url_prefix: str,
    icon: str = "bi-grid",
    allowed_roles: set | frozenset | None = None,
    sidebar_roles: set | frozenset | None = None,
    sort_order: int = 50,
    parent: str = "",
) -> None:
    """
    يُسجّل وحدة جديدة في السجل المركزي.

    Parameters
    ----------
    name : str
        مفتاح فريد (يجب ألا يتكرر).
    label : str
        العنوان العربي الذي يظهر في القائمة.
    url_prefix : str
        بداية المسار المحمي (e.g. "/assessments/").
    icon : str
        أيقونة Bootstrap Icons.
    allowed_roles : set
        الأدوار المسموح لها بالوصول (للـ Middleware).
    sidebar_roles : set | None
        الأدوار التي ترى الوحدة في القائمة — إذا None تساوي allowed_roles.
    sort_order : int
        ترتيب العرض في القائمة الجانبية.
    parent : str
        اسم الوحدة الأب (للوحدات الفرعية مثل quality/evaluations).
    """
    if name in _MODULES:
        logger.debug("Module '%s' already registered — skipping", name)
        return

    roles = frozenset(allowed_roles or set())
    sidebar = frozenset(sidebar_roles) if sidebar_roles is not None else roles

    _MODULES[name] = ModuleInfo(
        name=name,
        label=label,
        url_prefix=url_prefix,
        icon=icon,
        allowed_roles=roles,
        sidebar_roles=sidebar,
        sort_order=sort_order,
        parent=parent,
    )
    logger.debug("Module registered: %s (%s)", name, url_prefix)


# ══════════════════════════════════════════════════════════════════
# واجهات القراءة — للـ Middleware و Context Processors
# ══════════════════════════════════════════════════════════════════


def get_all_modules() -> dict[str, ModuleInfo]:
    """يُعيد كل الوحدات المسجّلة — نسخة للقراءة فقط."""
    return dict(_MODULES)


def get_protected_paths() -> dict[str, list[str]]:
    """
    يُعيد قاموس {url_prefix: [roles]} متوافق مع SchoolPermissionMiddleware.

    الترتيب: الأطول أولاً لضمان مطابقة الوحدات الفرعية قبل الأب.
    مثال: "/quality/evaluations/" تُطابَق قبل "/quality/"
    """
    paths = {}
    # ترتيب بالأطول أولاً — الوحدات الفرعية تأخذ الأولوية
    for mod in sorted(_MODULES.values(), key=lambda m: -len(m.url_prefix)):
        paths[mod.url_prefix] = sorted(mod.allowed_roles)
    return paths


def get_accessible_modules_from_registry(user) -> list[dict]:
    """
    يُعيد قائمة الوحدات التي يمكن للمستخدم الوصول إليها.

    Returns
    -------
    list[dict]
        كل عنصر: {"name", "label", "url", "icon", "parent"}
    """
    if not user or not user.is_authenticated:
        return []

    if user.is_superuser:
        return [
            {
                "name": m.name,
                "label": m.label,
                "url": m.url_prefix,
                "icon": m.icon,
                "parent": m.parent,
            }
            for m in sorted(_MODULES.values(), key=lambda m: m.sort_order)
        ]

    role = user.get_role()
    result = []
    for m in sorted(_MODULES.values(), key=lambda m: m.sort_order):
        if role in m.sidebar_roles:
            result.append(
                {
                    "name": m.name,
                    "label": m.label,
                    "url": m.url_prefix,
                    "icon": m.icon,
                    "parent": m.parent,
                }
            )
    return result


def get_module(name: str) -> ModuleInfo | None:
    """يُعيد بيانات وحدة بالاسم."""
    return _MODULES.get(name)


def is_registered(name: str) -> bool:
    """هل الوحدة مسجّلة؟"""
    return name in _MODULES


def _clear_registry() -> None:
    """للاختبارات فقط — يمسح كل التسجيلات."""
    _MODULES.clear()
