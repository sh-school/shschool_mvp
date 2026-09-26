"""آليّةُ التصدير المركزيّة (VI-30ب): السجلُّ، والسقوف، ورموزُ الخطأ بلا نصّ استثناء، والاحتفاظُ الصلب.

عقدُ Backend (2026-09-26): (1) احتفاظٌ صلبٌ 24 ساعةً بمهمّةٍ كلَّ ساعة تحذف الصفَّ كلَّه في كلّ الحالات؛ (2) رموزٌ ثابتةٌ
لا `str(exc)`؛ (3) سجلٌّ بلا `exc_info` ولا نصّ استثناء — بقيمةٍ كاناري؛ (5) سقفٌ للحجم وللصفوف النشطة وdedupe؛
(6) القدرةُ تُفحص في العامل ثانيةً؛ والافتراضُ الآمنُ: نوعٌ متزامنٌ بلا قياسِ p95 مثبَّتٍ لا يُسجَّل.
والحرّاسُ الساكنةُ (كلُّ `log_export(kind)` له بنّاءٌ أو في قائمةٍ تنقص) في `tests/test_export_guards.py`.
"""

import json
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.utils import timezone

from core.exports import messages, registry
from core.exports.registry import ExportResult
from core.exports.runner import run_job
from core.exports.services import DIRECT_LOCK_SECONDS, MAX_ACTIVE_PER_USER, respond_export
from core.models import ExportJob

pytestmark = pytest.mark.django_db

CANARY = "SECRET-CANARY-7f3a"
AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


def _ok(school, user, params):
    return ExportResult(b"data-" + params.urlencode().encode(), "text/plain", "t.txt")


@pytest.fixture
def register():
    """يسجّل أنواعاً تجريبيّةً `test.*` ويُزيلها بعد الاختبار فيبقى السجلُّ كما كان."""

    def _register(name="test.export", **overrides):
        options = {"build": _ok, "capability": "schedule.settings", **overrides}
        registry.register(name, **options)
        return name

    yield _register
    for name in [k for k in registry.kinds() if k.startswith("test.")]:
        registry.unregister(name)


def _request(school, user, query="a=1", **extra):
    request = RequestFactory().get(f"/x/?{query}", **extra)
    request.user = user
    request.school = school
    return request


def _teacher(school):
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    user = UserFactory(full_name="معلّمٌ")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


# ── السجلّ ──────────────────────────────────────────────────────────────


class TestTheRegistry:
    def test_a_kind_registers_once(self, register):
        register("test.once")
        with pytest.raises(ValueError, match="مسجَّلٌ من قبل"):
            register("test.once")

    def test_the_schedule_kinds_are_registered_by_the_operations_app(self):
        kinds = registry.kinds()
        assert {"schedule.pdf", "schedule.xlsx", "schedule.pages_pdf"} <= set(kinds)
        assert all(
            kinds[k].mode == "job" for k in ("schedule.pdf", "schedule.xlsx", "schedule.pages_pdf")
        )

    def test_a_direct_kind_without_a_measured_p95_is_refused(self, register):
        """الافتراضُ الآمن: نوعٌ جديدٌ أو غيرُ مقيسٍ = خلفيّ."""
        with pytest.raises(ValueError, match="بلا قياسِ p95"):
            register("test.unmeasured", mode="direct")
        with pytest.raises(ValueError, match="بلا قياسِ p95"):
            register("test.nosource", mode="direct", p95_ms=400)

    def test_a_direct_kind_above_the_ceiling_is_refused(self, register):
        with pytest.raises(ValueError, match="يجب أن يكون job"):
            register("test.slow", mode="direct", p95_ms=1500, measured_on="warm×20 2026-09-26")

    def test_a_measured_fast_kind_may_be_direct(self, register):
        spec = registry.get(
            register("test.fast", mode="direct", p95_ms=420, measured_on="warm×20 2026-09-26")
        )
        assert spec.mode == "direct" and spec.p95_ms == 420


# ── المدخل: قدرةٌ وسقوفٌ وdedupe ────────────────────────────────────────────


