"""حارسُ تطابق نسخ الفلو مع flow.md (W-20261016-015): الإصدارُ وعددُ الدفعات ورقمُ خطوة الدفع."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import flow_facts  # noqa: E402

#: انحرافٌ معروفٌ قائمٌ اليوم (سقّاطة): تصحيحُه بطاقةٌ منفصلةٌ لأنّ النسخةَ ملفٌّ حاكم (يحتاج اعتماداً بالرأس).
#: بعد التصحيح يفشل هذا الاختبارُ حتى يُحذف السطرُ من القائمة، فلا يبقى انحرافٌ مسكوتٌ عنه.
KNOWN_DRIFT = {
    ".claude/skills/schoolos-flow/SKILL.md": "version",
}


def _drifted(root: Path) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for line in flow_facts.mismatches(root):
        rel, rest = line.split(": ", 1)
        out.setdefault(rel, set()).add(rest.split(" = ", 1)[0])
    return out


def test_no_new_drift_and_known_drift_is_still_real():
    drift = _drifted(ROOT)
    known = {rel: {key} for rel, key in KNOWN_DRIFT.items()}
    assert drift == known, (
        "انحرافٌ بين نسخ الفلو وflow.md: "
        + "؛ ".join(flow_facts.mismatches(ROOT))
        + " — صحّح النسخةَ (بطاقةٌ منفصلة) أو احذف سطرها من KNOWN_DRIFT بعد تصحيحها."
    )


def _tree(tmp_path: Path, source_version: str, copy_version: str) -> Path:
    (tmp_path / "docs/governance").mkdir(parents=True)
    (tmp_path / "docs/governance/flow.md").write_text(
        f"(الفلو v{source_version})\nدفعتا نشرٍ يومياً\n5. **ادفع فورَ الاعتماد**\n", encoding="utf-8"
    )
    (tmp_path / "CLAUDE.md").write_text(
        f"(الفلو v{copy_version})\nدفعتا نشرٍ يوميّاً\n", encoding="utf-8"
    )
    return tmp_path


def test_matching_copy_passes(tmp_path):
    assert flow_facts.mismatches(_tree(tmp_path, "2.23", "2.23")) == []


def test_changing_only_the_source_version_fails_the_guard(tmp_path):
    out = flow_facts.mismatches(_tree(tmp_path, "2.24", "2.23"))
    assert out and "CLAUDE.md" in out[0] and "version" in out[0]


def test_wrong_batch_count_is_named(tmp_path):
    root = _tree(tmp_path, "2.23", "2.23")
    (root / "CLAUDE.md").write_text("(الفلو v2.23)\nثلاث دفعات نشر يومياً\n", encoding="utf-8")
    assert any("batches" in line for line in flow_facts.mismatches(root))


def test_wrong_push_step_number_is_named(tmp_path):
    root = _tree(tmp_path, "2.23", "2.23")
    (root / "CLAUDE.md").write_text("(الفلو v2.23)\n6. **ادفع** بعد الاعتماد\n", encoding="utf-8")
    assert any("push_step" in line for line in flow_facts.mismatches(root))
