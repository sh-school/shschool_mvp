"""جداولُ متابعة الغياب على عقد التصدير المركزيّ (W-20261110-004): التواصلُ مع الأولياء وإجراءاتُ الغياب.

المحدِّدُ واحدٌ للصفحة وExcel وPDF: `followup_rows` بنطاق الدور ثمّ ترشيحُ الشاشة كاملاً (لا صفحةُ الترقيم وحدَها)؛
والعمودُ «م» وفرزُ الجناح والأعمدةُ المخفيّةُ من العقد. جدولُ التواصل بنسختين: بعمود التغذية الراجعة لمن يحملُ قدرتَها
وبدونه لغيره — فلا يخرج عمودٌ لا تعرضه الشاشةُ لصاحبه.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.utils import timezone

from core.exports.contract import Column, TableSpec, register_table

PRINT = "operations.absence_followup_print"
FEEDBACK = "operations.absence_followup_feedback"

_BASE = (
    Column("student", "الطالب"),
    Column("wing", "الجناح"),
    Column("class_label", "الصف"),
)
_CONTACT = (
    *_BASE,
    Column("phones", "هاتف ولي الأمر"),
    Column("outcome", "حالة التواصل"),
    Column("contacted_at", "آخر اتصال"),
)
_ACTIONS = (
    *_BASE,
    Column("absent_days", "أيام الغياب"),
    Column("action", "الإجراء الحالي"),
    Column("acted_at", "وقت التنفيذ"),
    Column("action_status", "متابعة الإجراء"),
    Column("followed", "وقت المتابعة ومن سجّلها"),
)


def day_of(params: Any) -> dt.date:
    try:
        return dt.date.fromisoformat(params.get("date") or "")
    except ValueError:
        return timezone.localdate()


def shown_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    """صفوفُ الشاشة بنطاق الدور وترشيحها وفرزها (جناحٌ فصفٌّ فشعبةٌ فاسم) — مصدرُ الصفحة وExcel وPDF معاً."""
    from operations.absence_followup_print import by_wing, shown_rows_of
    from operations.services.absence_followup import followup_rows

    return by_wing(shown_rows_of(followup_rows(user, day_of(params)), params))


def _common(row: dict[str, Any]) -> dict[str, Any]:
    group = row.get("class_group")
    wing = getattr(group, "wing", None)
    return {
        "student": row["student"].full_name,
        "wing": row["wing_title"],
        "class_label": group.short_label if group else "",
        "wing_order": getattr(wing, "order", None),
    }


def contact_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    """سطرُ التواصل لكلّ غائب: الهاتفُ وحالةُ آخر اتصالٍ ووقتُه والتغذيةُ الراجعة."""
    rows = []
    for r in shown_rows(user, params):
        contact = r.get("contact")
        rows.append(
            {
                **_common(r),
                "phones": " ، ".join(r.get("phones") or []),
                "outcome": contact.get_outcome_display() if contact else "",
                "contacted_at": f"{contact.contacted_at:%d/%m %H:%M}" if contact else "",
                "feedback": r.get("feedback") or "",
            }
        )
    return rows


def action_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    """سطرُ الإجراء لكلّ غائب: أيّامُ الغياب والإجراءُ الحاليّ ومتابعتُه."""
    from operations.absence_followup_print import action_text, followed_text

    rows = []
    for r in shown_rows(user, params):
        action = r.get("action")
        rows.append(
            {
                **_common(r),
                "absent_days": r.get("absent_days", 0),
                "action": action_text(r),
                "acted_at": f"{action.acted_at:%d/%m %H:%M}" if action else "",
                "action_status": r.get("action_status") or "لم تتمّ المتابعة",
                "followed": followed_text(r),
            }
        )
    return rows


CONTACT_TABLE = TableSpec(
    kind="operations.absence_contact_xlsx",
    title="التواصل مع أولياء الأمور",
    capability=PRINT,
    columns=_CONTACT,
    rows_for=contact_rows,
    file_module="operations",
)
CONTACT_FEEDBACK_TABLE = TableSpec(
    kind="operations.absence_contact_feedback_xlsx",
    title="التواصل مع أولياء الأمور",
    capability=FEEDBACK,
    columns=(*_CONTACT, Column("feedback", "التغذية الراجعة من ولي الأمر")),
    rows_for=contact_rows,
    file_module="operations",
)
ACTIONS_TABLE = TableSpec(
    kind="operations.absence_actions_xlsx",
    title="متابعة إجراءات الغياب",
    capability=PRINT,
    columns=_ACTIONS,
    rows_for=action_rows,
    file_module="operations",
)

OPERATIONS_TABLES = (CONTACT_TABLE, CONTACT_FEEDBACK_TABLE, ACTIONS_TABLE)


def table_for(user: Any, page: str) -> TableSpec:
    """جدولُ الصفحة المطلوبة: التواصلُ بنسخته حسب قدرة التغذية الراجعة، أو الإجراءات."""
    from core.capabilities import has_capability

    if page == "actions":
        return ACTIONS_TABLE
    return CONTACT_FEEDBACK_TABLE if has_capability(user, FEEDBACK) else CONTACT_TABLE


def register_operations_tables() -> None:
    """يسجّل جداولَ متابعة الغياب في عقد التصدير — من `OperationsConfig.ready()`."""
    for table in OPERATIONS_TABLES:
        register_table(table)
