"""[W-20261001-016] تاريخُ ميلاد الطالب القاصر مشفَّرٌ at-rest (PDPPL م.16).

مرحلةُ «التوسيع» من توسيعٍ ثمّ تقليص: عمودٌ مشفَّرٌ جديدٌ يُكتب مع القديم
(كتابةٌ مزدوجة، فتبقى النسخةُ القديمةُ من الكود صالحةً أثناء النشر)، والقراءةُ
تتحوّل إلى `Profile.date_of_birth`. حذفُ `birth_date` الصريح إصدارٌ لاحق.
"""

from datetime import date

import pytest
from django.core.management import call_command
from django.db import connection

from core.models import Profile

from .conftest import UserFactory

DOB = date(2011, 5, 17)


def _raw(profile, column):
    with connection.cursor() as cur:
        cur.execute(f"SELECT {column} FROM core_profile WHERE id = %s", [profile.pk])
        return cur.fetchone()[0]


@pytest.mark.django_db
class TestBirthDateEncrypted:
    def test_stored_value_is_not_a_plain_date(self):
        profile = Profile.objects.create(user=UserFactory(), birth_date=DOB)

        raw = _raw(profile, "birth_date_encrypted")

        assert raw, "العمودُ المشفَّر فارغ"
        assert "2011" not in raw and "05-17" not in raw, "القيمةُ في القاعدة تاريخٌ صريح"

    def test_reads_back_as_a_date(self):
        profile = Profile.objects.create(user=UserFactory(), birth_date=DOB)

        assert Profile.objects.get(pk=profile.pk).date_of_birth == DOB

    def test_update_fields_save_keeps_both_columns_in_step(self):
        profile = Profile.objects.create(user=UserFactory(), birth_date=DOB)
        profile.birth_date = date(2012, 1, 2)
        profile.save(update_fields=["birth_date"])  # كما يفعل ministry_import

        assert Profile.objects.get(pk=profile.pk).date_of_birth == date(2012, 1, 2)

    def test_clearing_clears_the_encrypted_column(self):
        profile = Profile.objects.create(user=UserFactory(), birth_date=DOB)
        profile.date_of_birth = None  # التفريغُ فعلٌ صريح؛ حفظٌ عاديّ لا يصفّر (W-20261002-041)
        profile.save()

        assert _raw(profile, "birth_date_encrypted") in ("", None)
        assert Profile.objects.get(pk=profile.pk).date_of_birth is None

    def test_legacy_row_without_encrypted_value_still_reads(self):
        """صفٌّ سبق الهجرة: القراءةُ تسقط إلى القديم حتى يُملأ بالأمر."""
        profile = Profile.objects.create(user=UserFactory(), birth_date=DOB)
        Profile.objects.filter(pk=profile.pk).update(birth_date_encrypted="")

        assert Profile.objects.get(pk=profile.pk).date_of_birth == DOB

    def test_backfill_command_fills_legacy_rows_and_is_idempotent(self):
        profile = Profile.objects.create(user=UserFactory(), birth_date=DOB)
        Profile.objects.filter(pk=profile.pk).update(birth_date_encrypted="")

        call_command("backfill_birth_date_encrypted")
        first = _raw(profile, "birth_date_encrypted")
        call_command("backfill_birth_date_encrypted")

        assert first and "2011" not in first
        assert Profile.objects.get(pk=profile.pk).date_of_birth == DOB
        assert _raw(profile, "birth_date_encrypted") == first, "الأمرُ أعاد كتابة صفٍّ مملوء"


# ── [M1] كتابةٌ تتجاوز save() تترك مشفَّراً قديماً يتقدّم على الصريح ──


