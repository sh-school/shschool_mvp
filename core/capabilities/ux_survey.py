"""قدرتا استبانة تجربة المستخدم (W-20261015-002).

مضمومتان إلى حزمة `core/capabilities/` (كانتا ملفّاً جانبيّاً يلتفّ على سقف الألف سطر)؛
يستدعيهما السجلُّ بمصنع `_cap` ووحدة الصلاحيّات فلا استيرادَ دائريّ.
"""

from collections.abc import Callable
from types import ModuleType
from typing import Any


def ux_survey_capabilities(cap: Callable[..., Any], perms: ModuleType) -> list[Any]:
    """الموظفون يجيبون، والمدير والمطوّر المالك يرون التجميع."""
    return [
        cap(
            "ux_survey.respond",
            "الإجابةُ على استبانة تجربة المستخدم (الموظفون فقط)",
            perms.ALL_STAFF_ROLES - {"platform_developer"},
            basis="قرارُ المالك 2026-10-15 — استبانةٌ مجهولةٌ للموظفين",
        ),
        cap(
            "ux_survey.dashboard",
            "لوحةُ تجميع الاستبانة (المدير والمطوّر المالك)",
            {"principal", "platform_developer"},
            basis="قرارُ المالك 2026-10-15 — اللوحةُ للإدارة بحجب المجموعات الصغيرة",
        ),
    ]
