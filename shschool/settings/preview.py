"""
shschool/settings/preview.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
المعاينةُ المركزيّةُ المحلّيّة — إعداداتُ الإنتاج نفسُها إلّا ما لا يُملَك على الجهاز.

الغرضُ (docker-compose.preview.yml، scripts/preview.sh): أن يرى صاحبُ القرار `main` بوضع
الإنتاج قبل أن يُرقّى الإنتاجُ — `DEBUG` مطفأ، وdaphne، والملفّاتُ الثابتةُ بالبصمة
والتصغير، وCSP مفروضة — فما يكسر في الإنتاج يكسر هنا قبلَه. لذلك تستورد هذه الوحدةُ
`production` كاملاً وتغيّر ثلاثةَ أشياءَ فقط:

  ١. التخزين. الإنتاجُ يفرض S3 ويسقط عند الإقلاع بلا مفاتيحه (البند 11)، ومفاتيحُ
     الإنتاج الحقيقيّةُ لا تُوضَع هنا أبداً وإلّا كتبت المعاينةُ في حاويته. فيُمرَّر في
     `docker-compose.preview.yml` مفتاحٌ شكليٌّ يجتاز فحصَ الإقلاع وحدَه، ثمّ يُستبدَل
     الوجهُ هنا بـ`DatabaseStorage` كما في التطوير — فلا اتّصالَ بأيّ S3.
  ٢. http. لا إعادةَ توجيهٍ إلى https ولا HSTS ولا كوكي `Secure`: المعاينةُ على
     `http://localhost`، وأحياناً على عنوان الشبكة لمعاينة الجوال، والمتصفّحُ يرفض كوكي
     `Secure` عبر http على غير `localhost`.
  ٣. اسمُ الكوكي. الخوادمُ كلُّها على `localhost` والمتصفّحُ يُفرز الكوكي بالمضيف لا
     بالمنفذ، فيُخرج الدخولُ إلى خادمٍ صاحبَه من آخر (انظر development.py). فللمعاينة
     كوكيُّها.

وما عدا ذلك لا يُمسّ: البريدُ يبقى `UndeliveredEmailBackend` (يُمرَّر في الإنشاء)، وSentry
مُطفأ (لا DSN)، وRedis في قاعدةٍ منطقيّةٍ خاصّة فلا يلتقط عاملٌ آخرُ مهامَّها.
"""

from . import base as _base
from .production import *  # noqa: F401,F403

# ── ١. التخزين: قاعدةُ البيانات لا S3 ─────────────────────────
# نسخةٌ لا تعديلٌ في المكان: القاموسُ نفسُه مستورَدٌ من production.
STORAGES = dict(STORAGES)
STORAGES["default"] = {"BACKEND": "core.db_storage.DatabaseStorage"}
MEDIA_URL = _base.MEDIA_URL

# ── ٢. http ────────────────────────────────────────────────────
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# ── ٣. الكوكي ──────────────────────────────────────────────────
SESSION_COOKIE_NAME = "sessionid_preview"
CSRF_COOKIE_NAME = "csrftoken_preview"
