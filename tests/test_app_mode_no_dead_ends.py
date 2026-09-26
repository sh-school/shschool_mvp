"""التطبيقُ المثبَّت بلا طريقٍ مسدود (بلاغ 2026-09-14، لقطةٌ من آيفون).

المنصّةُ مثبَّتةً على الجوال بلا شريطِ متصفّح، وآيفون لا يعطي فيها زرَّ رجوع:

- ملفُّ PDF كان يُعرض مكانَ المنصّة بعارض النظام فلا يُخرج منه إلّا بإغلاق
  التطبيق — حتى ما يُطلب تنزيلاً (`as_attachment=True`). فكلُّ رابطِ ملفٍّ يحمل
  `data-app-file`، وjs/export-center.js (مركزُ التصدير، VI-30أ) يسلّمه لقائمة المشاركة بدل الانتقال إليه.
- الأوراقُ المستقلّة (لا تمتدّ من base.html) تحمل شريطَ «رجوع إلى المنصّة».

والحارسُ هنا لأنّ الفخَّ يعود من أوّل زرِّ PDF يُضاف بلا وسم.
"""

import pathlib
import re

from django.template.loader import render_to_string

TEMPLATES = pathlib.Path("templates")

#: ما يدلّ على أنّ الرابطَ ملفٌّ لا صفحة. أسماءُ مسارات الملفّات على اصطلاحٍ
#: (`…pdf`، `…excel`، `…_export`، `…_template`، `export_…`) يحرسه
#: `test_file_views_follow_the_naming_convention` أدناه.
FILE_URL_NAME = r"(?:[a-z_]+:)?(?:[a-z_]*(?:pdf|excel|xlsx|_export|_template)|export_[a-z_]+)"
FILE_HINTS = re.compile(
    "|".join(
        [
            r"\{%\s*url\s+['\"]" + FILE_URL_NAME + r"['\"]",
            r"(?<![a-z_])export=(?:pdf|excel|xlsx)",
            r"format=(?:pdf|xlsx)",
            r"name=['\"]format['\"][^>]*value=['\"](?:pdf|xlsx)['\"]",  # كشفا الجناح والشعبة
            r"download=1",
            r"\.file\.url",
            r"protected_media",
            r"\sdownload[\s>=]",
        ]
    )
)
#: أسماءٌ على الاصطلاح وهي صفحات — و`weekly_schedule?…&export=` صفحةُ الجدول تبدأ التصديرَ
#: بنفسها بإشعارٍ عائم (export-center.js)، فالرابطُ صفحةٌ لا ملفّ.
PAGE_URL_NAMES = re.compile(r"\{%\s*url\s+['\"](?:student_import_export|weekly_schedule)['\"]")
TAG = re.compile(r"<(?:a|button)\b[^>]*>", re.S)

#: صفحاتٌ كاملةٌ بلا base.html ولا تحتاج الشريط: الدخولُ قبل المنصّة، والبريدُ
#: لا يُفتح فيها، وصفحةُ الخطأ لها رابطا رجوعٍ، وصفحتا «بلا اتّصال» لا منصّةَ خلفهما،
#: وقالبا PDF خالصان لا يُعرضان صفحةً قطّ (كلُّ مساراتهما render_pdf) — والشريطُ
#: فيهما كان يُسقط مولّدَ PDF الاحتياطيّ.
STANDALONE_EXEMPT = {
    "templates/auth/login.html",
    "templates/base/base.html",
    "templates/email/_base.html",
    "templates/errors/_error_page.html",
    "templates/parents/pwa/offline.html",
    "templates/pwa/offline_global.html",
    "templates/behavior/pdf/base_form.html",
    "templates/quality/observation_pdf.html",
}

