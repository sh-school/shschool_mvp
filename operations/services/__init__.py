"""operations/services — خدماتُ التشغيل مقسومةً بحسب المجال (البند 8).

كانت ملفّاً واحداً من 2709 سطراً. الاستيراد القديم `from operations.services
import ScheduleService` يعمل كما هو — الحزمةُ تُعيد تصدير كلّ اسمٍ عامّ.
"""

from operations.services.absence_swap import AbsenceSwapService
from operations.services.attendance import AttendanceService
from operations.services.capacity_check import CapacityCheckService
from operations.services.compensatory import CompensatoryService
from operations.services.free_slot import FreeSlotService
from operations.services.schedule import ScheduleService, parallel_labels
from operations.services.substitute import SubstituteService
from operations.services.swap import SwapService
from operations.services.teacher_load import TeacherLoadService

__all__ = [
    "AbsenceSwapService",
    "AttendanceService",
    "CapacityCheckService",
    "CompensatoryService",
    "FreeSlotService",
    "ScheduleService",
    "SubstituteService",
    "SwapService",
    "TeacherLoadService",
    "parallel_labels",
]
