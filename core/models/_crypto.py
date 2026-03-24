import logging

from django.conf import settings

try:
    from cryptography.fernet import Fernet, InvalidToken

    _FERNET_AVAILABLE = True
except ImportError:
    _FERNET_AVAILABLE = False
    InvalidToken = Exception  # fallback

logger = logging.getLogger(__name__)


def _get_fernet():
    if not _FERNET_AVAILABLE:
        return None
    key = getattr(settings, "FERNET_KEY", None)
    if not key:
        if getattr(settings, "DEBUG", True):
            import logging

            logging.getLogger(__name__).warning(
                "⚠️ FERNET_KEY غير مضبوط — البيانات الصحية بدون تشفير"
            )
            return None
        else:
            from django.core.exceptions import ImproperlyConfigured

            raise ImproperlyConfigured("FERNET_KEY مطلوب في الإنتاج. أضفه إلى .env")
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError, UnicodeDecodeError) as e:
        logger.error("FERNET_KEY غير صالح: %s", e)
        return None


def encrypt_field(value):
    if not value:
        return value
    f = _get_fernet()
    if not f:
        return value
    return f.encrypt(value.encode()).decode()


def decrypt_field(value):
    if not value:
        return value
    f = _get_fernet()
    if not f:
        return value
    try:
        return f.decrypt(value.encode()).decode()
    except (InvalidToken, ValueError, TypeError, UnicodeDecodeError):
        logger.exception("فشل فك تشفير الحقل — إعادة القيمة الأصلية")
        return value


# ── HMAC for searchable encrypted fields ─────────────────────────
import hashlib
import hmac as _hmac


def hmac_field(value: str) -> str:
    """
    HMAC-SHA256 — يُنتج hash حتمي (deterministic) للبحث والتفرد.
    لا يمكن عكسه إلى القيمة الأصلية.
    يُستخدم مع national_id: يُخزّن HMAC في عمود مفهرس للبحث،
    والقيمة المشفّرة بـ Fernet في عمود آخر للعرض.
    """
    if not value:
        return ""
    key = getattr(settings, "FERNET_KEY", "")
    if not key:
        # لا يوجد مفتاح — أعد القيمة الأصلية كـ fallback
        return value
    key_bytes = key.encode() if isinstance(key, str) else key
    return _hmac.new(key_bytes, value.strip().encode(), hashlib.sha256).hexdigest()
