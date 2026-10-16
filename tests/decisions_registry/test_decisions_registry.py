"""سجلُّ قرارات المالك: تحليلٌ وحجبٌ واستيرادٌ idempotent وكشفُ انجراف وقراءةٌ مقيَّدة (W-20260928-019)."""

import pytest
from django.contrib import admin as django_admin
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory

from core.capabilities import registry
from decisions_registry import admin as reg_admin
from decisions_registry.models import Decision, ImportBatch
from decisions_registry.parsing import fingerprint, parse_decisions_md, parse_meta
from decisions_registry.scrub import MASK, mask_personal
from decisions_registry.services import DecisionsImportError, check_drift, import_decisions

MD = (
    "# قرارات\n"
    "- D-1م | 2026-09-01 | نصٌّ كاملٌ | أثرٌ | مرجع-1\n"
    "- D-2م | 2026-09-02 | نصٌّ فيه | شرطة | أثر | مرجع-2\n"
    "- D-3م | 2026-09-03 | نصٌّ وأثر فقط | أثر3\n"
    "- D-4م | 2026-09-04 | نصٌّ وحده\n"
    "سطرٌ ليس قراراً\n"
)
META = (
    '{"id": "D-1م", "type": "approval", "location": "الموضع", "ts": "2026-09-01T10:00"}\n'
    "سطرٌ معيب\n"
    '{"id": "D-2م", "type": "structural"}\n'
)


@pytest.fixture
def files(tmp_path):
    md = tmp_path / "decisions.md"
    meta = tmp_path / "meta.jsonl"
    md.write_text(MD, encoding="utf-8")
    meta.write_text(META, encoding="utf-8")
    return md, meta


def test_parse_handles_all_row_shapes():
    rows = {r.decision_id: r for r in parse_decisions_md(MD)}
    assert list(rows) == ["D-1م", "D-2م", "D-3م", "D-4م"]
    assert (rows["D-1م"].text, rows["D-1م"].effect, rows["D-1م"].reference) == (
        "نصٌّ كاملٌ",
        "أثرٌ",
        "مرجع-1",
    )
    assert rows["D-2م"].text == "نصٌّ فيه|شرطة"
    assert (rows["D-3م"].text, rows["D-3م"].effect, rows["D-3م"].reference) == (
        "نصٌّ وأثر فقط",
        "أثر3",
        "",
    )
    assert rows["D-4م"].text == "نصٌّ وحده" and rows["D-4م"].effect == ""


def test_parse_meta_skips_bad_lines():
    assert set(parse_meta(META)) == {"D-1م", "D-2م"}


def test_mask_numbers_emails_and_names():
    out = mask_personal(
        "الطالب فلان 29876543210 بريد a@b.com جوال +974 55512345 ورقم 123", ("فلان",)
    )
    assert "29876543210" not in out and "a@b.com" not in out and "55512345" not in out
    assert "فلان" not in out and "123" in out and MASK in out


def test_fingerprint_ignores_whitespace_only():
    assert fingerprint("a", "d", "x  y", "e", "r") == fingerprint("a", "d", "x y ", "e", "r")
    assert fingerprint("a", "d", "x", "e", "r") != fingerprint("a", "d", "z", "e", "r")


@pytest.mark.django_db
def test_import_is_idempotent(files):
    md, meta = files
    first = import_decisions(md, meta)
    assert (first.total, first.created, first.unchanged) == (4, 4, 0)
    second = import_decisions(md, meta)
    assert (second.created, second.unchanged, second.batch_id) == (0, 4, None)
    assert Decision.objects.count() == 4 and ImportBatch.objects.count() == 1
    assert Decision.objects.get(decision_id="D-1م").kind == "approval"


@pytest.mark.django_db
def test_new_rows_only_are_added_on_growth(files):
    md, meta = files
    import_decisions(md, meta)
    md.write_text(MD + "- D-5م | 2026-09-05 | جديد | أثر | مرجع\n", encoding="utf-8")
    result = import_decisions(md, meta)
    assert (result.created, result.unchanged) == (1, 4)


@pytest.mark.django_db
def test_changed_existing_row_fails_whole_import_without_writing(files):
    md, meta = files
    import_decisions(md, meta)
    md.write_text(
        MD.replace("نصٌّ كاملٌ", "نصٌّ مُغيَّر") + "- D-5م | 2026-09-05 | جديد | أثر | مرجع\n",
        encoding="utf-8",
    )
    with pytest.raises(DecisionsImportError):
        import_decisions(md, meta)
    assert (
        Decision.objects.count() == 4 and not Decision.objects.filter(decision_id="D-5م").exists()
    )


@pytest.mark.django_db
def test_duplicate_id_in_file_fails(tmp_path):
    md = tmp_path / "d.md"
    md.write_text("- D-1م | d | أ | ب | ج\n- D-1م | d | أ2 | ب | ج\n", encoding="utf-8")
    with pytest.raises(DecisionsImportError):
        import_decisions(md)
    assert Decision.objects.count() == 0


@pytest.mark.django_db
def test_names_are_masked_before_storing(files):
    md, meta = files
    md.write_text("- D-1م | d | قرار بشأن فلان 29876543210 | أثر | م\n", encoding="utf-8")
    import_decisions(md, None, names=("فلان",))
    stored = Decision.objects.get(decision_id="D-1م")
    assert "فلان" not in stored.text and "29876543210" not in stored.text
    assert ImportBatch.objects.get().names_masked is True


@pytest.mark.django_db
def test_drift_detected_after_direct_edit(files):
    md, meta = files
    import_decisions(md, meta)
    assert check_drift() == []
    Decision.objects.filter(decision_id="D-3م").update(text="تعديلٌ مباشر")
    assert check_drift() == ["D-3م"]


@pytest.mark.django_db
def test_commands(files, capsys):
    md, meta = files
    call_command("decisions_import", file=str(md), meta=str(meta))
    assert "أُنشئ 4" in capsys.readouterr().out
    call_command("decisions_drift_check")
    Decision.objects.filter(decision_id="D-1م").update(effect="x")
    with pytest.raises(CommandError):
        call_command("decisions_drift_check")
    with pytest.raises(CommandError):
        call_command("decisions_import", file=str(md.parent / "missing.md"))


def test_capability_is_principal_only():
    cap = registry()["decisions.view"]
    assert "principal" in cap.expanded_roles
    assert not {"teacher", "student", "parent", "secretary"} & set(cap.expanded_roles)


@pytest.mark.parametrize("model", [Decision, ImportBatch])
def test_admin_is_read_only_and_capability_gated(model, monkeypatch):
    model_admin = django_admin.site._registry[model]
    request = RequestFactory().get("/")
    request.user = object()
    for method in ("has_add_permission", "has_change_permission", "has_delete_permission"):
        assert getattr(model_admin, method)(request) is False
    monkeypatch.setattr(reg_admin, "has_capability", lambda user, key: key == "decisions.view")
    assert model_admin.has_view_permission(request) is True
    assert model_admin.has_module_permission(request) is True
    monkeypatch.setattr(reg_admin, "has_capability", lambda user, key: False)
    assert model_admin.has_view_permission(request) is False
    assert model_admin.has_module_permission(request) is False
