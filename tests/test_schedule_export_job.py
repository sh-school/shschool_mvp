"""[SCHEDULE] البند 5 — تصديرُ PDF/Excel صار خلفيّاً لا متزامناً داخل الطلب.

WeasyPrint بطيءٌ بما يكفي ليُخالف معيار المشروع (>300ms → Background Job).
فالرابطُ ينشئ `ExportJob` ويُرجع فوراً، وعاملُ Celery يملؤه، وصفحةُ
`export_job_status` تُنزّل الناتج حين يجهز. راجع `operations/tasks.py`.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import ExportJob
from operations.tasks import purge_expired_export_jobs_task

pytestmark = pytest.mark.django_db


def test_the_view_creates_a_pending_job_without_rendering_synchronously(
    client_as, school, principal_user, monkeypatch
):
    """لا عملَ ثقيلاً في الطلب — العاملُ وحده يُنجزه، ولو تأخّر.

    الاستيرادُ داخل الدالّة في `views_schedule.py` (لا في رأس الملفّ)، فتصحيحُ
    `.delay` يكون على الكائن نفسه في `operations.tasks` — المرجع واحدٌ أينما استُورد.
    """
    import operations.tasks as tasks_module

    monkeypatch.setattr(tasks_module.render_schedule_export_task, "delay", lambda *a, **k: None)

    resp = client_as(principal_user).get(
        reverse("schedule_export_pdf") + "?view=all_teachers", follow=False
    )

    assert resp.status_code == 302
    job = ExportJob.objects.get(school=school, kind="schedule.pdf")
    assert job.status == "pending"
    assert job.requested_by_id == principal_user.id
    assert reverse("export_job_status", args=[job.id]) in resp.url


def test_the_job_ends_done_or_failed_end_to_end(client_as, school, principal_user):
    """`CELERY_TASK_ALWAYS_EAGER=True` في الاختبارات — العاملُ يعمل فوراً هنا."""
    resp = client_as(principal_user).get(
        reverse("schedule_export_pdf") + "?view=all_teachers&paper=a3", follow=True
    )

    job = ExportJob.objects.get(school=school, kind="schedule.pdf")
    assert job.status in ("done", "failed")
    assert resp.status_code == 200
    if job.status == "done":
        assert job.content_type == "application/pdf"
        assert bytes(job.content).startswith(b"%PDF")
        assert job.filename.endswith(".pdf")
    else:
        assert job.error_message


def test_the_excel_job_produces_a_workbook(client_as, school, principal_user):
    client_as(principal_user).get(
        reverse("schedule_export_excel") + "?view=all_teachers&paper=a3", follow=True
    )

    job = ExportJob.objects.get(school=school, kind="schedule.xlsx")
    assert job.status == "done"
    assert job.content_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert job.filename.endswith(".xlsx")


def test_a_user_cannot_reach_another_users_export_job(client_as, school, principal_user):
    """IDOR: صفّ تصديرٍ يخصّ مستخدماً لا يُفتح بمعرّفه من مستخدمٍ آخر."""
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    other_admin = UserFactory(full_name="مديرٌ آخر")
    MembershipFactory(
        user=other_admin, school=school, role=RoleFactory(school=school, name="principal")
    )

    job = ExportJob.objects.create(
        school=school,
        requested_by=principal_user,
        kind="schedule.pdf",
        query_string="view=all_teachers",
        status="done",
        content=b"%PDF-fake",
        content_type="application/pdf",
        filename="x.pdf",
    )

    resp = client_as(other_admin).get(reverse("export_job_status", args=[job.id]))

    assert resp.status_code == 404


def test_purge_deletes_only_jobs_older_than_a_day(school, principal_user):
    old = ExportJob.objects.create(
        school=school, requested_by=principal_user, kind="schedule.pdf", status="done"
    )
    ExportJob.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=25))
    fresh = ExportJob.objects.create(
        school=school, requested_by=principal_user, kind="schedule.pdf", status="done"
    )

    purge_expired_export_jobs_task()

    assert not ExportJob.objects.filter(pk=old.pk).exists()
    assert ExportJob.objects.filter(pk=fresh.pk).exists()
