"""شهاداتُ الفصل PDF مهمّةٌ خلفيّةٌ عبر سجلّ التصدير المركزيّ (VI-30ب، الطلب 3).

كانت متزامنةً 2.9ث (قياس 2026-09-26). زرُّ «تحميل» في عارض التقارير (`download=1`) صار يُنشئ صفَّ تصديرٍ ويردّ فوراً؛
أمّا المعاينةُ (`preview=1`) والإطارُ المضمَّنُ في العارض فيبقيان متزامنَين — عرضٌ يقرأ المهمّةَ قرارُ تصميمٍ منفصل.
ما يُحرس هنا: أنّ `class_id` (من الرابط لا من الاستعلام) يصل العامل، وأنّ فصلَ مدرسةٍ أخرى لا يُبنى، وأنّ الرقمَ الشخصيَّ مستورٌ،
وأنّ العاملَ لا يحلّ ملفّاً ساكناً بـmanifest، وأنّ أثرَ «كم صفّاً خرج ولأيّ فصل» ما زال يُكتب.
"""

import json

import pytest
from django.core.exceptions import PermissionDenied
from django.http import QueryDict
from django.urls import reverse

from core.exports import registry
from core.exports.runner import run_job
from core.models import AuditLog, ExportJob
from reports.export_builders import build_class_certificates_pdf
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    SchoolFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

KIND = "reports.class_certificates"
STUDENT_ID = "99900000538"
MASKED = "*******0538"
STRICT_MANIFEST = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


@pytest.fixture
def klass(school, seeded_calendar):
    return ClassGroupFactory(school=school, academic_year=seeded_calendar, grade="G7", section="أ")


@pytest.fixture
def pupil(school, klass):
    user = UserFactory(full_name="طالبُ الشهادة", national_id=STUDENT_ID)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    StudentEnrollmentFactory(student=user, class_group=klass)
    return user


@pytest.fixture
def captured(monkeypatch):
    """يلتقط (HTML، المقاس) الذي كان سيُحوَّل PDF — بلا WeasyPrint فيُقاس المضمونُ لا الوقت."""
    seen: list[tuple[str, str]] = []

    def fake(html, paper_size="A4"):
        seen.append((html, paper_size))
        return b"%PDF-stub"

    monkeypatch.setattr("core.pdf_utils.render_pdf_bytes", fake)
    return seen


def _run(school, user, klass, query=""):
    params = QueryDict(query, mutable=True)
    params["class_id"] = str(klass.pk)
    job = ExportJob.objects.create(
        school=school, requested_by=user, kind=KIND, query_string=params.urlencode()
    )
    result = run_job(str(job.id))
    job.refresh_from_db()
    return job, result


class TestTheRegistration:
    def test_it_is_a_background_job_for_school_report_readers(self):
        spec = registry.get(KIND)

        assert spec is not None
        assert spec.mode == "job", "2.9ث مقيسةً — لا يجوز متزامناً"
        assert spec.capability == "reports.school"


class TestTheView:
    def _no_build(self, monkeypatch):
        def forbidden(*args, **kwargs):
            raise AssertionError("PDF يُولَّد داخل طلب الويب")

        # `_generate_pdf_bytes` يقرؤه `render_pdf` و`render_pdf_bytes` معاً وقتَ النداء؛ ولا يُرقَّع `render_pdf` نفسُه: وحدةُ العرض
        # تستورده بالاسم عند أوّل طلبٍ فيبقى المرقَّعُ فيها بعد الاختبار ويُفسد ما بعده.
        monkeypatch.setattr("core.pdf_utils._generate_pdf_bytes", forbidden)
        monkeypatch.setattr("core.tasks.run_export_job.apply_async", lambda *a, **k: None)

    def test_the_download_button_starts_a_job_and_builds_nothing(
        self, client_as, principal_user, klass, pupil, monkeypatch
    ):
        self._no_build(monkeypatch)

        resp = client_as(principal_user).get(
            reverse("class_certificates_pdf", args=[klass.pk]) + "?download=1&paper=A3", **AJAX
        )

        job = ExportJob.objects.get()
        assert resp.status_code == 202
        assert json.loads(resp.content)["status_url"] == f"/exports/{job.id}/status/"
        assert job.kind == KIND and job.status == "pending"
        stored = QueryDict(job.query_string)
        assert stored["class_id"] == str(klass.pk) and stored["paper"] == "A3"
        assert "download" not in stored

    def test_without_js_the_link_lands_on_the_status_page(
        self, client_as, principal_user, klass, pupil, monkeypatch
    ):
        self._no_build(monkeypatch)

        resp = client_as(principal_user).get(
            reverse("class_certificates_pdf", args=[klass.pk]) + "?download=1"
        )

        assert resp.status_code == 302
        assert resp["Location"] == reverse("export_page", args=[ExportJob.objects.get().id])

    def test_a_class_of_another_school_is_a_404_and_no_job(
        self, client_as, principal_user, seeded_calendar, monkeypatch
    ):
        self._no_build(monkeypatch)
        foreign = ClassGroupFactory(
            school=SchoolFactory(), academic_year=seeded_calendar, grade="G7", section="ز"
        )

        resp = client_as(principal_user).get(
            reverse("class_certificates_pdf", args=[foreign.pk]) + "?download=1", **AJAX
        )

        assert resp.status_code == 404
        assert not ExportJob.objects.exists()

    def test_the_preview_and_the_viewer_frame_stay_synchronous(
        self, client_as, principal_user, klass, pupil
    ):
        """المعاينةُ HTML، والإطارُ المضمَّنُ PDF مباشرٌ inline — لا صفَّ تصديرٍ لهما."""
        preview = client_as(principal_user).get(
            reverse("class_certificates_pdf", args=[klass.pk]) + "?preview=1"
        )
        frame = client_as(principal_user).get(reverse("class_certificates_pdf", args=[klass.pk]))

        assert preview.status_code == 200 and MASKED in preview.content.decode()
        assert frame.status_code == 200 and frame["Content-Type"] == "application/pdf"
        assert frame["Content-Disposition"].startswith("inline;")
        assert not ExportJob.objects.exists()

    def test_a_teacher_without_the_capability_gets_no_job(self, client_as, school, klass, pupil):
        teacher = UserFactory(full_name="معلّمٌ")
        MembershipFactory(
            user=teacher, school=school, role=RoleFactory(school=school, name="teacher")
        )

        resp = client_as(teacher).get(
            reverse("class_certificates_pdf", args=[klass.pk]) + "?download=1", **AJAX
        )

        assert resp.status_code in (302, 403)
        assert not ExportJob.objects.exists()


