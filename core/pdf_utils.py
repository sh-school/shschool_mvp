"""
core/pdf_utils.py — توليد PDF احترافي بدعم كامل للعربية
هيدر + فوتر على كل صفحة — WeasyPrint / Playwright / xhtml2pdf

v7: Professional headers/footers on every page
    WeasyPrint  → @page running elements (CSS Paged Media Level 3)
    Playwright  → header_template + footer_template (Chromium native)
    xhtml2pdf   → body header only (fallback, page 1)
"""

import logging
import os
import re
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Cache للـ backend الناجح — نتجنّب إعادة المحاولة في كل طلب ────────────
_WORKING_BACKEND: str | None = None  # "weasyprint" | "playwright" | "xhtml2pdf"
_FAILED_BACKENDS: set = set()

_FONTS_DIR = None


def _fonts_dir() -> Path:
    global _FONTS_DIR
    if _FONTS_DIR is None:
        _FONTS_DIR = Path(settings.BASE_DIR) / "static" / "fonts"
    return _FONTS_DIR


# ── استخراج معلومات التقرير من HTML المُولَّد ──────────────────────────


def _extract_pdf_meta(html_str: str) -> dict:
    """
    يستخرج اسم المدرسة وعنوان التقرير والسنة من HTML المُولَّد
    (بعد تفسير Django templates)
    """

    def _clean(s: str) -> str:
        return re.sub(r"<[^>]+>", "", s or "").strip()

    school_m = re.search(r'class="report-header".*?<h1[^>]*>(.*?)</h1>', html_str, re.DOTALL)
    title_m = re.search(r'class="report-title"[^>]*>(.*?)</div>', html_str, re.DOTALL)
    year_m = re.search(r"(\d{4}-\d{4})", html_str)

    return {
        "school": _clean(school_m.group(1)) if school_m else "SchoolOS",
        "title": _clean(title_m.group(1)) if title_m else "",
        "year": year_m.group(1) if year_m else "",
    }


# ── WeasyPrint @font-face ────────────────────────────────────────────────


def _font_face_css_weasyprint() -> str:
    fd = _fonts_dir()
    parts = []
    for family, weight, filename in [
        ("Amiri", "400", "Amiri-Regular.ttf"),
        ("Amiri", "700", "Amiri-Bold.ttf"),
        ("Tajawal", "400", "Tajawal-Regular.ttf"),
        ("Tajawal", "500", "Tajawal-Medium.ttf"),
        ("Tajawal", "700", "Tajawal-Bold.ttf"),
    ]:
        p = fd / filename
        if p.exists():
            parts.append(
                f"@font-face {{ font-family: '{family}'; font-weight: {weight}; "
                f"src: url('{p.as_uri()}') format('truetype'); }}"
            )
    if not parts:
        return "@import url('https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&family=Tajawal:wght@400;500;700&display=swap');"
    return "\n".join(parts)


def _inject_fonts(html_str: str) -> str:
    # تخطّي فقط إذا Tajawal/Amiri محلّي موجود فعلاً — لا تتخطى بسبب @import خارجي
    lower = html_str.lower()
    if "@font-face" in lower and ("tajawal" in lower or "amiri" in lower):
        return html_str
    font_css = _font_face_css_weasyprint()
    if "</style>" in html_str:
        return html_str.replace("</style>", f"{font_css}\n</style>", 1)
    return f"<style>{font_css}</style>\n{html_str}"


# ── WeasyPrint: حقن CSS الهيدر/الفوتر على كل صفحة ───────────────────────


