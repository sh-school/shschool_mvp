"""[PDPPL] مرفقُ استثناء الموظّف (نموذج 03، م-31) يُحفظ نظيفاً — DBT-41.

المرفقُ إلزاميٌّ «ما يثبت حاجة الموظّف»، وقد يكون تقريراً طبّيّاً بصورةٍ من جوّال. كانت الخدمةُ تفحصه بامتداد
اسمه وحجمِه وحدَهما فتحفظه كما رُفع: إحداثيّاتٌ وتاريخٌ وجهازٌ (EXIF) بحجمها كاملاً، وملفٌّ اسمُه `.jpg`
وليس صورةً يمرّ. صار يمرّ بـ`clean_photo` كمسار أعذار الغياب وإذن التأخّر (قرار 2026-09-14).
"""

import io
from datetime import date, time

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from core.photo_privacy import MAX_PIXELS, MAX_SIDE
from staff_affairs.attendance import ExceptionService, PolicyError
from staff_affairs.models import AttendanceException
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db


def _staff(school):
    user = UserFactory(full_name="موظّف اصطناعيّ", employee_number="T-9001")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


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


def _submit(school, staff, upload):
    return ExceptionService.submit(
        school=school,
        staff=staff,
        exception_type="early_departure",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 1),
        boundary=time(13, 0),
        content="ظرفٌ صحّيّ",
        evidence="تقرير",
        evidence_file=upload,
    )


def _stored(exception):
    with exception.evidence_file.open("rb") as handle:
        return handle.read()


def test_a_phone_photo_is_stored_shrunk_and_without_hidden_data(school):
    upload = SimpleUploadedFile("report.jpg", _gps_photo(), content_type="image/jpeg")

    exception = _submit(school, _staff(school), upload)

    data = _stored(exception)
    assert exception.evidence_file.name.endswith(".jpg")
    with Image.open(io.BytesIO(data)) as result:
        assert result.format == "JPEG"
        assert max(result.size) <= MAX_SIDE, "لم تُصغَّر"
        assert not result.getexif(), "إحداثيّاتٌ أو تاريخٌ أو جهازٌ بقي في الصورة"
        assert "exif" not in result.info and "xmp" not in result.info
    assert len(data) < len(_gps_photo())


def test_a_pdf_is_kept_as_it_is(school):
    pdf = "%PDF-1.4 تقرير".encode()

    exception = _submit(school, _staff(school), SimpleUploadedFile("r.pdf", pdf))

    assert _stored(exception) == pdf


def test_a_file_named_jpg_that_is_not_an_image_is_refused(school):
    """الامتدادُ يفحصه الاسمُ وحدَه في `_check_evidence` — فالبايتاتُ هي الحكم."""
    upload = SimpleUploadedFile("report.jpg", b"<html><script>alert(1)</script></html>")

    with pytest.raises(PolicyError):
        _submit(school, _staff(school), upload)

    assert not AttendanceException.objects.exists()


def test_an_oversized_image_is_refused_before_anything_is_written(school):
    side = int(MAX_PIXELS**0.5) + 100
    out = io.BytesIO()
    Image.new("1", (side, side), 1).save(out, format="PNG", optimize=True)

    with pytest.raises(PolicyError):
        _submit(school, _staff(school), SimpleUploadedFile("huge.png", out.getvalue()))

    assert not AttendanceException.objects.exists()
