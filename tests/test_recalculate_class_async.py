"""إعادةُ حساب الشعبة خلفيّاً (W-20261027-029): الطابورُ من الإعداد، وعلَمُ «قيد الحساب»، وبنّاءُ كشف النتائج Excel."""

from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.http import QueryDict

from assessments import tasks
from assessments.models import SubjectClassSetup
from operations.models import Subject


@pytest.fixture
def setup(db, school, class_group, teacher_user):
    subject = Subject.objects.create(school=school, name_ar="العلوم", code="SCI")
    return SubjectClassSetup.objects.create(
        school=school,
        subject=subject,
        class_group=class_group,
        teacher=teacher_user,
        academic_year="2025-2026",
    )


@pytest.fixture(autouse=True)
def _clean_flag(db):
    yield
    cache.clear()


class TestDispatch:
    def test_queue_comes_from_settings_not_a_literal(self, setup, settings):
        settings.EXPORT_JOB_QUEUE = "exports"
        with patch.object(tasks.recalculate_class_task, "apply_async") as send:
            tasks.dispatch_recalculate_class(setup.pk, "u1")
        assert send.call_args.kwargs["queue"] == "exports"
        assert tasks.is_recalculating(setup.pk)

    def test_without_setting_no_explicit_queue(self, setup, settings):
        if hasattr(settings, "EXPORT_JOB_QUEUE"):
            del settings.EXPORT_JOB_QUEUE
        with patch.object(tasks.recalculate_class_task, "apply_async") as send:
            tasks.dispatch_recalculate_class(setup.pk)
        assert "queue" not in send.call_args.kwargs


class TestTask:
    def test_runs_service_and_clears_flag(self, setup):
        cache.set(tasks.recalc_flag_key(setup.pk), "1", 60)
        with patch("assessments.services.GradeService.recalculate_full_class") as svc:
            out = tasks.recalculate_class_task(str(setup.pk))
        assert out == {"ok": True} and svc.call_count == 1
        assert not tasks.is_recalculating(setup.pk)

    def test_failure_returns_fixed_code_and_clears_flag(self, setup):
        cache.set(tasks.recalc_flag_key(setup.pk), "1", 60)
        with patch(
            "assessments.services.GradeService.recalculate_full_class",
            side_effect=RuntimeError("سرّ"),
        ):
            out = tasks.recalculate_class_task(str(setup.pk))
        assert out == {"ok": False, "code": "failed"}
        assert not tasks.is_recalculating(setup.pk)


class TestView:
    def test_post_dispatches_and_does_not_calculate_inline(
        self, client_as, teacher_user, setup, enrolled_student
    ):
        with (
            patch("assessments.views.dispatch_recalculate_class", return_value=True) as send,
            patch("assessments.services.GradeService.recalculate_full_class") as inline,
        ):
            resp = client_as(teacher_user).post(f"/assessments/setup/{setup.id}/recalculate/")
        assert resp.status_code == 302
        send.assert_called_once()
        inline.assert_not_called()

    def test_second_post_while_running_does_not_dispatch_again(
        self, client_as, teacher_user, setup, enrolled_student
    ):
        cache.set(tasks.recalc_flag_key(setup.pk), "1", 60)
        with patch.object(tasks.recalculate_class_task, "apply_async") as send:
            client_as(teacher_user).post(f"/assessments/setup/{setup.id}/recalculate/")
        send.assert_not_called()


class TestClassResultsXlsxBuilder:
    def test_builder_returns_workbook_bytes_and_denies_foreign_teacher(
        self, school, principal_user, teacher_user, class_group
    ):
        from django.core.exceptions import PermissionDenied

        from reports.export_builders import build_class_results_xlsx

        params = QueryDict(f"class_id={class_group.pk}&year=2025-2026")
        result = build_class_results_xlsx(school, principal_user, params)
        assert result.content[:2] == b"PK" and result.filename.endswith(".xlsx")
        assert result.full_national_id is False
        with pytest.raises(PermissionDenied):
            build_class_results_xlsx(school, teacher_user, params)  # معلّمٌ بلا إسنادٍ لهذا الفصل