@pytest.mark.django_db
class TestVerifyAndGuards:
    def test_verify_passes_when_in_step(self):
        Profile.objects.create(user=UserFactory(), birth_date=DOB)

        call_command("backfill_birth_date_encrypted", "--verify")

    def test_verify_fails_on_missing_encrypted(self):
        from django.core.management.base import CommandError

        profile = Profile.objects.create(user=UserFactory(), birth_date=DOB)
        Profile.objects.filter(pk=profile.pk).update(birth_date_encrypted="")

        with pytest.raises(CommandError):
            call_command("backfill_birth_date_encrypted", "--verify")

    def test_verify_fails_on_stale_encrypted(self):
        """الكتابةُ بـupdate() تُبقي المشفَّرَ قديماً — وهو ما يُعرض خاطئاً بصمت."""
        from django.core.management.base import CommandError

        profile = Profile.objects.create(user=UserFactory(), birth_date=DOB)
        Profile.objects.filter(pk=profile.pk).update(birth_date=date(2000, 1, 1))

        with pytest.raises(CommandError):
            call_command("backfill_birth_date_encrypted", "--verify")

    def test_corrupt_value_falls_back_and_logs_pk_not_value(self, caplog):
        profile = Profile.objects.create(user=UserFactory(), birth_date=DOB)
        Profile.objects.filter(pk=profile.pk).update(birth_date_encrypted="not-a-date")

        with caplog.at_level("WARNING"):
            value = Profile.objects.get(pk=profile.pk).date_of_birth

        assert value == DOB
        assert str(profile.pk) in caplog.text
        assert "not-a-date" not in caplog.text and "2011" not in caplog.text


