"""قائمةُ الطلاب PDF مهمّةٌ خلفيّةٌ عبر سجلّ التصدير المركزيّ (VI-30ب، الطلب 2).

كانت متزامنةً 8.3ث على قاعدة القياس (2026-09-26) — WeasyPrint على سجلّ المدرسة كلِّه داخل طلب الويب. فصارت الـview تُنشئ
صفَّ تصديرٍ وتردّ فوراً، والعاملُ يبني الملفَّ بالمُحدِّد نفسِه الذي يبني به Excel (`student_affairs.selectors.student_register`).
ما يُحرس هنا: أنّ الترشيحَ يصل العاملَ سليماً، وأنّ الرقمَ الشخصيَّ مستورٌ (كشفٌ جماعيّ)، وأنّ العاملَ لا يحلّ ملفّاً ساكناً
بـmanifest (Sentry SCHOOLOS-PRODUCTION-2X)، وأنّ أثرَ «كم صفّاً خرج» الذي كان يكتبه المسارُ المتزامنُ ما زال يُكتب.
"""

import json

import pytest
from django.http import QueryDict
from django.urls import reverse

from core.exports import registry
from core.exports.runner import run_job
from core.models import AuditLog, ExportJob
from student_affairs.export_builders import build_students_pdf
from student_affairs.list_selectors import rows_for
from student_affairs.selectors import student_register
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

KIND = "student_affairs.students_pdf"
STUDENT_ID = "99900000538"
MASKED = "*******0538"
STRICT_MANIFEST = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


def _pupil(school, name, national_id, klass=None):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    if klass is not None:
        StudentEnrollmentFactory(student=user, class_group=klass)
    return user


@pytest.fixture
def seventh(school, seeded_calendar):
    return ClassGroupFactory(school=school, academic_year=seeded_calendar, grade="G7", section="أ")


@pytest.fixture
def eighth(school, seeded_calendar):
    return ClassGroupFactory(school=school, academic_year=seeded_calendar, grade="G8", section="ب")


@pytest.fixture
def pupils(school, seventh, eighth):
    return {
        "seventh": _pupil(school, "طالبُ السابع", STUDENT_ID, seventh),
        "eighth": _pupil(school, "طالبُ الثامن", "99900000777", eighth),
        "unenrolled": _pupil(school, "طالبٌ بلا قيد", "99900000999"),
    }


@pytest.fixture
def captured_html(monkeypatch):
    """يلتقط HTML الذي كان سيُحوَّل PDF — بلا WeasyPrint فيُقاس المضمونُ لا الوقت."""
    seen: list[str] = []

    def fake(html, paper_size="A4"):
        seen.append(html)
        return b"%PDF-stub"

    monkeypatch.setattr("core.pdf_utils.render_pdf_bytes", fake)
    return seen


def _run(school, user, query=""):
    job = ExportJob.objects.create(school=school, requested_by=user, kind=KIND, query_string=query)
    result = run_job(str(job.id))
    job.refresh_from_db()
    return job, result


class TestTheRegistration:
    def test_it_is_a_background_job_for_student_affairs_managers(self):
        spec = registry.get(KIND)

        assert spec is not None
        assert spec.mode == "job", "8.3ث مقيسةً — لا يجوز متزامناً"
        assert spec.capability == "student_affairs.manage"


