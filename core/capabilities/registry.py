"""تجميعُ سجلّ القدرات من أقسام المجالات بالترتيب نفسِه (W-20261019-007)."""

from __future__ import annotations

from functools import cache

from core.capabilities.assessment import assessment_capabilities
from core.capabilities.attendance_schedule import attendance_schedule_capabilities
from core.capabilities.base import Capability, Shared
from core.capabilities.behavior import behavior_capabilities
from core.capabilities.clinic_library_transport import clinic_library_transport_capabilities
from core.capabilities.dashboard import dashboard_capabilities
from core.capabilities.exam_control import exam_control_capabilities
from core.capabilities.notifications_analytics import notifications_analytics_capabilities
from core.capabilities.parents import parents_capabilities
from core.capabilities.quality import quality_capabilities
from core.capabilities.staff_affairs import staff_affairs_capabilities
from core.capabilities.student_affairs import student_affairs_capabilities
from core.capabilities.technical_tools import technical_tools_capabilities
from core.capabilities.wings import wings_capabilities
from core.capabilities.workload import workload_capabilities


@cache
def registry() -> dict[str, Capability]:
    """السجلُّ مبنيّاً — كسولٌ لأنّ بعضَ المجموعات في تطبيقاتٍ تستورد ``core``."""
    from core import permissions as P  # noqa: N812 — اختصارٌ يُقرأ به السجلُّ كجدول

    leadership = P.LEADERSHIP
    #: كتابةُ «متابعة الغياب» (W-20261013-011): مشرفُ الجناح مقيَّدٌ بجناحه في العرض، والنائبُ الأكاديميّ ومنسّقُ القسم مراقبان.
    followup_writers = frozenset(
        {"principal", "vice_admin", "admin_supervisor", "student_affairs_coordinator", "admin"}
    )
    #: أعمدةُ «المتابعة» في كشف الغياب (W-20261014-018، قولُ المالك): ثلاثةٌ وحدَهم؛ ومشرفُ الجناح لا يرثها
    #: وإن كان من كتّاب المتابعة، فالقدرةُ منفصلةٌ عن `followup_writers` عمداً.
    followup_columns = frozenset({"principal", "vice_admin", "student_affairs_coordinator"})
    #: من يتّصل بأسر الطلبة — تعريفٌ واحدٌ لقدرتَي الاستدعاء واسمِ الوليّ فلا تنجرف إحداهما.
    family_callers = P.BEHAVIOR_MANAGE | {"psychologist", "student_affairs_coordinator"}
    shared = Shared(
        leadership=leadership,
        followup_writers=followup_writers,
        followup_columns=followup_columns,
        family_callers=family_callers,
    )
    caps = [
        *dashboard_capabilities(shared),
        *student_affairs_capabilities(shared),
        *staff_affairs_capabilities(shared),
        *notifications_analytics_capabilities(shared),
        *assessment_capabilities(shared),
        *workload_capabilities(shared),
        *behavior_capabilities(shared),
        *clinic_library_transport_capabilities(shared),
        *technical_tools_capabilities(shared),
        *exam_control_capabilities(shared),
        *attendance_schedule_capabilities(shared),
        *quality_capabilities(shared),
        *parents_capabilities(shared),
        *wings_capabilities(shared),
    ]
    out = {}
    for cap in caps:
        assert cap.key not in out, f"قدرةٌ مكرّرة: {cap.key}"
        out[cap.key] = cap
    return out
