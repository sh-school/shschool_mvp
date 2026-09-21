"""كلماتُ المرور الأوّليّة للحسابات المُنشأة: عشوائيّةٌ، لا الرقمُ الشخصيّ، وتُعرض مرّةً.

قرارُ المالك: لا يُنشأ حسابٌ كلمتُه رقمُه الشخصيّ. والاستيرادُ يعرض ورقةَ اعتمادٍ في
استجابته وحدَها — لا قاعدةَ ولا جلسةَ ولا سجلَّ تدقيقٍ ولا سجلَّ تطبيق.
"""

from __future__ import annotations

import io
import logging
import os
import stat

import openpyxl
import pytest
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.initial_passwords import (
    LENGTH,
    make_initial_password,
    write_credentials_csv,
)
from core.models import CustomUser
from core.models.audit import AuditLog
from tests.conftest import ClassGroupFactory, RoleFactory

# أرقامٌ وهميّةٌ صريحة — لا رقمَ شخصيّاً حقيقيّاً في الشيفرة.
STUDENT_NID = "39900000001"
STUDENT2_NID = "39900000002"
PARENT_NID = "29900000001"


def _workbook(rows) -> SimpleUploadedFile:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["رأس"] * 11)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return SimpleUploadedFile(
        "students.xlsx",
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _row(nid, name, parent_nid="", parent_name=""):
    return [nid, name, "G7", "1", "", "", parent_nid, parent_name, "", "", "father"]


@pytest.fixture
def import_roles(db, school):
    RoleFactory(school=school, name="student")
    RoleFactory(school=school, name="parent")
    ClassGroupFactory(school=school, grade="G7", section="1")


def _import(client, user, rows):
    client.force_login(user)
    return client.post(
        reverse("student_import_export"),
        {"student_file": _workbook(rows)},
    )


class TestGenerator:
    def test_length_and_policy(self):
        for _ in range(30):
            password = make_initial_password()
            assert len(password) == LENGTH >= 12
            validate_password(password)

    def test_alphabet_is_unambiguous(self):
        confusable = set("Ol1I0")
        assert not any(set(make_initial_password()) & confusable for _ in range(100))

    def test_random_each_time(self):
        assert len({make_initial_password() for _ in range(200)}) == 200

    def test_never_starts_with_a_formula_character(self):
        assert not any(make_initial_password()[0] in "=+-@" for _ in range(500))


@pytest.mark.django_db
class TestImportFlow:
    def test_password_is_not_the_national_id_and_must_change(
        self, client, principal_user, import_roles
    ):
        response = _import(
            client,
            principal_user,
            [_row(STUDENT_NID, "طالب تجريبي", PARENT_NID, "ولي تجريبي")],
        )
        assert response.status_code == 200
        for nid in (STUDENT_NID, PARENT_NID):
            user = CustomUser.objects.get(national_id=nid)
            assert user.has_usable_password()
            assert not user.check_password(nid)
            assert not user.check_password(nid[-6:])
            assert user.must_change_password is True

    def test_each_account_gets_its_own_random_password(self, client, principal_user, import_roles):
        response = _import(
            client,
            principal_user,
            [
                _row(STUDENT_NID, "طالب أول", PARENT_NID, "ولي"),
                _row(STUDENT2_NID, "طالب ثانٍ", PARENT_NID, "ولي"),
            ],
        )
        sheet = response.context["credentials"]
        # طالبان + وليٌّ واحدٌ (يظهر مرّةً: أُنشئ مرّةً)
        assert len(sheet) == 3
        assert len({row["password"] for row in sheet}) == 3

    def test_sheet_matches_the_real_passwords_and_shows_each_once(
        self, client, principal_user, import_roles
    ):
        response = _import(
            client, principal_user, [_row(STUDENT_NID, "طالب تجريبي", PARENT_NID, "ولي تجريبي")]
        )
        sheet = response.context["credentials"]
        html = response.content.decode()
        by_role = {row["role"]: row for row in sheet}
        assert CustomUser.objects.get(national_id=STUDENT_NID).check_password(
            by_role["طالب"]["password"]
        )
        assert CustomUser.objects.get(national_id=PARENT_NID).check_password(
            by_role["ولي أمر"]["password"]
        )
        for row in sheet:
            assert html.count(row["password"]) == 1
            # الرقمُ في الورقة مستورٌ (كشفٌ جماعيّ)، لا خام
            assert "*" in row["nid"]
        assert STUDENT_NID not in html
        assert PARENT_NID not in html

    def test_reimport_issues_nothing_and_keeps_passwords(
        self, client, principal_user, import_roles
    ):
        rows = [_row(STUDENT_NID, "طالب تجريبي")]
        _import(client, principal_user, rows)
        before = CustomUser.objects.get(national_id=STUDENT_NID).password
        response = _import(client, principal_user, rows)
        assert not response.context.get("credentials")
        assert b"credentials-sheet" not in response.content
        assert CustomUser.objects.get(national_id=STUDENT_NID).password == before

    def test_nothing_plaintext_is_persisted_or_logged(
        self, client, principal_user, import_roles, caplog
    ):
        with caplog.at_level(logging.DEBUG):
            response = _import(
                client,
                principal_user,
                [_row(STUDENT_NID, "طالب تجريبي", PARENT_NID, "ولي تجريبي")],
            )
        passwords = [row["password"] for row in response.context["credentials"]]
        assert passwords

        audit = " ".join(f"{log.object_repr} {log.changes}" for log in AuditLog.objects.all())
        session = " ".join(str(v) for v in client.session.items())
        stored = " ".join(CustomUser.objects.values_list("password", flat=True))
        raw_sessions = " ".join(Session.objects.values_list("session_data", flat=True))
        for password in passwords:
            assert password not in audit
            assert password not in session
            assert password not in stored  # مجزَّأةٌ لا نصّ
            assert password not in raw_sessions
            assert password not in caplog.text

        # الأثرُ يقول كم صدر لا ما صدر
        entry = AuditLog.objects.get(changes__event="import_initial_passwords_issued")
        assert entry.changes["count"] == 2

    def test_page_is_not_cacheable(self, client, principal_user, import_roles):
        response = _import(client, principal_user, [_row(STUDENT_NID, "طالب تجريبي")])
        assert "no-store" in response["Cache-Control"]

    def test_the_old_default_password_warning_is_gone(self, client, principal_user):
        client.force_login(principal_user)
        html = client.get(reverse("student_import_export")).content.decode()
        assert "هي الرقم الشخصي" not in html
        assert "عشوائيّة" in html


@pytest.mark.django_db
class TestCreateStudentService:
    def test_random_password_not_the_national_id(self, school, class_group):
        from student_affairs.services import StudentService

        user = StudentService.create_student(
            school,
            {
                "national_id": STUDENT_NID,
                "full_name": "طالب جديد",
                "class_group_id": class_group.pk,
            },
        )
        user.refresh_from_db()
        assert user.must_change_password is True
        assert not user.check_password(STUDENT_NID)

    def test_the_caller_gets_the_password_in_memory_only(self, school, class_group):
        from student_affairs.services import StudentService

        user = StudentService.create_student(
            school,
            {
                "national_id": STUDENT_NID,
                "full_name": "طالب جديد",
                "class_group_id": class_group.pk,
            },
        )
        assert user.check_password(user.initial_password)
        assert not hasattr(CustomUser.objects.get(pk=user.pk), "initial_password")

    def test_two_students_two_different_passwords(self, school, class_group):
        from student_affairs.services import StudentService

        passwords = {
            StudentService.create_student(
                school,
                {"national_id": nid, "full_name": "طالب", "class_group_id": class_group.pk},
            ).initial_password
            for nid in (STUDENT_NID, STUDENT2_NID)
        }
        assert len(passwords) == 2


class TestCredentialsCsv:
    def test_file_is_owner_only_and_neutralises_formulas(self, tmp_path):
        target = tmp_path / "creds.csv"
        password = make_initial_password()
        count = write_credentials_csv(
            str(target),
            [{"role": "طالب", "nid": "*******0001", "name": "=HYPERLINK(1)", "password": password}],
        )
        text = target.read_text(encoding="utf-8-sig")
        assert count == 1
        assert text.count(password) == 1
        assert "'=HYPERLINK(1)" in text
        if os.name == "posix":
            assert stat.S_IMODE(target.stat().st_mode) == 0o600
