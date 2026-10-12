"""أسطرُ `view_as_*` في سجلّ التدقيق — كلُّ دخولٍ وخروجٍ وتبديلٍ وصفحةٍ ورفضٍ بالمنفّذ الفعليّ والصفة المعروضة.

المسارُ وحدَه بلا استعلامٍ ولا محتوى («بلا محتواها»)، وصفةُ الفاعل في `changes["acting"]` صريحةً (لا يُعتمد على حقن
`AuditLog.save` وحدَه، فبعضُها يُكتب بعد أن تتبدّل الجلسة).
"""

from __future__ import annotations

from typing import Any

from .policy import clean_path, role_label


def record(
    request: Any,
    action: str,
    *,
    actor: Any,
    acting: dict[str, str],
    label: str,
    model_name: str = "other",
    object_id: Any = "",
    **extra: Any,
) -> None:
    from core.models import AuditLog

    AuditLog.log(
        user=actor,
        action=action,
        model_name=model_name,
        object_id=str(object_id or ""),
        object_repr=label[:300],
        changes={"path": clean_path(request.path), **extra, "acting": acting},
        request=request,
    )


def preview_label(prefix: str, role: str) -> str:
    return f"{prefix}: {role_label(role)}"
