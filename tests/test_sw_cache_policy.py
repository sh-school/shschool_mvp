"""
tests/test_sw_cache_policy.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
عاملُ الخدمة لا يخدم أصلاً غيرَ مبصومٍ من ذاكرته أوّلاً.

كان `sw_global.js` يخدم كلَّ `/static/` بسياسة cache-first بذاكرةٍ باسمٍ
ثابت. فأوّلُ نسخةٍ تُحمَّل من `custom.css` تبقى على جهاز المستخدم إلى الأبد:
`Cache-Control: max-age=0` لا يُقرأ أصلاً لأنّ عاملَ الخدمة يجلس **أمام**
الشبكة والترويسات، فلا يبلغها الطلب. و`Ctrl+Shift+R` وحدَه يتخطّاه.

وأبطل ذلك ثلاثةَ أعمالٍ سابقةٍ في التخزين دفعةً واحدة: إزالةُ `?v=`،
و`max-age=0` في التطوير، ووسيطُ `no-store` لصفحات المسجَّلين — كلُّها خلف
الحاجز.

والتخزينُ الأوّليُّ صحيحٌ حيث يحمل الاسمُ بصمةَ محتواه (الإنتاج، عبر
`CompressedManifestStaticFilesStorage`): تغيُّرُ المحتوى يغيّر العنوان.
فالتفرقةُ بالبصمة لا بالمسار.
"""

import pathlib
import re

import pytest

#: عاملا الخدمة في المنصّة — العامُّ وعاملُ بوّابة وليّ الأمر.
WORKERS = [
    pathlib.Path("templates/pwa/sw_global.js"),
    pathlib.Path("templates/parents/pwa/sw.js"),
]

#: سطرٌ في قائمة التخزين المسبق يشير إلى أصلٍ ثابتٍ بلا بصمة.
PRECACHED_STATIC = re.compile(r"""['"](/static/[^'"]+)['"]""")

#: بصمةُ المحتوى كما يكتبها manifest storage.
FINGERPRINTED = re.compile(r"\.[0-9a-f]{8,}\.[a-z0-9]+$", re.I)


@pytest.fixture(params=WORKERS, ids=lambda p: p.name)
def worker(request):
    path = request.param
    assert path.exists(), f"عاملُ خدمةٍ مفقود: {path}"
    return path, path.read_text(encoding="utf-8")


def test_no_worker_precaches_an_unfingerprinted_static_asset(worker):
    """`cache.addAll(['/static/css/custom.css', …])` يثبّت نسخةً لا تُراجَع.

    وهو أوّلُ نصفِ الفخّ: الأصلُ يدخل الذاكرةَ عند التثبيت، ثمّ يخدمه
    `cache-first` إلى الأبد.
    """
    path, src = worker
    # قائمةُ التخزين المسبق هي ما بين `[` و`]` بعد اسمٍ يحوي ASSETS
    m = re.search(r"(?:CACHE_ASSETS|STATIC_ASSETS)\s*=\s*\[(.*?)\]", src, re.S)
    assert m, f"{path}: لا قائمةَ تخزينٍ مسبقٍ يمكن قراءتها"
    offenders = [u for u in PRECACHED_STATIC.findall(m.group(1)) if not FINGERPRINTED.search(u)]
    assert not offenders, (
        f"{path}: أصولٌ بلا بصمةٍ في التخزين المسبق — تبقى قديمةً إلى الأبد:\n  "
        + "\n  ".join(offenders)
    )


#: سطرُ تعريفِ الدالّة — يُطرح قبل البحث عن موضعِ **استعمالها**.
DEFINITION = re.compile(r"^\s*(?:function\s+isFingerprinted|const\s+isFingerprinted\s*=).*$", re.M)


def test_every_worker_checks_the_fingerprint_before_serving_static_from_cache(worker):
    """لا `caches.match` لأصلٍ ثابتٍ إلّا بعد التحقّق من بصمة اسمه.

    ولا يكفي أن تكون الدالّةُ معرَّفةً: أوّلُ صياغةٍ لهذا الفحص اكتفت بوجود
    الاسم، فمرّت وأنا أُعيد `cacheFirst` للجميع عمداً. فيُطرح التعريفُ
    ويُشترط موضعُ نداءٍ بعده.
    """
    path, src = worker
    assert "FINGERPRINTED" in src, f"{path}: لا تعريفَ لبصمة المحتوى — فكلُّ أصلٍ يُخدَم بسياسةٍ واحدة"
    body = DEFINITION.sub("", src)
    assert re.search(
        r"isFingerprinted\s*\(", body
    ), f"{path}: البصمةُ معرَّفةٌ ولا تُنادى — فالسياسةُ واحدةٌ للمبصوم وغيره"


def test_the_fingerprint_pattern_tells_the_two_apart(worker):
    """النمطُ نفسُه يُجرَّب على عنوانين حقيقيّين — وإلّا حَرَسَ بلا تمييز."""
    path, src = worker
    m = re.search(r"FINGERPRINTED\s*=\s*/(.+?)/([a-z]*)\s*;", src)
    assert m, f"{path}: تعريفُ البصمة غيرُ مقروء"
    flags = re.I if "i" in m.group(2) else 0
    pattern = re.compile(m.group(1), flags)
    assert pattern.search("/static/css/custom.06dcd9ebed41.css"), "المبصومُ لم يُعرَف"
    assert not pattern.search("/static/css/custom.css"), "غيرُ المبصوم عُدَّ مبصوماً"


def test_the_served_worker_is_the_reviewed_one(db, client):
    """القالبُ قد يُصلَح ويُخدَم غيرُه — فيُقرأ ما يصل المتصفّحَ فعلاً.

    و`db` لازمةٌ لا لأنّ العاملَ يقرأ القاعدة، بل لأنّ وسائطَ المنصّة
    (المستأجِر والجلسة) تعبر قبل أيّ عرض.
    """
    response = client.get("/sw.js")

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "isFingerprinted" in body, "المخدومُ ليس النسخةَ المُصلَحة"
    assert "schoolos-global-v" in body
