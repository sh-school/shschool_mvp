"""
core/request_utils.py — أدوات استخراج بيانات الطلب.

get_client_ip: عنوانُ العميل الحقيقيّ خلف وكيلٍ عكسيّ.

كان يأخذ **آخرَ** إدخالٍ في X-Forwarded-For على افتراض أنّ الوكيل يضع العميلَ
آخراً. وRailway لا يفعل: يُلحق العميلَ ثمّ قفزةَ حافّته، فيصير الأخيرُ عنوانَ
الحافّة لا العميل. سجّل الحارسُ `internal_only` ما رآه في 2026-09-05:

    XFF='176.202.42.52, 152.233.12.245'   REMOTE_ADDR='100.64.0.8'

الأوّلُ عميلٌ في قطر، والثاني الحافّة، والثالثُ الوكيلُ الداخليّ. فكانت قائمةُ
السماح على /metrics لا تطابق أحداً، وسجلّاتُ التدقيق تكتب عنواناً واحداً للجميع.

القاعدة: عددُ القفزات الموثوقة `TRUSTED_PROXY_HOPS` (الإنتاج 1، محلّياً 0) —
العميلُ هو الإدخالُ الذي قبل تلك القفزات من اليمين؛ وما قبله في القائمة كتبه
العميلُ نفسُه فلا يُصدَّق. وبلا وكيلٍ موثوق تُهمَل الترويسةُ كلُّها.
"""

from django.conf import settings


def get_client_ip(request) -> str:
    if not request:
        return ""
    remote = request.META.get("REMOTE_ADDR", "") or ""
    hops = int(getattr(settings, "TRUSTED_PROXY_HOPS", 0) or 0)
    if hops <= 0:
        return remote

    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if not parts:
        return remote
    # الحافّةُ أضافت `hops` إدخالاً من اليمين؛ العميلُ هو الذي قبلها. وإن جاءت
    # القائمةُ أقصرَ — وكيلٌ لم يُلحق شيئاً — فآخرُ ما هناك.
    index = len(parts) - hops - 1
    return parts[index] if index >= 0 else parts[-1]