class TestTheView:
    def test_it_answers_at_once_with_a_job_and_builds_nothing(
        self, client_as, principal_user, pupils, monkeypatch
    ):
        """الطلبُ لا يولّد PDF: الشاهدُ أنّ WeasyPrint لو نُودي من الطلب لَسقط هذا الاختبارُ."""

        def forbidden(*args, **kwargs):
            raise AssertionError("PDF يُولَّد داخل طلب الويب")

        # `_generate_pdf_bytes` يقرؤه `render_pdf` و`render_pdf_bytes` معاً وقتَ النداء؛ ولا يُرقَّع `render_pdf` نفسُه: وحدةُ العرض
        # تستورده بالاسم عند أوّل طلبٍ فيبقى المرقَّعُ فيها بعد الاختبار ويُفسد ما بعده.
        monkeypatch.setattr("core.pdf_utils._generate_pdf_bytes", forbidden)
        monkeypatch.setattr("core.tasks.run_export_job.apply_async", lambda *a, **k: None)

        resp = client_as(principal_user).get(
            reverse("student_affairs:student_list_pdf") + "?grade=G8", **AJAX
        )

        job = ExportJob.objects.get()
        body = json.loads(resp.content)
        assert resp.status_code == 202
        assert body["job"] == str(job.id) and body["status_url"] == f"/exports/{job.id}/status/"
        assert (job.kind, job.query_string, job.status) == (KIND, "grade=G8", "pending")

    def test_without_js_the_link_lands_on_the_status_page(
        self, client_as, principal_user, pupils, monkeypatch
    ):
        """الرابطُ يُفتح في تبويبٍ (`target=_blank`) بلا XHR: يُحوَّل لصفحة المتابعة فيصل الملفُّ حين يجهز."""
        monkeypatch.setattr("core.tasks.run_export_job.apply_async", lambda *a, **k: None)

        resp = client_as(principal_user).get(reverse("student_affairs:student_list_pdf"))

        job = ExportJob.objects.get()
        assert resp.status_code == 302
        assert resp["Location"] == reverse("export_page", args=[job.id])

    def test_a_teacher_without_the_capability_gets_no_job(self, client_as, school, pupils):
        teacher = UserFactory(full_name="معلّمٌ")
        MembershipFactory(
            user=teacher, school=school, role=RoleFactory(school=school, name="teacher")
        )

        resp = client_as(teacher).get(reverse("student_affairs:student_list_pdf"), **AJAX)

        assert resp.status_code == 403
        assert not ExportJob.objects.exists()


class TestTheWorkerBuildsTheSameList:
    def test_the_filters_survive_the_trip_through_the_query_string(
        self, school, principal_user, pupils, captured_html
    ):
        job, result = _run(school, principal_user, "grade=G8")

        assert result["ok"] is True and job.status == "done"
        html = captured_html[0]
        assert "طالبُ الثامن" in html
        assert "طالبُ السابع" not in html and "طالبٌ بلا قيد" not in html

    def test_by_default_only_the_enrolled_are_listed(
        self, school, principal_user, pupils, captured_html
    ):
        _run(school, principal_user)

        html = captured_html[0]
        assert "طالبُ السابع" in html and "طالبُ الثامن" in html
        assert "طالبٌ بلا قيد" not in html

    def test_the_status_all_lists_the_unenrolled_too(
        self, school, principal_user, pupils, captured_html
    ):
        _run(school, principal_user, "status=all")

        assert "طالبٌ بلا قيد" in captured_html[0]

    def test_the_number_is_masked_in_a_bulk_list(
        self, school, principal_user, pupils, captured_html
    ):
        _run(school, principal_user)

        html = captured_html[0]
        assert (
            MASKED not in html and STUDENT_ID not in html
        ), "كشفٌ جماعيّ — لا رقمَ فيه مستوراً ولا كاملاً (W-20261011-014)"

    def test_it_renders_under_a_strict_manifest_like_the_worker_has(
        self, school, principal_user, pupils, captured_html, settings
    ):
        """العاملُ بلا manifest الويب: أيُّ `{% static %}` غيرِ محروسٍ يرمي فتفشل المهمّةُ صامتةً برمزٍ ثابت."""
        settings.STORAGES = {**settings.STORAGES, "staticfiles": {"BACKEND": STRICT_MANIFEST}}

        job, result = _run(school, principal_user)

        assert result["ok"] is True, "قالبُ قائمة الطلاب يحلّ ملفّاً ساكناً في مسار PDF"
        assert "app-back-bar" not in captured_html[0]

    def test_a_real_pdf_is_produced(self, school, principal_user, pupils):
        job, result = _run(school, principal_user)

        assert job.status == "done" and bytes(job.content).startswith(b"%PDF")
        assert job.content_type == "application/pdf"
        assert job.filename.startswith("SchoolOS_students_list_") and job.filename.endswith(".pdf")