def _inject_wp_page_header_css(html_str: str, school: str, title: str) -> str:
    """
    يحقن:
    1. CSS — @page مع @top-center / @bottom-*
    2. div running header في body
    (لا يؤثر على xhtml2pdf لأن هذا الكود يُنفَّذ فقط في مسار WeasyPrint)
    """
    # القوالب التي لديها هيدر/فوتر خاص بها لا تحتاج حقن إضافي
    if "doc-header" in html_str:
        return html_str
    today_str = timezone.now().strftime("%Y/%m/%d")
    title_part = f" — {title}" if title else ""

    css = f"""
/* ── RTL جذري لجميع العناصر ──────────────────── */
html, body {{ direction: rtl !important; }}
*, div, p, span, td, th, li, h1, h2, h3, h4, h5, h6 {{
    direction: rtl !important;
    text-align: right;
    unicode-bidi: embed;
}}
table {{ direction: rtl !important; border-collapse: collapse; }}

/* ── WeasyPrint: هيدر/فوتر على كل صفحة ──────────────────── */
.wp-page-header {{
    position:     running(wp-header);
    direction:    rtl;
    font-family:  'Tajawal', 'Amiri', Arial, sans-serif;
    font-size:    9.5px;
    font-weight:  700;
    color:        #8A1538;
    text-align:   center !important;
    padding:      3px 0 5px;
    border-bottom: 1.5px solid #8A1538;
    width:        100%;
}}
.wp-page-footer {{
    position:     running(wp-footer);
    direction:    rtl;
    font-family:  'Tajawal', Arial, sans-serif;
    font-size:    8px;
    color:        #888;
    text-align:   center !important;
    padding:      4px 0 0;
    border-top:   1px solid #e5e5e5;
    width:        100%;
}}

@page {{
    size:   A4;
    margin: 3.2cm 1.5cm 2.8cm 1.5cm;

    @top-center {{
        content:         element(wp-header);
        vertical-align:  bottom;
        padding-bottom:  6px;
    }}

    @bottom-right {{
        content:      "SchoolOS v6";
        font-family:  'Tajawal', Arial, sans-serif;
        font-size:    8px;
        color:        #bbb;
        vertical-align: top;
        padding-top:  5px;
    }}
    @bottom-center {{
        content:      counter(page) " / " counter(pages);
        font-family:  'Tajawal', Arial, sans-serif;
        font-size:    8.5px;
        color:        #555;
        vertical-align: top;
        padding-top:  5px;
    }}
    @bottom-left {{
        content:      "{today_str}";
        font-family:  'Tajawal', Arial, sans-serif;
        font-size:    8px;
        color:        #aaa;
        vertical-align: top;
        padding-top:  5px;
    }}
}}
"""
    html_str = html_str.replace("</style>", f"{css}\n</style>", 1)

    # حقن running div في بداية body
    running_div = f'<div class="wp-page-header">{school}{title_part}</div>\n'
    html_str = re.sub(r"(<body[^>]*>)", r"\1\n" + running_div, html_str, count=1)
    return html_str


# ── xhtml2pdf: تسجيل الخطوط مع ReportLab ───────────────────────────────
#
# ⚠️  الاستراتيجية:
#   1. نسجّل Amiri (يدعم Arabic Presentation Forms B كاملاً)
#      بنمط تسمية xhtml2pdf: fontname_BD (lowercase)
#   2. نسجّل Amiri في fontList عبر monkey-patch لـ pisaContext
#   3. نحذف أي @font-face (تسبب مشكلة temp files على Windows)
#   4. نغيّر font-family في CSS إلى Amiri
#   5. نعالج النصوص العربية بـ arabic-reshaper + python-bidi
#
#   Tajawal لا يحتوي على بعض presentation forms (U+FE8D, U+FEA9, U+FEAD)
#   لذلك نستخدم Amiri كخط PDF الأساسي.
# ────────────────────────────────────────────────────────────────────────

_FONTS_REGISTERED = False
_XHTML2PDF_PATCHED = False


