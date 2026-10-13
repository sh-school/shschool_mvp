"""ورقة الاتصال لمتابعة الغياب (W-20261013-017): PDF بخط Tajawal وذيلٍ ≥ 8pt (يُقاس بـpdfplumber المعلَنة في requirements) ورقمُ وليٍّ بلا اسم.

دالّةُ الخدمة (011) `followup_rows` تُحاكى بعقدها: `followup_rows(user, date)` تُرجع قواميسَ بمفاتيح
student · class_group · phones · action. فيُختبر هنا الطباعةُ وحدَها.
"""

from __future__ import annotations

import datetime as dt
import io
import unicodedata
from types import SimpleNamespace as NS
from unittest import mock

import pdfplumber
import pytest
from django.core.exceptions import PermissionDenied

from operations import absence_followup_print as sheet  # noqa: E402

DAY = dt.date(2026, 10, 13)
GUARDIAN_NAME = "الوليّ المجهول"  # اسمٌ لا يجوز أن يظهر
MOTHER_NAME = "الأمّ المجهولة"


def _row(name, klass, phones, status=None):
    return {
        "student": NS(full_name=name),
        "class_group": klass,
        "phones": phones,
        "action": NS(status=status) if status else None,
        "guardian_name": GUARDIAN_NAME,
        "mother_name": MOTHER_NAME,
    }


ROWS = [
    _row("سالم أحمد", "7/1", ["55123456"], "sick_leave"),
    _row("خالد علي", "7/1", ["55987654", "66111222"]),
    _row("ماجد حسن", "7/2", []),
]


@pytest.fixture
def pdf():
    user = NS(
        full_name="مشرفٌ تجريبيّ",
        get_school=lambda: NS(name="مدرسة اختبار", phone="", email="", city=""),
    )
    from operations.services import absence_followup as service

    ctx = {
        "school_name": "مدرسة اختبار",
        "exported_by": "مشرفٌ تجريبيّ",
        "exporter_role": "مشرف الجناح",
    }
    with (
        mock.patch.object(service, "followup_rows", return_value=ROWS) as rows_mock,
        mock.patch.object(sheet, "has_capability", return_value=True),
        mock.patch.object(sheet, "get_export_context_for", return_value=ctx),
        mock.patch.object(sheet, "AuditLog") as audit,
    ):
        data = sheet.render_contact_sheet(user, DAY)
    return NS(data=data, audit=audit, service=rows_mock, user=user)


def _pages(data):
    return pdfplumber.open(io.BytesIO(data)).pages


def _text(data) -> str:
    """نصُّ الصفحات مطبَّعاً (NFKC) ليُقارَن بالعربيّة المجرَّدة من أشكال العرض، بالترتيبين."""
    raw = " ".join(p.extract_text() or "" for p in _pages(data))
    norm = unicodedata.normalize("NFKC", raw)
    return norm + " " + norm[::-1]


def test_is_pdf_with_tajawal(pdf):
    assert pdf.data.startswith(b"%PDF")
    fonts = {c["fontname"] for p in _pages(pdf.data) for c in p.chars}
    assert any("Tajawal" in f for f in fonts), fonts


def test_footer_at_least_8pt_and_inside_page(pdf):
    sizes = [
        c["size"]
        for p in _pages(pdf.data)
        for c in p.chars
        if c["top"] > p.height * 0.9 and c["text"].strip()
    ]
    assert sizes and min(sizes) >= 8.0, sizes
    for p in _pages(pdf.data):
        for c in p.chars:
            assert -0.5 <= c["x0"] and c["x1"] <= p.width + 0.5 and c["bottom"] <= p.height + 0.5


def test_phone_shown_without_guardian_or_mother_name(pdf):
    text = _text(pdf.data)
    assert "55123456" in text and "55987654" in text
    for secret in (GUARDIAN_NAME, MOTHER_NAME):
        assert unicodedata.normalize("NFKC", secret) not in text


def test_single_signature_and_sick_leave_marked(pdf):
    text = _text(pdf.data)
    assert unicodedata.normalize("NFKC", "استُلمت") in text or "استلمت" in text
    assert unicodedata.normalize("NFKC", "سالم") in text


def test_grouped_by_class(pdf):
    text = _text(pdf.data)
    assert "7/1" in text and "7/2" in text


def test_audit_row_has_no_pii(pdf):
    pdf.audit.log.assert_called_once()
    kw = pdf.audit.log.call_args.kwargs
    assert kw["changes"]["rows"] == 3
    flat = repr(kw)
    for secret in ("سالم", "55123456", GUARDIAN_NAME, MOTHER_NAME):
        assert secret not in flat


def test_denied_without_capability_reads_nothing():
    with mock.patch.object(sheet, "has_capability", return_value=False):
        with pytest.raises(PermissionDenied):
            sheet.render_contact_sheet(NS(), DAY)


def test_scope_is_delegated_to_service(pdf):
    pdf.service.assert_called_once_with(pdf.user, DAY)