class TestTheEntryPoint:
    def test_an_unknown_kind_fails_closed_with_a_fixed_code(self, school, principal_user):
        response = respond_export(_request(school, principal_user, **AJAX), "test.nope")

        assert response.status_code == 400
        assert json.loads(response.content) == {"error": messages.error_payload("unknown_kind")}
        assert not ExportJob.objects.exists()

    def test_a_user_without_the_capability_is_refused(self, school, register):
        register()
        teacher = _teacher(school)

        response = respond_export(_request(school, teacher, **AJAX), "test.export")
        assert response.status_code == 403
        assert json.loads(response.content)["error"]["code"] == "forbidden"
        with pytest.raises(PermissionDenied):
            respond_export(_request(school, teacher), "test.export")
        assert not ExportJob.objects.exists()

    def test_a_job_answers_202_with_the_contract_shape(self, school, principal_user, register):
        register()

        response = respond_export(_request(school, principal_user, **AJAX), "test.export")

        job = ExportJob.objects.get()
        assert response.status_code == 202
        body = json.loads(response.content)
        assert body["job"] == body["job_id"] == str(job.id)
        assert body["status_url"] == f"/exports/{job.id}/status/" and body["poll_ms"] == 2000

    def test_the_same_request_within_a_minute_returns_the_same_job(
        self, school, principal_user, register
    ):
        register()

        first = json.loads(
            respond_export(_request(school, principal_user, **AJAX), "test.export").content
        )
        again = json.loads(
            respond_export(_request(school, principal_user, **AJAX), "test.export").content
        )
        other = json.loads(
            respond_export(
                _request(school, principal_user, query="a=2", **AJAX), "test.export"
            ).content
        )

        assert first["job"] == again["job"] and other["job"] != first["job"]
        assert ExportJob.objects.count() == 2

    def test_a_dedupe_never_reuses_a_failed_job(self, school, principal_user, register):
        register()
        failed = ExportJob.objects.create(
            school=school,
            requested_by=principal_user,
            kind="test.export",
            query_string="a=1",
            status="failed",
        )

        body = json.loads(
            respond_export(_request(school, principal_user, **AJAX), "test.export").content
        )

        assert body["job"] != str(failed.id)

    def test_the_active_jobs_cap_answers_429_busy_with_a_fixed_message(
        self, school, principal_user, register
    ):
        register()
        for i in range(MAX_ACTIVE_PER_USER):
            ExportJob.objects.create(
                school=school,
                requested_by=principal_user,
                kind="test.export",
                query_string=f"n={i}",
            )

        response = respond_export(
            _request(school, principal_user, query="n=99", **AJAX), "test.export"
        )

        assert response.status_code == 429
        assert json.loads(response.content) == {"error": messages.error_payload("busy")}
        assert ExportJob.objects.count() == MAX_ACTIVE_PER_USER


# ── النمطُ المتزامن (بقياسٍ مثبَّتٍ فقط) ───────────────────────────────────


class TestTheDirectMode:
    @pytest.fixture
    def direct(self, register):
        return register(
            "test.direct", mode="direct", p95_ms=420, measured_on="warm×20 2026-09-26", max_bytes=64
        )

    def test_it_returns_the_file_itself(self, school, principal_user, direct):
        response = respond_export(_request(school, principal_user, **AJAX), direct)

        assert response.status_code == 200
        assert response["Content-Type"] == "text/plain"
        assert "attachment" in response["Content-Disposition"]
        assert response.content == b"data-a=1"
        assert not ExportJob.objects.exists()  # لا صفَّ لمتزامن

    def test_one_direct_export_per_user_at_a_time(self, school, principal_user, direct):
        cache.set(f"export:direct:{principal_user.pk}", "1", timeout=DIRECT_LOCK_SECONDS)

        response = respond_export(_request(school, principal_user, **AJAX), direct)

        assert response.status_code == 429
        assert json.loads(response.content)["error"]["code"] == "busy"
        cache.delete(f"export:direct:{principal_user.pk}")

    def test_an_oversized_file_is_413_with_a_fixed_code(self, school, principal_user, register):
        name = register(
            "test.big",
            mode="direct",
            p95_ms=300,
            measured_on="warm×20 2026-09-26",
            max_bytes=4,
        )

        response = respond_export(_request(school, principal_user, **AJAX), name)

        assert response.status_code == 413
        assert json.loads(response.content)["error"]["code"] == "too_large"

    def test_a_failure_never_leaks_the_exception_text(
        self, school, principal_user, register, caplog
    ):
        def boom(school, user, params):
            raise RuntimeError(CANARY)

        name = register(
            "test.boom", build=boom, mode="direct", p95_ms=300, measured_on="warm×20 2026-09-26"
        )

        response = respond_export(_request(school, principal_user, **AJAX), name)

        assert response.status_code == 500
        assert CANARY not in response.content.decode()
        assert CANARY not in caplog.text and all(r.exc_info is None for r in caplog.records)
        assert cache.get(f"export:direct:{principal_user.pk}") is None  # القفلُ يُفَكّ


# ── العامل: رموزٌ ثابتةٌ بلا نصّ استثناءٍ ولا exc_info ──────────────────────


def _job(school, user, kind="test.export", **extra):
    return ExportJob.objects.create(
        school=school, requested_by=user, kind=kind, query_string="a=1", **extra
    )


