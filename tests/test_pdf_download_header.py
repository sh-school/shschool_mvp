"""[PDF] ترويسة التنزيل تصل إلى المتصفّح فعلاً.

`Content-Disposition` كانت تُبنى هكذا:

    resp["Content-Disposition"] = f'attachment; filename="{filename}"'

وأسماء ملفّاتنا عربية. فيُرمّز Django قيمة الترويسة **كاملةً** بـRFC 2047:

    Content-Disposition: =?utf-8?b?YXR0YWNobWVudDsgZmlsZW5hbWU9…?=

والمتصفّحات لا تفهم ذلك الترميز في هذه الترويسة تحديداً، فلا ترى `attachment`
وتعود إلى `inline` — أي أن الملفّ يحلّ محلّ الصفحة رغم أن الخادم طلب تنزيله.

والعطب من الصنف الذي لا يظهر في اختبارٍ يفحص المنطق: `as_attachment=True`
يصل إلى `render_pdf` صحيحاً، والخلل في **تشفير الترويسة** بعده.
"""

import pytest
from django.urls import reverse

from core.models import ClassGroup
from core.pdf_utils import _content_disposition


@pytest.mark.parametrize(
    ("filename", "attach"),
    [
        ("نتائج_الصف العاشر_2025-2026.pdf", True),
        ("شهادات.pdf", False),
        ("report_2026.pdf", True),
    ],
)
def test_the_header_stays_ascii_so_django_never_encodes_it(filename, attach):
    """قيمةٌ غير ASCII تدفع Django إلى ترميز الترويسة كاملةً — فتضيع الكلمة الحاسمة."""
    header = _content_disposition(filename, attach)

    assert header.isascii()


@pytest.mark.parametrize("attach", [True, False])
def test_the_disposition_word_is_readable(attach):
    header = _content_disposition("نتائج.pdf", attach)

    assert header.startswith("attachment;" if attach else "inline;")


def test_an_arabic_name_still_reaches_the_browser():
    """`filename*` بترميز RFC 5987 يحمل الاسم العربيّ، و`filename` بديلٌ لاتينيّ."""
    header = _content_disposition("نتيجة_احمد.pdf", True)

    assert "filename*=UTF-8''" in header
    assert "%D9%86" in header  # «ن» مُرمَّزة
    assert 'filename="' in header


def test_a_fully_arabic_name_does_not_become_a_bare_extension():
    """كان التنظيف يُنتج «.pdf» أو «pdf.pdf» — اسمٌ لا يُقرأ في مجلّد التنزيلات."""
    header = _content_disposition("شهادات.pdf", True)

    assert 'filename="document.pdf"' in header


@pytest.mark.django_db
def test_the_download_link_really_sends_attachment(client, principal_user, school):
    """يُقاس على استجابةٍ حقيقية لا على بناء النصّ وحده."""
    from core.models import StudentEnrollment

    cls = ClassGroup.objects.create(school=school, grade="10", section="3")
    client.force_login(principal_user)

    resp = client.get(reverse("class_certificates_pdf", args=[cls.id]), {"download": "1"})

    disposition = resp.headers.get("Content-Disposition", "")
    assert disposition.startswith("attachment;"), disposition
    assert not disposition.startswith("=?"), "الترويسة مُرمَّزة بـRFC 2047"
    assert StudentEnrollment  # يُبقي الاستيراد مقروءاً


@pytest.mark.django_db
def test_the_viewer_link_still_sends_inline(client, principal_user, school):
    """الصفحة العارضة تُضمّن الملفّ في إطار — فالعرض داخليّ لا تنزيل."""
    cls = ClassGroup.objects.create(school=school, grade="10", section="4")
    client.force_login(principal_user)

    resp = client.get(reverse("class_certificates_pdf", args=[cls.id]))

    assert resp.headers.get("Content-Disposition", "").startswith("inline;")
