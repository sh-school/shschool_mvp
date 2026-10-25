"""[CACHE] لا رقمَ إصدارٍ يدويّ في روابط الأصول — `?v=N` ممنوع (W-20260928-023).

كسرُ ذاكرة المتصفّح بالمحتوى لا بالرقم: الإنتاج يبصم اسمَ الملفّ بمحتواه (WhiteNoise/ManifestStaticFilesStorage)،
فرقمٌ يدويّ يُنسى ثمّ يخدم المتصفّحَ نسخةً قديمة، أو يُرفع بلا حاجةٍ فيُبطل الذاكرةَ. والعددُ اليومَ صفر (قيس 2026-10-20:
`grep` لـ`?v=` في templates وstatic) والسقفُ صفر.

يفحص روابطَ الأصول المحليّة فقط؛ وما يشير إلى مضيفٍ خارجيّ (http/https/`//`) يُستثنى لأنّ الإصدارَ فيه
لغيرنا. وقائمةُ الاستثناء الصريحة `ALLOWED` فارغة، وتُضاف إليها مسارات بقرار.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN = (
    ("templates", ("*.html", "*.txt")),
    ("static/js", ("*.js", "*.html")),
    ("static/css", ("*.css", "*.html")),
)
#: مسارات (نسبةً للجذر) مستثناة بقرار؛ فارغةٌ اليوم.
ALLOWED: frozenset[str] = frozenset()

#: `?v=` متبوعةً بما يشبه رقمَ إصدار (رقم/نص قصير/قالب Django) — لا استعلامٌ لغرضٍ آخر مثل `?view=`.
MANUAL = re.compile(r"""\?v=(?:[0-9]|\{\{|\{%|[A-Za-z0-9._-]{1,12}(?=["'\s)>&]|$))""")
EXTERNAL = re.compile(r"""(?:https?:)?//""")


def manual_cache_busts(text: str) -> list[tuple[int, str]]:
    """أسطرٌ فيها `?v=` يدويّ على أصلٍ محليّ (يُستثنى إن كان الرابطُ الذي يسبق `?v=` خارجيّاً)."""
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        for m in MANUAL.finditer(line):
            before = line[: m.start()]
            last_ref = max(
                before.rfind('"'), before.rfind("'"), before.rfind("("), before.rfind("=")
            )
            if EXTERNAL.search(before[last_ref + 1 :]):
                continue
            hits.append((n, line.strip()[:120]))
            break
    return hits


def _files():
    for folder, patterns in SCAN:
        base = ROOT / folder
        for pattern in patterns:
            yield from sorted(base.rglob(pattern))


def test_no_manual_cache_bust_in_templates_or_static():
    found = []
    for path in _files():
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOWED:
            continue
        for n, line in manual_cache_busts(path.read_text(encoding="utf-8", errors="replace")):
            found.append(f"{rel}:{n}: {line}")
    assert not found, (
        "رقمُ إصدارٍ يدويّ `?v=` في رابط أصل — احذفه: الإنتاج يبصم الاسمَ بالمحتوى (CLAUDE.md، كسر ذاكرة المتصفّح):\n"
        + "\n".join(found)
    )


def test_the_scan_actually_sees_files():
    """حارسٌ يمسح لا شيء يمرّ دائماً."""
    assert len(list(_files())) > 50


def test_detector_flags_manual_versions():
    for line in (
        '<link rel="stylesheet" href="{% static \'css/app.css\' %}?v=3">',
        '<script src="/static/js/app.js?v=20261020"></script>',
        '<script src="{% static "js/a.js" %}?v={{ build }}"></script>',
        "import x from './m.js?v=2';",
    ):
        assert manual_cache_busts(line), line


def test_detector_ignores_external_hosts_and_other_queries():
    for line in (
        '<script src="https://cdn.example.com/lib.js?v=1.2.3"></script>',
        '<script src="//cdn.example.com/lib.js?v=4"></script>',
        '<a href="/report/?view=all">',
        '<a href="/search/?q=v">',
        "// يكفي أن تكتب v= في تعليق",
    ):
        assert not manual_cache_busts(line), line
