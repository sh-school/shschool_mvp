"""
خدمة تعمية معرّف المستخدم (SHA-256) قبل إرساله إلى الإيميل الخارجي.
تحمي هوية المستخدم وفق متطلبات PDPPL — لا يمكن عكس الـ hash.

الاستخدام:
    from developer_feedback.services.hashing import hash_user_id

    msg.user_id_hash = hash_user_id(request.user.id)
"""

import hashlib

from django.conf import settings


def hash_user_id(user_id: int | str) -> str:
    """يعيد sha256 لـ user_id + SECRET_KEY كـ salt.

    النتيجة: 64 char hex string — آمن للإرسال عبر SMTP.
    """
    salt = settings.SECRET_KEY.encode("utf-8")
    raw = f"{salt.decode()}:user:{user_id}".encode()
    return hashlib.sha256(raw).hexdigest()


def verify_user_id(user_id: int | str, candidate_hash: str) -> bool:
    """يتحقق من تطابق user_id مع hash معروف."""
    return hash_user_id(user_id) == candidate_hash
