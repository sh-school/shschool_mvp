from django.conf import settings

try:
    from cryptography.fernet import Fernet

    _FERNET_AVAILABLE = True
except ImportError:
    _FERNET_AVAILABLE = False


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
    except Exception as e:
        import logging

        logging.getLogger(__name__).error("FERNET_KEY غير صالح: %s", e)
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
    except Exception:
        return value
