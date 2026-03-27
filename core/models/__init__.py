# ══════════════════════════════════════════════════════════════════════
# core/models/__init__.py
# تجميع كل نماذج core في مكان واحد للتوافق الخلفي الكامل
# ══════════════════════════════════════════════════════════════════════

# ── التوافق الخلفي مع النماذج المنقولة لتطبيقاتها ────────────────────
# from core.models import HealthRecord  ← لا يزال يعمل
from behavior.models import BehaviorInfraction, BehaviorPointRecovery  # noqa: F401,E402
from clinic.models import ClinicVisit, HealthRecord  # noqa: F401,E402
from library.models import BookBorrowing, LibraryActivity, LibraryBook  # noqa: F401,E402
from transport.models import BusRoute, SchoolBus  # noqa: F401,E402

from ._crypto import _get_fernet, decrypt_field, encrypt_field, hmac_field  # noqa: F401
from .academic import AcademicYear, ClassGroup, ParentStudentLink, StudentEnrollment  # noqa: F401
from .access import (  # noqa: F401
    ACADEMIC_ROLES,
    ADMIN_ROLES,
    ALL_STAFF_ROLES,
    LEADERSHIP,
    TIER_1_LEADERSHIP,
    TIER_2_DEPUTIES,
    TIER_3_SUPERVISORS,
    TIER_4_STAFF,
    TIER_5_BENEFICIARIES,
    Membership,
    Role,
)
from .audit import AuditLog, BreachReport, ConsentRecord, ErasureRequest  # noqa: F401
from .department import Department  # noqa: F401
from .permission_audit import PermissionAuditLog  # noqa: F401
from .base import (  # noqa: F401
    AuditedModel,
    SchoolScopedModel,
    SoftDeleteModel,
    TimeStampedModel,
)
from .school import School, _uuid  # noqa: F401
from .user import (  # noqa: F401
    CustomUser,
    Profile,
    _national_id_validator,
    _phone_validator,
)

__all__ = [
    # abstract base models
    "TimeStampedModel",
    "AuditedModel",
    "SoftDeleteModel",
    "SchoolScopedModel",
    # crypto utils
    "_get_fernet",
    "encrypt_field",
    "decrypt_field",
    "hmac_field",
    # core
    "_uuid",
    "School",
    "CustomUser",
    "Profile",
    "Role",
    "Membership",
    "AcademicYear",
    "ClassGroup",
    "StudentEnrollment",
    "ParentStudentLink",
    "AuditLog",
    "ConsentRecord",
    "BreachReport",
    "ErasureRequest",
    "Department",
    "PermissionAuditLog",
    # re-exported from sub-apps
    "HealthRecord",
    "ClinicVisit",
    "BehaviorInfraction",
    "BehaviorPointRecovery",
    "SchoolBus",
    "BusRoute",
    "LibraryBook",
    "BookBorrowing",
    "LibraryActivity",
]