class TestTheAuditTrail:
    def test_the_built_entry_says_how_many_rows_left_and_that_no_full_number_did(
        self, school, principal_user, pupils, captured_html
    ):
        _run(school, principal_user)

        trail = AuditLog.objects.get(
            action="export", changes__kind=KIND, object_repr=f"{KIND}:built"
        )
        assert trail.user == principal_user
        assert trail.changes == {"kind": KIND, "rows": 2, "full_national_id": False}
        assert STUDENT_ID not in (trail.object_repr + json.dumps(trail.changes))

    def test_the_request_is_audited_before_the_build(
        self, client_as, principal_user, pupils, monkeypatch
    ):
        monkeypatch.setattr("core.tasks.run_export_job.apply_async", lambda *a, **k: None)

        client_as(principal_user).get(reverse("student_affairs:student_list_pdf"), **AJAX)

        assert AuditLog.objects.filter(action="export", changes__kind=KIND).count() == 1

    def test_a_failed_build_leaves_no_built_entry(
        self, school, principal_user, pupils, monkeypatch
    ):
        def boom(html, paper_size="A4"):
            raise RuntimeError("SECRET-CANARY")

        monkeypatch.setattr("core.pdf_utils.render_pdf_bytes", boom)

        job, result = _run(school, principal_user)

        assert job.status == "failed" and job.error_message == "failed"
        assert not AuditLog.objects.filter(object_repr=f"{KIND}:built").exists()


class TestTheSharedSelector:
    def test_excel_and_pdf_read_the_same_register(self, school, seeded_calendar, pupils):
        """الاستعلامُ واحدٌ للتصديرَين: من يظهر في PDF يظهر في Excel."""
        students, enrollment = student_register(school, seeded_calendar, QueryDict("grade=G7"))

        assert [m.user.full_name for m in students] == ["طالبُ السابع"]
        assert {v["class_group__grade"] for v in enrollment.values()} == {"G7", "G8"}

    def test_the_search_matches_a_name_or_a_number(self, school, seeded_calendar, pupils):
        by_name, _ = student_register(school, seeded_calendar, QueryDict("q=الثامن"))
        by_fragment, _ = student_register(
            school, seeded_calendar, QueryDict("q=0538"), partial_id=True
        )
        by_fragment_unprivileged, _ = student_register(school, seeded_calendar, QueryDict("q=0538"))

        assert [m.user.full_name for m in by_name] == ["طالبُ الثامن"]
        # الجزءُ من الرقم للإدارة وحدَها (قرارُ المالك 2026-10-05)؛ وغيرُها لا يجد به أحداً.
        assert [m.user.full_name for m in by_fragment] == ["طالبُ السابع"]
        assert list(by_fragment_unprivileged) == []


def _pdf_names(school, user, query, captured_html):
    """أسماءُ الصفوف في PDF كما رُسمت (من HTML الملتقَط)، بترتيبها."""
    captured_html.clear()
    build_students_pdf(school, user, QueryDict(query))
    html = captured_html[0]
    found = [n for n in ("أحمد سالم", "بدر خالد", "ليلى حمد", "هند سعد") if n in html]
    return sorted(found, key=html.index)


