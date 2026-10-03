"""[W-20261003-013] محوُ الطالب يُفرِّغ عنوانَ IP ومتصفّحَه من سجلّ التدقيق.

السجلُّ ملحقٌ لا يُعدَّل، وكان المحوُ يُبقي `ip_address` و`user_agent` مربوطَين بوقائع
دخول الطالب القاصر. قرارُ المالك بصفته DPO (2026-10-03): تفريغٌ **عند المحو** لصفوف
المستخدم وحده — `NULL` كاملٌ لا HMAC — ويشمل محاولاتِ الدخول الفاشلة على حسابه؛ وتبقى
الواقعةُ (من فعل ماذا ومتى). والسياسةُ العامّةُ للاحتفاظ مؤجَّلة.

الاستثناءُ الجديدُ ضيّقٌ على مستويَين: الفئةُ (`redact_network_identity` وحدها) والزنادُ في
القاعدة (`ip_address` إلى NULL و`user_agent` إلى فارغ، وكلُّ عمودٍ آخرَ كما هو).
"""

import ast
import pathlib

import pytest
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, InternalError, connection, transaction

from core.models import AuditLog, ErasureRequest
from governance.erasure_service import ErasureService

from .conftest import UserFactory

pytestmark = pytest.mark.django_db

IP = "203.0.113.7"
UA = "Mozilla/5.0 (اختبار)"


def _entry(user, *, action="login", object_id="", ip=IP, ua=UA, changes=None):
    return AuditLog.objects.create(
        user=user,
        action=action,
        model_name="CustomUser",
        object_id=str(object_id),
        object_repr="واقعة",
        changes=changes,
        ip_address=ip,
        user_agent=ua,
    )


@pytest.fixture
def student(db):
    return UserFactory(full_name="طالب المحو")


@pytest.fixture
def other(db):
    return UserFactory(full_name="مستخدم آخر")


class TestRedaction:
    def test_clears_ip_and_agent_of_that_user_only(self, student, other):
        mine = _entry(student)
        theirs = _entry(other)

        count = AuditLog.objects.redact_network_identity(student)

        assert count == 1
        mine.refresh_from_db()
        theirs.refresh_from_db()
        assert mine.ip_address is None and mine.user_agent == ""
        assert (theirs.ip_address, theirs.user_agent) == (IP, UA), "صفُّ غيره لا يُمسّ"

    def test_includes_failed_logins_on_the_account(self, student):
        failed = _entry(student, action="login_failed", object_id=student.pk)
        mfa = _entry(student, action="mfa_failed", object_id=student.pk)

        AuditLog.objects.redact_network_identity(student)

        for row in (failed, mfa):
            row.refresh_from_db()
            assert row.ip_address is None and row.user_agent == ""

    def test_the_fact_survives(self, student):
        row = _entry(student, action="view", changes={"k": "v"})
        before = (row.action, row.model_name, row.object_repr, row.changes, row.timestamp)

        AuditLog.objects.redact_network_identity(student)

        row.refresh_from_db()
        assert (row.action, row.model_name, row.object_repr, row.changes, row.timestamp) == before
        assert row.user_id == student.pk

    def test_is_idempotent(self, student):
        _entry(student)

        first = AuditLog.objects.redact_network_identity(student)
        second = AuditLog.objects.redact_network_identity(student)

        assert (first, second) == (1, 0)


class TestEverythingElseStaysForbidden:
    def test_ordinary_update_of_ip_is_still_refused(self, student):
        row = _entry(student)

        with pytest.raises(PermissionDenied):
            AuditLog.objects.filter(pk=row.pk).update(ip_address=None)

    def test_ordinary_update_of_agent_is_still_refused(self, student):
        row = _entry(student)

        with pytest.raises(PermissionDenied):
            AuditLog.objects.filter(pk=row.pk).update(user_agent="")

    def test_database_trigger_still_blocks_other_columns(self, student):
        row = _entry(student)

        with pytest.raises((InternalError, IntegrityError)), transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "UPDATE core_auditlog SET action = 'delete', ip_address = NULL, "
                    "user_agent = '' WHERE id = %s",
                    [row.pk],
                )

    def test_database_trigger_refuses_rewriting_ip_to_another_value(self, student):
        row = _entry(student)

        with pytest.raises((InternalError, IntegrityError)), transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "UPDATE core_auditlog SET ip_address = '198.51.100.1' WHERE id = %s", [row.pk]
                )


def test_erasure_service_redacts_and_records_the_count(student_user, school):
    _entry(student_user)
    _entry(student_user, action="login_failed", object_id=student_user.pk)
    admin = UserFactory(full_name="مدير", is_superuser=True)
    req = ErasureRequest.objects.create(
        school=school,
        student=student_user,
        requested_by=admin,
        reason="اختبار تفريغ الشبكة",
        status="approved",
        reviewed_by=admin,
    )

    summary = ErasureService.execute(req)

    assert summary["models"]["AuditLog_network_redacted"] == 2
    assert not AuditLog.objects.filter(user=student_user).exclude(ip_address=None).exists()
    assert not AuditLog.objects.filter(user=student_user).exclude(user_agent="").exists()


def test_only_the_erasure_service_may_redact():
    """حارسٌ معماريّ: لا يستدعي `redact_network_identity` غيرُ خدمة المحو."""
    root = pathlib.Path(__file__).resolve().parent.parent
    skipped = {"tests", "migrations", "scripts", "node_modules", "worktrees", "staticfiles"}
    allowed = {"governance/erasure_service.py", "core/models/audit.py"}
    offenders = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root)
        if skipped & set(rel.parts) or any(p.startswith(".") for p in rel.parts):
            continue
        if rel.as_posix() in allowed:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "redact_network_identity":
                offenders.append(f"{rel}:{node.lineno}")

    assert offenders == [], f"تفريغُ سجلّ التدقيق خارج خدمة المحو: {offenders}"
