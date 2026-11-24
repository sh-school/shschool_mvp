"""كتابةُ شاشة طلب الانتقال: تحضيرُ الطلب وحفظُه وتنفيذُ النقل المباشر (W-20261124-001).

طبقةُ خدماتٍ للعرض `transfer_create_views`؛ منطقُ الانتقال والاعتماد كما هو في
`internal_transfer` و`transfer_decision` (لا تغيير في من يملك النقل المباشر، D-343م).
"""

from typing import Any

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from core.models import CustomUser

from .internal_transfer import build_request
from .services import StudentService
from .transfer_decision import may_decide, move_directly


def prepare_request(school: Any, data: dict[str, Any], year: str, actor: Any) -> tuple[Any, str]:
    """طلبُ النموذج المتحقَّق منه: يفحص صلاحيةَ النقل المباشر أوّلاً ثمّ يجلب الطالبَ ويبني الطلبَ (لا يحفظه).

    يُستدعى في كلّ طلبٍ من طلبَي النقل المباشر (المراجعة والتأكيد) فتُتحقَّق الصلاحيةُ فيهما معاً.
    """
    if data["direct"] and not may_decide(actor):
        raise PermissionDenied("النقل المباشر للمدير أو النائب الإداري.")
    student = get_object_or_404(
        CustomUser, id=data["student_id"], memberships__school=school, memberships__is_active=True
    )
    return build_request(school, student, data, year, actor)


def save_request(transfer: Any, actor: Any) -> None:
    """يحفظ طلبَ انتقالٍ عاديّاً (معلَّقاً) ويسجّل حدثَه في سجلّ التدقيق."""
    transfer.save()
    StudentService.audit_student_event(
        transfer.school, actor, transfer.student, "transfer_requested"
    )


def direct_move(transfer: Any, actor: Any, school: Any) -> str:
    """ينفّذ النقلَ المباشر ويُرجع سببَ الرفض أو «» عند النجاح؛ والصلاحيةُ تُفحص ثانيةً داخل `move_directly`."""
    try:
        move_directly(transfer, actor, school)
    except ValueError as exc:
        return str(exc)
    return ""