def _register_fonts_reportlab() -> list:
    """
    تسجيل الخطوط مع ReportLab + addMapping لربط أسماء CSS.
    xhtml2pdf يبحث في addMapping أولاً قبل @font-face.
    """
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return ["Tajawal", "Amiri"]

    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        return []

    fd = _fonts_dir()
    registered = []

    # ── تسجيل ReportLab الأساسي (للـ WeasyPrint/Playwright) ──
    for name, path in [
        ("Tajawal", fd / "Tajawal-Regular.ttf"),
        ("Tajawal-Bold", fd / "Tajawal-Bold.ttf"),
        ("Tajawal-Medium", fd / "Tajawal-Medium.ttf"),
        ("Amiri", fd / "Amiri-Regular.ttf"),
        ("Amiri-Bold", fd / "Amiri-Bold.ttf"),
    ]:
        if path.exists():
            try:
                if name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(name, str(path)))
                registered.append(name)
            except (OSError, KeyError, ValueError) as e:
                logger.debug("registerFont %s: %s", name, e)

    try:
        from reportlab.pdfbase.pdfmetrics import registerFontFamily

        if "Tajawal" in registered and "Tajawal-Bold" in registered:
            registerFontFamily(
                "Tajawal",
                normal="Tajawal",
                bold="Tajawal-Bold",
                italic="Tajawal",
                boldItalic="Tajawal-Bold",
            )
        if "Amiri" in registered and "Amiri-Bold" in registered:
            registerFontFamily(
                "Amiri", normal="Amiri", bold="Amiri-Bold", italic="Amiri", boldItalic="Amiri-Bold"
            )
    except (KeyError, ValueError, RuntimeError) as e:
        logger.debug("registerFontFamily failed: %s", e)

    # ── تسجيل بنمط xhtml2pdf: fontname_BD (lowercase) ──
    # xhtml2pdf يسمّي الخطوط هكذا داخلياً عند @font-face
    # نحاكي نفس الآلية لتجنّب مشكلة temp files على Windows
    try:
        from reportlab.lib.fonts import addMapping

        # الملفات الفعلية: Amiri-Regular.ttf, Amiri-Bold.ttf
        for font_name, bold, italic, ttf_file in [
            ("amiri", 0, 0, "Amiri-Regular.ttf"),
            ("amiri", 1, 0, "Amiri-Bold.ttf"),
            ("amiri", 0, 1, "Amiri-Regular.ttf"),
            ("amiri", 1, 1, "Amiri-Bold.ttf"),
            ("tajawal", 0, 0, "Amiri-Regular.ttf"),  # Tajawal CSS → Amiri (أكمل دعماً)
            ("tajawal", 1, 0, "Amiri-Bold.ttf"),
            ("tajawal", 0, 1, "Amiri-Regular.ttf"),
            ("tajawal", 1, 1, "Amiri-Bold.ttf"),
        ]:
            full_name = f"{font_name}_{bold}{italic}"
            ttf_path = fd / ttf_file
            if ttf_path.exists():
                if full_name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(full_name, str(ttf_path)))
                addMapping(font_name, bold, italic, full_name)
    except (OSError, KeyError, ValueError, RuntimeError) as e:
        logger.debug("xhtml2pdf font mapping failed: %s", e)

    _FONTS_REGISTERED = True
    return registered


def _patch_xhtml2pdf_context():
    """
    monkey-patch لـ pisaContext.__init__ — يسجّل Amiri في fontList
    حتى يعرف xhtml2pdf أن font-family:'Amiri' خط صالح.
    بدون هذا، xhtml2pdf يتجاهل CSS font-family ويستخدم Helvetica.
    """
    global _XHTML2PDF_PATCHED
    if _XHTML2PDF_PATCHED:
        return

    try:
        from xhtml2pdf.context import pisaContext

        _orig_init = pisaContext.__init__

        def _patched_init(self, *args, **kwargs):
            _orig_init(self, *args, **kwargs)
            # تسجيل Amiri في fontList (بأسماء CSS المحتملة)
            self.registerFont("amiri", ["amiri", "amiri_00", "amiri_10"])
            # Tajawal CSS → Amiri أيضاً (لأن القوالب تستخدم Tajawal)
            self.registerFont("tajawal", ["tajawal", "tajawal_00", "tajawal_10"])

        pisaContext.__init__ = _patched_init
        _XHTML2PDF_PATCHED = True
    except ImportError:
        pass


def _strip_font_face(html_str: str) -> str:
    """حذف @font-face — xhtml2pdf لا يحتاجها (تسبب مشكلة temp files على Windows)"""
    return re.sub(r"@font-face\s*\{[^}]+\}", "", html_str)


