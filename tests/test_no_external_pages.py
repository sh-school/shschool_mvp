"""لا صفحةَ تُفتح خارج المنصّة ولا في صفحةٍ/لسانٍ جديد — كلُّ شيءٍ داخل المنصّة (قرارُ المالك 2026-10-13).

يمنع في القوالب وجافاسكربت المنصّة: `target="_blank"` و`window.open(` والروابطَ المطلقةَ `href="http(s)://…"`.
المواضعُ التي سبقت القاعدةَ مسجَّلةٌ في `no_external_pages_baseline.json` بعددها لكلّ ملفّ: لا يزيد عددٌ ولا يُضاف ملفّ،
وتُنقَص الأعدادُ كلّما رُحِّل موضع (يُنبّه الاختبارُ إلى ذلك حتى لا يبقى الخطُّ الأساس أوسعَ من الواقع).
"""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = json.loads(
    (ROOT / "tests" / "no_external_pages_baseline.json").read_text(encoding="utf-8")
)["files"]

_PATTERN = re.compile(r"""target\s*=\s*["']_blank["']|window\.open\s*\(|href\s*=\s*["']https?://""")


def _scanned():
    yield from sorted((ROOT / "templates").rglob("*.html"))
    for p in sorted((ROOT / "static" / "js").rglob("*.js")):
        if ".min." not in p.name and "vendor" not in p.parts:
            yield p


def _counts() -> dict[str, int]:
    out = {}
    for p in _scanned():
        n = len(_PATTERN.findall(p.read_text(encoding="utf-8")))
        if n:
            out[p.relative_to(ROOT).as_posix()] = n
    return out


def test_no_new_page_opens_outside_the_platform():
    over = {f: (n, BASELINE.get(f, 0)) for f, n in _counts().items() if n > BASELINE.get(f, 0)}
    assert not over, (
        "قاعدة المالك: لا صفحةَ تُفتح خارج المنصّة ولا في لسانٍ جديد. افتح الوجهةَ داخل المنصّة "
        f"(الصفحةُ نفسُها أو نافذةٌ داخليّة أو مركزُ التصدير data-app-file): {over}"
    )


def test_baseline_is_not_wider_than_reality():
    stale = {f: n for f, n in BASELINE.items() if _counts().get(f, 0) < n}
    assert not stale, f"رُحِّلت مواضعُ — أنقِص الأعدادَ في no_external_pages_baseline.json: {stale}"
