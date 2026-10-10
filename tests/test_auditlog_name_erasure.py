"""[W-20261004-002] محوُ المستخدم يُجهِّل اسمَه في `object_repr` بمعرّفه المقنَّع (قرار DPO D-186م ب).

سجلُّ التدقيق ملحقٌ لا يُعدَّل، وكتبت المُلتقِطاتُ القديمةُ (قبل W-20261003-019) اسمَ الطالب في وصف
السجلّ. فعند المحو: الاسمُ في `object_repr` وحدَه يُستبدل بـ`CustomUser 3f2a91bc`، وتبقى الواقعةُ بكلّ ما
عداه. وتُتخطّى الأسماءُ المشتركةُ والقصيرةُ والوصفُ الذي يطول، وتُعدّ للإبلاغ اليدويّ.

الاستثناءُ ضيّقٌ على مستويَين: الفئةُ (`anonymize_name_in_repr` وحدها، تستدعيها خدمةُ المحو) والزنادُ
(الهجرة 0082: `object_repr` وحدَه وبعلَم المعاملة `app.auditlog_name_erasure`).
لا أسماءَ حقيقيّةً هنا: أسماءٌ مصطنعة.
"""

import ast
import pathlib

import pytest
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, InternalError, connection, transaction

from core.audit_repr import masked_repr
from core.models import AuditLog, ErasureRequest
from governance.erasure_service import ErasureService

from .conftest import UserFactory

pytestmark = pytest.mark.django_db

NAME = "طالب المحو الاختباري"
IP = "203.0.113.9"
FLAG = "app.auditlog_name_erasure"


def _entry(*, repr_, user=None, model="CustomUser", changes=None, ip=IP):
    return AuditLog.objects.create(
        user=user,
        action="update",
        model_name=model,
        object_id="x1",
        object_repr=repr_,
        changes=changes,
        ip_address=ip,
        user_agent="ua",
    )


@pytest.fixture
def student(db):
    return UserFactory(full_name=NAME)


class TestAnonymization:
    def test_replaces_the_name_with_the_masked_id_in_every_row(self, student):
        plain = _entry(repr_=NAME)
        legacy_link = _entry(repr_=f"ولي-اختباري ← {NAME} (أم)", model="ParentStudentLink")
        masked = masked_repr(student)

        counts = AuditLog.objects.anonymize_name_in_repr(student, NAME)

        assert counts["anonymized"] == 2
        plain.refresh_from_db()
        legacy_link.refresh_from_db()
        assert plain.object_repr == masked
        assert legacy_link.object_repr == f"ولي-اختباري ← {masked} (أم)"
        assert NAME not in plain.object_repr + legacy_link.object_repr

    def test_only_the_description_changes(self, student):
        row = _entry(repr_=NAME, changes={"k": "v"}, user=student)
        before = (
            row.id,
            row.school_id,
            row.user_id,
            row.action,
            row.model_name,
            row.object_id,
            row.changes,
            row.ip_address,
            row.user_agent,
            row.timestamp,
        )

        AuditLog.objects.anonymize_name_in_repr(student, NAME)

        row.refresh_from_db()
        after = (
            row.id,
            row.school_id,
            row.user_id,
            row.action,
            row.model_name,
            row.object_id,
            row.changes,
            row.ip_address,
            row.user_agent,
            row.timestamp,
        )
        assert after == before

    def test_other_rows_are_untouched(self, student):
        other = _entry(repr_="سجلّ لا يخصّ أحداً بالاسم")

        AuditLog.objects.anonymize_name_in_repr(student, NAME)

        other.refresh_from_db()
        assert other.object_repr == "سجلّ لا يخصّ أحداً بالاسم"

    def test_is_idempotent(self, student):
        _entry(repr_=NAME)

        first = AuditLog.objects.anonymize_name_in_repr(student, NAME)
        second = AuditLog.objects.anonymize_name_in_repr(student, NAME)

        assert (first["anonymized"], second["anonymized"]) == (1, 0)

    def test_a_blank_name_does_nothing(self, student):
        row = _entry(repr_="")

        counts = AuditLog.objects.anonymize_name_in_repr(student, "  ")

        assert counts["anonymized"] == 0
        row.refresh_from_db()
        assert row.object_repr == ""


class TestSkippedRowsAreCountedNotWritten:
    def test_a_shared_name_is_skipped(self, student):
        UserFactory(full_name=NAME)  # مستخدمٌ آخر بالاسم نفسه
        row = _entry(repr_=NAME)

        counts = AuditLog.objects.anonymize_name_in_repr(student, NAME)

        assert (counts["anonymized"], counts["skipped_shared"]) == (0, 1)
        row.refresh_from_db()
        assert row.object_repr == NAME

    def test_a_name_inside_another_users_longer_name_is_skipped(self, student):
        UserFactory(full_name=f"{NAME} الكبير")
        row = _entry(repr_=f"{NAME} الكبير")

        counts = AuditLog.objects.anonymize_name_in_repr(student, NAME)

        assert (counts["anonymized"], counts["skipped_shared"]) == (0, 1)
        row.refresh_from_db()
        assert row.object_repr == f"{NAME} الكبير"

    def test_a_one_word_name_is_skipped(self, db):
        single = UserFactory(full_name="اسمفريد")
        row = _entry(repr_="اسمفريد")

        counts = AuditLog.objects.anonymize_name_in_repr(single, "اسمفريد")

        assert (counts["anonymized"], counts["skipped_short"]) == (0, 1)
        row.refresh_from_db()
        assert row.object_repr == "اسمفريد"

    def test_a_description_that_would_exceed_the_column_is_skipped(self, db):
        short = UserFactory(full_name="س ص")  # أقصر من المعرّف المقنَّع فيطول الوصف بالاستبدال
        long_repr = "س ص" + "ع" * 296  # 299 حرفاً: بعد الاستبدال يتجاوز 300
        row = _entry(repr_=long_repr)

        counts = AuditLog.objects.anonymize_name_in_repr(short, "س ص")

        assert (counts["anonymized"], counts["skipped_long"]) == (0, 1)
        row.refresh_from_db()
        assert row.object_repr == long_repr