def test_no_write_bypasses_profile_save():
    """حارسٌ معماريّ: لا `.update(birth_date…)` ولا `bulk_*` على Profile خارج save().

    وإلّا بقي المشفَّرُ قديماً وتقدّم على الصريح الصحيح (حكم 0105 M1).
    """
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    skipped = {"tests", "migrations", "scripts", "node_modules", "worktrees", "staticfiles"}
    offenders = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root)
        if skipped & set(rel.parts) or any(p.startswith(".") for p in rel.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            attr = node.func.attr
            if attr == "update" and any(
                k.arg in {"birth_date", "birth_date_encrypted"} for k in node.keywords
            ):
                offenders.append(f"{rel}:{node.lineno}")
            elif attr in {"bulk_create", "bulk_update"} and any(
                isinstance(n, ast.Name) and n.id == "Profile" for n in ast.walk(node.func)
            ):
                offenders.append(f"{rel}:{node.lineno}")

    assert offenders == [], f"كتابةٌ على Profile تتجاوز save(): {offenders}"


@pytest.mark.django_db
def test_admin_inline_does_not_expose_plain_birth_date():
    from core.admin import ProfileInline

    assert "birth_date" not in ProfileInline.fields
    assert "date_of_birth" in ProfileInline.readonly_fields


@pytest.mark.django_db
def test_verify_fails_on_unreadable_encrypted_value():
    """مشفَّرٌ تالفٌ لا يمرّ التحقّقَ بسقوط date_of_birth إلى الصريح (0105 P3)."""
    from django.core.management.base import CommandError

    profile = Profile.objects.create(user=UserFactory(), birth_date=DOB)
    Profile.objects.filter(pk=profile.pk).update(birth_date_encrypted="not-a-date")

    with pytest.raises(CommandError):
        call_command("backfill_birth_date_encrypted", "--verify")


# ── W-20261002-041: لا فقدانَ لتاريخ قاصر عند تحويل الكتّاب إلى date_of_birth ──


@pytest.mark.django_db
class TestNoLossOnDobWriters:
    def _profile(self):
        p = Profile.objects.create(user=UserFactory())
        p.date_of_birth = DOB
        p.save()
        return Profile.objects.get(pk=p.pk)

    def test_setter_writes_the_encrypted_column(self):
        p = self._profile()
        assert "2011" not in _raw(p, "birth_date_encrypted")
        assert p.date_of_birth == DOB

    def test_update_fields_save_without_the_date_keeps_it(self):
        p = self._profile()
        p.notes = "ملاحظة"
        p.save(update_fields=["notes"])
        assert Profile.objects.get(pk=p.pk).date_of_birth == DOB

    def test_save_with_empty_legacy_and_filled_encrypted_never_zeroes(self):
        """مسحُ حفظٍ قديمٍ تاريخَ قاصرٍ: القديمُ فارغ والمشفَّرُ مملوء."""
        p = self._profile()
        Profile.objects.filter(pk=p.pk).update(birth_date=None)
        stale = Profile.objects.get(pk=p.pk)
        stale.notes = "x"
        stale.save()
        assert Profile.objects.get(pk=p.pk).date_of_birth == DOB

    def test_save_from_an_object_read_before_the_encrypted_value_was_set(self):
        stale = Profile.objects.create(user=UserFactory())  # لا تاريخ بعد
        other = Profile.objects.get(pk=stale.pk)
        other.date_of_birth = DOB
        other.save()
        stale.notes = "لا يمسّ التاريخ"
        stale.save()
        assert Profile.objects.get(pk=stale.pk).date_of_birth == DOB

    def test_explicit_change_goes_through_the_setter_and_keeps_verify_clean(self):
        p = self._profile()
        p.date_of_birth = date(2012, 3, 4)
        p.save(update_fields=["birth_date_encrypted"])
        assert Profile.objects.get(pk=p.pk).date_of_birth == date(2012, 3, 4)
        call_command("backfill_birth_date_encrypted", "--verify")  # 0/0

    def test_ministry_import_creates_and_updates(self):
        from core.ministry_import import _sync_student_profile

        student, cache = UserFactory(), {}
        _sync_student_profile(student, DOB, cache)
        assert Profile.objects.get(user=student).date_of_birth == DOB
        _sync_student_profile(student, date(2012, 1, 2), cache)
        assert Profile.objects.get(user=student).date_of_birth == date(2012, 1, 2)
        call_command("backfill_birth_date_encrypted", "--verify")

    def test_ministry_import_unchanged_date_leaves_encrypted_alone(self):
        from core.ministry_import import _sync_student_profile

        student = UserFactory()
        cache = {}
        _sync_student_profile(student, DOB, cache)
        before = _raw(Profile.objects.get(user=student), "birth_date_encrypted")
        _sync_student_profile(student, DOB, cache)
        assert _raw(Profile.objects.get(user=student), "birth_date_encrypted") == before

    def test_student_update_service_sets_changes_and_clears_explicitly(self):
        from types import SimpleNamespace

        from student_affairs.services import StudentService

        student, school = UserFactory(), SimpleNamespace(code="T")
        data = {"full_name": "اسم", "birth_date": DOB, "notes": "n"}
        StudentService.update_student(student, school, data)
        assert Profile.objects.get(user=student).date_of_birth == DOB
        StudentService.update_student(student, school, {**data, "birth_date": date(2012, 5, 6)})
        assert Profile.objects.get(user=student).date_of_birth == date(2012, 5, 6)
        StudentService.update_student(
            student, school, {"full_name": "اسم", "notes": "m"}
        )  # غيابُ المفتاح لا يفرّغ
        assert Profile.objects.get(user=student).date_of_birth == date(2012, 5, 6)
        StudentService.update_student(
            student, school, {**data, "birth_date": None}
        )  # تفريغٌ من النموذج
        assert Profile.objects.get(user=student).date_of_birth is None


def test_no_direct_birth_date_write_outside_profile():
    """حارسٌ نصّيّ: لا `profile.birth_date` ولا `Profile(... birth_date=)` خارج Profile وأمرِ التعبئة والهجرات."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parent.parent
    allowed = {
        "core/models/user.py",
        "core/management/commands/backfill_birth_date_encrypted.py",
    }
    skipped = {"tests", "migrations", "scripts", "node_modules", "worktrees", "staticfiles", "docs"}
    pat = re.compile(r"\.birth_date\b|Profile[^\n]*\bbirth_date\s*=")
    offenders = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root)
        if skipped & set(rel.parts) or any(part.startswith(".") for part in rel.parts):
            continue
        if rel.as_posix() in allowed:
            continue
        for no, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            if pat.search(line.split("#", 1)[0]):
                offenders.append(f"{rel}:{no}")
    assert (
        offenders == []
    ), f"كتابةٌ أو قراءةٌ لـbirth_date خارج Profile — استعمل date_of_birth: {offenders}"
