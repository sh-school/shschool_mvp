"""التطبيقُ المثبَّت بلا طريقٍ مسدود (بلاغ 2026-09-14، لقطةٌ من آيفون).

المنصّةُ مثبَّتةً على الجوال بلا شريطِ متصفّح، وآيفون لا يعطي فيها زرَّ رجوع:

- ملفُّ PDF كان يُعرض مكانَ المنصّة بعارض النظام فلا يُخرج منه إلّا بإغلاق
  التطبيق — حتى ما يُطلب تنزيلاً (`as_attachment=True`). فكلُّ رابطِ ملفٍّ يحمل
  `data-app-file`، وjs/app-mode.js يسلّمه لقائمة المشاركة بدل الانتقال إليه.
- الأوراقُ المستقلّة (لا تمتدّ من base.html) تحمل شريطَ «رجوع إلى المنصّة».

والحارسُ هنا لأنّ الفخَّ يعود من أوّل زرِّ PDF يُضاف بلا وسم.
"""

import pathlib
import re

from django.template.loader import render_to_string

TEMPLATES = pathlib.Path("templates")

#: ما يدلّ على أنّ الرابطَ ملفٌّ لا صفحة.
FILE_HINTS = re.compile(
    "|".join(
        [
            r"\{%\s*url\s+['\"][^'\"]*pdf['\"]",  # مساراتُ الملفّات تنتهي بـpdf
            r"export=pdf",
            r"download=1",
            r"\.file\.url",
            r"protected_media",
            r"\sdownload[\s>]",
        ]
    )
)
TAG = re.compile(r"<(?:a|button)\b[^>]*>", re.S)

#: صفحاتٌ كاملةٌ بلا base.html ولا تحتاج الشريط: الدخولُ قبل المنصّة، والبريدُ
#: لا يُفتح فيها، وصفحةُ الخطأ لها رابطا رجوعٍ، وصفحتا «بلا اتّصال» لا منصّةَ خلفهما.
STANDALONE_EXEMPT = {
    "auth/login.html",
    "base/base.html",
    "email/_base.html",
    "errors/_error_page.html",
    "parents/pwa/offline.html",
    "pwa/offline_global.html",
}


def _templates():
    return sorted(TEMPLATES.rglob("*.html"))


def test_every_file_link_is_handed_to_the_share_sheet_in_the_app():
    untagged = [
        f"{path.as_posix()}: {' '.join(tag.split())[:120]}"
        for path in _templates()
        for tag in TAG.findall(path.read_text(encoding="utf-8"))
        if FILE_HINTS.search(tag) and "data-app-file" not in tag
    ]

    assert not untagged, "روابطُ ملفّاتٍ بلا data-app-file — طريقٌ مسدودٌ في التطبيق:\n" + "\n".join(
        untagged
    )


def test_every_standalone_page_carries_the_back_bar():
    missing = []
    for path in _templates():
        src = path.read_text(encoding="utf-8")
        rel = path.relative_to(TEMPLATES).as_posix()
        if "<body" not in src or "{% extends" in src or rel in STANDALONE_EXEMPT:
            continue
        if '{% include "components/app_back_bar.html" %}' not in src:
            missing.append(rel)

    assert not missing, f"أوراقٌ مستقلّةٌ بلا شريط رجوع: {missing}"


def test_the_back_bar_is_born_hidden_and_never_printed():
    """خارج التطبيق لا يُرى، ومولّدُ PDF يحترم `hidden` فلا يبلغ الورق."""
    html = render_to_string("components/app_back_bar.html")

    assert re.search(r"<div[^>]*data-app-back-bar[^>]*\shidden", html)
    assert 'href="/dashboard/"' in html  # يعمل بلا سكربت
    assert "@media print" in html
    assert "js/app-mode.js" in html


def test_the_platform_frame_loads_app_mode():
    assert "js/app-mode.js" in (TEMPLATES / "base/base.html").read_text(encoding="utf-8")


def test_app_mode_script_keeps_its_contract():
    """ما تعتمد عليه القوالبُ والحارسُ أعلاه — لا يُعاد تسميتُه من طرفٍ واحد."""
    src = pathlib.Path("static/js/app-mode.js").read_text(encoding="utf-8")

    for needle in (
        "(display-mode: standalone)",
        "data-app-file",
        "data-app-back-bar",
        "data-app-back",
        "NotAllowedError",  # سفاري: ضغطةٌ ثانيةٌ حين يتأخّر الملفّ
        "window.top !== window",  # الورقةُ داخل إطار المنصّة بلا شريط
    ):
        assert needle in src, needle


def test_the_pages_view_offers_one_pdf_button_on_touch_screens():
    """زرُّ PDF العلويُّ يختفي على اللمس مع «طباعة» — ويبقى الكبيرُ تحت «فتح الجداول»."""
    src = (TEMPLATES / "schedule/pages_view.html").read_text(encoding="utf-8")
    header_pdf = re.search(r"<a[^>]*schedule_pages_pdf[^>]*btn-sm[^>]*>", src)

    assert header_pdf and "schedule-frame-print" in header_pdf.group(0)
