"""
core/validators.py — مدققات مشتركة للمنصة

يشمل:
  - تحقق أنواع الملفات (MIME type) + حجم الملفات
  - تحقق قوة كلمات المرور (NIST SP 800-63B)
OWASP File Upload: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
"""

import mimetypes
import re

from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible


# ── مدقق قوة كلمة المرور (NIST SP 800-63B) ─────────────────────
@deconstructible
class StrongPasswordValidator:
    """
    يفرض كلمة مرور قوية: 12+ حرف مع تنوع (حرف كبير + صغير + رقم + رمز).
    متوافق مع توصيات NIST SP 800-63B و OWASP ASVS Level 2.
    """

    def validate(self, password, user=None):
        errors = []
        if len(password) < 12:
            errors.append("كلمة المرور يجب أن تكون 12 حرفاً على الأقل.")
        if not re.search(r"[A-Z]", password):
            errors.append("يجب أن تحتوي على حرف كبير (A-Z) واحد على الأقل.")
        if not re.search(r"[a-z]", password):
            errors.append("يجب أن تحتوي على حرف صغير (a-z) واحد على الأقل.")
        if not re.search(r"[0-9]", password):
            errors.append("يجب أن تحتوي على رقم واحد على الأقل.")
        if not re.search(r'[!@#$%^&*()\-_=+\[\]{};:\'",.<>?/\\|`~]', password):
            errors.append("يجب أن تحتوي على رمز خاص واحد على الأقل (!@#$%...).")
        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return "كلمة المرور يجب أن تكون 12 حرفاً على الأقل وتحتوي على حرف كبير وصغير ورقم ورمز خاص."


# ── الأنواع المسموح بها لكل سياق ────────────────────────────────
ALLOWED_DOCUMENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # docx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # xlsx
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # pptx
    "application/msword",  # doc
    "application/vnd.ms-excel",  # xls
    "text/plain",
}

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    # SVG غير مسموح: قد يحوي <script> → XSS مخزّن عند تقديمه inline
}

ALLOWED_LIBRARY_TYPES = ALLOWED_DOCUMENT_TYPES | {"application/epub+zip"}

ALLOWED_EXTENSIONS_DOCUMENT = {
    ".pdf",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".pptx",
    ".txt",
}
ALLOWED_EXTENSIONS_IMAGE = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_EXTENSIONS_LIBRARY = ALLOWED_EXTENSIONS_DOCUMENT | {".epub"}

# F-005: أنواع ملفات الأعذار (PDF + صور)
ALLOWED_EXCUSE_TYPES = {"application/pdf"} | ALLOWED_IMAGE_TYPES
ALLOWED_EXTENSIONS_EXCUSE = {".pdf"} | ALLOWED_EXTENSIONS_IMAGE


