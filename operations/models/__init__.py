"""نماذجُ تطبيق operations — حزمةٌ بوحداتٍ حسب المسؤوليّة (كان `models.py` واحداً بأكثر من 2200 سطر).

الاستيرادُ من `operations.models` كما كان: كلُّ الأسماء (بما فيها `_uuid` و`_excuse_upload_path` اللتان تشير إليهما الهجرات)
مُعاد تصديرُها هنا، فلا يتغيّر مستوردٌ ولا هجرة. والتقسيم: `schedule` (الجدول)، و`attendance` (الحصص والحضور)،
و`attendance_ledger` (سجلُّ رصد المعلّم المضافُ إليه ولا يُمحى)، و`substitution` (الغياب والتبديل والتعويض)،
و`permissions` (الأذونات المؤقّتة). الاعتماديّةُ باتّجاهٍ واحد:
`schedule` ← `attendance` ← `attendance_ledger`/`substitution` ← `permissions` بلا دورة."""

from .attendance import (  # noqa: F401
    AbsenceAlert,
    AbsenceExcuse,
    ClassExit,
    GuardianContact,
    PeriodConfirmation,
    SectionDayConfirmation,
    Session,
    StudentAttendance,
    _excuse_upload_path,
)
from .attendance_ledger import (  # noqa: F401
    AttendanceDecision,
    AttendanceEntry,
)
from .common import (  # noqa: F401
    _uuid,
)
from .permissions import (  # noqa: F401
    PermissionAuditLog,
    TemporaryPermission,
)
from .schedule import (  # noqa: F401
    FreeSlotRegistry,
    ScheduleBaseline,
    ScheduleConstraintOverride,
    ScheduleGeneration,
    ScheduleGenerationQuerySet,
    ScheduleSlot,
    SchedulingResource,
    Subject,
    SubjectClassAssignment,
    TeacherExemption,
    TeacherPreference,
    TimeSlotConfig,
)
from .substitution import (  # noqa: F401
    CompensatorySession,
    SubstituteAssignment,
    TeacherAbsence,
    TeacherSwap,
)

__all__ = [
    "AttendanceEntry",
    "AttendanceDecision",
    "Subject",
    "ScheduleSlot",
    "TimeSlotConfig",
    "SubjectClassAssignment",
    "SchedulingResource",
    "TeacherPreference",
    "TeacherExemption",
    "ScheduleBaseline",
    "ScheduleConstraintOverride",
    "ScheduleGenerationQuerySet",
    "ScheduleGeneration",
    "FreeSlotRegistry",
    "Session",
    "StudentAttendance",
    "AbsenceExcuse",
    "GuardianContact",
    "AbsenceAlert",
    "SectionDayConfirmation",
    "ClassExit",
    "PeriodConfirmation",
    "TeacherAbsence",
    "SubstituteAssignment",
    "TeacherSwap",
    "CompensatorySession",
    "TemporaryPermission",
    "PermissionAuditLog",
]
