# scripts/test-docker.ps1 — الاختبارات داخل حاوية التطوير كما يشغّلها CI تماماً.
#
# `docker exec … pytest` وحدَها تُشغّل الاختبارات على إعدادات *التطوير*: متغيّرُ
# البيئة DJANGO_SETTINGS_MODULE في الحاوية يتغلّب على pytest.ini، وهناك Redis
# موجودٌ فـCelery غيرُ فوريّ — فمهمّةُ التوليد تذهب إلى العامل الحقيقيّ خارج
# معاملة الاختبار ويرى الاختبارُ «queued». فتخضرّ اختباراتٌ كاذبةً وتحمرّ صادقة.
# (النظيرُ لـ`make test-docker` لمن لا `make` عنده.)
#
# الاستعمال:
#   .\scripts\test-docker.ps1                       # كلّ الاختبارات
#   .\scripts\test-docker.ps1 tests/test_x.py       # ملفٌّ بعينه
#   .\scripts\test-docker.ps1 tests/test_x.py -k foo

param([Parameter(ValueFromRemainingArguments = $true)] [string[]] $PytestArgs = @("tests/"))

$inner = "DJANGO_SETTINGS_MODULE=shschool.settings.testing " +
         "TEST_DB_HOST=`$DB_HOST TEST_DB_PORT=`$DB_PORT " +
         "TEST_DB_USER=`$DB_USER TEST_DB_PASSWORD=`$DB_PASSWORD " +
         "python -m pytest $($PytestArgs -join ' ') -q -p no:cacheprovider"

docker exec -i shschool-dev-web sh -c $inner
exit $LASTEXITCODE