@deconstructible
class FileTypeValidator:
    """
    يتحقق من نوع الملف (MIME) وامتداده.
    يمنع رفع ملفات تنفيذية أو أنواع غير مسموح بها.

    الاستخدام:
        digital_file = models.FileField(
            validators=[FileTypeValidator(allowed_types='library')],
        )
    """

    PRESETS = {
        "document": (ALLOWED_DOCUMENT_TYPES, ALLOWED_EXTENSIONS_DOCUMENT),
        "image": (ALLOWED_IMAGE_TYPES, ALLOWED_EXTENSIONS_IMAGE),
        "library": (ALLOWED_LIBRARY_TYPES, ALLOWED_EXTENSIONS_LIBRARY),
        "excuse": (ALLOWED_EXCUSE_TYPES, ALLOWED_EXTENSIONS_EXCUSE),
    }

    # امتدادات خطيرة — ممنوعة دائماً بغض النظر عن الإعدادات
    DANGEROUS_EXTENSIONS = {
        ".exe",
        ".bat",
        ".cmd",
        ".com",
        ".msi",
        ".scr",
        ".pif",
        ".js",
        ".vbs",
        ".wsf",
        ".ps1",
        ".sh",
        ".bash",
        ".php",
        ".py",
        ".rb",
        ".pl",
        ".cgi",
        ".dll",
        ".sys",
        ".drv",
        ".jar",
        ".class",
    }

    def __init__(self, allowed_types="document", max_size_mb=50):
        if isinstance(allowed_types, str):
            if allowed_types not in self.PRESETS:
                raise ValueError(f"نوع غير معروف: {allowed_types}. الخيارات: {list(self.PRESETS)}")
            self.allowed_mimes, self.allowed_extensions = self.PRESETS[allowed_types]
        else:
            # مجموعة مخصصة
            self.allowed_mimes = set(allowed_types)
            self.allowed_extensions = set()

        self.max_size_bytes = max_size_mb * 1024 * 1024

    def __call__(self, file):
        # 1. فحص الحجم
        if hasattr(file, "size") and file.size > self.max_size_bytes:
            max_mb = self.max_size_bytes // (1024 * 1024)
            raise ValidationError(
                f"حجم الملف ({file.size // (1024 * 1024)} ميجابايت) "
                f"يتجاوز الحد المسموح ({max_mb} ميجابايت).",
                code="file_too_large",
            )

        # 2. فحص الامتداد
        filename = getattr(file, "name", "")
        ext = ""
        if filename:
            ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        if ext in self.DANGEROUS_EXTENSIONS:
            raise ValidationError(
                f"نوع الملف ({ext}) غير مسموح به لأسباب أمنية.",
                code="dangerous_extension",
            )

        if self.allowed_extensions and ext and ext not in self.allowed_extensions:
            allowed = ", ".join(sorted(self.allowed_extensions))
            raise ValidationError(
                f"امتداد الملف ({ext}) غير مسموح. الامتدادات المسموحة: {allowed}",
                code="invalid_extension",
            )

        # 3. فحص MIME type (من الامتداد — فحص أولي)
        if self.allowed_mimes and ext:
            guessed_mime, _ = mimetypes.guess_type(filename)
            if guessed_mime and guessed_mime not in self.allowed_mimes:
                allowed = ", ".join(sorted(self.allowed_mimes))
                raise ValidationError(
                    f"نوع الملف ({guessed_mime}) غير مسموح.",
                    code="invalid_mime_type",
                )

        # 4. فحص المحتوى الفعلي (magic bytes) — لمنع تغيير الامتداد
        if hasattr(file, "read"):
            try:
                header = file.read(16)
                file.seek(0)
                self._check_magic_bytes(header, ext)
            except (OSError, AttributeError):
                pass

    def _check_magic_bytes(self, header, ext):
        """يفحص أول بايتات الملف لضمان تطابق المحتوى مع الامتداد."""
        if not header:
            return

        # PDF يجب أن يبدأ بـ %PDF
        if ext == ".pdf" and not header.startswith(b"%PDF"):
            raise ValidationError(
                "محتوى الملف لا يتطابق مع امتداد PDF.",
                code="content_mismatch",
            )

        # F-002: JPEG يجب أن يبدأ بـ FF D8 FF
        if ext in (".jpg", ".jpeg") and header[:3] != b"\xff\xd8\xff":
            raise ValidationError(
                "الملف لا يطابق صيغة JPEG.",
                code="content_mismatch",
            )

        # F-002: PNG يجب أن يبدأ بـ 89 50 4E 47 0D 0A 1A 0A
        if ext == ".png" and header[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValidationError(
                "الملف لا يطابق صيغة PNG.",
                code="content_mismatch",
            )

        # الملفات التنفيذية (PE format) — ممنوعة دائماً
        if header[:2] == b"MZ":
            raise ValidationError(
                "لا يُسمح برفع ملفات تنفيذية.",
                code="executable_blocked",
            )

    def __eq__(self, other):
        return (
            isinstance(other, FileTypeValidator)
            and self.allowed_mimes == other.allowed_mimes
            and self.max_size_bytes == other.max_size_bytes
        )