# ── Arabic text reshaping for xhtml2pdf ──────────────────────────────────

_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]+")


def _has_arabic(text: str) -> bool:
    return bool(_ARABIC_RE.search(text))


def _reshape_arabic_text(text: str) -> str:
    """
    يعالج النص العربي: reshaping (توصيل الحروف) + BiDi (ترتيب العرض).
    بدون هذه المعالجة، ReportLab يعرض كل حرف منفصلاً (مربعات □□□).
    """
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError:
        logger.warning("arabic-reshaper / python-bidi غير مثبتين — PDF العربي لن يعمل")
        return text

    if not _has_arabic(text):
        return text

    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)


def _reverse_table_columns(html_str: str) -> str:
    """
    يعكس ترتيب أعمدة الجداول (th/td داخل كل tr) لمحاكاة RTL.
    xhtml2pdf لا يدعم direction:rtl للجداول — الأعمدة دائماً LTR.
    هذا الحل يعكس ترتيب HTML ليظهر بشكل RTL في PDF.
    """

    def _reverse_cells(match):
        tr_content = match.group(1)
        # استخرج كل الخلايا (th أو td) مع محتوياتها
        cells = re.findall(
            r"(<t[hd][^>]*>.*?</t[hd]>)",
            tr_content,
            re.DOTALL | re.IGNORECASE,
        )
        if not cells:
            return match.group(0)
        # اعكس ترتيب الخلايا
        reversed_cells = "\n".join(reversed(cells))
        return f"<tr>{reversed_cells}</tr>"

    return re.sub(
        r"<tr[^>]*>(.*?)</tr>",
        _reverse_cells,
        html_str,
        flags=re.DOTALL | re.IGNORECASE,
    )


def _reshape_html_for_xhtml2pdf(html_str: str) -> str:
    """
    يمر على HTML ويعالج كل النصوص العربية بـ arabic-reshaper + python-bidi.
    يحافظ على التاغات والـ CSS كما هي — يعالج فقط النصوص المرئية.
    أيضاً يعكس ترتيب أعمدة الجداول لمحاكاة RTL.
    """
    try:
        import arabic_reshaper  # noqa: F401
        from bidi.algorithm import get_display  # noqa: F401
    except ImportError:
        logger.warning("arabic-reshaper / python-bidi غير مثبتين")
        return html_str

    # ── عكس أعمدة الجداول (RTL) ──
    html_str = _reverse_table_columns(html_str)

    from html.parser import HTMLParser

    # تاغات لا نعالج محتواها
    _SKIP_TAGS = {"style", "script", "code", "pre"}

    class ArabicReshapeParser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.result = []
            self._skip_depth = 0

        def handle_starttag(self, tag, attrs):
            attr_str = ""
            for k, v in attrs:
                if v is None:
                    attr_str += f" {k}"
                else:
                    attr_str += f' {k}="{v}"'
            self.result.append(f"<{tag}{attr_str}>")
            if tag.lower() in _SKIP_TAGS:
                self._skip_depth += 1

        def handle_endtag(self, tag):
            if tag.lower() in _SKIP_TAGS:
                self._skip_depth = max(0, self._skip_depth - 1)
            self.result.append(f"</{tag}>")

        def handle_data(self, data):
            if self._skip_depth > 0 or not _has_arabic(data):
                self.result.append(data)
                return
            self.result.append(_reshape_arabic_text(data))

        def handle_entityref(self, name):
            self.result.append(f"&{name};")

        def handle_charref(self, name):
            self.result.append(f"&#{name};")

        def handle_comment(self, data):
            self.result.append(f"<!--{data}-->")

        def handle_decl(self, decl):
            self.result.append(f"<!{decl}>")

        def handle_pi(self, data):
            self.result.append(f"<?{data}>")

        def unknown_decl(self, data):
            self.result.append(f"<![{data}]>")

    parser = ArabicReshapeParser()
    parser.feed(html_str)
    return "".join(parser.result)


# ── Playwright: قوالب الهيدر والفوتر ────────────────────────────────────


