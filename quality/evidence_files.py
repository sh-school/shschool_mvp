"""
quality/evidence_files.py — ملفُّ دليلِ الإجراء يُفحص ويُنظَّف قبل أن يُحفظ (DBT-43، PDPPL).

للدليل بابان: نافذةُ تحديث الإجراء (`_process_task_update`) وصفحتُه (`upload_evidence`). كان الأوّلُ يمرّر
الملفَّ إلى الخدمة **بلا أيّ فحصِ نوعٍ أو حجم** — فملفٌّ `.html` أو `.svg` يُحفظ في القاعدة ويُقدَّم من نطاق المنصّة،
وصورةٌ من جوّالٍ تُحفظ بإحداثيّاتها. والثاني كان يفحص النوعَ بالامتداد وحدَه ويرفض الصورَ (والنافذةُ تَعِد
المستخدمَ بـ«PDF, Word, Images»).

فصار البابان يمرّان بهذه الدالّة، ومنها تُستدعى `QualityService` — فلا يمرّ ملفٌّ إلى الجدول من دونها:

1. **النوع والحجم والامتداد** — الإعدادُ المركزيّ `FileTypeValidator("evidence")`: مستندٌ (PDF وOffice وtxt) أو
   صورةٌ (JPEG وPNG وWebP وHEIC)، و`EVIDENCE_MAX_MB` كما تَعِد النافذة. ما عداها (`.html`، `.svg`، الملفّاتُ
   التنفيذيّة…) يُرفض.
2. **الحكمُ بالمحتوى لا بالاسم**: ما بدأ بتوقيع Office (`PK`/OLE) أو كان نصّاً عادّياً باسم `.txt` يُحفظ كما هو؛
   وما عداه يمرّ بـ`core.photo_privacy.clean_photo` — الـPDF كما هو، والصورةُ JPEG مصغّراً بلا إحداثيّاتٍ ولا
   تاريخٍ ولا جهاز، وغيرُ ذلك يُرفض. فصورةٌ اسمُها `.docx` لا تمرّ بإحداثيّاتها.
"""

from __future__ import annotations

from pathlib import PurePath

from django.core.files.base import File

from core.photo_privacy import clean_photo
from core.validators import FileTypeValidator

#: الحدُّ الذي تعِد به نافذةُ التحديث («Max 10MB») — والملفّاتُ في PostgreSQL فتدخل كلَّ نسخةٍ احتياطيّة.
EVIDENCE_MAX_MB = 10

#: توقيعُ Office: docx/xlsx/pptx حاويةُ zip، وdoc/xls حاويةُ OLE.
OFFICE_SIGNATURES = (b"PK\x03\x04", b"\xd0\xcf\x11\xe0")
#: نافذةُ الفحص لنصٍّ عادّيّ: ما فيه بايتٌ صفريٌّ في أوّل كيلوبايت ليس صورةً ولا ثنائيّاً.
TEXT_SAMPLE = 1024


def _head(upload: File, size: int) -> bytes:
    upload.seek(0)
    data = upload.read(size)
    upload.seek(0)
    return bytes(data)


def _is_office(upload: File) -> bool:
    return _head(upload, 4) in OFFICE_SIGNATURES


def _is_plain_text(upload: File) -> bool:
    name = getattr(upload, "name", "") or ""
    return PurePath(name).suffix.lower() == ".txt" and b"\x00" not in _head(upload, TEXT_SAMPLE)


def screen_evidence(upload: File) -> File:
    """الملفُّ الذي يُحفظ دليلاً — أو `ValidationError` برسالةٍ تُعرض للمستخدم قبل أن يُكتب شيء."""
    FileTypeValidator("evidence", max_size_mb=EVIDENCE_MAX_MB)(upload)
    if _is_office(upload) or _is_plain_text(upload):
        return upload
    return clean_photo(upload)
