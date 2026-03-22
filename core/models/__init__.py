# ══════════════════════════════════════════════════════════════════════
# core/models/__init__.py
# تجميع كل نماذج core في مكان واحد للتوافق الخلفي الكامل
# ══════════════════════════════════════════════════════════════════════

from behavior.models import BehaviorInfraction, BehaviorPointRecovery  # noqa: F401,E402

# ── التوافق الخلفي مع النماذج المنقولة لتطبيقاتها ────────────────────
# from core.models import HealthRecord  ← لا يزال يعمل
from clinic.models import ClinicVisit, HealthRecord  # noqa: F401,E402
from library.models import BookBorrowing, LibraryActivity, LibraryBook  # noqa: F401,E402
from transport.models import BusRoute, SchoolBus  # noqa: F401,E402

from ._crypto import _get_fernet, decrypt_field, encrypt_field  # noqa: F401
from .academic import ClassGroup, ParentStudentLink, StudentEnrollment  # noqa: F401
from .access import Membership, Role  # noqa: F401
from .audit import AuditLog, BreachReport, ConsentRecord, ErasureRequest  # noqa: F401
from .school import School, _uuid  # noqa: F401
from .user import (  # noqa: F401
    CustomUser,
    Profile,
    _national_id_validator,
    _phone_validator,
)

__all__ = [
    # crypto utils
    "_get_fernet",
    "encrypt_field",
    "decrypt_field",
    # core
    "_uuid",
    "School",
    "CustomUser",
    "Profile",
    "Role",
    "Membership",
    "ClassGroup",
    "StudentEnrollment",
    "ParentStudentLink",
    "AuditLog",
    "ConsentRecord",
    "BreachReport",
    "ErasureRequest",
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
