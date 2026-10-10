"""سقفُ الحصّة الأولى لكلّ معلّم (HC22) — توأمُ HC8 للطرف الآخر من اليوم (W-20261003-043).

استُخرج من `scheduler_constraints` لأن ذلك الملف فوق حدّ الحجم (راجع `tests/file_size_ratchet.py`)،
وتُعاد تصديرُ أسمائه من هناك فلا يتغيّر استيرادُ أحد.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scheduler import ScheduleGrid
    from .scheduler_constraints import Task

#: أولى حصةٍ في اليوم.
FIRST_PERIOD = 1

#: أكثرُ ما يُقبل من الحصص الأولى لمعلّمٍ في الأسبوع (HC22، D-166م وD-183م): اثنتان، صلبٌ قابلٌ للضبط.
#: توأمُ `MAX_LAST_PERIODS` (HC8) وقيمتُه مثلُه؛ ولا سقفَ شخصيّاً للأولى كما للسابعة (قرارٌ منفصلٌ إن لزم).
#: وهو غيرُ `MIN_FIRST_PERIODS`: ذاك حدٌّ أدنى مرنٌ يُرجَّح، وهذا سقفٌ صلبٌ يُمنَع.
MAX_FIRST_PERIODS = 2


def check_first_period_share(grid: ScheduleGrid, period: int, task: Task) -> bool:
    """HC22: لا تتكدّس الحصّةُ الأولى على معلّمٍ بعينه — أكثرُ من `MAX_FIRST_PERIODS` أسبوعيّاً.

    توأمُ HC8 للطرف الآخر من اليوم، ومنطقُه مثلُه: يُسأل كم أولى للمعلّم في الجدول (دون هذه الحصّة)
    فإن بلغ السقفَ رُفضت. والسقفُ الأعلى لمعلّمٍ بعينه (`first_cap` على عضو المهمّة) تخفيفٌ معلَنٌ بقرار
    المالك يمرّره المُقيِّمُ من ناتج الحلّال (نظيرُ `first_cap_override` في V2)؛ وغيابُه يعني العامّ.
    وهو منعٌ للأولى وحدَها لا للسابعة: السابعةُ لها HC8.
    """
    if period != FIRST_PERIOD:
        return True
    for m in task.members:
        if grid.teacher_periods_at(m.teacher_id, FIRST_PERIOD) >= (
            getattr(m, "first_cap", 0) or MAX_FIRST_PERIODS
        ):
            return False
    return True
