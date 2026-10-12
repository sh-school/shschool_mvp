"""[W-20261010-053] محوُ المستخدم يمسح اسمَه من عمود `changes` أيضاً (قرار DPO D-342م).

يكمل W-20261004-002 (الاسم في `object_repr`). المسحُ في Python على القيمة المفكوكة لا SQL ولا regex على
النصّ، لأنّ الهروبَ في jsonb (`\\"` و`\\\\`) يُخفي الاسمَ في النصّ ولا يخفيه في القيمة.

مستوياتُ الاختبار: الدالّةُ الصرفةُ (`core.audit_changes_scrub`)، والمديرُ (`anonymize_name_in_changes`)،
والزنادُ (الهجرة 0083: `changes` وحدَه وبعلَم `app.auditlog_changes_erasure`)، وخدمةُ المحو، وحارسٌ معماريّ.
لا أسماءَ حقيقيّةً هنا: أسماءٌ مصطنعة.
"""

import ast
import pathlib

import pytest
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, InternalError, connection, transaction

from core.audit_changes_scrub import MAX_DEPTH, TooDeepError, scrub_name
from core.audit_repr import masked_repr
from core.models import AuditLog, ErasureRequest
from governance.erasure_service import ErasureService

from .conftest import UserFactory

NAME = "طالب المحو الاختباري"
MASKED = "CustomUser 3f2a91bc"
IP = "203.0.113.9"
FLAG = "app.auditlog_changes_erasure"


class TestScrubIsPureAndRecursive:
    def test_replaces_every_occurrence_in_strings(self):
        value, changed = scrub_name(f"{NAME} ثم {NAME}", NAME, MASKED)
        assert (value, changed) == (f"{MASKED} ثم {MASKED}", True)

    def test_values_nested_at_any_depth_in_dicts_and_lists(self):
        before = {"a": [{"b": f"قبل {NAME}"}, [NAME]], "c": {"d": {"e": NAME}}}
        after, changed = scrub_name(before, NAME, MASKED)
        assert changed is True
        assert after == {"a": [{"b": f"قبل {MASKED}"}, [MASKED]], "c": {"d": {"e": MASKED}}}

    def test_keys_are_scrubbed_too(self):
        after, changed = scrub_name({f"حقل {NAME}": 1}, NAME, MASKED)
        assert (after, changed) == ({f"حقل {MASKED}": 1}, True)

    def test_numbers_booleans_null_and_types_are_untouched(self):
        before = {"n": 3, "f": 1.5, "t": True, "z": None, "l": [1, None, False]}
        after, changed = scrub_name(before, NAME, MASKED)
        assert (after, changed) == (before, False)
        assert (
            isinstance(after["n"], int) and not isinstance(after["n"], bool) and after["t"] is True
        )

    def test_key_order_is_preserved(self):
        after, _ = scrub_name({"z": NAME, "a": 1, "m": [NAME]}, NAME, MASKED)
        assert list(after) == ["z", "a", "m"]

    def test_the_input_is_not_mutated(self):
        before = {"k": [NAME]}
        scrub_name(before, NAME, MASKED)
        assert before == {"k": [NAME]}

    def test_a_value_without_the_name_reports_unchanged(self):
        assert scrub_name({"k": "v"}, NAME, MASKED) == ({"k": "v"}, False)
        assert scrub_name(None, NAME, MASKED) == (None, False)

    def test_name_with_quotes_and_backslashes_is_found_in_the_decoded_value(self):
        tricky = 'عبد "الله" \\ اختبار'
        after, changed = scrub_name({"k": f"x {tricky} y"}, tricky, MASKED)
        assert (after, changed) == ({"k": f"x {MASKED} y"}, True)


class TestKeyCollisions:
    def test_two_keys_colliding_after_scrub_get_a_numeric_suffix_not_a_merge(self):
        after, _ = scrub_name({NAME: 1, MASKED: 2}, NAME, MASKED)
        assert len(after) == 2
        assert after[MASKED] == 2  # المفتاحُ الذي لم يتغيّر يحتفظ باسمه
        assert after[f"{MASKED}_2"] == 1

    def test_three_way_collision_uses_increasing_suffixes(self):
        after, _ = scrub_name({NAME: 1, f"{NAME} ": 2, MASKED: 3}, NAME, MASKED)
        assert len(after) == 3 and sorted(after.values()) == [1, 2, 3]

    def test_a_suffix_does_not_take_an_existing_key(self):
        after, _ = scrub_name({NAME: 1, MASKED: 2, f"{MASKED}_2": 3}, NAME, MASKED)
        assert len(after) == 3
        assert after[f"{MASKED}_2"] == 3 and after[f"{MASKED}_3"] == 1