class TestThePdfEqualsThePage:
    """W-20261109-005: PDF وExcel يقرآن `rows_for` فصفوفُهما صفوفُ الصفحة، والمشرفُ لا يطبع غيرَ جناحه."""

    @pytest.fixture
    def wings(self, school, seeded_calendar):
        from core.models.academic import Wing

        mine = UserFactory(full_name="مشرف الأول", national_id="29000000011")
        other = UserFactory(full_name="مشرف الثاني", national_id="29000000012")
        for u in (mine, other):
            MembershipFactory(
                user=u, school=school, role=RoleFactory(school=school, name="admin_supervisor")
            )
        w1 = Wing.objects.create(
            school=school,
            code="w1",
            name="ج1",
            academic_year=seeded_calendar,
            supervisor=mine,
            order=1,
        )
        w2 = Wing.objects.create(
            school=school,
            code="w2",
            name="ج2",
            academic_year=seeded_calendar,
            supervisor=other,
            order=2,
        )
        k1 = ClassGroupFactory(
            school=school,
            grade="G7",
            section="1",
            academic_year=seeded_calendar,
            level_type="prep",
            wing=w1,
        )
        k2 = ClassGroupFactory(
            school=school,
            grade="G8",
            section="2",
            academic_year=seeded_calendar,
            level_type="prep",
            wing=w2,
        )
        _pupil(school, "أحمد سالم", "29000000021", k1)
        _pupil(school, "بدر خالد", "29000000022", k2)
        _pupil(school, "ليلى حمد", "29000000023", k1)
        _pupil(school, "هند سعد", "29000000024")
        return mine

    @pytest.mark.parametrize(
        "query", ["", "grade=G7&section=1", "status=all", "status=unenrolled", "grade=G8"]
    )
    def test_pdf_and_excel_rows_equal_the_page_for_a_principal(
        self, school, principal_user, wings, captured_html, client_as, query
    ):
        from django.urls import reverse

        page = client_as(principal_user).get(reverse("student_affairs:student_list") + "?" + query)
        page_names = {r["full_name"] for r in page.context["students"]}
        pdf = set(_pdf_names(school, principal_user, query, captured_html))
        xlsx = {r["full_name"] for r in rows_for(principal_user, QueryDict(query))}

        assert pdf == page_names == xlsx

    def test_the_wing_supervisor_prints_only_his_wing_with_number_and_wing_order(
        self, school, wings, captured_html
    ):
        names = _pdf_names(school, wings, "status=all", captured_html)

        assert names == ["أحمد سالم", "ليلى حمد"], "لا طالبَ من جناحٍ آخر ولا غيرَ مقيَّد"
        assert "بدر خالد" not in captured_html[0]

    def test_the_pdf_is_wing_sorted_and_numbered(
        self, school, principal_user, wings, captured_html
    ):
        names = _pdf_names(school, principal_user, "", captured_html)

        # الجناح 1 (أحمد، ليلى) ثمّ الجناح 2 (بدر) — لا فرزَ بالاسم وحده.
        assert names == ["أحمد سالم", "ليلى حمد", "بدر خالد"]
        assert ">م<" in captured_html[0]

    def test_the_pdf_honours_status_and_parent_status(
        self, school, principal_user, wings, captured_html
    ):
        assert _pdf_names(school, principal_user, "status=unenrolled", captured_html) == ["هند سعد"]
        assert _pdf_names(school, principal_user, "parent_status=linked", captured_html) == []

    def test_the_admin_sees_a_wing_filter_that_narrows_page_pdf_and_excel(
        self, school, principal_user, wings, captured_html, client_as
    ):
        """رفضُ المالك: لا فلترَ للجناح في سجلّ الطلاب للمدير — يظهر ويُضيّق الصفحةَ والملفَّين معاً."""
        from django.urls import reverse

        from core.models.academic import Wing

        w2 = Wing.objects.get(school=school, code="w2")
        query = f"wing={w2.pk}"
        page = client_as(principal_user).get(reverse("student_affairs:student_list") + "?" + query)

        assert [name for _pk, name in page.context["wings"]] == ["ج1", "ج2"]
        assert 'name="wing"' in page.content.decode()
        assert [r["full_name"] for r in page.context["students"]] == ["بدر خالد"]
        assert _pdf_names(school, principal_user, query, captured_html) == ["بدر خالد"]
        assert [r["full_name"] for r in rows_for(principal_user, QueryDict(query))] == ["بدر خالد"]

    def test_the_wing_supervisor_gets_no_wing_filter(self, wings, client_as):
        from django.urls import reverse

        page = client_as(wings).get(reverse("student_affairs:student_list"))

        assert page.context["wings"] == []


def test_the_pdf_button_reads_the_fields_at_click_time():
    """زرُّ PDF كزرّ Excel: الفلاترُ تُرسَل بـHTMX فلا يُحدَّث رابطٌ كُتب عند فتح الصفحة."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    js = (root / "static/js/student-list-export.js").read_text(encoding="utf-8")
    html = (root / "templates/student_affairs/student_list.html").read_text(encoding="utf-8")

    assert "#student-list-pdf" in js and "#student-list-xlsx" in js
    assert '"wing"' in js, "الجناحُ يدخل في الملفّ كما في الصفحة"
    # على window لا document: يسبق معالجَ مركز التصدير فلا يقرأ الرابطَ القديم (الفلترة السابقة)
    assert 'window.addEventListener("click"' in js and "document.addEventListener" not in js
    assert 'id="student-list-pdf"' in html and "grade={{ grade_filter }}" not in html


def test_the_builder_needs_no_request(school, principal_user, pupils, captured_html):
    """العقدُ: `(school, user, params)` فقط — تعمل في العامل بلا `request`."""
    result = build_students_pdf(school, principal_user, QueryDict("grade=G7"))

    assert result.rows == 1 and result.full_national_id is False
    assert result.content_type == "application/pdf"