class TestTheWorkerBuildsTheSameFile:
    def test_the_class_and_paper_survive_the_trip_through_the_query_string(
        self, school, principal_user, klass, pupil, captured
    ):
        job, result = _run(school, principal_user, klass, "paper=a3&year=2030-2031")

        assert result["ok"] is True and job.status == "done"
        html, paper = captured[0]
        assert paper == "A3" and "طالبُ الشهادة" in html and "2030-2031" in html
        assert job.filename == "شهادات_7_أ_2030-2031.pdf"

    def test_the_number_is_masked_in_a_class_file(
        self, school, principal_user, klass, pupil, captured
    ):
        _run(school, principal_user, klass)

        html, _ = captured[0]
        assert MASKED in html
        assert STUDENT_ID not in html, "ملفٌّ واحدٌ لفصلٍ كامل كشفٌ جماعيّ — يُستر وإن طُبع"

    def test_a_class_of_another_school_is_never_built(
        self, school, principal_user, seeded_calendar, captured
    ):
        foreign = ClassGroupFactory(
            school=SchoolFactory(), academic_year=seeded_calendar, grade="G7", section="ز"
        )

        job, result = _run(school, principal_user, foreign)

        assert job.status == "failed" and job.error_message == "failed"
        assert not captured

    def test_it_renders_under_a_strict_manifest_like_the_worker_has(
        self, school, principal_user, klass, pupil, captured, settings
    ):
        """العاملُ بلا manifest الويب: أيُّ `{% static %}` غيرِ محروسٍ يرمي فتفشل المهمّةُ صامتةً برمزٍ ثابت."""
        settings.STORAGES = {**settings.STORAGES, "staticfiles": {"BACKEND": STRICT_MANIFEST}}

        job, result = _run(school, principal_user, klass)

        assert result["ok"] is True, "قالبُ شهادات الفصل يحلّ ملفّاً ساكناً في مسار PDF"
        assert "app-back-bar" not in captured[0][0]

    def test_a_real_pdf_is_produced(self, school, principal_user, klass, pupil):
        job, result = _run(school, principal_user, klass)

        assert job.status == "done" and bytes(job.content).startswith(b"%PDF")
        assert job.content_type == "application/pdf"


class TestTheDownloadThroughTheJob:
    def test_the_finished_file_downloads_as_an_attachment_with_the_arabic_name(
        self, client_as, principal_user, school, klass, pupil, captured
    ):
        """الترويسةُ على استجابةٍ حقيقيّة (كان العطبُ في ترميز RFC 2047 لاسمٍ عربيّ لا في المنطق)."""
        job, _ = _run(school, principal_user, klass)

        resp = client_as(principal_user).get(reverse("export_download", args=[job.id]))

        disposition = resp["Content-Disposition"]
        assert resp.status_code == 200 and disposition.startswith("attachment;")
        assert not disposition.startswith("=?"), "الترويسة مُرمَّزة بـRFC 2047"
        assert "UTF-8''" in disposition and resp.content == b"%PDF-stub"


class TestTheAuditTrail:
    def test_the_built_entry_names_the_class_and_the_rows_and_no_full_number(
        self, school, principal_user, klass, pupil, captured
    ):
        _run(school, principal_user, klass)

        trail = AuditLog.objects.get(
            action="export", changes__kind=KIND, object_repr=f"{KIND}:built"
        )
        assert trail.user == principal_user and trail.object_id == str(klass.pk)
        assert trail.changes == {"kind": KIND, "rows": 1, "full_national_id": False}
        assert STUDENT_ID not in (trail.object_repr + json.dumps(trail.changes))

    def test_the_request_is_audited_before_the_build(
        self, client_as, principal_user, klass, pupil, monkeypatch
    ):
        monkeypatch.setattr("core.tasks.run_export_job.apply_async", lambda *a, **k: None)

        client_as(principal_user).get(
            reverse("class_certificates_pdf", args=[klass.pk]) + "?download=1", **AJAX
        )

        assert AuditLog.objects.filter(action="export", changes__kind=KIND).count() == 1


def test_the_builder_refuses_a_non_admin(school, klass, pupil, captured):
    """العاملُ يفحص القدرةَ فقط؛ ما كان الـview يشترطه (`is_admin`) يُعاد فحصُه في البنّاء."""
    teacher = UserFactory(full_name="معلّمٌ")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))

    with pytest.raises(PermissionDenied):
        build_class_certificates_pdf(school, teacher, QueryDict(f"class_id={klass.pk}"))

    assert not captured


def test_the_builder_needs_no_request(school, principal_user, klass, pupil, captured):
    result = build_class_certificates_pdf(school, principal_user, QueryDict(f"class_id={klass.pk}"))

    assert result.rows == 1 and result.object_id == str(klass.pk)
    assert result.full_national_id is False and result.content_type == "application/pdf"
