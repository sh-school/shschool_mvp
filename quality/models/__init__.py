"""نماذجُ تطبيق quality — حزمةٌ بوحداتٍ حسب المسؤوليّة (كان `models.py` واحداً بأكثر من 1400 سطر).

الخطّةُ التشغيليّة + لجنةٌ موحَّدة (تنفيذيّةٌ ومراجعةٌ ذاتيّة) + ربطُ المنفّذين + تقييمُ أداء الموظّفين (متعدّدُ المقيّمين + قوالبُ أدوار)،
والهيكلُ الهرميّ: مجال ← هدف ← مؤشّر ← إجراء ← دليل.

الاستيرادُ من `quality.models` كما كان: كلُّ الأسماء (بما فيها الثوابتُ الخاصّة و`_uuid` التي تشير إليها الهجرات) مُعاد تصديرُها هنا،
فلا يتغيّر مستوردٌ ولا هجرة. والتقسيم: `operational` (الخطّة)، و`committee` (اللجنة)، و`appraisal` (تقييم الأداء)؛ والاعتماديّةُ باتّجاهٍ واحد بلا دورة."""

# ── الإشراف على أداء المعلّم (الملاحظة الصفّية) — وحدة مستقلّة ──────────
from quality.observation_models import (  # noqa: F401
    ClassroomObservation,
    ObservationCriterion,
    ObservationScore,
)

from .appraisal import (  # noqa: F401
    _DEFAULT_AXES,
    _EVALUABLE_ROLES,
    _SCORE_ACCEPTABLE,
    _SCORE_EXCELLENT,
    _SCORE_GOOD_ABOVE,
    _SCORE_VERY_GOOD_ABOVE,
    APPRAISAL_GRIEVANCE_DECISION_DAYS,
    APPRAISAL_GRIEVANCE_WINDOW_DAYS,
    EmployeeEvaluation,
    EvaluationAxis,
    EvaluationCycle,
    EvaluationLevelBackup,
    EvaluationScore,
    RoleEvaluationTemplate,
    _grievance_days,
)
from .committee import (  # noqa: F401
    CommitteeManager,
    QualityCommitteeMember,
)
from .common import (  # noqa: F401
    _uuid,
)
from .operational import (  # noqa: F401
    ExecutorMapping,
    OperationalDomain,
    OperationalIndicator,
    OperationalProcedure,
    OperationalTarget,
    ProcedureEvidence,
    ProcedureStatusLog,
)

__all__ = [
    "OperationalDomain",
    "OperationalTarget",
    "OperationalIndicator",
    "OperationalProcedure",
    "ProcedureEvidence",
    "ProcedureStatusLog",
    "ExecutorMapping",
    "CommitteeManager",
    "QualityCommitteeMember",
    "RoleEvaluationTemplate",
    "EvaluationAxis",
    "EmployeeEvaluation",
    "EvaluationScore",
    "EvaluationLevelBackup",
    "EvaluationCycle",
]
