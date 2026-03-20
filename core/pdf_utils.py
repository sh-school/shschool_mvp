"""
core/pdf_utils.py — توليد PDF بدعم كامل للعربية
يحاول WeasyPrint أولاً (Linux/Mac) ثم xhtml2pdf (Windows)
"""
import os
from pathlib import Path
from django.conf import settings
from django.http import HttpResponse


def _font_face_css() -> str:
    """يعيد @font-face CSS لخط Amiri من static/fonts/ محلياً"""
    fonts_dir = Path(settings.BASE_DIR) / "static" / "fonts"
    regular   = fonts_dir / "Amiri-Regular.ttf"
    bold      = fonts_dir / "Amiri-Bold.ttf"

    if not regular.exists():
        # fallback: Google Fonts (يحتاج إنترنت — للإنتاج فقط)
        return "@import url('https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&display=swap');"

    def file_url(p: Path) -> str:
        return p.as_uri()

    css = f"""
@font-face {{
    font-family: 'Amiri';
    font-weight: 400;
    src: url('{file_url(regular)}') format('truetype');
}}
@font-face {{
    font-family: 'Amiri';
    font-weight: 700;
    src: url('{file_url(bold)}') format('truetype');
}}
"""
    return css


def render_pdf(html_str: str, filename: str) -> HttpResponse:
    """
    يحوّل HTML → PDF مع دعم العربية الكامل.
    يحاول WeasyPrint أولاً، ثم xhtml2pdf كـ fallback (Windows).
    """
    # حقن @font-face إذا لم يكن موجوداً
    font_css = _font_face_css()
    if "@font-face" not in html_str and "@import" not in html_str:
        html_str = html_str.replace("</style>", f"{font_css}\n</style>", 1)

    # ── WeasyPrint ────────────────────────────────────────────────
    try:
        from weasyprint import HTML
        from weasyprint.text.fonts import FontConfiguration
        font_config = FontConfiguration()
        base_url    = Path(settings.BASE_DIR).as_uri() + "/"
        pdf = HTML(string=html_str, base_url=base_url).write_pdf(
            font_config=font_config
        )
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{filename}"'
        return resp
    except (ImportError, OSError):
        pass

    # ── xhtml2pdf (Windows / fallback) ───────────────────────────
    try:
        from xhtml2pdf import pisa
        from io import BytesIO
        buffer = BytesIO()
        status = pisa.CreatePDF(
            html_str.encode("utf-8"), dest=buffer, encoding="utf-8"
        )
        if status.err:
            return HttpResponse(f"خطأ في توليد PDF: {status.err}", status=500)
        resp = HttpResponse(buffer.getvalue(), content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{filename}"'
        return resp
    except ImportError:
        return HttpResponse(
            "يحتاج مكتبة PDF — شغّل: pip install xhtml2pdf",
            status=500,
        )
