"""[SCHEDULE] البند 5 — تصديرُ PDF/Excel صار خلفيّاً لا متزامناً داخل الطلب (والآليّةُ مركزيّةٌ منذ VI-30ب).

WeasyPrint بطيءٌ بما يكفي ليُخالف معيار المشروع (>300ms → Background Job). فالرابطُ ينشئ `ExportJob` ويُرجع
فوراً، وعاملُ Celery يملؤه (`core.export.run_job`، بنّاءُ `operations/schedule_export_builders.py`)، وصفحةُ
`export_page` (أو `export_status` + `export_download` للواجهة) تُنزّل الناتج حين يجهز. راجع `core/exports`.
والاختباراتُ العامّةُ للآليّة (السجلّ، السقوف، رموزُ الخطأ، الاحتفاظ) في `tests/test_export_core.py`.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from core.exports import messages
from core.models import ExportJob
from operations.tasks import purge_expired_export_jobs_task

pytestmark = pytest.mark.django_db


def test_the_view_creates_a_pending_job_without_rendering_synchronously(
    client_as, school, principal_user, monkeypatch
):
    """لا عملَ ثقيلاً في الطلب — العاملُ وحده يُنجزه، ولو تأخّر."""
    import core.tasks as tasks_module

    monkeypatch.setattr(tasks_module.run_export_job, "apply_async", lambda *a, **k: None)

    resp = client_as(principal_user).get(
        reverse("schedule_export_pdf") + "?view=all_teachers", follow=False
    )

    assert resp.status_code == 302
    job = ExportJob.objects.get(school=school, kind="schedule.pdf")
    assert job.status == "pending"
    assert job.requested_by_id == principal_user.id
    assert reverse("export_page", args=[job.id]) in resp.url


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
        assert job.error_message in messages.STORED_CODES  # رمزٌ ثابتٌ لا نصُّ استثناء


def test_the_excel_job_produces_a_workbook(client_as, school, principal_user):
    client_as(principal_user).get(
        reverse("schedule_export_excel") + "?view=all_teachers&paper=a3", follow=True
    )

    job = ExportJob.objects.get(school=school, kind="schedule.xlsx")
    assert job.status == "done"
    assert job.content_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert job.filename.endswith(".xlsx")


def test_a_user_cannot_reach_another_users_export_job(client_as, school, principal_user):
    """IDOR: صفّ تصديرٍ يخصّ مستخدماً لا يُفتح بمعرّفه من مستخدمٍ آخر — في المسارَين المركزيّ والقديم."""
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

    for name in ("export_job_status", "export_page", "export_status", "export_download"):
        assert client_as(other_admin).get(reverse(name, args=[job.id])).status_code == 404, name


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


# ── مهلةُ المهمّة العالقة: لا تحديثَ تلقائيّاً بلا نهاية ─────────────────────


def _job(school, user, status, age_minutes):
    job = ExportJob.objects.create(
        school=school, requested_by=user, kind="schedule.pdf", status=status
    )
    ExportJob.objects.filter(pk=job.pk).update(
        created_at=timezone.now() - timedelta(minutes=age_minutes)
    )
    job.refresh_from_db()
    return job


@pytest.mark.parametrize("status", ["pending", "running"])
def test_a_stuck_job_past_the_timeout_fails_with_a_message_and_stops_refreshing(
    client_as, school, principal_user, status
):
    job = _job(school, principal_user, status, age_minutes=10)

    resp = client_as(principal_user).get(reverse("export_page", args=[job.id]))

    job.refresh_from_db()
    assert job.status == "failed" and job.error_message == messages.TIMEOUT
    assert job.finished_at is not None
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "انتهت مهلةُ تحضير الملفّ" in content
    assert 'http-equiv="refresh"' not in content  # لا إعادةَ تحميلٍ بعد الآن


def test_a_fresh_pending_job_keeps_refreshing_and_is_not_touched(client_as, school, principal_user):
    job = _job(school, principal_user, "pending", age_minutes=1)

    resp = client_as(principal_user).get(reverse("export_page", args=[job.id]))

    job.refresh_from_db()
    assert job.status == "pending" and job.error_message == ""
    assert 'http-equiv="refresh"' in resp.content.decode()


def test_the_timeout_never_overrides_a_job_the_worker_finished(school, principal_user):
    from core.exports.timeouts import expire_if_stale

    job = _job(school, principal_user, "pending", age_minutes=10)
    ExportJob.objects.filter(pk=job.pk).update(status="done")  # العاملُ أنهاها بعد قراءتنا

    assert expire_if_stale(job) is False
    job.refresh_from_db()
    assert job.status == "done"


def test_expiry_is_idempotent_and_ignores_finished_jobs(school, principal_user):
    from core.exports.timeouts import expire_if_stale

    stuck = _job(school, principal_user, "running", age_minutes=10)
    done = _job(school, principal_user, "done", age_minutes=10)

    assert expire_if_stale(stuck) is True
    assert expire_if_stale(stuck) is False  # ثانيةً: لم يعد نشطاً
    assert expire_if_stale(done) is False
    done.refresh_from_db()
    assert done.status == "done"


# ── الإشعار العائم: JSON بدل صفحة المتابعة (عقدُ الاستجابة) ────────────────────

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


def test_an_ajax_export_request_gets_202_json_with_the_status_url_not_a_redirect(
    client_as, school, principal_user, monkeypatch
):
    import core.tasks as tasks_module

    monkeypatch.setattr(tasks_module.run_export_job, "apply_async", lambda *a, **k: None)

    resp = client_as(principal_user).get(
        reverse("schedule_export_excel") + "?view=all_teachers", **AJAX
    )

    job = ExportJob.objects.get(school=school, kind="schedule.xlsx")
    assert resp.status_code == 202
    assert resp.json() == {
        "job": str(job.id),
        "job_id": str(job.id),
        "status_url": reverse("export_status", args=[job.id]),
        "poll_ms": 2000,
    }


def test_the_status_endpoint_is_always_json_and_ignores_the_legacy_format_switch(
    client_as, school, principal_user
):
    job = _job(school, principal_user, "pending", age_minutes=1)

    plain = client_as(principal_user).get(reverse("export_status", args=[job.id]))
    legacy = client_as(principal_user).get(reverse("export_status", args=[job.id]) + "?format=json")

    expected = {"status": "pending", "download_url": None, "error": None}
    assert plain.json() == expected and legacy.json() == expected


def test_a_failure_carries_a_fixed_arabic_message_never_an_exception_text(
    client_as, school, principal_user
):
    job = _job(school, principal_user, "failed", age_minutes=1)
    ExportJob.objects.filter(pk=job.pk).update(error_message="سببٌ صريح — SELECT password FROM x")

    body = client_as(principal_user).get(reverse("export_status", args=[job.id])).json()

    assert body["status"] == "failed" and body["download_url"] is None
    assert body["error"] == {"code": "failed", "message": messages.MESSAGES["failed"]}
    assert "SELECT" not in str(body)


def test_a_done_job_downloads_the_file_repeatedly_and_each_fetch_is_audited(
    client_as, school, principal_user
):
    from core.models.audit import AuditLog

    job = ExportJob.objects.create(
        school=school,
        requested_by=principal_user,
        kind="schedule.pdf",
        status="done",
        content=b"%PDF-1.4 x",
        content_type="application/pdf",
        filename="جدول.pdf",
    )
    client = client_as(principal_user)
    status = client.get(reverse("export_status", args=[job.id])).json()
    assert status == {
        "status": "done",
        "download_url": reverse("export_download", args=[job.id]),
        "error": None,
    }

    for _ in range(2):
        resp = client.get(status["download_url"])
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/pdf"
        assert "attachment" in resp["Content-Disposition"]
        assert resp.content == b"%PDF-1.4 x"

    assert (
        AuditLog.objects.filter(action="export", object_repr="schedule.pdf:download").count() == 2
    )


def test_the_legacy_status_route_still_answers_the_old_shape_and_redirects_the_rest(
    client_as, school, principal_user
):
    job = _job(school, principal_user, "pending", age_minutes=1)
    old = reverse("export_job_status", args=[job.id])

    legacy = client_as(principal_user).get(old + "?format=json")
    plain = client_as(principal_user).get(old)

    assert legacy.json() == {"status": "pending", "error": ""}
    assert plain.status_code == 302 and plain.url == reverse("export_page", args=[job.id])


def test_a_done_job_at_the_page_url_redirects_to_the_file(client_as, school, principal_user):
    job = ExportJob.objects.create(
        school=school,
        requested_by=principal_user,
        kind="schedule.pdf",
        status="done",
        content=b"%PDF-1.4 x",
        content_type="application/pdf",
        filename="جدول.pdf",
    )

    resp = client_as(principal_user).get(reverse("export_page", args=[job.id]))

    assert resp.status_code == 302 and resp.url == reverse("export_download", args=[job.id])


def test_the_standalone_sheet_exports_through_the_platform_page_not_a_status_page(
    client_as, principal_user
):
    """الورقةُ المستقلّة بلا إشعارٍ عائم — فتصديرُها يفتح صفحةَ الجدول بـ`export=` بالاختيار نفسِه."""
    html = (
        client_as(principal_user)
        .get(reverse("schedule_print") + "?view=all_teachers&paper=a3")
        .content.decode()
    )

    page = reverse("weekly_schedule")
    assert f'href="{page}?view=all_teachers&amp;paper=a3' in html
    assert "&amp;export=pdf" in html and "&amp;export=excel" in html
    assert reverse("schedule_export_pdf") not in html
    assert reverse("schedule_export_excel") not in html
