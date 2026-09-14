"""أثرُ التصدير وأثرُ الفشل — على الخادم الحيّ لا في النصّ وحدَه.

`test_national_id_never_bulk` يقرأ الشيفرةَ ويحكم عليها؛ وهذا يطلب الصفحاتِ
فعلاً ويقرأ ما تكتبه في `AuditLog`:

- كشفُ الحضور وشهاداتُ الفصل كشوفٌ جماعيّة: الرقمُ مستورٌ فيهما، والتوليدُ
  مسجَّلٌ بعدد الصفوف وبلا رايةِ «رقمٌ كامل».
- شهادةُ الطالب وثيقةٌ فرديّة: الرقمُ كاملٌ فيها، والسجلُّ يقولها.
- ردُّ بحث التأخّر وتمثيلُ API المختصر يستران الرقمَ حتى للقيادة.
- كلمةُ مرورٍ خاطئةٌ تكتب `login_failed` — لحسابٍ معروفٍ ولمعرّفٍ لا وجودَ له —
  بلا معرّفٍ خام. ورمزُ تحقّقٍ خاطئٌ يكتب `mfa_failed` ويزيد العدّادَ نفسَه
  ويقفل عند الحدّ.
"""

import json

import pyotp
import pytest
from django.urls import reverse

from core.models import AuditLog, encrypt_field
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

STUDENT_ID = "99900000538"
MASKED = "*******0538"
PASSWORD = "Probe-Passw0rd-Audit!"  # pragma: allowlist secret


def _exports(kind):
    return AuditLog.objects.filter(action="export", changes__kind=kind)


@pytest.fixture
def klass(school, seeded_calendar):
    return ClassGroupFactory(school=school, academic_year=seeded_calendar)


@pytest.fixture
def pupil(school, klass):
    user = UserFactory(full_name="طالبُ الكشف", national_id=STUDENT_ID)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    StudentEnrollmentFactory(student=user, class_group=klass)
    return user


class TestBulkDocumentsMaskAndLog:
    def test_the_attendance_report_masks_and_leaves_a_trail(
        self, client_as, principal_user, klass, pupil
    ):
        resp = client_as(principal_user).get(
            reverse("attendance_report_pdf", args=[klass.pk]) + "?preview=1"
        )
        body = resp.content.decode()

        assert resp.status_code == 200
        assert MASKED in body
        assert STUDENT_ID not in body, "كشفُ فصلٍ كامل كشفٌ جماعيّ — يُستر وإن طُبع"
        trail = _exports("reports.attendance").get()
        assert trail.user == principal_user
        assert trail.changes["rows"] == 1
        assert trail.changes["full_national_id"] is False
        assert STUDENT_ID not in (trail.object_repr + json.dumps(trail.changes))

    def test_class_certificates_in_one_file_are_masked(
        self, client_as, principal_user, klass, pupil
    ):
        resp = client_as(principal_user).get(
            reverse("class_certificates_pdf", args=[klass.pk]) + "?preview=1"
        )
        body = resp.content.decode()

        assert resp.status_code == 200
        assert MASKED in body and STUDENT_ID not in body
        assert _exports("reports.class_certificates").get().changes["rows"] == 1


class TestIndividualDocumentsKeepTheNumberAndLog:
    def test_the_certificate_carries_the_full_number_and_says_so(
        self, client_as, principal_user, klass, pupil
    ):
        resp = client_as(principal_user).get(
            reverse("student_certificate_pdf", args=[pupil.pk]) + "?preview=1"
        )

        assert resp.status_code == 200
        assert STUDENT_ID in resp.content.decode()
        trail = _exports("reports.certificate").get()
        assert trail.changes == {"kind": "reports.certificate", "rows": 1, "full_national_id": True}
        assert trail.object_id == str(pupil.pk)
        assert STUDENT_ID not in trail.object_repr

    def test_the_import_compatible_register_keeps_the_number_and_says_so(
        self, client_as, principal_user, klass, pupil
    ):
        """كشفُ الطلبة الكامل يعود بالاستيراد فيُطابَق على الرقم — كاملٌ بقرارٍ مسمّى."""
        resp = client_as(principal_user).get(reverse("student_export_excel"))

        assert resp.status_code == 200
        assert STUDENT_ID in _cells(resp)
        assert _exports("core.students_xlsx").get().changes["full_national_id"] is True


def _cells(resp) -> set[str]:
    import io

    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(resp.content), read_only=True)
    return {
        str(cell) for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for cell in row
    }


class TestExcelRegistersMaskTheNumber:
    """قرار المالك 2026-09-14: Excel لا يعود بالاستيراد يستر الرقمَ — والسجلُّ يقولها."""

    @pytest.mark.parametrize(
        ("route", "kind"),
        [
            ("student_affairs:student_export", "student_affairs.students_xlsx"),
            ("student_affairs:attendance_export", "student_affairs.attendance_xlsx"),
            ("student_affairs:behavior_export", "student_affairs.behavior_xlsx"),
        ],
    )
    def test_a_student_affairs_register_is_masked(
        self, client_as, principal_user, klass, pupil, route, kind
    ):
        resp = client_as(principal_user).get(reverse(route))

        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("application/vnd.openxmlformats")
        cells = _cells(resp)
        assert STUDENT_ID not in cells, f"{kind}: الرقمُ كاملٌ في ورقةٍ جماعيّة"
        trail = _exports(kind).get()
        assert trail.changes["full_national_id"] is False

    def test_the_class_results_sheet_is_masked(self, client_as, principal_user, klass, pupil):
        resp = client_as(principal_user).get(reverse("class_results_excel", args=[klass.pk]))

        assert resp.status_code == 200
        cells = _cells(resp)
        assert MASKED in cells and STUDENT_ID not in cells
        trail = _exports("reports.class_results_xlsx").get()
        assert trail.changes["rows"] == 1 and trail.changes["full_national_id"] is False


