"""سقّاطةُ حجم الدستور (W-20261003-005، D-158م): `CLAUDE.md` وقواعدُ `.claude/rules` ≤ 200 سطر.

التوصيةُ الرسميّة لـClaude Code: دستورٌ قصيرٌ يُقرأ كلَّ جلسة؛ والزيادةُ تُنقل إلى قاعدةٍ مشروطةٍ بمسارٍ في
`.claude/rules/` بدل تكبير الدستور.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 200


def _constitution_files():
    files = [ROOT / "CLAUDE.md", ROOT / "docs" / "governance" / "flow.md"]
    files += sorted((ROOT / ".claude" / "rules").glob("*.md"))
    return [path for path in files if path.exists()]


def _lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


@pytest.mark.parametrize("path", _constitution_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_the_constitution_stays_short(path):
    count = _lines(path)

    assert count <= LIMIT, (
        f"{path.relative_to(ROOT)} بلغ {count} سطراً (الحدّ {LIMIT}) — انقل الزيادةَ إلى قاعدةٍ مشروطةٍ "
        "بمسارٍ في `.claude/rules/` بدل تكبير الدستور."
    )


def test_the_guard_sees_the_constitution():
    """سقّاطةٌ بلا ملفٍّ تفحصه تنجح كاذبةً: الدستورُ نفسُه موجود."""
    assert (ROOT / "CLAUDE.md") in _constitution_files()