#: دوالُّ تُرجع ملفّاً وأسماءُ مساراتها خارج الاصطلاح — راجعناها واحدةً واحدة.
FILE_VIEWS_OUTSIDE_CONVENTION = {
    # تقاريرُ الشؤون الأكاديميّة: صفحةٌ، والملفُّ بـ`?export=pdf|excel` (نمطٌ أعلاه).
    "academic_management:academic_progress_reports",
    "academic_management:exam_results_reports",
    "academic_management:monthly_ba_report",
    "academic_management:quiz_reports",
    "observation_pdf_view",  # صفحةٌ عارضة؛ ذكرُ الترويسة في وثيقتها لا في شيفرتها
    "serve_db_file",  # الملفّاتُ المخزَّنة: `.file.url` (نمطٌ أعلاه)
    "student_affairs:protected_media",  # نمطٌ أعلاه
    "api_v1:schema",
    "pwa_manifest",
    "pwa_offline",
    "pwa_sw",
}


def _templates():
    roots = [TEMPLATES, *sorted(p for p in pathlib.Path(".").glob("*/templates") if p.is_dir())]
    return [path for root in roots for path in sorted(root.rglob("*.html"))]


def test_every_file_link_is_handed_to_the_share_sheet_in_the_app():
    """كلُّ رابطٍ أو زرِّ ملفٍّ يحمل الوسمَ الذي يقرؤه مركزُ التصدير — وإلّا مرّ بلا إشعارٍ ولا قائمةِ مشاركة."""
    untagged = [
        f"{path.as_posix()}: {' '.join(tag.split())[:120]}"
        for path in _templates()
        for tag in TAG.findall(path.read_text(encoding="utf-8"))
        if FILE_HINTS.search(tag) and not PAGE_URL_NAMES.search(tag) and "data-app-file" not in tag
    ]

    assert not untagged, "روابطُ ملفّاتٍ بلا data-app-file — طريقٌ مسدودٌ في التطبيق:\n" + "\n".join(
        untagged
    )


def test_every_standalone_page_carries_the_back_bar():
    missing = []
    for path in _templates():
        src = path.read_text(encoding="utf-8")
        rel = path.as_posix()
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
    assert ":not(" not in html  # xhtml2pdf لا يحلّلها فيسقط الملفّ


def test_the_back_bar_never_reaches_the_pdf_path():
    assert render_to_string("components/app_back_bar.html", {"for_pdf": True}).strip() == ""


def test_file_views_follow_the_naming_convention():
    """دالّةٌ تُرجع ملفّاً باسمٍ خارج الاصطلاح لا يراها حارسُ الروابط — فتُراجَع هنا."""
    import inspect

    from django.urls import URLPattern, URLResolver, get_resolver

    marks = re.compile(
        r"render_pdf|excel_to_response|ExcelService\.to_response|FileResponse|Content-Disposition"
    )
    name_ok = re.compile(r"(?:pdf|excel|xlsx)$|_export$|_template$|^export_")
    strays = []

    def walk(resolver, ns=""):
        for p in resolver.url_patterns:
            if isinstance(p, URLResolver):
                walk(p, ns + (f"{p.namespace}:" if p.namespace else ""))
            elif isinstance(p, URLPattern) and p.name:
                view = getattr(p.callback, "view_class", None) or p.callback
                while hasattr(view, "__wrapped__"):
                    view = view.__wrapped__
                try:
                    src = inspect.getsource(view)
                except (OSError, TypeError):
                    continue
                full = ns + p.name
                if (
                    marks.search(src)
                    and not name_ok.search(p.name)
                    and full not in FILE_VIEWS_OUTSIDE_CONVENTION
                ):
                    strays.append(full)

    walk(get_resolver())
    assert not strays, f"دوالُّ ملفّاتٍ بأسماءٍ خارج الاصطلاح — سمِّها أو راجِعها وأضِفها: {strays}"


def test_the_platform_frame_loads_app_mode():
    assert "js/app-mode.js" in (TEMPLATES / "base/base.html").read_text(encoding="utf-8")


def test_app_mode_script_keeps_its_contract():
    """ما تعتمد عليه القوالبُ والحارسُ أعلاه — لا يُعاد تسميتُه من طرفٍ واحد."""
    src = pathlib.Path("static/js/app-mode.js").read_text(encoding="utf-8")

    for needle in (
        "(display-mode: standalone)",
        "data-app-file",  # يتركه لمركز التصدير ولا يعالجه
        "data-app-back-bar",
        "data-app-back",
        "window.top !== window",  # الورقةُ داخل إطار المنصّة بلا شريط
    ):
        assert needle in src, needle


