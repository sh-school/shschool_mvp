"""
core/photo_privacy.py — صورةٌ من جوّالٍ تُحفظ نظيفةً وصغيرة.

قرارُ 2026-09-14: المشرفُ يصوّر التقريرَ الطبّيَّ بجوّاله أو يرفع صورةً من جهازه، والخادمُ:

1. **يحوّلها** — ومنها صيغةُ آيفون (HEIC/HEIF) — إلى JPEG يفتحه كلُّ متصفّح.
2. **يصغّرها** إلى ضلعٍ أقصاه `MAX_SIDE` نقطة: تبقى مقروءةً ولا تتضخّم القاعدة، فالملفّاتُ
   في PostgreSQL لا على قرص، وتدخل كلَّ نسخةٍ احتياطيّة.
3. **يمحو كلَّ ما يتبعها**: الإحداثيّات والتاريخ ونوع الجهاز (EXIF) وXMP وملفَّ الألوان. التقريرُ
   الطبّيُّ بيانٌ صحّيٌّ حسّاس (قانونُ حماية البيانات 13/2016)، ولا يُحفظ معه موقعُ بيت وليّ الأمر.

والمحوُ يكون ببناء صورةٍ جديدةٍ لا يُنسخ إليها إلّا النقاط: فلا يتسرّب حقلٌ لم نسمع به.
ويُطبَّق اتّجاهُ الالتقاط قبل المحو، وإلّا انقلبت الصورةُ حين تُحذف علامةُ اتّجاهها.
"""

from __future__ import annotations

import io
from pathlib import PurePath

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile, File
from PIL import Image, ImageOps, UnidentifiedImageError

#: أطولُ ضلعٍ بعد التصغير — تقريرٌ بخطٍّ صغيرٍ يبقى مقروءاً عنده.
MAX_SIDE = 1600
JPEG_QUALITY = 82

PHOTO_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"})


def _open_heif_too() -> None:
    """يعلّم Pillow قراءةَ صور آيفون — مرّةً واحدة، وعند الحاجة فقط."""
    from pillow_heif import register_heif_opener

    register_heif_opener()


def is_photo(name: str) -> bool:
    return PurePath(name or "").suffix.lower() in PHOTO_EXTENSIONS


def clean_photo(upload: File) -> File:
    """يُعيد الصورةَ JPEG مصغّرةً بلا بياناتٍ مخفيّة — وما ليس صورةً (كـPDF) يُعاد كما هو."""
    name = getattr(upload, "name", "") or ""
    if not is_photo(name):
        return upload
    _open_heif_too()
    try:
        upload.seek(0)
        with Image.open(upload) as original:
            upright = ImageOps.exif_transpose(original)
            if upright.mode in ("RGBA", "LA") or "transparency" in upright.info:
                rgba = upright.convert("RGBA")
                flat = Image.new("RGB", rgba.size, "white")
                flat.paste(rgba, mask=rgba.getchannel("A"))
            else:
                flat = upright.convert("RGB")
            flat.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            # صورةٌ جديدةٌ فارغةُ البيانات، تُنسخ إليها النقاطُ وحدَها.
            bare = Image.new("RGB", flat.size)
            bare.paste(flat)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as err:
        raise ValidationError(
            "تعذّرت قراءةُ الصورة — صوّر المستندَ مرّةً أخرى، أو ارفعه ملفَّ PDF.",
            code="unreadable_photo",
        ) from err

    out = io.BytesIO()
    bare.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return ContentFile(out.getvalue(), name=f"{PurePath(name).stem or 'document'}.jpg")
