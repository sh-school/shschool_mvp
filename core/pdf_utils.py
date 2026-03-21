"""
core/pdf_utils.py — توليد PDF احترافي بدعم كامل للعربية
هيدر + فوتر على كل صفحة — WeasyPrint / Playwright / xhtml2pdf

v7: Professional headers/footers on every page
    WeasyPrint  → @page running elements (CSS Paged Media Level 3)
    Playwright  → header_template + footer_template (Chromium native)
    xhtml2pdf   → body header only (fallback, page 1)
"""
import os
import re
import logging
from datetime import date as _date
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

logger = logging.getLogger(__name__)

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
        return re.sub(r'<[^>]+>', '', s or '').strip()

    school_m = re.search(
        r'class="report-header".*?<h1[^>]*>(.*?)</h1>', html_str, re.DOTALL
    )
    title_m = re.search(
        r'class="report-title"[^>]*>(.*?)</div>', html_str, re.DOTALL
    )
    year_m = re.search(r'(\d{4}-\d{4})', html_str)

    return {
        'school': _clean(school_m.group(1)) if school_m else 'SchoolOS',
        'title':  _clean(title_m.group(1)) if title_m else '',
        'year':   year_m.group(1) if year_m else '',
    }


# ── WeasyPrint @font-face ────────────────────────────────────────────────

def _font_face_css_weasyprint() -> str:
    fd = _fonts_dir()
    parts = []
    for family, weight, filename in [
        ("Amiri",   "400", "Amiri-Regular.ttf"),
        ("Amiri",   "700", "Amiri-Bold.ttf"),
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
    if "@font-face" in html_str or "@import" in html_str:
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
    today_str = timezone.now().strftime("%Y/%m/%d")
    title_part = f" — {title}" if title else ""

    css = f"""
/* ── WeasyPrint: هيدر/فوتر على كل صفحة ──────────────────── */
.wp-page-header {{
    position:     running(wp-header);
    font-family:  'Tajawal', 'Amiri', Arial, sans-serif;
    font-size:    9.5px;
    font-weight:  700;
    color:        #8A1538;
    text-align:   center;
    padding:      3px 0 5px;
    border-bottom: 1.5px solid #8A1538;
    width:        100%;
}}
.wp-page-footer {{
    position:     running(wp-footer);
    font-family:  'Tajawal', Arial, sans-serif;
    font-size:    8px;
    color:        #888;
    text-align:   center;
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

    @bottom-left {{
        content:      "SchoolOS v6";
        font-family:  Arial, sans-serif;
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
    @bottom-right {{
        content:      "{today_str}";
        font-family:  Arial, sans-serif;
        font-size:    8px;
        color:        #aaa;
        vertical-align: top;
        padding-top:  5px;
    }}
}}
"""
    html_str = html_str.replace('</style>', f'{css}\n</style>', 1)

    # حقن running div في بداية body
    running_div = (
        f'<div class="wp-page-header">{school}{title_part}</div>\n'
    )
    html_str = re.sub(r'(<body[^>]*>)', r'\1\n' + running_div, html_str, count=1)
    return html_str


# ── xhtml2pdf: تسجيل الخطوط مع ReportLab ───────────────────────────────

def _register_fonts_reportlab() -> list:
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        return []

    fd = _fonts_dir()
    registered = []
    for name, path in [
        ("Tajawal",        fd / "Tajawal-Regular.ttf"),
        ("Tajawal-Bold",   fd / "Tajawal-Bold.ttf"),
        ("Tajawal-Medium", fd / "Tajawal-Medium.ttf"),
        ("Amiri",          fd / "Amiri-Regular.ttf"),
        ("Amiri-Bold",     fd / "Amiri-Bold.ttf"),
    ]:
        if path.exists():
            try:
                if name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(name, str(path)))
                registered.append(name)
            except Exception as e:
                logger.debug("registerFont %s: %s", name, e)

    try:
        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        if "Tajawal" in registered and "Tajawal-Bold" in registered:
            registerFontFamily("Tajawal", normal="Tajawal", bold="Tajawal-Bold",
                               italic="Tajawal", boldItalic="Tajawal-Bold")
        if "Amiri" in registered and "Amiri-Bold" in registered:
            registerFontFamily("Amiri", normal="Amiri", bold="Amiri-Bold",
                               italic="Amiri", boldItalic="Amiri-Bold")
    except Exception:
        pass
    return registered


def _strip_font_face(html_str: str) -> str:
    return re.sub(r'@font-face\s*\{[^}]+\}', '', html_str)


# ── Playwright: قوالب الهيدر والفوتر ────────────────────────────────────

def _playwright_header_template(school: str, title: str) -> str:
    """هيدر احترافي — يعمل على كل صفحة في Playwright"""
    title_part = f" — {title}" if title else ""
    return f"""
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
.ph {{
    font-family: Arial, 'Arial Unicode MS', Tahoma, sans-serif;
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
    font-family: Arial, 'Arial Unicode MS', Tahoma, sans-serif;
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
    """
    # استخراج معلومات الهيدر من HTML
    meta   = _extract_pdf_meta(html_str)
    today  = timezone.now().strftime("%Y/%m/%d")

    # ── WeasyPrint ─────────────────────────────────────────────────────
    try:
        from weasyprint import HTML
        from weasyprint.text.fonts import FontConfiguration

        wp_html = _inject_fonts(html_str)
        wp_html = _inject_wp_page_header_css(wp_html, meta['school'], meta['title'])

        font_config = FontConfiguration()
        base_url    = Path(settings.BASE_DIR).as_uri() + "/"
        pdf_bytes   = HTML(string=wp_html, base_url=base_url).write_pdf(
            font_config=font_config
        )
        logger.info("PDF ← WeasyPrint (مع هيدر/فوتر @page)")
        return pdf_bytes
    except ImportError:
        logger.info("WeasyPrint غير مثبت")
    except OSError as e:
        logger.warning("WeasyPrint OSError: %s", e)

    # ── Playwright / Chromium ──────────────────────────────────────────
    try:
        from playwright.sync_api import sync_playwright

        chr_html = _inject_fonts(html_str)
        header   = _playwright_header_template(meta['school'], meta['title'])
        footer   = _playwright_footer_template(today)

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page    = browser.new_page()
            page.set_content(chr_html, wait_until="networkidle")

            pdf_bytes = page.pdf(
                format="A4",
                margin={
                    "top":    "2.8cm",   # مساحة للهيدر
                    "bottom": "2.2cm",   # مساحة للفوتر
                    "left":   "1.5cm",
                    "right":  "1.5cm",
                },
                display_header_footer=True,
                header_template=header,
                footer_template=footer,
                print_background=True,
            )
            browser.close()

        logger.info("PDF ← Playwright/Chromium (مع هيدر/فوتر كل صفحة)")
        return pdf_bytes
    except ImportError:
        logger.info("Playwright غير مثبت — تجربة xhtml2pdf")
    except Exception as e:
        logger.warning("Playwright error: %s — تجربة xhtml2pdf", e)

    # ── xhtml2pdf (fallback — هيدر الصفحة الأولى فقط) ─────────────────
    try:
        from xhtml2pdf import pisa
        from io import BytesIO

        _register_fonts_reportlab()
        xhtml_html  = _strip_font_face(html_str)
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
        logger.info("PDF ← xhtml2pdf (هيدر الصفحة الأولى فقط)")
        return buffer.getvalue()

    except ImportError:
        raise RuntimeError(
            "لا توجد مكتبة PDF — شغّل: pip install weasyprint أو pip install xhtml2pdf"
        )


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