class TestTheWorker:
    def test_it_builds_and_stores_the_file(self, school, principal_user, register):
        register()
        job = _job(school, principal_user)

        result = run_job(str(job.id))

        job.refresh_from_db()
        assert result == {"ok": True, "filename": "t.txt"}
        assert job.status == "done" and bytes(job.content) == b"data-a=1"
        assert job.content_type == "text/plain" and job.filename == "t.txt"

    def test_a_failing_builder_stores_only_a_fixed_code_and_logs_no_exception_text(
        self, school, principal_user, register, caplog
    ):
        """الكاناري: قيمةٌ سرّيّةٌ في نصّ الاستثناء لا تظهر في القاعدة ولا الردّ ولا السجلّ ولا الإطارات."""

        def boom(school, user, params):
            secret = CANARY  # noqa: F841 — متغيّرٌ محلّيٌّ كان سيظهر في إطارات Sentry
            raise RuntimeError(f"SELECT * FROM x WHERE token = '{CANARY}'")

        register(build=boom)
        job = _job(school, principal_user)

        with caplog.at_level("DEBUG"):
            run_job(str(job.id))

        job.refresh_from_db()
        assert job.status == "failed" and job.error_message == messages.FAILED
        assert CANARY not in caplog.text
        assert all(r.exc_info is None and r.exc_text is None for r in caplog.records)
        assert any("export_job_failed" in r.getMessage() for r in caplog.records)
        assert CANARY not in json.dumps(
            __import__("core.exports.services", fromlist=["status_payload"]).status_payload(job)
        )

    def test_an_oversized_result_is_too_large(self, school, principal_user, register):
        register(max_bytes=3)
        job = _job(school, principal_user)

        run_job(str(job.id))

        job.refresh_from_db()
        assert job.status == "failed" and job.error_message == messages.TOO_LARGE
        assert not job.content

    def test_the_capability_is_checked_again_in_the_worker(self, school, register):
        register()
        job = _job(school, _teacher(school))  # سُحبت صلاحيّتُه (أو لم تكن) بين الطلب والتنفيذ

        run_job(str(job.id))

        job.refresh_from_db()
        assert job.status == "failed" and job.error_message == messages.FORBIDDEN

    def test_an_unregistered_kind_fails_with_a_fixed_code(self, school, principal_user):
        job = _job(school, principal_user, kind="test.never_registered")

        run_job(str(job.id))

        job.refresh_from_db()
        assert job.status == "failed" and job.error_message == messages.FAILED

    def test_a_job_that_is_not_pending_is_not_built_twice(self, school, principal_user, register):
        calls = []

        def counting(school, user, params):
            calls.append(1)
            return ExportResult(b"x", "text/plain", "t.txt")

        register(build=counting)
        job = _job(school, principal_user, status="running")

        assert run_job(str(job.id)) == {"ok": False, "code": "not_pending"}
        assert calls == []

    def test_a_legacy_row_with_a_long_message_never_reaches_the_client(
        self, school, principal_user
    ):
        job = _job(school, principal_user, status="failed")
        ExportJob.objects.filter(pk=job.pk).update(error_message="سببٌ طويلٌ فيه SELECT password")
        job.refresh_from_db()

        payload = __import__("core.exports.services", fromlist=["status_payload"]).status_payload(
            job
        )

        assert payload["error"] == messages.error_payload("failed")


# ── الاحتفاظ: حدٌّ صلبٌ 24 ساعةً كلَّ ساعة لكلّ الحالات ─────────────────────


class TestRetention:
    def test_the_purge_runs_every_hour(self):
        from celery.schedules import crontab

        from shschool.celery import app

        entry = app.conf.beat_schedule["purge-expired-export-jobs"]
        assert entry["task"] == "operations.purge_expired_export_jobs"
        assert entry["schedule"] == crontab(minute=5)

    @pytest.mark.parametrize("status", ["pending", "running", "done", "failed"])
    def test_a_row_older_than_a_day_is_deleted_whatever_its_state(
        self, school, principal_user, status
    ):
        from operations.tasks import purge_expired_export_jobs_task

        old = _job(school, principal_user, status=status)
        ExportJob.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=25))
        fresh = _job(school, principal_user, status=status)

        purge_expired_export_jobs_task()

        assert not ExportJob.objects.filter(pk=old.pk).exists()
        assert ExportJob.objects.filter(pk=fresh.pk).exists()

    def test_the_documented_retention_matches_the_code(self):
        from pathlib import Path

        doc = (Path(__file__).resolve().parent.parent / "docs/privacy/data_retention.md").read_text(
            encoding="utf-8"
        )
        assert "كلَّ ساعة" in doc and "رمزاً ثابتاً" in doc


# ── المسارات والمهمّة ───────────────────────────────────────────────────


class TestTheWiring:
    def test_the_task_keeps_a_time_limit_below_the_row_timeout(self):
        from core.exports.timeouts import EXPORT_JOB_TIMEOUT
        from core.tasks import run_export_job

        assert run_export_job.name == "core.export.run_job"
        assert (
            run_export_job.soft_time_limit
            < run_export_job.time_limit
            < EXPORT_JOB_TIMEOUT.total_seconds()
        )

    def test_the_legacy_task_name_stays_and_delegates(self, school, principal_user, register):
        """أسماءُ المهامّ تبقى: صفوفٌ أُنشئت قبل النشر وعاملٌ لم يُحدَّث يشيران إليها."""
        from operations.tasks import render_schedule_export_task

        register()
        job = _job(school, principal_user)

        result = render_schedule_export_task.apply(args=[str(job.id), "pdf"]).get()

        job.refresh_from_db()
        assert render_schedule_export_task.name == "operations.render_schedule_export"
        assert result["ok"] is True and job.status == "done"
