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
)


class DeveloperAccessAuditMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        response = self.get_response(request)
        path = request.path
        if path.startswith(AUDITED_PREFIXES) and response.status_code < 400:
            self._audit(request, response)
        return response

    @staticmethod
    def _audit(request: HttpRequest, response: HttpResponseBase) -> None:
        try:
            user = getattr(request, "user", None)
            if not has_unrestricted_role(user):
                return
            from core.models import AuditLog

            AuditLog.log(
                user=user,
                action="view",
                model_name="other",
                object_repr=f"دخول مطوّر المنصّة: {request.method} {request.path}",
                changes={
                    "path": request.path,
                    "method": request.method,
                    "status": response.status_code,
                    "via": "platform_developer",
                },
                request=request,
            )
        except Exception:  # noqa: BLE001 — التدقيق لا يُسقط الطلب
            logger.exception("developer access audit failed path=%s", request.path)
