"""
tests/test_db_file_authz.py
تفويض خدمة الملفات (serve_db_file) — منع IDOR/BOLA + عزل المدارس + منع XSS عبر SVG.
"""

import datetime

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.urls import reverse

from core.models import School, StoredFile
from library.models import LibraryBook
from staff_affairs.models import LeaveRequest


def _save(name, content=b"data"):
    return default_storage.save(name, ContentFile(content))


def _url(name):
    return reverse("serve_db_file", kwargs={"name": name})


def _book(school, name):
    return LibraryBook.objects.create(
        school=school, title="كتاب", author="مؤلف", category="000", digital_file=name
    )


def _leave(school, staff, name):
    return LeaveRequest.objects.create(
        school=school,
        staff=staff,
        leave_type="sick",
        start_date=datetime.date(2026, 6, 1),
        end_date=datetime.date(2026, 6, 3),
        days_count=3,
        reason="مرض",
        attachment=name,
    )


@pytest.mark.django_db
def test_orphan_file_returns_404(client_as, principal_user):
    # ملف بلا سجلّ مالك → لا يُقدَّم (fail-closed)
    name = _save("library/digital/orphan.pdf")
    assert client_as(principal_user).get(_url(name)).status_code == 404
    default_storage.delete(name)


@pytest.mark.django_db
def test_anonymous_redirected_to_login(client):
    name = _save("library/digital/b.pdf")
    _book(School.objects.create(name="م", code="C1"), name)
    resp = client.get(_url(name))
    assert resp.status_code in (301, 302)
    assert "/auth/login" in resp["Location"]
    default_storage.delete(name)


@pytest.mark.django_db
def test_cross_school_blocked(client_as, librarian_user):
    # كتاب في مدرسة أخرى؛ أمين مكتبة من مدرسته → 404 (عزل المدارس)
    other = School.objects.create(name="مدرسة أخرى", code="OTH1")
    name = _save("library/digital/other.pdf")
    _book(other, name)
    assert client_as(librarian_user).get(_url(name)).status_code == 404
    default_storage.delete(name)


@pytest.mark.django_db
def test_same_school_with_role_allowed(client_as, librarian_user, school):
    name = _save("library/digital/ok.pdf", b"PDFBYTES")
    _book(school, name)
    resp = client_as(librarian_user).get(_url(name))
    assert resp.status_code == 200
    assert resp.content == b"PDFBYTES"
    default_storage.delete(name)


@pytest.mark.django_db
def test_same_school_wrong_role_blocked(client_as, nurse_user, school):
    # ممرض ليس في صلاحيات المكتبة وليس مالكاً → 404
    name = _save("library/digital/np.pdf")
    _book(school, name)
    assert client_as(nurse_user).get(_url(name)).status_code == 404
    default_storage.delete(name)


@pytest.mark.django_db
def test_leave_attachment_owner_allowed(client_as, teacher_user, school):
    # مرفق إجازة طبية: المالك (الموظف نفسه) يصل رغم أنه ليس قيادة
    name = _save("leave_attachments/2026/06/med.pdf", b"MED")
    _leave(school, teacher_user, name)
    resp = client_as(teacher_user).get(_url(name))
    assert resp.status_code == 200
    assert resp.content == b"MED"
    default_storage.delete(name)


@pytest.mark.django_db
def test_leave_attachment_nonowner_blocked(client_as, nurse_user, teacher_user, school):
    # ممرض (نفس المدرسة، ليس المالك ولا قيادة) لا يطّلع على إجازة طبية لزميل
    name = _save("leave_attachments/2026/06/med2.pdf")
    _leave(school, teacher_user, name)
    assert client_as(nurse_user).get(_url(name)).status_code == 404
    default_storage.delete(name)


@pytest.mark.django_db
def test_leave_attachment_principal_allowed(client_as, principal_user, teacher_user, school):
    name = _save("leave_attachments/2026/06/med3.pdf", b"M3")
    _leave(school, teacher_user, name)
    assert client_as(principal_user).get(_url(name)).status_code == 200
    default_storage.delete(name)


@pytest.mark.django_db
def test_school_logo_requires_login_and_school_scoped(client, client_as, teacher_user, school):
    name = _save("schools/logos/logo.png", b"PNG")
    school.logo = name
    school.save()
    # مجهول → تحويل للدخول
    assert client.get(_url(name)).status_code in (301, 302)
    # مستخدم مُصادَق من نفس المدرسة → يصل
    resp = client_as(teacher_user).get(_url(name))
    assert resp.status_code == 200
    assert resp.content == b"PNG"
    default_storage.delete(name)


@pytest.mark.django_db
def test_svg_served_as_attachment_octet(client_as, librarian_user, school):
    name = _save("library/digital/x.svg", b"<svg onload=alert(1)></svg>")
    sf = StoredFile.objects.get(name=name)
    sf.content_type = "image/svg+xml"
    sf.save()
    _book(school, name)
    resp = client_as(librarian_user).get(_url(name))
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/octet-stream"
    assert resp["Content-Disposition"].startswith("attachment")
    default_storage.delete(name)