class TestEverythingElseStaysForbidden:
    def test_ordinary_update_of_the_description_is_still_refused(self, student):
        row = _entry(repr_=NAME)

        with pytest.raises(PermissionDenied):
            AuditLog.objects.filter(pk=row.pk).update(object_repr="x")

    def test_raw_sql_without_the_flag_is_refused(self, student):
        row = _entry(repr_=NAME)

        with pytest.raises((InternalError, IntegrityError)), transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("UPDATE core_auditlog SET object_repr = 'x' WHERE id = %s", [row.pk])

        row.refresh_from_db()
        assert row.object_repr == NAME

    def test_with_the_flag_the_description_alone_is_allowed(self, student):
        row = _entry(repr_=NAME)

        with transaction.atomic(), connection.cursor() as cur:
            cur.execute("SELECT set_config(%s, 'on', true)", [FLAG])
            cur.execute("UPDATE core_auditlog SET object_repr = 'x' WHERE id = %s", [row.pk])

        row.refresh_from_db()
        assert row.object_repr == "x"

    @pytest.mark.parametrize(
        "extra",
        ["ip_address = NULL", "user_agent = ''", "action = 'delete'", "changes = '{}'::jsonb"],
    )
    def test_with_the_flag_any_other_column_changing_with_it_is_refused(self, student, extra):
        row = _entry(repr_=NAME, changes={"k": "v"})

        with pytest.raises((InternalError, IntegrityError)), transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("SELECT set_config(%s, 'on', true)", [FLAG])
                cur.execute(
                    f"UPDATE core_auditlog SET object_repr = 'x', {extra} WHERE id = %s", [row.pk]
                )

        row.refresh_from_db()
        assert row.object_repr == NAME

    def test_the_network_erasure_flag_does_not_open_the_description(self, student):
        row = _entry(repr_=NAME)

        with pytest.raises((InternalError, IntegrityError)), transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("SELECT set_config('app.auditlog_network_erasure', 'on', true)")
                cur.execute("UPDATE core_auditlog SET object_repr = 'x' WHERE id = %s", [row.pk])

    def test_the_flag_is_closed_after_anonymizing(self, student):
        _entry(repr_=NAME)
        AuditLog.objects.anonymize_name_in_repr(student, NAME)
        later = _entry(repr_=NAME)

        with pytest.raises((InternalError, IntegrityError)), transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("UPDATE core_auditlog SET object_repr = 'x' WHERE id = %s", [later.pk])

        with connection.cursor() as cur:
            cur.execute("SELECT coalesce(current_setting(%s, true), '')", [FLAG])
            assert cur.fetchone()[0] in ("", "off")

    def test_the_earlier_exceptions_still_work(self, student):
        actor_row = _entry(repr_="واقعة", user=student)

        AuditLog.objects.filter(pk=actor_row.pk).update(user=None)  # فصلُ الفاعل (0059)
        actor_row.refresh_from_db()
        assert actor_row.user_id is None


def _erasure_request(student, school):
    admin = UserFactory(full_name="مدير الاختبار", is_superuser=True)
    return ErasureRequest.objects.create(
        school=school,
        student=student,
        requested_by=admin,
        reason="اختبار تجهيل الاسم",
        status="approved",
        reviewed_by=admin,
    )


def test_erasure_service_anonymizes_the_name_it_captured_before_overwriting_it(
    student_user, school
):
    name = student_user.full_name
    masked = masked_repr(student_user)
    row = _entry(repr_=f"تعديل {name}", user=student_user)

    summary = ErasureService.execute(_erasure_request(student_user, school))

    assert summary["models"]["AuditLog_name_anonymized"] == 1
    assert "auditlog_name_note" not in summary
    row.refresh_from_db()
    assert row.object_repr == f"تعديل {masked}"
    assert not AuditLog.objects.filter(object_repr__contains=name).exists()


def test_erasure_service_reports_skipped_rows_for_manual_follow_up(student_user, school):
    name = student_user.full_name
    UserFactory(full_name=name)  # مشتركٌ: لا يُجهَّل ويُبلَّغ يدوياً
    row = _entry(repr_=name)

    summary = ErasureService.execute(_erasure_request(student_user, school))

    assert "AuditLog_name_anonymized" not in summary["models"]
    assert summary["auditlog_name_manual_report"] == {"skipped_shared": 1}
    assert "إبلاغ" in summary["auditlog_name_note"]
    assert name not in str(summary)
    row.refresh_from_db()
    assert row.object_repr == name


def test_only_the_erasure_service_may_anonymize_names():
    """حارسٌ معماريّ: لا يستدعي `anonymize_name_in_repr` غيرُ خدمة المحو."""
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
            if isinstance(node, ast.Attribute) and node.attr == "anonymize_name_in_repr":
                offenders.append(f"{rel}:{node.lineno}")

    assert offenders == [], f"تجهيلُ الأسماء في سجلّ التدقيق خارج خدمة المحو: {offenders}"
