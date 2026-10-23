"""تلوينُ صفوف الجداول بدرجةِ الصفّ الدراسيّ (قرارُ المالك، W-20261013-024، رموزُ 0419 `--grade-N`).

كلُّ جدولٍ صفوفُه من حلقة `{% for %}` وفي صفّه صفٌّ دراسيٌّ (`.grade` أو `class_group`) يحمل على `<tr>` الصنفَ `grade-tint`
(أو يستعمل `{% grade_row_css %}` في قوالب PDF). الحارسُ يمنع الجديدَ فقط: القديمُ مسجَّلٌ بعدد الجداول في
`grade_row_tint_baseline.json` وتُنقَص الأعدادُ مع كلّ موجةِ ترحيل حتى يصير فارغاً.
"""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = json.loads(
    (ROOT / "tests" / "grade_row_tint_baseline.json").read_text(encoding="utf-8")
)["files"]

_TABLE = re.compile(r"<table\b.*?</table>", re.S | re.I)
_GRADE = re.compile(r"\.grade\b|class_group")
_TINTED = re.compile(r"grade-tint|grade_row_css|\bg-g\d")


def _violations(text: str) -> int:
    """جداولُ صفوفُها من حلقةٍ وفيها صفٌّ دراسيٌّ بلا صنفِ تلوين."""
    if "grade_row_css" in text:
        return 0
    count = 0
    for m in _TABLE.finditer(text):
        body = m.group(0)
        if "{% for" in body and _GRADE.search(body) and not _TINTED.search(body):
            count += 1
    return count


def _counts() -> dict[str, int]:
    out = {}
    for p in sorted((ROOT / "templates").rglob("*.html")):
        n = _violations(p.read_text(encoding="utf-8"))
        if n:
            out[p.relative_to(ROOT).as_posix()] = n
    return out


def test_new_grade_tables_are_tinted():
    over = {f: (n, BASELINE.get(f, 0)) for f, n in _counts().items() if n > BASELINE.get(f, 0)}
    assert not over, f"جدولٌ فيه صفٌّ دراسيٌّ بلا `grade-tint grade-gN` على صفّه: {over}"


def test_baseline_is_not_wider_than_reality():
    counts = _counts()
    stale = {f: n for f, n in BASELINE.items() if counts.get(f, 0) < n}
    assert not stale, f"رُحِّلت جداول — أنقِص الأعداد في grade_row_tint_baseline.json: {stale}"


def test_the_detector_sees_the_bad_shape_and_accepts_the_good_one():
    bad = (
        "<table>{% for r in rows %}<tr><td>{{ r.class_group.grade }}</td></tr>{% endfor %}</table>"
    )
    good = bad.replace("<tr>", '<tr class="grade-tint grade-{{ r.class_group.grade|lower }}">')
    assert _violations(bad) == 1 and _violations(good) == 0
    assert _violations("{% grade_row_css '.g' %}" + bad) == 0
