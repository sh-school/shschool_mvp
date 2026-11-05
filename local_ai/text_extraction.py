"""استخراجُ النصّ من ملفّات المعرفة — PDF وDOCX وTXT/MD (المكتباتُ موجودةٌ في المتطلّبات).

يعمل على كائن ملفٍّ ثنائيّ (ما يعيده `FieldFile.open("rb")`) لا على مسار، كي يصلح مع
`DatabaseStorage` وS3 كما مع القرص. النصُّ يُطبَّع (أسطرٌ فارغةٌ متكرّرة، مسافاتٌ غيرُ قابلةٍ للكسر)
ويُعاد كسلسلةٍ واحدة؛ ملفٌّ بلا نصٍّ (PDF ممسوحٌ ضوئيّاً) يرفع `UnsupportedDocumentError` بعبارةٍ واضحة.
"""

from __future__ import annotations

import re
from typing import IO

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")
_BLANK_LINES = re.compile(r"\n{3,}")


class UnsupportedDocumentError(ValueError):
    """امتدادٌ غيرُ مدعوم أو ملفٌّ بلا نصٍّ قابلٍ للاستخراج."""


def extension_of(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def normalise(text: str) -> str:
    text = (text or "").replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return _BLANK_LINES.sub("\n\n", text).strip()


def _from_pdf(stream: IO[bytes]) -> str:
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(stream) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n\n".join(pages)


def _from_docx(stream: IO[bytes]) -> str:
    import docx

    document = docx.Document(stream)
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _from_text(stream: IO[bytes]) -> str:
    raw = stream.read()
    for encoding in ("utf-8-sig", "utf-8", "cp1256"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_text(stream: IO[bytes], filename: str) -> str:
    """نصُّ الملفّ مطبَّعاً. يرفع `UnsupportedDocumentError` للامتداد غير المدعوم أو الملفّ الفارغ."""
    ext = extension_of(filename)
    if ext == ".pdf":
        text = _from_pdf(stream)
    elif ext == ".docx":
        text = _from_docx(stream)
    elif ext in (".txt", ".md"):
        text = _from_text(stream)
    else:
        raise UnsupportedDocumentError(
            f"الامتدادُ {ext or '(بلا امتداد)'} غيرُ مدعوم؛ المدعوم: PDF وDOCX وTXT وMD."
        )
    text = normalise(text)
    if len(text) < 20:
        raise UnsupportedDocumentError("لا نصَّ قابلاً للاستخراج في الملفّ (ربّما ممسوحٌ ضوئيّاً بلا OCR).")
    return text
