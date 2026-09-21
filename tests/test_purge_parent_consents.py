"""أمر purge_parent_consents: عرضٌ فقط افتراضاً، والحذفُ بـ --apply مع سطر تدقيق."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.models import AuditLog, ConsentRecord, ParentStudentLink

pytestmark = pytest.mark.django_db


@pytest.fixture
def records(school, parent_user, student_user):
    ParentStudentLink.objects.get_or_create(
        parent=parent_user, student=student_user, school=school
    )
    for data_type in ("health", "grades"):
        ConsentRecord.objects.create(
            school=school, parent=parent_user, student=student_user, data_type=data_type
        )


def _run(*args):
    out = StringIO()
    call_command("purge_parent_consents", *args, stdout=out)
    return out.getvalue()


def test_dry_run_by_default_deletes_nothing(records):
    out = _run()
    assert ConsentRecord.objects.count() == 2
    assert "health: 1" in out and "grades: 1" in out
    assert "عرضٌ فقط" in out
    assert not AuditLog.objects.filter(model_name="ConsentRecord", action="delete").exists()


def test_apply_deletes_all_and_audits(records, school):
    _run("--apply")
    assert ConsentRecord.objects.count() == 0
    entry = AuditLog.objects.get(model_name="ConsentRecord", action="delete")
    assert entry.school_id == school.pk
    assert entry.changes["deleted"] == 2


def test_reset_gate_only_with_apply(records, parent_user):
    parent_user.consent_given_at = timezone.now()
    parent_user.save(update_fields=["consent_given_at"])

    _run("--reset-gate")
    parent_user.refresh_from_db()
    assert parent_user.consent_given_at is not None

    _run("--apply", "--reset-gate")
    parent_user.refresh_from_db()
    assert parent_user.consent_given_at is None