def test_the_platform_frame_loads_the_export_center():
    """VI-30أ: سكربتٌ مركزيٌّ واحدٌ يحلّ محلّ `schedule-export.js` وشقِّ الملفّات في `app-mode.js`."""
    assert "js/export-center.js" in (TEMPLATES / "base/base.html").read_text(encoding="utf-8")
    assert not pathlib.Path("static/js/schedule-export.js").exists(), "آليّةُ التصدير الثانية عادت"
    loaders = [
        path.as_posix()
        for path in _templates()
        if "schedule-export.js" in path.read_text(encoding="utf-8")
    ]
    assert not loaders, f"قوالبُ تحمّل schedule-export.js المحذوف: {loaders}"


def test_app_mode_no_longer_handles_files_itself():
    """الشقُّ ١ انتقل: لا جلبَ ولا مشاركةَ ولا تنزيلَ في app-mode.js (وإلّا عاد المسارُ المزدوج)."""
    src = pathlib.Path("static/js/app-mode.js").read_text(encoding="utf-8")
    for gone in ("navigator.share", "URL.createObjectURL", "fetch(", "NotAllowedError"):
        assert gone not in src, f"app-mode.js يعالج الملفّاتِ ثانيةً: {gone}"


def test_export_center_script_keeps_its_contract():
    """عقدُ الاستجابة مع الخادم (VI-30ب) وسلوكُ الجوال المثبَّت — لا يُعاد تسميتُه من طرفٍ واحد."""
    src = pathlib.Path("static/js/export-center.js").read_text(encoding="utf-8")

    for needle in (
        "a[data-app-file][href], button[data-app-file]",  # ما يلتقطه
        "'X-Requested-With': 'XMLHttpRequest'",  # ما يميّز XHR عند الخادم
        "status_url",  # مهمّةٌ خلفيّة (202، والشكلُ القديم 200)
        "poll_ms",
        "error.message",  # نصُّ الخطأ عربيّةٌ ثابتةٌ من الخادم لا استثناء
        "text/html",  # لا يُنزَّل HTML ملفّاً
        "NOTICE_AFTER_MS = 600",  # الإشعارُ بعد 600ms فقط
        "(display-mode: standalone)",
        "navigator.canShare",  # قائمةُ المشاركة على جهاز لمس في التطبيق
        "NotAllowedError",  # سفاري: ضغطةٌ ثانيةٌ حين يتأخّر الملفّ
        "GIVE_UP_MS",  # سقفٌ للاستطلاع: لا انتظارَ بلا نهاية
    ):
        assert needle in src, needle


def test_the_pages_view_offers_one_pdf_button_on_touch_screens():
    """زرُّ PDF واحدٌ لا اثنان: العرضُ الجديد (قرار 2026-09-18، فصلُ العرض عن
    الطباعة) جدولٌ عاديٌّ في الصفحة على كلّ شاشة — فلا حاجةَ لزرٍّ ثانٍ يظهر
    على اللمس وحدَه ولا لإخفاء أحدهما بصنفٍ خاصّ باللمس."""
    src = (TEMPLATES / "schedule/pages_view.html").read_text(encoding="utf-8")
    pdf_links = re.findall(r"<a[^>]*schedule_pages_pdf[^>]*>", src)

    assert len(pdf_links) == 1


def test_export_center_treats_target_blank_links_like_every_other_export():
    """قرارُ المالك 2026-09-26: لا عرضَ PDF مضمَّناً في لسانٍ جديد — كلُّ التصديرات تُنزَّل بإشعارٍ واحد (ولا blob يرث CSP الصفحة)."""
    src = pathlib.Path("static/js/export-center.js").read_text(encoding="utf-8")
    assert "el.target === '_blank'" not in src, "عاد استثناءُ target=_blank"
    assert "window.open" not in src, "المركزُ لا يفتح ألسنةً"
