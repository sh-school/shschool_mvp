"""قدراتُ مجال «الأنصبة» — قسمٌ من سجلّ القدرات نُقل حرفاً بلا تغيير قدرةٍ ولا حامل (W-20261019-007)."""

from __future__ import annotations

from core.capabilities.base import Capability, Shared, _cap, _delegated


def workload_capabilities(shared: Shared) -> list[Capability]:
    from academic_management.workload_workflow import _DEFAULT_ROLES as WORKLOAD
    from academic_management.workload_workflow import APPROVE, EDIT, REVIEW

    return [
        # ── الأنصبة — تهيّئها المدرسةُ في WorkloadGovernance ─────────
        _cap(
            "workload.edit",
            "إدخالُ خطط الأنصبة",
            WORKLOAD[EDIT],
            scope="قسمُ المنسّق — وكلُّ الأقسام لمُشغِّل الجدول",
            basis="افتراضٌ موصى به — تُبدّله المدرسة (WorkloadGovernance)؛ ومُشغِّلُ الجدول (`schedule.operator`) يُدخل بمنحه",
            grant=_delegated("schedule.operator"),
        ),
        _cap(
            "workload.review",
            "مراجعةُ خطط الأنصبة",
            WORKLOAD[REVIEW],
            basis="افتراضٌ موصى به — تُبدّله المدرسة (WorkloadGovernance)",
        ),
        _cap(
            "workload.approve",
            "اعتمادُ خطط الأنصبة",
            WORKLOAD[APPROVE],
            basis="افتراضٌ موصى به — تُبدّله المدرسة (WorkloadGovernance)",
        ),
    ]
