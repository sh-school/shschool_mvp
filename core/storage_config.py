"""core/storage_config.py — بناء STORAGES["default"] لـS3/R2، مشتركٌ بين إعدادات التطوير والإنتاج.

كان هذا الحسابُ مكتوباً مرّةً واحدة في `production.py` فقط، خلف `if USE_S3:`
تتراجع صامتةً إلى `DatabaseStorage` عند نقص المفاتيح — تراجعٌ خطيرٌ في
الإنتاج تحديداً: يعني فقدان ملفٍّ رفعه مستخدمٌ بلا أن يلاحظ أحد (حاويةُ الويب
على Railway بلا قرصٍ دائم). البند 11 يجعل S3 إلزامياً في الإنتاج — فمن يستدعي
هذه الدالّة هناك يريد `ImproperlyConfigured` صريحةً عند نقص المفاتيح، لا
تحذيراً يُبتلع.

والتطويرُ يبقى اختيارياً (`USE_S3` راية Opt-in لكلّ شجرة عملٍ على حدة) —
هذه الدالّة لا تفرض ذلك، فقط تبني الإعداد حين يُستدعى بها.
"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured


def s3_default_storage(
    *,
    access_key_id: str,
    secret_access_key: str,
    bucket_name: str,
    region_name: str,
    endpoint_url: str,
    querystring_expire: int,
    custom_domain: str = "",
) -> tuple[dict, str]:
    """(إعدادُ `STORAGES["default"]`، رابطُ `media`) — أو `ImproperlyConfigured` إن نقصت المفاتيح."""
    if not all([access_key_id, secret_access_key, bucket_name]):
        raise ImproperlyConfigured(
            "USE_S3 مفعَّلٌ لكن AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY/"
            "AWS_STORAGE_BUCKET_NAME ناقصة — أضفها إلى .env قبل الإقلاع."
        )

    storage = {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "bucket_name": bucket_name,
            "region_name": region_name,
            "endpoint_url": endpoint_url or None,
            "location": "media",
            "file_overwrite": False,
            "default_acl": "private",
            "querystring_auth": True,
            "querystring_expire": querystring_expire,
            "object_parameters": {
                "ContentDisposition": "inline",
            },
        },
    }

    if custom_domain:
        media_url = f"https://{custom_domain}/media/"
    elif endpoint_url:
        media_url = f"{endpoint_url}/{bucket_name}/media/"
    else:
        media_url = f"https://{bucket_name}.s3.{region_name}.amazonaws.com/media/"

    return storage, media_url
