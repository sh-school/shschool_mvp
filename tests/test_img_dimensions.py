"""كلُّ `<img>` في صفحات المنصّة يحمل `width` و`height` — فيُحجَز مكانُه قبل أن يصل الملفّ.

بلا أبعادٍ يجهل المتصفّحُ حجمَ الصورة حتّى يُحمَّل ملفُّها، فيقفز ما تحتها حين تصل (CLS، ميزانيتُه ≤ 0.1 في
`tests/web_vitals.py`). والأبعادُ هنا **تلميحُ نسبةٍ لا مقاسٌ**: مقاسُ العرض يبقى في CSS الصنف. غيرَ أنّ للتلميح فخّاً: صنفٌ
يحدّد `height` وحده على `<img width="295">` يُبقي العرضَ 295px فتتشوّه الصورة — فمتى حدّد CSS الصنف بُعداً واحداً
فأضِف الآخرَ `auto` (كما في `.print-emblem` بـ`schedule/print_pages.html`).

المستثنى كما في مقياس K19 (`scripts/measure_identity_kpis.py`): قوالبُ PDF والبريد — ملفٌّ لا صفحةٌ تتحرّك.
"""

import pathlib
import re

ROOTS = [pathlib.Path("templates")] + sorted(pathlib.Path(".").glob("*/templates"))
IMG_START = re.compile(r"<img\b")
#: وسومُ جانغو داخل الوسم قد تحوي `>` (`{% if a > b %}`) فتُقفَز كاملةً. ماسحٌ خطّيٌّ لا تعبيرٌ متداخل البدائل (CodeQL: تراجعٌ أسّيّ).
DJANGO_CLOSERS = {"{%": "%}", "{{": "}}"}
HAS_WIDTH = re.compile(r"\swidth\s*=")
HAS_HEIGHT = re.compile(r"\sheight\s*=")

#: أدنى عددٍ من الصور يجب أن يبلغه المسح، وإلّا صار الحارسُ يمرّ على لا شيء.
MIN_IMAGES_SCANNED = 10


def _tag_end(text: str, start: int) -> int:
    """موضعُ `>` الذي يُغلق الوسمَ المبدوء عند `start`، مع القفز فوق وسوم جانغو."""
    i = start
    while i < len(text):
        closer = DJANGO_CLOSERS.get(text[i : i + 2])
        if closer:
            end = text.find(closer, i + 2)
            i = len(text) if end < 0 else end + 2
        elif text[i] == ">":
            return i
        else:
            i += 1
    return len(text) - 1


def _images():
    for root in ROOTS:
        for path in sorted(root.rglob("*.html")):
            if "pdf" in path.as_posix() or "email" in path.as_posix():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in IMG_START.finditer(text):
                end = _tag_end(text, match.end())
                yield path, text[: match.start()].count("\n") + 1, text[match.start() : end + 1]


def test_the_scan_reaches_the_images():
    assert len(list(_images())) >= MIN_IMAGES_SCANNED


def test_every_img_in_a_page_template_carries_width_and_height():
    offenders = [
        f"  {path.as_posix()}:{line}: {tag[:100]!r}"
        for path, line, tag in _images()
        if not (HAS_WIDTH.search(tag) and HAS_HEIGHT.search(tag))
    ]
    assert not offenders, (
        "صورةٌ بلا `width`/`height` — يقفز ما تحتها حين يصل ملفُّها (CLS). أضِف أبعادَ الملفّ الأصليّة "
        "(نسبةً لا مقاساً) وأبقِ مقاسَ العرض في CSS:\n" + "\n".join(offenders)
    )
