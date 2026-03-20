"""
core/pdf_utils.py — توليد PDF بدعم كامل للعربية
يحاول WeasyPrint أولاً (Linux/Mac) ثم xhtml2pdf (Windows)

v6: إضافة render_pdf_bytes() للاستخدام في Celery + تحسين الخطوط
"""
import os
import logging
from pathlib import Path
from django.conf import settings
from django.http import HttpResponse

logger = logging.getLogger(__name__)


def _font_face_css() -> str:
    """يعيد @font-face CSS للخطوط العربية المحلية (Amiri + Tajawal)"""
    fonts_dir = Path(settings.BASE_DIR) / "static" / "fonts"
    css_parts = []

    # Amiri (للتقارير الرسمية)
    amiri_regular = fonts_dir / "Amiri-Regular.ttf"
    amiri_bold    = fonts_dir / "Amiri-Bold.ttf"
    if amiri_regular.exists():
        css_parts.append(f"""
@font-face {{
    font-family: 'Amiri';
    font-weight: 400;
    src: url('{amiri_regular.as_uri()}') format('truetype');
}}""")
    if amiri_bold.exists():
        css_parts.append(f"""
@font-face {{
    font-family: 'Amiri';
    font-weight: 700;
    src: url('{amiri_bold.as_uri()}') format('truetype');
}}""")

    # Tajawal (للواجهات والعناوين)
    for weight, suffix in [("400", "Regular"), ("500", "Medium"), ("700", "Bold")]:
        path = fonts_dir / f"Tajawal-{suffix}.ttf"
        if path.exists():
            css_parts.append(f"""
@font-face {{
    font-family: 'Tajawal';
    font-weight: {weight};
    src: url('{path.as_uri()}') format('truetype');
}}""")

    if not css_parts:
        logger.warning("لم يتم العثور على الخطوط المحلية — استخدام Google Fonts")
        return "@import url('https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&family=Tajawal:wght@400;500;700&display=swap');"

    return "\n".join(css_parts)


def _inject_fonts(html_str: str) -> str:
    """يحقن @font-face في HTML إذا لم تكن موجودة"""
    font_css = _font_face_css()
    if "@font-face" not in html_str and "@import" not in html_str:
        if "</style>" in html_str:
            html_str = html_str.replace("</style>", f"{font_css}\n</style>", 1)
        else:
            html_str = f"<style>{font_css}</style>\n{html_str}"
    return html_str


def _generate_pdf_bytes(html_str: str) -> bytes:
    """
    يحوّل HTML → PDF bytes.
    يحاول WeasyPrint أولاً، ثم xhtml2pdf.
    Returns: bytes (محتوى PDF)
    Raises: RuntimeError إذا فشلت كل المحاولات
    """
    html_str = _inject_fonts(html_str)

    # ── WeasyPrint ────────────────────────────────────────────
    try:
        from weasyprint import HTML
        from weasyprint.text.fonts import FontConfiguration
        font_config = FontConfiguration()
        base_url = Path(settings.BASE_DIR).as_uri() + "/"
        pdf_bytes = HTML(string=html_str, base_url=base_url).write_pdf(
            font_config=font_config
        )
        return pdf_bytes
    except ImportError:
        logger.info("WeasyPrint غير مثبت — تجربة xhtml2pdf")
    except OSError as e:
        logger.warning(f"WeasyPrint OSError: {e} — تجربة xhtml2pdf")

    # ── xhtml2pdf (Windows / fallback) ────────────────────────
    try:
        from xhtml2pdf import pisa
        from io import BytesIO
        buffer = BytesIO()
        status = pisa.CreatePDF(
            html_str.encode("utf-8"), dest=buffer, encoding="utf-8"
        )
        if status.err:
            raise RuntimeError(f"xhtml2pdf error: {status.err}")
        return buffer.getvalue()
    except ImportError:
        raise RuntimeError(
            "لا توجد مكتبة PDF — شغّل: pip install weasyprint أو pip install xhtml2pdf"
        )


def render_pdf(html_str: str, filename: str) -> HttpResponse:
    """
    يحوّل HTML → PDF ويُرجع HttpResponse.
    للاستخدام في Django views.
    """
    try:
        pdf_bytes = _generate_pdf_bytes(html_str)
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{filename}"'
        return resp
    except RuntimeError as e:
        return HttpResponse(str(e), status=500)


def render_pdf_bytes(html_str: str) -> bytes:
    """
    يحوّل HTML → PDF bytes فقط (بدون HttpResponse).
    للاستخدام في Celery tasks، حفظ في ملف، إرفاق بالبريد.

    Usage:
        pdf_bytes = render_pdf_bytes(html_string)
        with open("report.pdf", "wb") as f:
            f.write(pdf_bytes)
    """
    return _generate_pdf_bytes(html_str)
