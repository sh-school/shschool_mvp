"""اختباراتُ سجلِّ مصدر الحقيقة: التحميلُ idempotent، الحذفُ ناعمٌ فقط، الظهورُ بالدور، وحارسُ الفهرس."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.management.base import CommandError

from sot_registry import services
from sot_registry.management.commands.sot_load import in_school_hours
from sot_registry.models import (
    CodeLink,
    Conflict,
    ProtectedDeletionError,
    Provision,
    Revision,
    Source,
)
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[2]


def _snapshot(n: int = 3) -> dict:
    provisions = [
        {
            "pid": f"SCH-T-{i:03d}",
            "article": f"م{i}",
            "printed_page": i,
            "file_page": i + 1,
            "verbatim": f"نصٌّ {i}",
            "rank": i,
        }
        for i in range(1, n + 1)
    ]
    return {
        "source": {"code": "SCH-T", "kind": "SCH", "title": "وثيقةٌ اختباريّة"},
        "expected_count": n,
        "sha256": services.snapshot_sha256(provisions),
        "provisions": provisions,
    }


@pytest.fixture
def make_user(school):
    counter = iter(range(10**9, 10**9 + 10000))

    def _make(role: str):
        user = UserFactory(full_name=f"مستخدم {role}", national_id=str(next(counter)))
        MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
        return user

    return _make


def test_load_is_idempotent_and_matches_count():
    first = services.load_snapshot(_snapshot(3))
    second = services.load_snapshot(_snapshot(3))
    assert first == {"created": 3, "skipped": 0}
    assert second == {"created": 0, "skipped": 3}
    assert Provision.objects.count() == 3
    assert Revision.objects.filter(action=Revision.LOAD).count() == 3
    assert set(Provision.objects.values_list("status", flat=True)) == {Provision.UNVERIFIED}


def test_load_never_touches_a_reviewed_provision():
    services.load_snapshot(_snapshot(1))
    p = Provision.objects.get()
    p.verbatim = "نصٌّ راجعه إنسان"
    p.status = Provision.IN_REVIEW
    p.save()
    services.load_snapshot(_snapshot(1))
    p.refresh_from_db()
    assert p.verbatim == "نصٌّ راجعه إنسان" and p.status == Provision.IN_REVIEW


def test_count_and_hash_mismatch_reject_before_any_write():
    bad_count = _snapshot(3)
    bad_count["expected_count"] = 4
    with pytest.raises(services.SotError):
        services.load_snapshot(bad_count)
    bad_hash = _snapshot(3)
    bad_hash["provisions"][0]["verbatim"] = "غُيِّر بعد البصمة"
    with pytest.raises(services.SotError):
        services.load_snapshot(bad_hash)
    assert Provision.objects.count() == 0 and Source.objects.count() == 0


def test_provision_without_page_or_text_is_rejected():
    snap = _snapshot(1)
    snap["provisions"][0]["printed_page"] = None
    snap.pop("sha256")
    with pytest.raises(services.SotError):
        services.load_snapshot(snap)


def test_hard_delete_is_blocked_on_every_model():
    services.load_snapshot(_snapshot(1))
    p = Provision.objects.get()
    for obj in (p, p.source, Revision.objects.first()):
        with pytest.raises(ProtectedDeletionError):
            obj.delete()
    with pytest.raises(ProtectedDeletionError):
        Revision.objects.first().save()


def test_provision_with_code_link_or_open_conflict_cannot_be_soft_deleted(make_user):
    services.load_snapshot(_snapshot(2))
    a, b = Provision.objects.order_by("pid")
    owner = make_user("platform_developer")
    CodeLink.objects.create(provision=a, code_path="behavior/conduct_2026.py", symbol="X")
    Conflict.objects.create(provision_a=b, description="تعارضٌ")
    for p in (a, b):
        with pytest.raises(services.SotError):
            services.soft_delete(owner, p, "سبب")


def test_soft_delete_writes_revision_and_requires_owner(make_user):
    services.load_snapshot(_snapshot(1))
    p = Provision.objects.get()
    with pytest.raises(PermissionDenied):
        services.soft_delete(make_user("teacher"), p, "سبب")
    services.soft_delete(make_user("platform_developer"), p, "سبب")
    p.refresh_from_db()
    assert p.is_deleted and Revision.objects.filter(action=Revision.SOFT_DELETE).count() == 1


def test_effective_requires_human_review_by_someone_other_than_loader(make_user):
    services.load_snapshot(_snapshot(1))
    p = Provision.objects.get()
    owner = make_user("platform_developer")
    with pytest.raises(services.SotError):
        services.change_status(owner, p, Provision.EFFECTIVE)
    services.mark_reviewed(owner, p)
    services.change_status(owner, p, Provision.EFFECTIVE)
    p.refresh_from_db()
    assert p.status == Provision.EFFECTIVE


@pytest.mark.parametrize(
    "role,sees_unverified,can_read",
    [
        ("teacher", False, True),
        ("principal", False, True),
        ("platform_developer", True, True),
        ("parent", False, False),
        ("student", False, False),
    ],
)
def test_visibility_per_role(make_user, role, sees_unverified, can_read):
    services.load_snapshot(_snapshot(2))
    eff = Provision.objects.order_by("pid").first()
    Provision.objects.filter(pk=eff.pk).update(status=Provision.EFFECTIVE)
    rows = services.visible_for(make_user(role))
    if not can_read:
        assert rows.count() == 0
    elif sees_unverified:
        assert rows.count() == 2
    else:
        assert list(rows) == [eff]


def test_editing_a_provision_leaves_a_revision_and_reopens_effective(make_user):
    services.load_snapshot(_snapshot(1))
    p = Provision.objects.get()
    Provision.objects.filter(pk=p.pk).update(status=Provision.EFFECTIVE)
    p.refresh_from_db()
    services.edit_provision(make_user("principal"), p, explanation="شرحٌ")
    p.refresh_from_db()
    assert p.status == Provision.IN_REVIEW
    assert Revision.objects.filter(action=Revision.EDIT).count() == 1
    with pytest.raises(services.SotError):
        services.edit_provision(make_user("principal"), p, status="effective")


def test_sot_load_command_loads_file_and_refuses_in_school_hours(tmp_path, monkeypatch):
    f = tmp_path / "snap.json"
    f.write_text(json.dumps(_snapshot(2), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(
        "sot_registry.management.commands.sot_load.in_school_hours", lambda now: False
    )
    call_command("sot_load", str(f))
    assert Provision.objects.count() == 2
    monkeypatch.setattr(
        "sot_registry.management.commands.sot_load.in_school_hours", lambda now: True
    )
    with pytest.raises(CommandError):
        call_command("sot_load", str(f))
    call_command("sot_load", str(f), "--allow-school-hours")


def test_school_hours_window():
    import datetime as dt
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Qatar")
    assert in_school_hours(dt.datetime(2026, 10, 12, 9, 0, tzinfo=tz))  # الاثنين 09:00
    assert not in_school_hours(dt.datetime(2026, 10, 12, 15, 0, tzinfo=tz))
    assert not in_school_hours(dt.datetime(2026, 10, 16, 9, 0, tzinfo=tz))  # الجمعة


def test_verbatim_snapshots_are_never_tracked_in_git():
    """لقطتا النصّ الحرفيّ خارج git (قرارُ المالك)؛ يُتتبَّع فهرسٌ فقط."""
    assert "AAdocs/ministry_data/2026_2027/sot_verbatim/" in (ROOT / ".gitignore").read_text(
        encoding="utf-8"
    )
    if shutil.which("git") is None:
        pytest.skip("git غير متاح في هذه البيئة؛ يعمل الفحصُ في CI")
    out = subprocess.run(
        ["git", "ls-files", "AAdocs/ministry_data/2026_2027/sot_verbatim"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.stdout.strip() == ""


def test_index_entries_have_article_page_and_matching_local_hash():
    """كلُّ سطرٍ في الفهرس المتتبَّع: معرّف ومادة وصفحة؛ وإن وُجدت اللقطةُ محلّيًا تطابقت البصمةُ."""
    index_dir = ROOT / "sot_registry" / "index"
    for idx in index_dir.glob("*.json"):
        entries = json.loads(idx.read_text(encoding="utf-8"))
        local = ROOT / "AAdocs" / "ministry_data" / "2026_2027" / "sot_verbatim" / idx.name
        local_by_pid = {}
        if local.exists():
            local_by_pid = {
                p["pid"]: p for p in json.loads(local.read_text(encoding="utf-8"))["provisions"]
            }
        for e in entries:
            assert e["pid"] and e["article"] and e["printed_page"], f"{idx.name}: {e}"
            if e["pid"] in local_by_pid:
                assert services.text_sha256(local_by_pid[e["pid"]]["verbatim"]) == e["sha256"], e[
                    "pid"
                ]
