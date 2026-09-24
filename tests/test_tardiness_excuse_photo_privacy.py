"""[PDPPL] ملفُّ إذن التأخّر يُحفظ نظيفاً — لا إحداثيّاتٍ ولا تاريخَ ولا جهاز، ولا حجمَ زائد.

`tardiness_record` كان يحفظ `excuse_file` كما رفعه المستخدمُ: صورةٌ من جوّالٍ بإحداثيّاتها (EXIF) وبحجمها
كاملاً في PostgreSQL، بينما مسارُ أعذار الغياب (`operations/excuses.py`) يمرّها بـ`core.photo_privacy.clean_photo`
منذ قرار 2026-09-14. والتحقّقُ الأوّلُ كان بالامتداد ونوع المحتوى اللذين يعلنهما المتصفّحُ وحدَهما.

يحرس هذا الملفُّ سلوكَ العرض. وحارسُ البنية (كلُّ مدخلِ رفعٍ يمرّ بالتنظيف أو مسمًّى بسببه) في
`test_uploads_are_photo_cleaned.py`.
"""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from core.photo_privacy import MAX_SIDE
from operations.models import StudentAttendance
from tests.test_supervisor_student_affairs_followup import world  # noqa: F401  (fixture)

pytestmark = pytest.mark.django_db


def _gps_photo(size=(4000, 3000)):
    image = Image.new("RGB", size, "white")
    exif = Image.Exif()
    exif[0x010F] = "Apple"
    exif[0x0132] = "2026:09:14 07:30:00"
    gps = exif.get_ifd(0x8825)
    gps[2] = (25.0, 17.0, 10.0)
    gps[4] = (51.0, 32.0, 0.0)
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def _post(client, student, upload):
    return client.post(
        reverse("student_affairs:tardiness_record"),
        {"student_id": str(student.id), "excuse_file": upload},
    )


def _stored(student):
    row = StudentAttendance.objects.get(student=student)
    with row.excuse_file.open("rb") as handle:
        return row, handle.read()


def test_a_phone_photo_is_stored_shrunk_and_without_hidden_data(client_as, world):  # noqa: F811
    upload = SimpleUploadedFile("IMG_0042.jpg", _gps_photo(), content_type="image/jpeg")

    response = _post(client_as(world["supervisor"]), world["own"], upload)

    assert response.status_code == 302
    row, data = _stored(world["own"])
    assert row.excuse_file.name.endswith(".jpg")
    with Image.open(io.BytesIO(data)) as result:
        assert result.format == "JPEG"
        assert max(result.size) <= MAX_SIDE, "لم تُصغَّر"
        assert not result.getexif(), "إحداثيّاتٌ أو تاريخٌ أو جهازٌ بقي في الصورة"
        assert "exif" not in result.info and "xmp" not in result.info
    assert len(data) < len(_gps_photo())


def test_a_pdf_is_kept_as_it_is(client_as, world):  # noqa: F811
    pdf = "%PDF-1.4 إذن ولي الأمر".encode()
    upload = SimpleUploadedFile("permit.pdf", pdf, content_type="application/pdf")

    _post(client_as(world["supervisor"]), world["own"], upload)

    _row, data = _stored(world["own"])
    assert data == pdf


def test_the_name_and_declared_type_are_not_trusted(client_as, world):  # noqa: F811
    """ملفٌّ اسمُه `.jpg` ونوعُه `image/jpeg` وبايتاتُه ليست صورةً ولا PDF: يُرفض ولا يُسجَّل شيء."""
    upload = SimpleUploadedFile(
        "permit.jpg", b"<html><script>alert(1)</script></html>", content_type="image/jpeg"
    )

    response = _post(client_as(world["supervisor"]), world["own"], upload)

    assert response.status_code == 302
    assert not StudentAttendance.objects.exists(), "سُجّل تأخّرٌ رغم رفض الملفّ"


def test_an_oversized_image_is_refused_before_anything_is_written(client_as, world):  # noqa: F811
    from core.photo_privacy import MAX_PIXELS

    side = int(MAX_PIXELS**0.5) + 100
    upload = SimpleUploadedFile("huge.png", _huge_png(side), content_type="image/png")

    _post(client_as(world["supervisor"]), world["own"], upload)

    assert not StudentAttendance.objects.exists()


def _huge_png(side):
    out = io.BytesIO()
    Image.new("1", (side, side), 1).save(out, format="PNG", optimize=True)
    return out.getvalue()