class TestJsonAndApiMaskTheNumber:
    def test_the_tardiness_search_masks_the_number(self, client_as, principal_user, klass, pupil):
        resp = client_as(principal_user).get(
            reverse("student_affairs:tardiness_search") + "?q=طالبُ"
        )

        payload = resp.json()
        assert [row["nid"] for row in payload["results"]] == [MASKED]

    def test_the_brief_serializer_masks_even_for_leadership(self, principal_user, pupil):
        from rest_framework.test import APIRequestFactory

        from api.serializers import UserBriefSerializer

        request = APIRequestFactory().get("/")
        request.user = principal_user

        data = UserBriefSerializer(pupil, context={"request": request}).data

        assert data["national_id"] == MASKED


def _staff(school, **kwargs):
    user = UserFactory(password=PASSWORD, **kwargs)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


class TestFailedLoginsAreAudited:
    def test_a_wrong_password_writes_login_failed_for_the_account(self, client, school):
        user = _staff(school, national_id="99900000601")

        client.post(reverse("login"), {"identifier": user.national_id, "password": "wrong"})

        trail = AuditLog.objects.get(action="login_failed")
        assert trail.user == user
        assert trail.changes["known"] is True
        assert trail.changes["locked"] is False
        assert user.national_id not in trail.object_repr, "المعرّفُ مستورٌ في السجلّ"
        assert user.national_id[-4:] in trail.object_repr

    def test_an_unknown_identifier_is_audited_without_an_account(self, client, school):
        client.post(
            reverse("login"),
            {"identifier": "99900000602", "password": "wrong"},  # pragma: allowlist secret
        )

        trail = AuditLog.objects.get(action="login_failed")
        assert trail.user is None
        assert trail.changes["known"] is False

    def test_the_locking_attempt_is_marked(self, client, school):
        user = _staff(school, national_id="99900000603")
        user.failed_login_attempts = 4
        user.save(update_fields=["failed_login_attempts"])

        client.post(reverse("login"), {"identifier": user.national_id, "password": "wrong"})

        assert AuditLog.objects.get(action="login_failed").changes["locked"] is True
        user.refresh_from_db()
        assert user.locked_until is not None


def _with_totp(school):
    user = _staff(school, national_id="99900000604")
    secret = pyotp.random_base32()
    user.totp_secret = encrypt_field(secret) or secret
    user.totp_enabled = True
    user.save(update_fields=["totp_secret", "totp_enabled"])
    return user, secret


class TestFailedCodesCountAndAreAudited:
    @pytest.fixture(autouse=True)
    def _two_factor_on(self, settings):
        """الرايةُ مطفأةٌ في إعدادات الاختبار (تجميدٌ كامل) — تُشعَل هنا ليُسأل عن الرمز."""
        settings.TWO_FACTOR_REQUIRED_FOR_STAFF = True

    def test_a_wrong_code_counts_against_the_account(self, client, school):
        user, _secret = _with_totp(school)
        client.post(reverse("login"), {"identifier": user.national_id, "password": PASSWORD})

        resp = client.post(reverse("verify_2fa"), {"code": "000000"})

        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.failed_login_attempts == 1
        trail = AuditLog.objects.get(action="mfa_failed")
        assert trail.user == user and trail.changes == {"locked": False}

    def test_the_right_code_still_gets_in_and_resets_nothing_it_should_not(self, client, school):
        user, secret = _with_totp(school)
        client.post(reverse("login"), {"identifier": user.national_id, "password": PASSWORD})

        resp = client.post(reverse("verify_2fa"), {"code": pyotp.TOTP(secret).now()})

        assert resp.status_code == 302 and client.session.get("_auth_user_id") == str(user.pk)
        assert not AuditLog.objects.filter(action="mfa_failed").exists()

    def test_the_fifth_wrong_code_locks_and_sends_back_to_login(self, client, school):
        user, _secret = _with_totp(school)
        client.post(reverse("login"), {"identifier": user.national_id, "password": PASSWORD})
        # كلمةُ المرور الصحيحةُ تصفّر العدّاد — فأربعُ محاولاتٍ خاطئةٍ على الرمز بعدها.
        user.failed_login_attempts = 4
        user.save(update_fields=["failed_login_attempts"])

        resp = client.post(reverse("verify_2fa"), {"code": "000000"})

        assert resp.status_code == 302 and resp["Location"].endswith(reverse("login"))
        assert "pending_2fa_user" not in client.session
        user.refresh_from_db()
        assert user.locked_until is not None
        assert AuditLog.objects.get(action="mfa_failed").changes["locked"] is True