def _playwright_header_template(school: str, title: str) -> str:
    """هيدر احترافي — يعمل على كل صفحة في Playwright"""
    title_part = f" — {title}" if title else ""
    return f"""
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
.ph {{
    font-family: 'Tajawal', 'Amiri', Arial, sans-serif;
    direction:   rtl;
    width:       100%;
    padding:     5px 26px 5px 26px;
    display:     flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1.5px solid #8A1538;
    background:  white;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}}
.ph-school {{
    font-size:   9px;
    font-weight: bold;
    color:       #8A1538;
    white-space: nowrap;
}}
.ph-brand {{
    font-size: 8.5px;
    color:     #8A1538;
    font-weight: bold;
}}
.ph-ministry {{
    font-size: 8px;
    color:     #777;
    direction: rtl;
}}
</style>
<div class="ph">
    <span class="ph-school">{school}{title_part}</span>
    <span class="ph-ministry">وزارة التربية والتعليم والتعليم العالي — دولة قطر</span>
</div>
"""


def _playwright_footer_template(today: str) -> str:
    """فوتر احترافي — يعمل على كل صفحة في Playwright"""
    return f"""
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
.pf {{
    font-family: 'Tajawal', 'Amiri', Arial, sans-serif;
    direction:   rtl;
    width:       100%;
    padding:     5px 26px;
    display:     flex;
    justify-content: space-between;
    align-items: center;
    border-top:  1px solid #e0e0e0;
    background:  white;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
    font-size:   8px;
    color:       #888;
}}
.pf-brand {{ color: #ccc; font-size: 7.5px; letter-spacing: 0.5px; }}
.pf-pages {{ color: #555; direction: ltr; font-size: 8.5px; }}
.pf-date  {{ color: #aaa; font-size: 7.5px; direction: ltr; }}
</style>
<div class="pf">
    <span class="pf-brand">SchoolOS v6</span>
    <span class="pf-pages">
        صفحة <span class="pageNumber"></span> / <span class="totalPages"></span>
    </span>
    <span class="pf-date">{today}</span>
</div>
"""


# ── المولّد الرئيسي ──────────────────────────────────────────────────────


