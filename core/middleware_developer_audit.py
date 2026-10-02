"""سجلُّ تدقيقٍ لدخول مطوّر المنصّة صفحاتِ الصحّة والتظلّم والتقييم — يسجَّل ولا يمنع (قرار المالك).

بعد رفع الحظر عن `platform_developer` (D-118م) صار يبلغ بياناتٍ حسّاسةً لطلبةٍ وموظّفين حقيقيّين؛
فيبقى الأثرُ: كلُّ طلبٍ ناجحٍ منه على هذه المسارات سطرٌ في `AuditLog` بمساره وطريقته ونتيجته. لا منعَ
ولا تحقّقَ ثنائيّاً (قرارُ المالك: يحفظ الصلاحيّةَ ويُبقي أثراً)، وعطلُ التسجيل نفسِه لا يُسقط الطلب.

يشمل مساراتِ الصفحات وواجهاتِ API معاً (توصية 0105): عيادة المدرسة (`/clinic/`، `/api/v1/clinic/`)،
وتقييمُ الأداء والتظلّمات (`/quality/evaluations/`، وفيها `/quality/evaluations/grievances/`).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from django.http import HttpRequest
from django.http.response import HttpResponseBase

from core.unrestricted_role import has_unrestricted_role

logger = logging.getLogger(__name__)

#: المسارات الحسّاسة التي يُدقَّق عليها دخولُ المطوّر: صحّةٌ، تقييمُ أداء، تظلّمات.
AUDITED_PREFIXES = (
    "/clinic/",
    "/api/v1/clinic/",
    "/quality/evaluations/",
    # ملفُّ الطالب (صفحةً وPDF) يعرض السجلَّ الصحّيَّ وزياراتِ العيادة خارج /clinic/ (مراجعة 0105 على #781).
    "/student-affairs/profile/",
)

#: اعتمادُ الجدول وتقييم الأداء بيد المطوّر (قرارُ المالك على #781): يُسجَّل بوسمٍ مميَّز «بصفة مطوّر»
#: فيفترق عن اعتماد صاحب الاختصاص، بدل أن يضيع بين أسطر العرض.
APPROVAL_SUFFIX = "/approve/"
CAPACITY_LABEL = "بصفة مطوّر"


def _is_approval(request: HttpRequest) -> bool:
    return request.method == "POST" and (
        request.path.startswith("/quality/evaluations/approve/")
        or (
            request.path.startswith("/teacher/smart-schedule/")
            and request.path.endswith(APPROVAL_SUFFIX)
        )
    )


#: طرقُ الكتابة: كلُّ طلبٍ ناجحٍ بها من حساب المطوّر يُوسم «بصفة مطوّر» على أيّ مسار، لا على قائمة
#: مساراتٍ مسمّاة تتقادم (حكمُ 0105 C2 وقرارُ المالك على #781).
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _is_write(request: HttpRequest) -> bool:
    return request.method in WRITE_METHODS


class DeveloperAccessAuditMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        response = self.get_response(request)
        if response.status_code < 400 and (
            request.path.startswith(AUDITED_PREFIXES) or _is_write(request)
        ):
            self._audit(request, response)
        return response

    @staticmethod
    def _audit(request: HttpRequest, response: HttpResponseBase) -> None:
        try:
            user = getattr(request, "user", None)
            if not has_unrestricted_role(user):
                return
            from core.models import AuditLog

            approval = _is_approval(request)
            write = _is_write(request)
            changes = {
                "path": request.path,
                "method": request.method,
                "status": response.status_code,
                "via": "platform_developer",
            }
            if write:
                changes["capacity"] = CAPACITY_LABEL
            if approval:
                changes["approval"] = True
            if approval:
                label = f"اعتمادٌ {CAPACITY_LABEL}: {request.path}"
            elif write:
                label = f"فعلٌ {CAPACITY_LABEL}: {request.method} {request.path}"
            else:
                label = f"دخول مطوّر المنصّة: {request.method} {request.path}"
            AuditLog.log(
                user=user,
                action="update" if write else "view",
                model_name="other",
                object_repr=label,
                changes=changes,
                request=request,
            )
        except Exception:  # noqa: BLE001 — التدقيق لا يُسقط الطلب
            logger.exception("developer access audit failed path=%s", request.path)
