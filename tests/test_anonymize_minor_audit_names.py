"""[W-20261004-003] العدُّ التجريبيُّ لتجهيل أسماء القاصرين في سجلّ التدقيق (D-186م ج).

الأمرُ يعدّ ولا يكتب، ولا يطبع اسماً، ويتخطّى الاسمَ المشتركَ مع بالغ والاسمَ الأحاديَّ، و`--apply`
مغلق. أسماءٌ اصطناعيّةٌ كلُّها.
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from core.management.commands.anonymize_minor_audit_names import plan_minor_name_anonymization
from core.models import AuditLog, ParentStudentLink
from tests.conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory

pytestmark = pytest.mark.django_db

MINOR = "قاصر اصطناعي أول"
SHARED = "اسم اصطناعي مشترك"
SINGLE = "مفرد"
PARENT = "وليّ اصطناعي"


def _row(model, object_id, object_repr, changes=None):
    return AuditLog.objects.create(
        action="login",
        model_name=model,
        object_id=str(object_id),
        object_repr=object_repr,
        changes=changes,
    )


@pytest.fixture
def world(db):
    school = SchoolFactory()
    student_role = RoleFactory(school=school, name="student")
    teacher_role = RoleFactory(school=school, name="teacher")
    minor = UserFactory(full_name=MINOR)
    shared_minor = UserFactory(full_name=SHARED)
    single_minor = UserFactory(full_name=SINGLE)
    for u in (minor, shared_minor, single_minor):
        MembershipFactory(user=u, school=school, role=student_role)
    adult_same_name = UserFactory(full_name=SHARED)
    MembershipFactory(user=adult_same_name, school=school, role=teacher_role)
    parent = UserFactory(full_name=PARENT)
    MembershipFactory(user=parent, school=school, role=RoleFactory(school=school, name="parent"))
    ParentStudentLink.objects.create(
        school=school, parent=parent, student=minor, relationship="father"
    )
    return {
        "school": school,
        "minor": minor,
        "shared": shared_minor,
        "single": single_minor,
        "parent": parent,
    }


def _delta(before, after):
    """الفرقُ بين تقريرَين: إشاراتُ التدقيق تكتب صفوفاً مقنَّعةً عند إنشاء المستخدمين فلا تُحسب."""
    out = {}
    for model, counts in after["by_model"].items():
        diff = {k: v - before["by_model"][model].get(k, 0) for k, v in counts.items()}
        out[model] = {k: v for k, v in diff.items() if v}
    return out


def _snapshot():
    with connection.cursor() as cur:
        cur.execute("SELECT id, object_repr, changes::text FROM core_auditlog ORDER BY id")
        return cur.fetchall()


class TestPlan:
    def test_categories_are_counted_per_model(self, world):
        base = plan_minor_name_anonymization()
        minor = world["minor"]
        _row("CustomUser", minor.pk, MINOR)  # سيُجهَّل
        _row(
            "CustomUser", minor.pk, "CustomUser 3f2a91bc", {"full_name": MINOR}
        )  # الاسمُ في changes
        _row("CustomUser", world["shared"].pk, SHARED)  # مشترك
        _row("CustomUser", world["single"].pk, SINGLE)  # أحاديّ
        _row("CustomUser", minor.pk, "CustomUser 3f2a91bc")  # مقنَّع
        _row("ParentStudentLink", "lnk-1", f"{PARENT} ← {MINOR} (الأب)")  # سيُجهَّل
        _row("ParentStudentLink", "lnk-2", f"{PARENT} ← غير معروف اصطناعي (الأب)")  # لا قاصر
        _row("Membership", "m-1", MINOR)  # خارج النطاق

        report = plan_minor_name_anonymization()
        delta = _delta(base, report)

        assert delta["CustomUser"] == {
            "to_anonymize": 2,
            "skip_shared_name": 1,
            "skip_short_name": 1,
            "no_minor_name": 1,
        }
        assert delta["ParentStudentLink"] == {"to_anonymize": 1, "no_minor_name": 1}
        assert report["totals"]["to_anonymize"] == 3 and report["rows_to_anonymize"] == 3
        assert report["rows_in_scope"] - base["rows_in_scope"] == 7  # صفُّ Membership خارج النطاق

    def test_adult_only_names_are_never_candidates(self, world):
        base = plan_minor_name_anonymization()
        _row("CustomUser", world["parent"].pk, PARENT)
        _row("ParentStudentLink", "lnk", f"{PARENT} ← {MINOR} (الأب)")
        report = plan_minor_name_anonymization()
        assert _delta(base, report)["CustomUser"] == {"no_minor_name": 1}
        assert report["totals"]["to_anonymize"] == 1  # اسمُ القاصر وحدَه، لا اسمُ الوليّ

    def test_unparsable_link_rows_fall_back_to_whole_name_matching(self, world):
        base = plan_minor_name_anonymization()
        _row("ParentStudentLink", "lnk", f"ربطٌ بصيغةٍ قديمة: {MINOR}")
        assert _delta(base, plan_minor_name_anonymization())["ParentStudentLink"] == {
            "to_anonymize": 1
        }


class TestCommand:
    def test_dry_run_writes_nothing_and_prints_no_names(self, world):
        _row("CustomUser", world["minor"].pk, MINOR)
        _row("ParentStudentLink", "lnk", f"{PARENT} ← {MINOR} (الأب)")
        before = _snapshot()
        out = StringIO()
        call_command("anonymize_minor_audit_names", stdout=out)
        text = out.getvalue()
        assert _snapshot() == before
        for name in (MINOR, SHARED, SINGLE, PARENT):
            assert name not in text
        assert "to_anonymize=1" in text and "عدٌّ فقط" in text

    def test_apply_is_closed(self, world):
        with pytest.raises(CommandError) as exc:
            call_command("anonymize_minor_audit_names", "--apply", stdout=StringIO())
        assert "W-20261004-002" in str(exc.value)

    def test_the_command_cannot_update_rows_even_in_principle(self, world):
        """الزنادُ لا يسمح بتعديل object_repr — فالعدُّ لا يحتاج كتابةً ولا يملكها."""
        row = _row("CustomUser", world["minor"].pk, MINOR)
        with pytest.raises(Exception):  # noqa: B017, PT011 — الزنادُ يرفع InternalError/PermissionDenied
            AuditLog.objects.filter(pk=row.pk).update(object_repr="x")
