"""
مولّد رقم تذكرة فريد بصيغة SOS-YYYYMMDD-XXXX
حيث XXXX = 4 أحرف عشوائية hex (16^4 = 65536 احتمال/يوم).

الفرادة على مستوى DB مضمونة عبر unique=True في حقل ticket_number.
هذا المولّد يحاول 10 مرات كحدّ أقصى لتجنّب صدام نادر.
"""

import secrets

from django.utils import timezone

TICKET_PREFIX = "SOS"
MAX_ATTEMPTS_DEFAULT = 10


def generate_ticket_number() -> str:
    """يولّد رقم تذكرة جديد. الفرادة تُضمن بـ unique constraint في DB."""
    today = timezone.now().strftime("%Y%m%d")
    suffix = secrets.token_hex(2).upper()  # 4 hex chars
    return f"{TICKET_PREFIX}-{today}-{suffix}"


def generate_unique_ticket_number(
    model_class,
    max_attempts: int = MAX_ATTEMPTS_DEFAULT,
) -> str:
    """يولّد رقم ويتأكد من عدم تكراره في DB.

    يرفع RuntimeError إذا فشل بعد max_attempts (نادر جداً: احتمال < 1/65000).
    """
    for _ in range(max_attempts):
        candidate = generate_ticket_number()
        if not model_class.objects.filter(ticket_number=candidate).exists():
            return candidate
    raise RuntimeError("فشل توليد رقم تذكرة فريد بعد 10 محاولات")