class TestDepthLimit:
    @staticmethod
    def _nest(levels):
        value = NAME
        for _ in range(levels):
            value = [value]
        return value

    def test_depth_at_the_limit_is_scrubbed(self):
        after, changed = scrub_name(self._nest(MAX_DEPTH), NAME, MASKED)
        assert changed is True
        for _ in range(MAX_DEPTH):
            after = after[0]
        assert after == MASKED

    def test_beyond_the_limit_raises_instead_of_failing_silently(self):
        with pytest.raises(TooDeepError):
            scrub_name(self._nest(MAX_DEPTH + 1), NAME, MASKED)


def _entry(*, repr_="واقعة", user=None, changes=None, ip=IP):
    return AuditLog.objects.create(
        user=user,
        action="update",
        model_name="CustomUser",
        object_id="x1",
        object_repr=repr_,
        changes=changes,
        ip_address=ip,
        user_agent="ua",
    )


def _columns_except_changes(row):
    return (
        row.id,
        row.school_id,
        row.user_id,
        row.action,
        row.model_name,
        row.object_id,
        row.object_repr,
        row.ip_address,
        row.user_agent,
        row.timestamp,
    )


@pytest.fixture
def student(db):
    return UserFactory(full_name=NAME)


@pytest.mark.django_db
class TestManagerScrubsChanges:
    def test_rewrites_the_value_and_leaves_every_other_column(self, student):
        row = _entry(changes={"قبل": NAME, "بعد": [f"{NAME}!"]}, user=student)
        masked = masked_repr(student)
        before = _columns_except_changes(row)

        counts = AuditLog.objects.anonymize_name_in_changes(student, NAME)

        assert counts["changes_anonymized"] == 1
        row.refresh_from_db()
        assert row.changes == {"قبل": masked, "بعد": [f"{masked}!"]}
        assert _columns_except_changes(row) == before

    def test_the_name_with_a_quote_inside_json_is_found(self, db):
        tricky = 'عبد "الله" المحوّ'
        user = UserFactory(full_name=tricky)
        row = _entry(changes={"k": f"تعديل {tricky}"})

        counts = AuditLog.objects.anonymize_name_in_changes(user, tricky)

        assert counts["changes_anonymized"] == 1
        row.refresh_from_db()
        assert tricky not in str(row.changes)

    def test_other_rows_are_untouched(self, student):
        other = _entry(changes={"k": "لا اسم هنا"})
        AuditLog.objects.anonymize_name_in_changes(student, NAME)
        other.refresh_from_db()
        assert other.changes == {"k": "لا اسم هنا"}

    def test_is_idempotent(self, student):
        _entry(changes={"k": NAME})
        first = AuditLog.objects.anonymize_name_in_changes(student, NAME)
        second = AuditLog.objects.anonymize_name_in_changes(student, NAME)
        assert (first["changes_anonymized"], second["changes_anonymized"]) == (1, 0)

    def test_a_blank_name_does_nothing(self, student):
        row = _entry(changes={"k": ""})
        assert AuditLog.objects.anonymize_name_in_changes(student, "  ")["changes_anonymized"] == 0
        row.refresh_from_db()
        assert row.changes == {"k": ""}

    def test_a_row_with_no_decoded_match_is_not_written(self, student):
        # الاسمُ مقسومٌ بين مفتاحٍ وقيمة: لا نصَّ مفكوكاً واحداً يحمله فلا يُكتب شيء.
        row = _entry(changes={"طالب": "المحو الاختباري"})
        counts = AuditLog.objects.anonymize_name_in_changes(student, NAME)
        assert counts["changes_anonymized"] == 0
        row.refresh_from_db()
        assert row.changes == {"طالب": "المحو الاختباري"}


