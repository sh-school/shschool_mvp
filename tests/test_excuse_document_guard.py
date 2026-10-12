"""مستندُ عذر الغياب يُفتح من عرضٍ محروسٍ مدقَّق، لا برابط /media/ مباشر (W-20261008-012، PDPPL).

المستندُ قد يكون تقريراً طبّياً. فالمعيار: قدرةٌ ونطاقٌ ومدرسةٌ، وسطرُ تدقيقٍ لكلّ فتحٍ بلا اسم الملف،
ولا رابطَ `document.url` في أيّ قالب.
"""

import pathlib

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.models import AuditLog, Wing
from operations.models import AbsenceExcuse
from tests.conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory
from tests.test_absence_excuses import vice_admin  # noqa: F401
from tests.test_period_register import (  # noqa: F401 — التجهيزاتُ نفسُها
    SUNDAY,
    kids,
    klass,
    subjects,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4 medical-report"
EVENT = "excuse_document_opened"


def _excuse(school, student, by, name="secret-medical-report.pdf"):
    return AbsenceExcuse.objects.create(
        school=school,
        student=student,
        date_from=SUNDAY,
        date_to=SUNDAY,
        kind="medical",
        document=SimpleUploadedFile(name, PDF, content_type="application/pdf"),
        granted_by=by,
        status="accepted",
    )


def _url(excuse):
    return reverse("wings:excuse_document", args=[excuse.pk])


def _opened():
    return AuditLog.objects.filter(changes__event=EVENT)


@pytest.fixture
def excuse(school, kids, supervisor):
    return _excuse(school, kids[0], supervisor)


class TestWhoMayOpenIt:
    def test_the_vice_admin_gets_the_file_as_a_nameless_attachment(
        self, client_as, excuse, vice_admin
    ):
        response = client_as(vice_admin).get(_url(excuse))

        assert response.status_code == 200
        assert b"".join(response.streaming_content) == PDF
        disposition = response["Content-Disposition"]
        assert disposition.startswith("attachment")
        assert "secret-medical-report" not in disposition, "اسمُ الملف الأصليّ لا يُكشف"
        assert response["X-Content-Type-Options"] == "nosniff"
        assert "no-store" in response["Cache-Control"]

    def test_the_wing_supervisor_opens_his_own_students_excuse(self, client_as, excuse, supervisor):
        assert client_as(supervisor).get(_url(excuse)).status_code == 200

    def test_another_wings_supervisor_gets_404_like_a_missing_file(
        self, client_as, school, year, excuse
    ):
        other = UserFactory(full_name="مشرفٌ آخر", national_id="29300000099")
        MembershipFactory(
            user=other, school=school, role=RoleFactory(school=school, name="admin_supervisor")
        )
        Wing.objects.create(
            school=school, code="w2", name="جناح 2", academic_year=year, supervisor=other
        )

        response = client_as(other).get(_url(excuse))

        assert response.status_code == 404
        assert not _opened().exists()

    def test_a_role_without_the_capability_is_refused(self, client_as, excuse, teacher):
        response = client_as(teacher).get(_url(excuse))

        assert response.status_code == 403
        assert not _opened().exists()

    def test_another_schools_excuse_is_404(self, client_as, excuse, vice_admin):
        foreign_school = SchoolFactory()
        foreign_student = UserFactory(full_name="طالبٌ غريب", national_id="29300000098")
        foreign = _excuse(foreign_school, foreign_student, None)

        assert client_as(vice_admin).get(_url(foreign)).status_code == 404

    def test_anonymous_goes_to_login_not_the_file(self, client, excuse):
        response = client.get(_url(excuse))

        assert response.status_code == 302 and "login" in response["Location"]

    def test_an_excuse_without_a_document_is_404(self, client_as, school, kids, vice_admin):
        bare = AbsenceExcuse.objects.create(
            school=school,
            student=kids[1],
            date_from=SUNDAY,
            date_to=SUNDAY,
            kind="medical",
            status="accepted",
        )

        assert client_as(vice_admin).get(_url(bare)).status_code == 404


class TestEveryOpeningIsAudited:
    def test_one_line_per_opening_with_who_and_which_record_but_no_file_name(
        self, client_as, excuse, vice_admin
    ):
        client = client_as(vice_admin)
        client.get(_url(excuse))
        client.get(_url(excuse))

        lines = list(_opened())
        assert len(lines) == 2
        line = lines[0]
        assert line.user_id == vice_admin.pk and line.action == "view"
        assert line.model_name == "AbsenceExcuse" and line.object_id == str(excuse.pk)
        assert line.timestamp is not None
        blob = f"{line.object_repr} {line.changes}"
        assert "secret-medical-report" not in blob and excuse.document.name not in blob
        assert excuse.student.full_name not in blob, "اسمُ الطالب لا يدخل السجلّ"


class TestRefusedAttemptsAreAudited:
    """توصيةُ 0104: المحاولةُ المرفوضة تترك سطراً أدنى — الحدثُ والدورُ ومعرّفُ العذر، بلا محتوًى."""

    def _denied(self):
        return AuditLog.objects.filter(changes__event="excuse_document_denied")

    def test_a_role_the_middleware_refuses_never_reaches_the_view_or_opens_anything(
        self, client_as, excuse, teacher
    ):
        """المعلّمُ يُردّ في وسيط الصلاحيّات قبل العرض (وهو يسجّل access_denied بنفسه): لا فتحَ ولا ملفّ."""
        assert client_as(teacher).get(_url(excuse)).status_code == 403

        assert not _opened().exists()

    def test_an_out_of_scope_supervisor_leaves_a_denied_line_and_no_opening(
        self, client_as, school, year, excuse
    ):
        other = UserFactory(full_name="مشرفٌ آخر", national_id="29300000097")
        MembershipFactory(
            user=other, school=school, role=RoleFactory(school=school, name="admin_supervisor")
        )
        Wing.objects.create(
            school=school, code="w3", name="جناح 3", academic_year=year, supervisor=other
        )

        assert client_as(other).get(_url(excuse)).status_code == 404

        assert self._denied().count() == 1 and not _opened().exists()
        blob = f"{self._denied().get().object_repr} {self._denied().get().changes}"
        assert excuse.student.full_name not in blob

    def test_a_missing_document_is_not_a_denial(self, client_as, school, kids, vice_admin):
        bare = AbsenceExcuse.objects.create(
            school=school,
            student=kids[1],
            date_from=SUNDAY,
            date_to=SUNDAY,
            kind="medical",
            status="accepted",
        )

        assert client_as(vice_admin).get(_url(bare)).status_code == 404

        assert not self._denied().exists() and not _opened().exists()


class TestNoDirectMediaLinkInTheTemplates:
    """حارسٌ نصّيّ: لا قالبَ يفتح `AbsenceExcuse.document` برابطه المباشر."""

    def test_the_two_excuse_templates_link_the_guarded_view(self):
        root = pathlib.Path(__file__).resolve().parent.parent / "templates" / "wings"
        for name in ("excuse_requests.html", "partials/excuse_card.html"):
            text = (root / name).read_text(encoding="utf-8")
            assert "document.url" not in text, name
            assert "wings:excuse_document" in text, name

    def test_no_template_anywhere_uses_document_url(self):
        root = pathlib.Path(__file__).resolve().parent.parent / "templates"
        offenders = [
            str(p.relative_to(root))
            for p in root.rglob("*.html")
            if ".document.url" in p.read_text(encoding="utf-8")
        ]
        assert not offenders, offenders
