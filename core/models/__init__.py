# ══════════════════════════════════════════════════════════════════════
# core/models/__init__.py
# تجميع كل نماذج core في مكان واحد للتوافق الخلفي الكامل
# ══════════════════════════════════════════════════════════════════════

from ._crypto import _get_fernet, encrypt_field, decrypt_field          # noqa: F401

from .school import _uuid, School                                        # noqa: F401

from .user import (                                                       # noqa: F401
    CustomUser,
    Profile,
    _national_id_validator,
    _phone_validator,
)

from .access import Role, Membership                                      # noqa: F401

from .academic import ClassGroup, StudentEnrollment, ParentStudentLink   # noqa: F401

from .audit import AuditLog, ConsentRecord, BreachReport, ErasureRequest  # noqa: F401

# ── التوافق الخلفي مع النماذج المنقولة لتطبيقاتها ────────────────────
# from core.models import HealthRecord  ← لا يزال يعمل
from clinic.models    import HealthRecord, ClinicVisit                   # noqa: F401,E402
from behavior.models  import BehaviorInfraction, BehaviorPointRecovery  # noqa: F401,E402
from transport.models import SchoolBus, BusRoute                         # noqa: F401,E402
from library.models   import LibraryBook, BookBorrowing, LibraryActivity # noqa: F401,E402

__all__ = [
    # crypto utils
    "_get_fernet", "encrypt_field", "decrypt_field",
    # core
    "_uuid",
    "School",
    "CustomUser", "Profile",
    "Role", "Membership",
    "ClassGroup", "StudentEnrollment", "ParentStudentLink",
    "AuditLog", "ConsentRecord", "BreachReport", "ErasureRequest",
    # re-exported from sub-apps
    "HealthRecord", "ClinicVisit",
    "BehaviorInfraction", "BehaviorPointRecovery",
    "SchoolBus", "BusRoute",
    "LibraryBook", "BookBorrowing", "LibraryActivity",
]
