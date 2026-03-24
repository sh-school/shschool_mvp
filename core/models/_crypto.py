"""
core/models/_crypto.py
━━━━━━━━━━━━━━━━━━━━━
Encryption utilities for SchoolOS — Fernet + HMAC

✅ v5.2: MultiFernet key rotation support
  - FERNET_KEY: المفتاح الحالي (أول مفتاح)
  - FERNET_OLD_KEYS: مفاتيح قديمة (مفصولة بفاصلة) لفك تشفير البيانات القديمة
  - encrypt_field() يشفّر دائماً بالمفتاح الحالي
  - decrypt_field() يحاول كل المفاتيح (الحالي + القديمة)
"""

import hashlib
import hmac as _hmac
import logging

from django.conf import settings

try:
    from cryptography.fernet import Fernet, InvalidToken, MultiFernet

    _FERNET_AVAILABLE = True
except ImportError:
    _FERNET_AVAILABLE = False
    InvalidToken = Exception  # fallback

logger = logging.getLogger(__name__)


def _get_fernet():
    """
    يُعيد MultiFernet (يدعم key rotation) أو Fernet عادي.
    المفتاح الأول هو الحالي (للتشفير)، والباقي للفك فقط.
    """
    if not _FERNET_AVAILABLE:
        return None

    key = getattr(settings, "FERNET_KEY", None)
    if not key:
        if getattr(settings, "DEBUG", True):
            logger.warning("⚠️ FERNET_KEY غير مضبوط — البيانات الصحية بدون تشفير")
            return None
        else:
            from django.core.exceptions import ImproperlyConfigured

            raise ImproperlyConfigured("FERNET_KEY مطلوب في الإنتاج. أضفه إلى .env")

    try:
        # المفتاح الحالي (يُستخدم للتشفير)
        current = Fernet(key.encode() if isinstance(key, str) else key)

        # المفاتيح القديمة (للفك فقط — key rotation)
        old_keys_str = getattr(settings, "FERNET_OLD_KEYS", "")
        if old_keys_str:
            old_fernets = []
            for k in old_keys_str.split(","):
                k = k.strip()
                if k:
                    old_fernets.append(Fernet(k.encode() if isinstance(k, str) else k))
            if old_fernets:
                return MultiFernet([current] + old_fernets)

        return current
    except (ValueError, TypeError, UnicodeDecodeError) as e:
        logger.error("FERNET_KEY غير صالح: %s", e)
        return None


def encrypt_field(value):
    """تشفير قيمة نصية بالمفتاح الحالي."""
    if not value:
        return value
    f = _get_fernet()
    if not f:
        return value
    return f.encrypt(value.encode()).decode()


def decrypt_field(value):
    """فك تشفير — يحاول المفتاح الحالي ثم القديمة (MultiFernet)."""
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
        return value
    key_bytes = key.encode() if isinstance(key, str) else key
    return _hmac.new(key_bytes, value.strip().encode(), hashlib.sha256).hexdigest()
