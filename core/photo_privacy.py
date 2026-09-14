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

**والحكمُ بالمحتوى لا بالاسم**: ملفٌّ بلا امتداد، أو اسمُه «.jpg» وحده، يُفحص بايتاته — ما بدأ
بـ`%PDF` يُحفظ كما هو، وكلُّ ما عداه يُعامل صورةً فيُنظَّف أو يُرفض. فلا تمرّ صورةٌ بإحداثيّاتها لأنّ
اسمَها لم يدلّ عليها.

**ولا تُفكّ صورةٌ أكبر من `MAX_PIXELS`**: صورةٌ مضغوطةٌ صغيرةُ الحجم بأبعادٍ هائلة تستهلك ذاكرةَ
عمليّة الويب الوحيدة. وصورُ JPEG تُفكّ مصغّرةً من البداية (`draft`) فلا تُحمَّل كاملةً مرّاتٍ.
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
#: أكبرُ صورةٍ تُفكّ — كاميراتُ الجوّالات اليوم دون 50 ميغابكسل.
MAX_PIXELS = 60_000_000


def _open_heif_too() -> None:
    """يعلّم Pillow قراءةَ صور آيفون إن كانت المكتبةُ مثبّتة — وغيابُها لا يُسقط JPEG."""
    try:
        from pillow_heif import register_heif_opener
    except ImportError:  # pragma: no cover — بيئةٌ أقدم من المتطلَّب
        return
    register_heif_opener()


def _is_pdf(upload: File) -> bool:
    upload.seek(0)
    head = upload.read(5)
    upload.seek(0)
    return bool(head.startswith(b"%PDF"))


def _unreadable(err: Exception | None = None) -> ValidationError:
    error = ValidationError(
        "تعذّرت قراءةُ الصورة — صوّر المستندَ مرّةً أخرى، أو ارفعه ملفَّ PDF.",
        code="unreadable_photo",
    )
    if err is not None:
        error.__cause__ = err
    return error


def clean_photo(upload: File) -> File:
    """يُعيد الصورةَ JPEG مصغّرةً بلا بياناتٍ مخفيّة — والـPDF يُعاد كما هو."""
    if _is_pdf(upload):
        return upload
    _open_heif_too()
    try:
        with Image.open(upload) as original:
            width, height = original.size
            if width * height > MAX_PIXELS:
                raise ValidationError(
                    "الصورةُ أكبرُ من أن تُعالَج — صوّر المستندَ بدقّةٍ أقلّ.",
                    code="photo_too_large",
                )
            if original.format == "JPEG":
                original.draft("RGB", (MAX_SIDE * 2, MAX_SIDE * 2))
            upright = ImageOps.exif_transpose(original)
            upright.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            if upright.mode in ("RGBA", "LA") or "transparency" in upright.info:
                rgba = upright.convert("RGBA")
                flat = Image.new("RGB", rgba.size, "white")
                flat.paste(rgba, mask=rgba.getchannel("A"))
            else:
                flat = upright.convert("RGB")
            # صورةٌ جديدةٌ فارغةُ البيانات، تُنسخ إليها النقاطُ وحدَها.
            bare = Image.new("RGB", flat.size)
            bare.paste(flat)
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as err:
        raise _unreadable(err) from err

    out = io.BytesIO()
    bare.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    stem = PurePath(getattr(upload, "name", "") or "").stem.lstrip(".") or "document"
    return ContentFile(out.getvalue(), name=f"{stem}.jpg")
