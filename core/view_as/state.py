"""حالةُ «العرض بصفة» في الجلسة الخادميّة: العلامةُ الموقَّعة، وحدُّ التبديل، وصفةُ الفاعل لسجلّ التدقيق.

العلامةُ في الجلسة (قاعدةٌ أو ذاكرةٌ مؤقّتة على الخادم، لا كعكة) وموقَّعةٌ فوق ذلك: فلا تُقبل علامةٌ لم يصدرها هذا
الكود ولو كُتبت في مخزن الجلسات. وتحمل الفاعلَ والدورَ (أو الحسابَ المرتبط) ولحظةَ البدء، وتُفحص في كلّ طلب.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import redis
from django.core import signing
from django.core.cache import cache

logger = logging.getLogger(__name__)

#: سقوطُ Redis كما يلتقطه `core/ratelimit_safe.py` — يقرؤه الحدُّ هنا والقفلُ في `linked.py`.
CACHE_DOWN = (OSError, redis.exceptions.RedisError)

ROLE_KEY = "view_as_role"
ROLE_SEEN_KEY = "view_as_role_seen"
LINKED_KEY = "view_as_linked"
LINKED_SEEN_KEY = "view_as_linked_seen"
REAUTH_KEY = "view_as_reauth"  # pragma: allowlist secret — اسمُ مفتاحٍ في الجلسة لا سرّ

ROLE_SALT = "core.view_as.role"
LINKED_SALT = "core.view_as.linked"
REAUTH_SALT = "core.view_as.reauth"

PREVIEW = "preview"
LINKED = "linked"


def now() -> int:
    return int(time.time())


@dataclass(frozen=True)
class ViewAs:
    """ما يُعرض الآن ومن يعرضه — يوضع على `request.view_as` لكلّ طلبٍ في أحد الوضعين."""

    kind: str
    actor_id: str
    started: int
    role: str = ""
    target_id: str = ""
    link_id: str = ""

    @property
    def is_preview(self) -> bool:
        return self.kind == PREVIEW

    @property
    def is_linked(self) -> bool:
        return self.kind == LINKED

    def acting(self) -> dict[str, str]:
        """الحقلان اللذان يحملهما كلُّ سطر تدقيقٍ أثناءه: المنفّذُ الفعليّ والصفةُ المعروضة (شرطُ 0104)."""
        if self.is_linked:
            return {"actor": self.actor_id, "as_user": self.target_id}
        return {"actor": self.actor_id, "as_role": self.role}


def sign(payload: dict[str, Any], salt: str) -> str:
    return signing.dumps(payload, salt=salt)


def unsign(token: Any, salt: str) -> dict[str, Any] | None:
    """الحمولةُ إن صحّ توقيعها وإلّا None — والمدّةُ تُفحص من `s` لا من التوقيع (التبديلُ لا يمدّ السقف)."""
    if not isinstance(token, str):
        return None
    try:
        payload = signing.loads(token, salt=salt)
    except signing.BadSignature:
        return None
    return payload if isinstance(payload, dict) else None


def allow_switch(actor_id: Any, kind: str, per_hour: int) -> bool:
    """حدُّ التبديل في نافذةٍ ساعيّةٍ تبدأ من أوّل تبديل — يُعدّ هذا الطلبُ منها.

    وإن سقط Redis رُفض التبديلُ (429) ولم يسقط 500 — لا تبديلَ بلا عدٍّ (ملاحظةُ 0104).
    """
    key = f"view_as:switches:{kind}:{actor_id}"
    try:
        cache.add(key, 0, timeout=3600)
        try:
            count = cache.incr(key)
        except ValueError:  # انقضى المفتاحُ بين add وincr
            cache.set(key, 1, timeout=3600)
            count = 1
    except CACHE_DOWN:
        logger.warning("view_as: switch limit store unavailable for actor %s", actor_id)
        return False
    return count <= per_hour


def acting_for_current_request() -> dict[str, str] | None:
    """صفةُ الفاعل في الطلب الجاري إن كان يعرض بصفة — يقرؤها `AuditLog.save` لكلّ سطرٍ جديد."""
    from core.middleware import get_current_request

    request = get_current_request()
    view_as = getattr(request, "view_as", None)
    return view_as.acting() if isinstance(view_as, ViewAs) else None


def with_acting(changes: Any, acting: dict[str, str]) -> Any:
    """`changes` وفيه `acting` — ولا يُستبدل ما كتبه المستدعي صراحةً."""
    if changes is None:
        return {"acting": acting}
    if isinstance(changes, dict):
        if "acting" in changes:
            return changes
        return {**changes, "acting": acting}
    return {"value": changes, "acting": acting}