@pytest.mark.django_db
class TestSkippedAreCountedNotWritten:
    def test_a_shared_name_is_skipped(self, student):
        UserFactory(full_name=NAME)
        row = _entry(changes={"k": NAME})
        counts = AuditLog.objects.anonymize_name_in_changes(student, NAME)
        assert (counts["changes_anonymized"], counts["skipped_changes_shared"]) == (0, 1)
        row.refresh_from_db()
        assert row.changes == {"k": NAME}

    def test_a_name_inside_another_users_longer_name_is_skipped(self, student):
        UserFactory(full_name=f"{NAME} الكبير")
        row = _entry(changes={"k": NAME})
        counts = AuditLog.objects.anonymize_name_in_changes(student, NAME)
        assert counts["skipped_changes_shared"] == 1
        row.refresh_from_db()
        assert row.changes == {"k": NAME}

    def test_a_one_word_name_is_skipped(self, db):
        single = UserFactory(full_name="اسمفريد")
        row = _entry(changes={"k": "اسمفريد"})
        counts = AuditLog.objects.anonymize_name_in_changes(single, "اسمفريد")
        assert (counts["changes_anonymized"], counts["skipped_changes_short"]) == (0, 1)
        row.refresh_from_db()
        assert row.changes == {"k": "اسمفريد"}

    def test_a_too_deep_value_is_skipped_and_does_not_fail_the_rest(self, student):
        deep = NAME
        for _ in range(MAX_DEPTH + 1):
            deep = [deep]
        deep_row = _entry(changes={"k": deep})
        good_row = _entry(changes={"k": NAME})

        counts = AuditLog.objects.anonymize_name_in_changes(student, NAME)

        assert (counts["changes_anonymized"], counts["skipped_changes_deep"]) == (1, 1)
        deep_row.refresh_from_db()
        good_row.refresh_from_db()
        assert deep_row.changes == {"k": deep}
        assert NAME not in str(good_row.changes)

    def test_skipped_counters_are_separate_from_the_repr_counters(self, student):
        counts = AuditLog.objects.anonymize_name_in_changes(student, NAME)
        assert not any(key in counts for key in ("skipped_shared", "skipped_short", "skipped_long"))


def _refused_update(sql, params=None, *, flags=()):
    """يشغّل UPDATE خاماً داخل معاملةٍ بعلَماتٍ معطاة ويتوقّع رفضَ الزناد له."""
    with pytest.raises((InternalError, IntegrityError)), transaction.atomic():
        with connection.cursor() as cur:
            for flag in flags:
                cur.execute("SELECT set_config(%s, 'on', true)", [flag])
            cur.execute(sql, params or [])


@pytest.mark.django_db
class TestTriggerKeepsEverythingElseForbidden:
    def test_ordinary_update_of_changes_is_still_refused(self, student):
        row = _entry(changes={"k": NAME})
        with pytest.raises(PermissionDenied):
            AuditLog.objects.filter(pk=row.pk).update(changes={})

    def test_raw_sql_without_the_flag_is_refused(self, student):
        row = _entry(changes={"k": NAME})
        _refused_update("UPDATE core_auditlog SET changes = '{}'::jsonb WHERE id = %s", [row.pk])
        row.refresh_from_db()
        assert row.changes == {"k": NAME}

    def test_with_the_flag_changes_alone_is_allowed(self, student):
        row = _entry(changes={"k": NAME})
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute("SELECT set_config(%s, 'on', true)", [FLAG])
            cur.execute("UPDATE core_auditlog SET changes = '{}'::jsonb WHERE id = %s", [row.pk])
        row.refresh_from_db()
        assert row.changes == {}

    @pytest.mark.parametrize(
        "extra",
        [
            "ip_address = NULL",
            "user_agent = ''",
            "action = 'delete'",
            "object_repr = 'x'",
            "model_name = 'other'",
        ],
    )
    def test_with_the_flag_any_other_column_changing_with_it_is_refused(self, student, extra):
        row = _entry(changes={"k": NAME})
        _refused_update(
            f"UPDATE core_auditlog SET changes = '{{}}'::jsonb, {extra} WHERE id = %s",
            [row.pk],
            flags=[FLAG],
        )
        row.refresh_from_db()
        assert row.changes == {"k": NAME}

    def test_with_the_flag_the_description_alone_is_refused(self, student):
        row = _entry(repr_=NAME, changes={"k": 1})
        _refused_update(
            "UPDATE core_auditlog SET object_repr = 'x' WHERE id = %s", [row.pk], flags=[FLAG]
        )

    @pytest.mark.parametrize(
        "other_flag", ["app.auditlog_name_erasure", "app.auditlog_network_erasure"]
    )
    def test_the_other_erasure_flags_do_not_open_changes(self, student, other_flag):
        row = _entry(changes={"k": NAME})
        _refused_update(
            "UPDATE core_auditlog SET changes = '{}'::jsonb WHERE id = %s",
            [row.pk],
            flags=[other_flag],
        )
        row.refresh_from_db()
        assert row.changes == {"k": NAME}

    def test_the_flag_is_closed_after_scrubbing(self, student):
        _entry(changes={"k": NAME})
        AuditLog.objects.anonymize_name_in_changes(student, NAME)
        later = _entry(changes={"k": NAME})

        _refused_update("UPDATE core_auditlog SET changes = '{}'::jsonb WHERE id = %s", [later.pk])

        with connection.cursor() as cur:
            cur.execute("SELECT coalesce(current_setting(%s, true), '')", [FLAG])
            assert cur.fetchone()[0] in ("", "off")

    def test_the_earlier_exceptions_still_work(self, student):
        row = _entry(repr_=NAME, user=student)
        AuditLog.objects.filter(pk=row.pk).update(user=None)  # فصلُ الفاعل (0059)
        AuditLog.objects.anonymize_name_in_repr(student, NAME)  # تجهيلُ الوصف (0082)
        row.refresh_from_db()
        assert row.user_id is None and NAME not in row.object_repr

    def test_delete_is_still_refused(self, student):
        row = _entry(changes={"k": NAME})
        with pytest.raises(PermissionDenied):
            AuditLog.objects.filter(pk=row.pk).delete()


