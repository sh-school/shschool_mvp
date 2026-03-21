"""
core/pdf_utils.py — توليد PDF بدعم كامل للعربية
يحاول WeasyPrint أولاً (Linux/Mac) ثم xhtml2pdf (Windows)

v6: إصلاح شامل لـ Windows — pre-register fonts + strip @font-face لـ xhtml2pdf
"""
import os
import re
import logging
from pathlib import Path
from django.conf import settings
from django.http import HttpResponse

logger = logging.getLogger(__name__)

_FONTS_DIR = None


def _fonts_dir() -> Path:
    global _FONTS_DIR
    if _FONTS_DIR is None:
        _FONTS_DIR = Path(settings.BASE_DIR) / "static" / "fonts"
    return _FONTS_DIR


# ── WeasyPrint @font-face CSS (file:// URIs — WeasyPrint يقرأها مباشرةً) ──

def _font_face_css_weasyprint() -> str:
    """@font-face CSS بمسارات file:// مطلقة — يعمل مع WeasyPrint فقط"""
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
    """يحقن @font-face في HTML إذا لم تكن موجودة (للـ WeasyPrint)"""
    if "@font-face" in html_str or "@import" in html_str:
        return html_str
    font_css = _font_face_css_weasyprint()
    if "</style>" in html_str:
        return html_str.replace("</style>", f"{font_css}\n</style>", 1)
    return f"<style>{font_css}</style>\n{html_str}"


# ── xhtml2pdf: تسجيل الخطوط مباشرةً مع ReportLab ──

def _register_fonts_reportlab() -> list:
    """
    يسجّل خطوط Tajawal/Amiri مع ReportLab مباشرةً (بدون @font-face).
    هذا يتجنب مشكلة xhtml2pdf + Windows temp files.
    """
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        return []

    fd = _fonts_dir()
    registered = []
    font_map = [
        ("Tajawal",        fd / "Tajawal-Regular.ttf"),
        ("Tajawal-Bold",   fd / "Tajawal-Bold.ttf"),
        ("Tajawal-Medium", fd / "Tajawal-Medium.ttf"),
        ("Amiri",          fd / "Amiri-Regular.ttf"),
        ("Amiri-Bold",     fd / "Amiri-Bold.ttf"),
    ]
    for name, path in font_map:
        if path.exists():
            try:
                # تجنّب إعادة التسجيل
                if name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(name, str(path)))
                registered.append(name)
            except Exception as e:
                logger.debug("registerFont %s: %s", name, e)

    # تسجيل عائلة الخطوط لدعم bold
    try:
        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        if "Tajawal" in registered and "Tajawal-Bold" in registered:
            registerFontFamily("Tajawal",
                normal="Tajawal", bold="Tajawal-Bold",
                italic="Tajawal", boldItalic="Tajawal-Bold")
        if "Amiri" in registered and "Amiri-Bold" in registered:
            registerFontFamily("Amiri",
                normal="Amiri", bold="Amiri-Bold",
                italic="Amiri", boldItalic="Amiri-Bold")
    except Exception:
        pass

    return registered


def _strip_font_face(html_str: str) -> str:
    """يحذف كتل @font-face من HTML لأن xhtml2pdf تتعامل معها بشكل خاطئ على Windows"""
    return re.sub(r'@font-face\s*\{[^}]+\}', '', html_str)


# ── المولّد الرئيسي ──

def _generate_pdf_bytes(html_str: str) -> bytes:
    """
    HTML → PDF bytes.
    الأولوية: WeasyPrint → Playwright (Chromium) → xhtml2pdf
    """

    # ── WeasyPrint ────────────────────────────────────────────
    try:
        from weasyprint import HTML
        from weasyprint.text.fonts import FontConfiguration

        wp_html = _inject_fonts(html_str)
        font_config = FontConfiguration()
        base_url = Path(settings.BASE_DIR).as_uri() + "/"
        pdf_bytes = HTML(string=wp_html, base_url=base_url).write_pdf(
            font_config=font_config
        )
        logger.info("PDF توليد بـ WeasyPrint")
        return pdf_bytes
    except ImportError:
        logger.info("WeasyPrint غير مثبت")
    except OSError as e:
        logger.warning("WeasyPrint OSError: %s", e)

    # ── Playwright / Chromium (أفضل دعم عربي على Windows) ────
    try:
        import tempfile, subprocess, json
        from playwright.sync_api import sync_playwright

        # حقن الخطوط بـ file:// URIs لـ Chromium
        chr_html = _inject_fonts(html_str)

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()

            # تحميل HTML مباشرةً
            page.set_content(chr_html, wait_until="networkidle")

            pdf_bytes = page.pdf(
                format="A4",
                margin={"top": "2cm", "bottom": "2.5cm",
                        "left": "1.5cm", "right": "1.5cm"},
                print_background=True,
            )
            browser.close()

        logger.info("PDF توليد بـ Playwright/Chromium")
        return pdf_bytes
    except ImportError:
        logger.info("Playwright غير مثبت — تجربة xhtml2pdf")
    except Exception as e:
        logger.warning("Playwright error: %s — تجربة xhtml2pdf", e)

    # ── xhtml2pdf + ReportLab pre-registered fonts ────────────
    try:
        from xhtml2pdf import pisa
        from io import BytesIO

        # تسجيل الخطوط مع ReportLab مباشرةً (يتجنب مشكلة temp files على Windows)
        _register_fonts_reportlab()

        # إزالة @font-face لأن xhtml2pdf يفشل في فتح file:// URIs على Windows
        xhtml_html = _strip_font_face(html_str)

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
        logger.info("PDF توليد بـ xhtml2pdf")
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
