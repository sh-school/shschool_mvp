"""operations/services/capacity_check.py — فحص سعة الفصول.

منقولٌ حرفيّاً من `operations/services.py` (البند 8)؛ لا تغيير في المنطق.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass


# ─────────────────────────────────────────────────────────────────────────────


class CapacityCheckService:
    """خدمة فحص طاقة الجداول — Pre-validation قبل التوليد الذكي."""

    @staticmethod
    def slot_demand(assignments) -> int:
        """الزمنُ الذي تستهلكه هذه الإسنادات — بالخانات لا بالحصص.

            InstructionalPeriods ≠ OccupiedSlots

        فالشعبةُ المنقسمةُ تأخذ مادّتين في التوقيت نفسه: حصّتان تُدرَّسان،
        وخانةٌ واحدةٌ تُستهلك. وعدُّ الحصص هنا يُنتج إنذاراً كاذباً — «مطلوب
        37 والسعة 35» — وليس في الشعبة فائضٌ أصلاً.

        والمجموعةُ المتوازيةُ تستهلك أكبرَ نصابٍ فيها: لو كانت الفنونُ حصّتين
        والتكنولوجيا ثلاثاً، فالخاناتُ ثلاثٌ لا خمس.
        """
        from collections import defaultdict as _dd

        plain = 0
        groups: dict = _dd(int)
        for a in assignments:
            label = (a.parallel_group or "").strip()
            if label:
                groups[label] = max(groups[label], a.weekly_periods)
            else:
                plain += a.weekly_periods
        return plain + sum(groups.values())

    @staticmethod
    def get_overcapacity_classes(assignments) -> list[dict]:
        """
        يكتشف الفصول التي يتجاوز طلبها الأسبوعي طاقتها الاستيعابية.

        ✅ v5.4: ينقل capacity check من smart_schedule_view إلى service layer.

        Args:
            assignments: QuerySet من SubjectClassAssignment (يجب أن يكون محدَّداً مسبقاً)

        Returns:
            list of dict: كل عنصر يحتوي class_id, demand, capacity, overflow
        """
        from collections import defaultdict

        from operations.scheduler_constraints import get_max_periods_for_day

        class_rows: dict = defaultdict(list)
        class_levels: dict = {}
        class_names: dict = {}
        for a in assignments:
            cid = str(a.class_group_id)
            class_rows[cid].append(a)
            # التحذيرُ بلا اسمِ الشعبة لا يُصلحه أحد: «مطلوب 37» مرّتين لا
            # تقول أيَّ شعبةٍ تُراجَع.
            class_names[cid] = str(a.class_group)
            # `ClassGroup.level_type` حقلٌ قائمٌ يحمل «prep»/«sec» — يُقرأ ولا
            # يُشتقّ من `grade`. وكان هنا `_grade_to_level` وقد حُذف من المولّد
            # حين صُحّح الاشتقاقُ هناك، فبقي الاستيرادُ معلّقاً وسقطت الصفحةُ
            # كلُّها بـ`ImportError` — لا الفحصُ وحدَه.
            class_levels[cid] = a.class_group.level_type or ""

        overcapacity = []
        class_demand = {
            cid: CapacityCheckService.slot_demand(rows) for cid, rows in class_rows.items()
        }
        for cid, demand in class_demand.items():
            level = class_levels.get(cid, "")
            thu_max = get_max_periods_for_day(4, level)
            weekly_capacity = 4 * 7 + thu_max
            if demand > weekly_capacity:
                overcapacity.append(
                    {
                        "class_id": cid,
                        "class_name": class_names.get(cid, cid),
                        "demand": demand,
                        "capacity": weekly_capacity,
                        "overflow": demand - weekly_capacity,
                        #: سببٌ مرجَّحٌ يُقال لا يُترك للتخمين: وسمُ توازٍ بلا
                        #: شريكٍ في الشعبة. فالمجموعةُ تستهلك خانةً واحدةً
                        #: لعضوَيها، وبعضوٍ واحدٍ لا خصمَ — فيظهر فائضٌ سببُه
                        #: وسمٌ ناقصٌ لا نصابٌ زائد. وعلاجُه إشعالُ «متوازية»
                        #: على شريكة المادّة في شاشة الإسناد.
                        "orphan_parallels": CapacityCheckService._orphan_tags(class_rows[cid]),
                    }
                )
        return overcapacity

    @staticmethod
    def _orphan_tags(rows) -> list[str]:
        """أسماءُ الموادّ الموسومةِ بتوازٍ لا شريكَ له في هذه الشعبة."""
        from collections import Counter as _C

        tally = _C((r.parallel_group or "").strip() for r in rows if r.parallel_group)
        return [
            r.subject.name_ar
            for r in rows
            if r.parallel_group and tally[(r.parallel_group or "").strip()] < 2
        ]
