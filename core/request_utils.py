"""
core/request_utils.py — أدوات استخراج بيانات الطلب.

get_client_ip: عنوان IP الحقيقي للعميل خلف وكيل عكسي واحد موثوق (Railway).
يأخذ آخر إدخال في X-Forwarded-For — وهو ما يضبطه الوكيل (غير قابل للتزوير من العميل،
بخلاف الإدخال الأول)، وإلا REMOTE_ADDR. لبيئة بعدّة وكلاء عدّل منطق الثقة وفق البنية.
"""


def get_client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "") if request else ""
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if parts:
        return parts[-1]
    return (request.META.get("REMOTE_ADDR", "") if request else "") or ""
