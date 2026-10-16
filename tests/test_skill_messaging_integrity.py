"""[SKILLS] مهارة schoolos-messaging: لا إحالة معلّقة، ولا رمز تعبيري، ولا حدّ إيقاظ مكتوب رقماً (W-20260928-022)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".claude" / "skills"
MESSAGING = SKILLS / "schoolos-messaging"
# مهاراتٌ عامّةٌ خارج المستودع يُحال إليها باسمها (تُضاف هنا عن وعي).
GLOBAL_SKILLS = {"arabic-rtl-review"}
EMOJI = re.compile("[\U0001f300-\U0001faff\u2600-\u27bf\u2b50\ufe0f\u200d]")


def _texts():
    for path in MESSAGING.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".py"}:
            yield path, path.read_text(encoding="utf-8")


def test_every_skill_reference_exists():
    known = {p.name for p in SKILLS.iterdir() if p.is_dir()} | GLOBAL_SKILLS
    missing = set()
    for _path, text in _texts():
        for name in re.findall(r"\bschoolos-[a-z0-9-]+\b", text):
            if name not in known:
                missing.add(name)
    assert not missing, f"إحالةٌ إلى مهارةٍ غير موجودة: {sorted(missing)}"


def test_no_emoji_in_skill():
    bad = [
        f"{p.name}:{i}"
        for p, t in _texts()
        for i, line in enumerate(t.splitlines(), 1)
        if EMOJI.search(line)
    ]
    assert not bad, f"رمزٌ تعبيريّ: {bad[:5]}"


def test_wake_limit_is_read_from_tabs_json_not_written():
    text = (MESSAGING / "SKILL.md").read_text(encoding="utf-8")
    assert "max_concurrent_wakes" in text
    line = next(line for line in text.splitlines() if "max_concurrent_wakes" in line)
    assert not re.search(r"القيمةُ اليوم\s*\d", line), "الرقمُ يُقرأ من tabs.json لا يُكتب في المهارة"


def test_flow_rules_v2_13_to_v2_15_present_in_both_skills():
    """W-20260929-019: اعتمادُ السجلّ، وما بعد الاعتماد آليّ، والرابطُ القابل للنقر."""
    flow = (SKILLS / "schoolos-flow" / "SKILL.md").read_text(encoding="utf-8")
    templates = (MESSAGING / "references" / "03-templates.md").read_text(encoding="utf-8")
    assert "مسجَّلٌ في الدفتر" in flow and "approval_check.py" in flow
    assert "ما بعد الاعتماد آليّ" in flow and "بلا انتظار تبليغٍ ولا سؤالٍ للمالك" in flow
    assert "http://localhost:8500/" in flow and "D-72م" in flow
    assert "http://localhost:8500/" in templates and "D-72م" in templates
    assert "v2.8" not in flow
