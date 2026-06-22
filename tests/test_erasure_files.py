"""
tests/test_erasure_files.py
المحو (PDPPL م.18) يطهّر ملفات StoredFile المرتبطة بالطالب (excuse_file/attachment).
"""

import datetime

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from core.erasure_service import ErasureService
from core.models import ErasureRequest, StoredFile
from student_affairs.models import StudentActivity


@pytest.mark.django_db
def test_erasure_purges_uploaded_files(school, student_user, principal_user):
    # ملف مرفوع في التخزين (DatabaseStorage → StoredFile)
    name = default_storage.save(
        "student_activities/2026/06/cert.pdf", ContentFile(b"PII certificate")
    )
    assert StoredFile.objects.filter(name=name).exists()

    StudentActivity.objects.create(
        school=school,
        student=student_user,
        activity_type="certificate",
        title="شهادة تفوّق",
        date=datetime.date(2026, 6, 1),
        attachment=name,
    )
    req = ErasureRequest.objects.create(
        school=school,
        student=student_user,
        requested_by=principal_user,
        reviewed_by=principal_user,
        reason="محو شامل لبيانات الطالب",
    )

    summary = ErasureService.execute(req)

    # الملف طُهِّر من التخزين (لا blob يتيم)
    assert not StoredFile.objects.filter(name=name).exists()
    assert summary.get("files_purged", 0) >= 1
    # سجلّ النشاط نفسه حُذف (PII)
    assert not StudentActivity.objects.filter(student=student_user).exists()