def _generate_pdf_bytes(html_str: str) -> bytes:
    """
    HTML → PDF bytes
    الأولوية: WeasyPrint → Playwright (Chromium) → xhtml2pdf
    يتذكّر الـ backend الناجح ويتخطّى الفاشلة في الطلبات اللاحقة.
    """
    global _WORKING_BACKEND, _FAILED_BACKENDS

    meta = _extract_pdf_meta(html_str)
    today = timezone.now().strftime("%Y/%m/%d")

    # ── WeasyPrint ─────────────────────────────────────────────────────
    if "weasyprint" not in _FAILED_BACKENDS:
        try:
            from weasyprint import HTML
            from weasyprint.text.fonts import FontConfiguration

            wp_html = _inject_fonts(html_str)
            wp_html = _inject_wp_page_header_css(wp_html, meta["school"], meta["title"])

            font_config = FontConfiguration()
            base_url = Path(settings.BASE_DIR).as_uri() + "/"
            pdf_bytes = HTML(string=wp_html, base_url=base_url).write_pdf(font_config=font_config)
            _WORKING_BACKEND = "weasyprint"
            logger.info("PDF ← WeasyPrint (مع هيدر/فوتر @page)")
            return pdf_bytes
        except ImportError:
            logger.debug("WeasyPrint غير مثبت")
            _FAILED_BACKENDS.add("weasyprint")
        except OSError as e:
            logger.debug("WeasyPrint غير متاح: %s", e)
            _FAILED_BACKENDS.add("weasyprint")

    # ── Playwright / Chromium ──────────────────────────────────────────
    # يعمل في thread منفصل لتجنّب تعارضه مع asyncio event loop (Daphne/Windows)
    if "playwright" not in _FAILED_BACKENDS:
        try:
            import threading

            from playwright.sync_api import sync_playwright

            chr_html = _inject_fonts(html_str)
            header = _playwright_header_template(meta["school"], meta["title"])
            footer = _playwright_footer_template(today)

            _pdf_result: dict = {}

            def _run_in_thread():
                import asyncio
                import sys

                # Windows: ProactorEventLoop لا يدعم subprocess داخل thread
                # → نستخدم SelectorEventLoop صراحةً
                if sys.platform == "win32":
                    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    with sync_playwright() as pw:
                        browser = pw.chromium.launch()
                        page = browser.new_page()
                        page.set_content(chr_html, wait_until="networkidle")
                        _pdf_result["bytes"] = page.pdf(
                            format="A4",
                            margin={
                                "top": "2.8cm",
                                "bottom": "2.2cm",
                                "left": "1.5cm",
                                "right": "1.5cm",
                            },
                            display_header_footer=True,
                            header_template=header,
                            footer_template=footer,
                            print_background=True,
                        )
                        browser.close()
                except (OSError, RuntimeError, TimeoutError) as exc:
                    logger.exception("فشل توليد PDF عبر Playwright")
                    _pdf_result["error"] = exc
                finally:
                    loop.close()

            t = threading.Thread(target=_run_in_thread, daemon=True)
            t.start()
            t.join(timeout=60)

            if "error" in _pdf_result:
                raise _pdf_result["error"]
            if "bytes" not in _pdf_result:
                raise RuntimeError("Playwright: انتهت المهلة")

            _WORKING_BACKEND = "playwright"
            logger.info("PDF ← Playwright/Chromium (مع هيدر/فوتر كل صفحة)")
            return _pdf_result["bytes"]

        except ImportError:
            logger.debug("Playwright غير مثبت")
            _FAILED_BACKENDS.add("playwright")
        except (OSError, RuntimeError) as e:
            logger.debug("Playwright غير متاح: %s", e)
            _FAILED_BACKENDS.add("playwright")

    # ── xhtml2pdf (fallback — هيدر الصفحة الأولى فقط) ─────────────────
    try:
        from io import BytesIO

        from xhtml2pdf import pisa

        _register_fonts_reportlab()
        _patch_xhtml2pdf_context()
        # حذف @font-face (تسبب مشكلة temp files على Windows)
        xhtml_html = _strip_font_face(html_str)
        # ── معالجة النص العربي: reshaping + BiDi ──
        xhtml_html = _reshape_html_for_xhtml2pdf(xhtml_html)
        static_root = str(Path(settings.BASE_DIR) / "static")

        def _link_callback(uri, rel):
            if uri.startswith("/static/"):
                return os.path.join(static_root, uri[8:].replace("/", os.sep))
            if uri.startswith("file:///"):
                return uri[8:].replace("/", os.sep)
            return uri

        buffer = BytesIO()
        status = pisa.CreatePDF(
            xhtml_html.encode("utf-8"),
            dest=buffer,
            encoding="utf-8",
            link_callback=_link_callback,
        )
        if status.err:
            raise RuntimeError(f"xhtml2pdf error: {status.err}")
        _WORKING_BACKEND = "xhtml2pdf"
        logger.info("PDF ← xhtml2pdf (هيدر الصفحة الأولى فقط)")
        return buffer.getvalue()

    except ImportError:
        raise RuntimeError(
            "لا توجد مكتبة PDF — شغّل: pip install weasyprint أو pip install xhtml2pdf"
        )
    except (OSError, RuntimeError, ValueError) as e:
        logger.error("xhtml2pdf فشل: %s", e)
        raise RuntimeError(f"فشل توليد PDF: {e}")


def render_pdf(html_str: str, filename: str) -> HttpResponse:
    """HTML → PDF HttpResponse — للاستخدام في Django views"""
    try:
        pdf_bytes = _generate_pdf_bytes(html_str)
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{filename}"'
        return resp
    except RuntimeError as e:
        return HttpResponse(str(e), status=500)


def render_pdf_bytes(html_str: str) -> bytes:
    """HTML → PDF bytes فقط — للاستخدام في Celery tasks"""
    return _generate_pdf_bytes(html_str)
