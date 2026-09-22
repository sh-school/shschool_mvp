"""مرفقُ النشاط ومرفقُ طلب الإجازة كانا `FileField` بلا مُدقِّق — أيّ نوعٍ وأيّ حجم.

`FileTypeValidator(allowed_types="document", max_size_mb=10)` صار على الحقلين:
يرفض التنفيذيّ بامتداده مهما صغر، ويرفض المستندَ الأكبر من 10 ميغابايت، ويقبل
مستنداً سليماً.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from staff_affairs.forms import LeaveRequestForm
from student_affairs.forms import ActivityForm

ELEVEN_MB = b"%PDF-1.4\n" + b"0" * (11 * 1024 * 1024)
VALID_PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< >>\nendobj\ntrailer\n<< >>\n"


def _leave_form(attachment=None):
    data = {
        "staff_id": "00000000-0000-0000-0000-000000000001",
        "leave_type": "annual",
        "start_date": "2026-10-01",
        "end_date": "2026-10-02",
        "reason": "سبب",
    }
    files = {"attachment": attachment} if attachment else {}
    return LeaveRequestForm(data=data, files=files)


def _activity_form(attachment=None):
    data = {
        "student_id": "00000000-0000-0000-0000-000000000001",
        "title": "نشاط",
        "date": "2026-10-01",
    }
    files = {"attachment": attachment} if attachment else {}
    return ActivityForm(data=data, files=files)


@pytest.mark.parametrize("build_form", [_leave_form, _activity_form])
class TestAttachmentValidatorAppliesToBothForms:
    def test_an_executable_is_rejected_regardless_of_size(self, build_form):
        exe = SimpleUploadedFile("update.exe", b"MZ" + b"\x00" * 100)
        form = build_form(exe)
        form.is_valid()
        assert "attachment" in form.errors

    def test_a_document_over_ten_megabytes_is_rejected(self, build_form):
        big = SimpleUploadedFile("report.pdf", ELEVEN_MB, content_type="application/pdf")
        form = build_form(big)
        form.is_valid()
        assert "attachment" in form.errors

    def test_a_valid_small_pdf_passes_the_attachment_validator(self, build_form):
        pdf = SimpleUploadedFile("report.pdf", VALID_PDF, content_type="application/pdf")
        form = build_form(pdf)
        form.is_valid()
        assert "attachment" not in form.errors
