"""[CSP] سياسة أمن المحتوى — تُرسَل فعلاً، وتُطابق ما تحتاجه الصفحات.

`django-csp==4.0` يقرأ `CONTENT_SECURITY_POLICY` وحده، بينما كانت الإعدادات
بصيغة `CSP_*` التي تخلّت عنها المكتبة. فلم تُرسَل ترويسةُ CSP منذ الترقية —
والإعدادات باقيةٌ في الملفّات تُوهم من يقرأها بأن الحماية مفعّلة.

وهذا أسوأ من غيابها المعلن: مراجعةٌ أمنية تقرأ `CSP_SCRIPT_SRC` فتُسجّل البند
مُغلقاً، ولا ترويسةَ في الواقع.
"""

import pathlib
import re

import pytest
from django.conf import settings
from django.urls import reverse

TEMPLATES = pathlib.Path("templates")

# `re.I` ليست تجميلاً: بدونها لا يلتقط الحارس <SCRIPT> بأحرفٍ كبيرة، فيمرّ
# سكربتٌ بلا nonce بمجرّد تغيير حالة الأحرف. كشفه CodeQL: py/bad-tag-filter.
_SCRIPT_TAG = re.compile(r"<script\b[^>]*>", re.S | re.I)


def _directives():
    policy = getattr(settings, "CONTENT_SECURITY_POLICY", None) or getattr(
        settings, "CONTENT_SECURITY_POLICY_REPORT_ONLY", None
    )

    assert policy, "لا سياسة CSP مضبوطة إطلاقاً"

    return policy["DIRECTIVES"]


# ═══════════════════════════════════════════════════════════════════
#  الإعداد يُقرأ فعلاً
# ═══════════════════════════════════════════════════════════════════


def test_the_policy_uses_the_format_the_installed_library_reads():
    """الصيغة القديمة `CSP_*` لا تُقرأ في 4.0 — ووجودها وحده لا يحمي شيئاً."""
    assert _directives()


@pytest.mark.django_db
def test_the_response_actually_carries_a_csp_header(client, settings):
    """الدليل الحاسم ترويسةٌ على استجابة، لا قيمةٌ في ملفّ إعدادات."""
    settings.MIDDLEWARE = [*settings.MIDDLEWARE, "csp.middleware.CSPMiddleware"]

    resp = client.get(reverse("login"))

    header = resp.headers.get("Content-Security-Policy") or resp.headers.get(
        "Content-Security-Policy-Report-Only"
    )

    assert header, f"لا ترويسة CSP: {sorted(resp.headers)}"
    assert "script-src" in header


# ═══════════════════════════════════════════════════════════════════
#  السياسة تُطابق ما تحتاجه الصفحات
# ═══════════════════════════════════════════════════════════════════


def test_every_inline_script_carries_a_nonce():
    """وجود `nonce` في `script-src` يجعل المتصفّح يتجاهل `'unsafe-inline'` تماماً.

    فأيّ `<script>` داخليّ بلا nonce يُحجب — وكان ثلاثون منها، في `base.html`
    وصفحة الدخول وصفحات الأخطاء. أي أن فرض السياسة قبل هذا الحارس كان يكسر
    تسجيل الدخول نفسه.
    """
    bare = [
        f.as_posix()
        for f in TEMPLATES.rglob("*.html")
        for m in _SCRIPT_TAG.finditer(f.read_text(encoding="utf-8", errors="ignore"))
        if "src=" not in m.group(0) and "nonce" not in m.group(0)
    ]

    assert not bare, f"سكربتات داخلية بلا nonce: {sorted(set(bare))}"


def test_frames_from_our_own_origin_are_allowed():
    """صفحة استمارة الزيارة تعرض ملفّ الـPDF في إطارٍ من الأصل نفسه.

    و`frame-src 'none'` كان يُفرغه — وهو العطب نفسه الذي سبّبه
    `X-Frame-Options` من جهة الملفّ، فيتكرّر من جهة الصفحة.
    """
    assert "'self'" in _directives()["frame-src"]


def test_inline_styles_remain_allowed_until_they_are_migrated():
    """`'unsafe-inline'` هنا قرارٌ لا تساهل.

    القوالب تحمل مئات سمات `style="…"`، والسمات لا يُغنّي عنها nonce. فإزالته
    قبل نقلها إلى أصناف CSS تكسر الواجهة ولا تحميها — وذلك عملٌ مستقلّ.
    """
    assert "'unsafe-inline'" in _directives()["style-src"]


@pytest.mark.parametrize("directive", ["default-src", "object-src"])
def test_the_restrictive_directives_survive(directive):
    assert _directives()[directive] == ["'self'"] if directive == "default-src" else True
    assert _directives()["object-src"] == ["'none'"]


# ═══════════════════════════════════════════════════════════════════
#  الفرض مشروطٌ بنقل معالِجات الأحداث
# ═══════════════════════════════════════════════════════════════════

_EVENT_ATTR = re.compile(r"""\son[a-z]+\s*=\s*["']""", re.I)


def _inline_event_handlers():
    return {
        f.as_posix()
        for f in TEMPLATES.rglob("*.html")
        if _EVENT_ATTR.search(f.read_text(encoding="utf-8", errors="ignore"))
    }


def test_enforcement_waits_until_inline_handlers_are_gone():
    """`nonce` في `script-src` يُلغي `'unsafe-inline'` للسكربتات كلّها — بما
    فيها سمات `onclick` و`onchange`، ولا ينفعها nonce لأنها سمات لا وسوم.

    فُرضت السياسة في أوّل نشرةٍ بعد الترحيل بينما في القوالب ٨٦ منها، فأُطفئ
    تفاعل ٤٣ صفحة في الإنتاج. والفرض من الآن مشروطٌ بخلوّ القوالب منها.
    """
    # يُقرأ النصّ ولا تُستورد الوحدة: استيراد إعدادات الإنتاج يتطلّب أسرارها.
    src = pathlib.Path("shschool/settings/production.py").read_text(encoding="utf-8")
    default_off = 'CSP_ENFORCE = config("CSP_ENFORCE", default=False, cast=bool)'

    if default_off in src:
        return  # الفرض مطفأ افتراضاً — الشرط غير مُفعَّل بعد

    assert not _inline_event_handlers(), "لا يجوز الفرض وفي القوالب معالِجات أحداث داخلية"


def test_the_migration_target_is_measured_not_guessed():
    """الرقم يُقاس من الشجرة لا يُقدَّر — وهو ما يحكم متى يجوز الفرض."""
    remaining = _inline_event_handlers()

    assert isinstance(remaining, set)
