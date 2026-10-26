"""فحصُ CI لسطر الاعتماد المطابق للرأس — W-20261003-003.

ثلاثُ حالاتٍ إلزاميّة (مطابقٌ يمرّ، رأسٌ قديمٌ يفشل، بلا سطرٍ يفشل) وما يحيط بها: التفويضُ المسجَّل، والمؤلّفُ الآليّ،
وغيابُ الرأس في سطر المالك. يقرأ الوصفَ والرأسَ فقط بلا شبكة.
"""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "pr_approval_head_check",
    Path(__file__).resolve().parent.parent / "scripts" / "pr_approval_head_check.py",
)
chk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chk)

HEAD = "f5321cac03d0a2fedd8edbe82257480d07e752c5"  # pragma: allowlist secret
LINE = "اعتُمد من المالك على 8500 — 2026-10-20 — الرأس f5321cac"


def test_a_matching_line_passes():
    assert chk.verdict(f"وصف\n\n{LINE}", HEAD)[0] == "ok"


def test_a_line_for_an_old_head_fails():
    old = "اعتُمد من المالك على 8500 — 2026-10-20 — الرأس 11111111"
    state, message = chk.verdict(f"وصف\n\n{old}", HEAD)
    assert state == "stale_head" and "11111111" in message and "f5321cac" in message


def test_no_approval_line_fails():
    assert chk.verdict("وصفٌ بلا اعتماد", HEAD)[0] == "no_line"
    assert chk.verdict("", HEAD)[0] == "no_line"


def test_an_owner_line_without_a_head_is_not_bound():
    assert chk.verdict("اعتُمد من المالك على 8500 — 2026-10-20", HEAD)[0] == "no_head"


def test_the_direct_no_preview_form_is_also_head_bound():
    line = "اعتُمد من المالك مباشرةً بلا معاينة 8500 — 2026-10-20 — الرأس f5321cac"
    assert chk.verdict(line, HEAD)[0] == "ok"
    assert chk.verdict(line.replace("f5321cac", "00000000"), HEAD)[0] == "stale_head"


def test_a_recorded_delegation_counts_only_on_the_exact_head():
    line = "اعتُمد بتفويض 0101 على الرأس f5321cac — 2026-10-20"
    assert chk.verdict(line, HEAD)[0] == "ok"
    assert chk.verdict(line.replace("f5321cac", "abcdef12"), HEAD)[0] == "stale_head"


def test_one_matching_line_among_stale_ones_passes():
    body = "اعتُمد من المالك على 8500 — 2026-10-19 — الرأس 11111111\n" + LINE
    assert chk.verdict(body, HEAD)[0] == "ok"


def test_a_too_short_head_never_matches():
    assert not chk.same_head("f5321c", HEAD)
    assert chk.same_head("f5321ca", HEAD)
    assert chk.same_head(HEAD, "f5321cac")


def test_an_automation_author_is_exempt():
    assert chk.verdict("", HEAD, "dependabot[bot]")[0] == "exempt"
    assert chk.verdict("", HEAD, "app/dependabot")[0] == "exempt"  # الصيغةُ الفعليّة من gh (طلب 1149)
    assert chk.verdict("", HEAD, "x", is_bot=True)[0] == "exempt"
    assert chk.verdict("", HEAD, "mesuef1974")[0] == "no_line"


def test_the_expression_has_a_single_source_with_the_merge_gate():
    assert chk.gate.APPROVAL.pattern in chk.OWNER_HEAD.pattern
    assert chk.ev.DELEGATED is chk.ev.DELEGATED and chk.ev.gate is chk.gate


def test_the_workflow_runs_the_script_and_is_not_a_merge_gate_need():
    import yaml

    root = Path(__file__).resolve().parent.parent / ".github" / "workflows"
    doc = yaml.safe_load((root / "pr-approval-head.yml").read_text(encoding="utf-8"))
    job = doc["jobs"]["approval-head"]
    assert "scripts/pr_approval_head_check.py" in job["steps"][-1]["run"]
    assert isinstance(job.get("timeout-minutes"), int)
    gate = yaml.safe_load((root / "quality-gate.yml").read_text(encoding="utf-8"))
    needs = {
        n
        for j in gate["jobs"].values()
        for n in ([j.get("needs")] if isinstance(j.get("needs"), str) else j.get("needs") or [])
    }
    assert (
        "approval-head" not in needs
    ), "الدخولُ في شروط البوّابة قرارُ المالك بعد أسبوع مراقبةٍ للإيجابيات الكاذبة"


def test_mandate_line_bound_to_head_is_accepted():
    line = "اعتُمد بتكليف المالك D-443م عبر 0101 — 2026-10-21 — الرأس " + HEAD[:8]
    assert chk.verdict(line, HEAD)[0] == "ok"
    assert chk.verdict(line, "ffffffff" + HEAD[8:])[0] == "stale_head"
    assert chk.verdict("اعتُمد بتكليف المالك D-443م عبر 0101 — 2026-10-21", HEAD)[0] == "no_line"
