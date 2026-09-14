"""العذرُ بعد مهلة العودة يُرسَل للنائب الإداريّ، والصورةُ تُحفظ نظيفةً وصغيرة (قرارا 2026-09-14).

- المشرفُ بعد يومين دراسيّين من عودة الطالب لا يُردّ: عذرُه يُحفظ «بانتظار النائب»
  بالضغطة نفسها، ولا يمسّ الحصصَ حتى يقبله النائب.
- النائبُ يقبل بسببٍ فيُكتب العذرُ على الحصص، أو يرفض بسببٍ فيبقى الغياب.
- صورةُ الجوّال تُحوَّل JPEG، وتُصغَّر، وتُمحى إحداثيّاتُها وتاريخُها وجهازُها.
"""

import datetime as dt
import io
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from core.photo_privacy import MAX_SIDE, clean_photo
from core.validators import FileTypeValidator
from operations.absence_standing import standing_for
from operations.excuses import ExcuseError, approve_excuse, grant_excuse, reject_excuse
from operations.models import AbsenceExcuse, StudentAttendance
from tests.test_absence_excuses import (  # noqa: F401 — التجهيزاتُ نفسُها
    MONDAY,
    _absent_day,
    _back,
    _report,
    vice_admin,
)
from tests.test_period_register import (  # noqa: F401
    SUNDAY,
    kids,
    klass,
    subjects,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db

THURSDAY = SUNDAY + dt.timedelta(days=4)


@pytest.fixture
def late_absence(school, seeded_calendar, klass, kids, teacher, supervisor):
    """غاب الأحد، وعاد الاثنين — فالمهلةُ حتى الأربعاء، واليومُ الخميس."""
    _absent_day(school, klass, kids[0], teacher, supervisor)
    _back(school, klass, teacher, supervisor, MONDAY)
    return kids[0]


def _forward(school, student, by, **extra):
    return grant_excuse(
        student=student,
        school=school,
        date_from=SUNDAY,
        date_to=SUNDAY,
        kind="medical",
        document=_report(),
        by=by,
        today=THURSDAY,
        forward_if_late=True,
        **extra,
    )


class TestForwarding:
    def test_a_late_excuse_waits_for_the_vice_admin_and_leaves_the_periods_alone(
        self, school, late_absence, supervisor
    ):
        excuse = _forward(school, late_absence, supervisor)

        assert excuse.status == "pending" and excuse.document
        assert (
            not StudentAttendance.objects.filter(student=late_absence)
            .exclude(excuse_type="")
            .exists()
        )
        assert standing_for(late_absence, school, grade="G7", on=THURSDAY).unexcused_days == 1

    def test_the_same_days_cannot_be_sent_twice(self, school, late_absence, supervisor):
        _forward(school, late_absence, supervisor)

        with pytest.raises(ExcuseError, match="ينتظر النائب"):
            _forward(school, late_absence, supervisor)


class TestTheVicesDecision:
    def test_accepting_writes_the_excuse_on_the_periods(
        self, school, late_absence, supervisor, vice_admin
    ):
        excuse = _forward(school, late_absence, supervisor)

        with pytest.raises(ExcuseError, match="سببَ القبول"):
            approve_excuse(excuse, by=vice_admin, reason="")
        covered = approve_excuse(excuse, by=vice_admin, reason="التقريرُ من المستشفى صحيح")

        excuse.refresh_from_db()
        assert covered == 7
        assert (excuse.status, excuse.after_deadline, excuse.reviewed_by) == (
            "accepted",
            True,
            vice_admin,
        )
        assert standing_for(late_absence, school, grade="G7", on=THURSDAY).unexcused_days == 0

    def test_rejecting_keeps_the_absence_and_the_record(
        self, school, late_absence, supervisor, vice_admin
    ):
        excuse = _forward(school, late_absence, supervisor)

        reject_excuse(excuse, by=vice_admin, reason="التقريرُ لا يغطّي هذا اليوم")

        excuse.refresh_from_db()
        assert (excuse.status, excuse.rejection_reason) == ("rejected", "التقريرُ لا يغطّي هذا اليوم")
        assert standing_for(late_absence, school, grade="G7", on=THURSDAY).unexcused_days == 1
        with pytest.raises(ExcuseError, match="ليس بانتظار"):
            approve_excuse(excuse, by=vice_admin, reason="تراجع")


class TestTheScreens:
    def test_the_supervisors_one_press_sends_it_and_says_so(
        self, client_as, school, seeded_calendar, klass, late_absence, supervisor, monkeypatch
    ):
        # «اليوم» الخميسُ لخدمة العذر وحدَها — لا لطبقة الطلب كلِّها.
        monkeypatch.setattr(
            "operations.excuses.timezone",
            SimpleNamespace(localdate=lambda: THURSDAY, now=timezone.now),
        )
        client = client_as(supervisor)
        page_url = reverse("wings:student_events", args=[klass.id, late_absence.id])

        response = client.post(
            reverse("wings:excuse_grant", args=[klass.id, late_absence.id]),
            {
                "date_from": SUNDAY.isoformat(),
                "date_to": SUNDAY.isoformat(),
                "kind": "medical",
                "document": _report(),
            },
            follow=True,
        )

        body = response.content.decode()
        assert "أُرسل العذرُ" in body and "النائب الإداريّ" in body
        assert AbsenceExcuse.objects.get(student=late_absence).status == "pending"
        assert "بانتظار النائب الإداريّ" in client.get(page_url).content.decode()

    def test_the_vice_admin_sees_the_request_on_the_dashboard_and_decides_it(
        self, client_as, school, late_absence, supervisor, vice_admin
    ):
        excuse = _forward(school, late_absence, supervisor)
        client = client_as(vice_admin)

        assert reverse("wings:excuse_requests") in client.get(reverse("dashboard")).content.decode()
        listing = client.get(reverse("wings:excuse_requests")).content.decode()
        assert late_absence.full_name in listing

        client.post(
            reverse("wings:excuse_request_decide", args=[excuse.pk]),
            {"decision": "accept", "reason": "تقريرٌ صحيح"},
        )

        excuse.refresh_from_db()
        assert excuse.status == "accepted"

    def test_a_supervisor_cannot_decide(self, client_as, school, late_absence, supervisor):
        excuse = _forward(school, late_absence, supervisor)

        response = client_as(supervisor).post(
            reverse("wings:excuse_request_decide", args=[excuse.pk]),
            {"decision": "accept", "reason": "أنا"},
        )

        assert response.status_code in (302, 403)
        excuse.refresh_from_db()
        assert excuse.status == "pending"


def _photo_with_gps(size=(4000, 3000), fmt="JPEG"):
    image = Image.new("RGB", size, "white")
    exif = Image.Exif()
    exif[0x010F] = "Apple"  # الصانع
    exif[0x0132] = "2026:09:14 07:30:00"  # التاريخ
    exif[0x0112] = 6  # الاتّجاه: مُدارةٌ 90°
    gps = exif.get_ifd(0x8825)
    gps[2] = (25.0, 17.0, 10.0)  # خطُّ العرض
    gps[4] = (51.0, 32.0, 0.0)  # خطُّ الطول
    out = io.BytesIO()
    image.save(out, format=fmt, exif=exif)
    return out.getvalue()


class TestThePhoto:
    def test_a_phone_photo_is_shrunk_turned_upright_and_stripped(self):
        cleaned = clean_photo(SimpleUploadedFile("IMG_0042.jpg", _photo_with_gps()))

        assert cleaned.name == "IMG_0042.jpg"
        with Image.open(cleaned) as result:
            assert result.format == "JPEG"
            assert max(result.size) == MAX_SIDE
            assert result.size[1] > result.size[0], "طُبّق اتّجاهُ الالتقاط قبل المحو"
            assert not result.getexif(), "لا إحداثيّاتَ ولا تاريخَ ولا جهاز"
            assert "exif" not in result.info and "xmp" not in result.info

    def test_an_iphone_heic_photo_becomes_a_clean_jpeg(self):
        from pillow_heif import register_heif_opener

        register_heif_opener()
        out = io.BytesIO()
        Image.new("RGB", (800, 600), "white").save(out, format="HEIF", exif=Image.Exif())
        heic = SimpleUploadedFile("IMG_0043.HEIC", out.getvalue())

        FileTypeValidator(allowed_types="excuse", max_size_mb=10)(heic)
        cleaned = clean_photo(heic)

        assert cleaned.name == "IMG_0043.jpg"
        with Image.open(cleaned) as result:
            assert result.format == "JPEG" and not result.getexif()

    def test_a_pdf_is_kept_as_it_is(self):
        report = _report()
        assert clean_photo(report) is report

    def test_a_broken_image_is_refused_with_a_clear_message(self):
        with pytest.raises(ValidationError, match="تعذّرت قراءةُ الصورة"):
            clean_photo(SimpleUploadedFile("IMG_0044.png", b"\x89PNG\r\n\x1a\nnot really"))

    def test_the_saved_excuse_holds_the_clean_photo(self, school, late_absence, supervisor):
        photo = SimpleUploadedFile("IMG_0045.jpg", _photo_with_gps(), content_type="image/jpeg")

        excuse = grant_excuse(
            student=late_absence,
            school=school,
            date_from=SUNDAY,
            date_to=SUNDAY,
            kind="medical",
            document=photo,
            by=supervisor,
            today=MONDAY,
        )

        excuse.document.open("rb")
        with Image.open(excuse.document) as stored:
            assert max(stored.size) == MAX_SIDE and not stored.getexif()
        assert excuse.document.size < 1_000_000