def _erasure_request(student, school):
    admin = UserFactory(full_name="مدير الاختبار", is_superuser=True)
    return ErasureRequest.objects.create(
        school=school,
        student=student,
        requested_by=admin,
        reason="اختبار مسح الاسم من التغييرات",
        status="approved",
        reviewed_by=admin,
    )


@pytest.mark.django_db
def test_erasure_service_scrubs_both_columns_in_one_run(student_user, school):
    name = student_user.full_name
    masked = masked_repr(student_user)
    both = _entry(repr_=f"تعديل {name}", changes={"قبل": name, "بعد": "x"}, user=student_user)
    only_changes = _entry(changes={"k": [name]})

    summary = ErasureService.execute(_erasure_request(student_user, school))

    assert summary["models"]["AuditLog_name_anonymized"] == 1
    assert summary["models"]["AuditLog_changes_anonymized"] == 2
    assert "auditlog_changes_note" not in summary
    both.refresh_from_db()
    only_changes.refresh_from_db()
    assert both.object_repr == f"تعديل {masked}"
    assert both.changes == {"قبل": masked, "بعد": "x"}
    assert only_changes.changes == {"k": [masked]}
    assert not AuditLog.objects.filter(object_repr__contains=name).exists()
    assert name not in str(list(AuditLog.objects.values_list("changes", flat=True)))
    assert name not in str(summary)


@pytest.mark.django_db
def test_erasure_service_reports_skipped_changes_by_counts_only(student_user, school):
    name = student_user.full_name
    UserFactory(full_name=name)  # مشتركٌ: لا يُمسح ويُبلَّغ يدوياً
    row = _entry(changes={"k": name})

    summary = ErasureService.execute(_erasure_request(student_user, school))

    assert "AuditLog_changes_anonymized" not in summary["models"]
    assert summary["auditlog_changes_manual_report"] == {"skipped_changes_shared": 1}
    assert "إبلاغ" in summary["auditlog_changes_note"]
    assert name not in str(summary)
    row.refresh_from_db()
    assert row.changes == {"k": name}


def test_only_the_erasure_service_may_scrub_changes():
    """حارسٌ معماريّ: لا يستدعي `anonymize_name_in_changes` غيرُ خدمة المحو."""
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
            if isinstance(node, ast.Attribute) and node.attr == "anonymize_name_in_changes":
                offenders.append(f"{rel}:{node.lineno}")

    assert offenders == [], f"مسحُ الأسماء من التغييرات خارج خدمة المحو: {offenders}"
