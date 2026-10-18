"""[W-20261012-033] وصفُ المخالفة والإجراءُ مشفَّران at-rest، وقراءةُ النصّ الكامل مدقَّقة.

الإصدار الأول: AlterField إلى EncryptedTextField (قراءةٌ تقبل القديمَ الصريح)؛ والثاني (هجرة بيانات) بعد استقرار الأول.
بياناتُ الاختبار مصنَّعة كلُّها (PDPPL).
"""

import pytest
from django.db import connection
from django.urls import reverse

from behavior.models import BehaviorCommitteeVote, BehaviorInfraction
from core.models import AuditLog
from tests.conftest import BehaviorInfractionFactory

pytestmark = pytest.mark.django_db

SECRET = "نصٌّ-مصنَّع-للتشفير-فقط"


def _raw(model, pk, column):
    with connection.cursor() as cur:
        cur.execute(f"SELECT {column} FROM {model._meta.db_table} WHERE id = %s", [pk])  # noqa: S608
        return cur.fetchone()[0]


def test_text_fields_are_encrypted_in_the_database_and_plain_through_the_orm(
    school, student_user, teacher_user
):
    inf = BehaviorInfractionFactory(
        school=school,
        student=student_user,
        reported_by=teacher_user,
        level=3,
        description=SECRET,
        action_taken=SECRET + "-إجراء",
    )
    assert SECRET not in _raw(BehaviorInfraction, inf.pk, "description")
    assert SECRET not in _raw(BehaviorInfraction, inf.pk, "action_taken")
    fresh = BehaviorInfraction.objects.get(pk=inf.pk)
    assert fresh.description == SECRET and fresh.action_taken == SECRET + "-إجراء"


def test_vote_action_is_encrypted_too(school, student_user, teacher_user):
    inf = BehaviorInfractionFactory(
        school=school, student=student_user, reported_by=teacher_user, level=3
    )
    vote = BehaviorCommitteeVote.objects.create(
        infraction=inf, voter=teacher_user, decision="apply", action_taken=SECRET
    )
    assert SECRET not in _raw(BehaviorCommitteeVote, vote.pk, "action_taken")
    assert BehaviorCommitteeVote.objects.get(pk=vote.pk).action_taken == SECRET


def test_old_plaintext_rows_still_read_correctly(school, student_user, teacher_user):
    """الإصدار الأول: صفٌّ قديم صريح يُقرأ صحيحاً حتى تُشفّره هجرةُ البيانات."""
    inf = BehaviorInfractionFactory(school=school, student=student_user, reported_by=teacher_user)
    with connection.cursor() as cur:
        cur.execute(
            f"UPDATE {BehaviorInfraction._meta.db_table} SET description = %s WHERE id = %s",  # noqa: S608
            [SECRET, inf.pk],
        )
    assert BehaviorInfraction.objects.get(pk=inf.pk).description == SECRET


def test_no_search_or_filter_on_the_encrypted_fields():
    """التشفيرُ لا يسمح بالبحث: لا `description__…` ولا `action_taken__…` في الشيفرة، ولا في search_fields."""
    import subprocess

    out = subprocess.run(
        [
            "git",
            "grep",
            "-nE",
            r"(description|action_taken)__(icontains|contains|exact|iexact|startswith|in)\b",
            "--",
            "*.py",
            ":!*/migrations/*",
            ":!tests/*",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    assert not [
        line for line in out.splitlines() if "BehaviorInfraction" in line or "behavior/" in line
    ]
    from behavior.admin import BehaviorInfractionAdmin

    assert "description" not in BehaviorInfractionAdmin.search_fields


def _audit_rows(inf):
    return AuditLog.objects.filter(
        model_name="BehaviorInfraction", object_id=str(inf.pk), action="view"
    )


def test_committee_case_reads_are_audited_once_per_window_without_text(
    client_as, school, principal_user, student_user, teacher_user
):
    inf = BehaviorInfractionFactory(
        school=school, student=student_user, reported_by=teacher_user, level=3, description=SECRET
    )
    client = client_as(principal_user)
    for _ in range(3):
        assert client.get(reverse("behavior:committee_decision", args=[inf.pk])).status_code == 200
    rows = _audit_rows(inf)
    assert rows.count() == 1
    row = rows.first()
    assert row.user_id == principal_user.pk
    blob = f"{row.object_repr}{row.changes}{row.object_id}"
    assert SECRET not in blob and student_user.full_name not in blob


def test_student_profile_read_is_audited_per_infraction(
    client_as, school, principal_user, student_user, teacher_user
):
    a = BehaviorInfractionFactory(school=school, student=student_user, reported_by=teacher_user)
    b = BehaviorInfractionFactory(school=school, student=student_user, reported_by=teacher_user)
    resp = client_as(principal_user).get(
        reverse("behavior:student_profile", args=[student_user.pk])
    )
    assert resp.status_code == 200
    assert _audit_rows(a).count() == 1 and _audit_rows(b).count() == 1


def test_dashboard_lists_are_not_audited(
    client_as, school, principal_user, student_user, teacher_user
):
    inf = BehaviorInfractionFactory(school=school, student=student_user, reported_by=teacher_user)
    client_as(principal_user).get(reverse("behavior:dashboard"))
    assert _audit_rows(inf).count() == 0
