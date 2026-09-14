"""سقّاطةُ الوصوليّة — ما يُعدّ في القوالب لا يزيد، وما رُحِّل لا يعود.

مراجعةُ 2026-09-14 وجدت 157 حقلاً مرئيّاً بلا اسمٍ برمجيّ (لا `label[for]`
ولا `aria-label` ولا التفاف)، و169 `<label>` بلا `for`، وصفحاتٍ بلا `<h1>`،
وجداولَ بلا غلافِ تمرير، وجزئيّاتٍ تعرض قائمةً ولا تقول شيئاً حين تفرغ.
والحقلُ بلا اسمٍ لا يُقرأ لقارئ الشاشة إلّا «حقلُ نصّ» — فلا يعرف الكفيفُ
ما يكتب فيه، ولا يفتح النقرُ على التسمية حقلَها.

والعلاجُ وسمُ `{% field %}` في `core/templatetags/ui.py`: يولّد التسميةَ
والحقلَ بمعرّفٍ واحد، فلا يكون حقلٌ بلا اسم. لكنّ الوسمَ لا يمنع أن يُكتب
`<input>` جديدٌ باليد غداً، فهنا الحارس — بمنطق `tests/design_ratchet.py`:

* لكلّ قالبٍ عددُه المسجَّل من كلّ مخالفة. **زاد** → يسقط البناء.
* **نقص** → يسقط كذلك حتّى يُسجَّل العددُ الجديد، فلا يُنفَق التحسّنُ مرّتين.
* قالبٌ جديدٌ عددُه صفر — يُكتب نظيفاً من أوّله.

وتسجيلُ الأعداد بعد تحسينٍ مقصود:

    python -m tests.a11y_ratchet --update

المقاييسُ الخمسة:

* `unnamed_field` — `<input>`/`<select>`/`<textarea>` مرئيٌّ بلا اسم: لا
  `aria-label` ولا `aria-labelledby` ولا `title`، ولا `<label for>` يشير إلى
  `id`ه في القالب نفسه، ولا `<label>` يلتفّ حوله.
* `label_without_for` — `<label>` بلا `for` لا يلتفّ حول حقل: نصٌّ يبدو
  تسميةً ولا يُربط بشيء.
* `page_without_h1` — صفحةٌ (تمتدّ من أساسٍ في المستودع أو وثيقةٌ كاملة) لا
  `<h1>` فيها ولا في آبائها ولا `{% page_header %}`.
* `table_without_wrap` — `<table>` في صفحة شاشةٍ بلا سَلَفٍ يمرّرها أفقيّاً
  (`table-wrap`)؛ فالجدولُ العريضُ في الهاتف يُقصّ لا يُمرَّر.
* `partial_without_empty_state` — جزئيّةٌ تُضمَّن وتدور على قائمةٍ بلا
  `{% empty %}` ولا حالةِ فراغ: الجدولُ يُبدَّل بـHTMX فيبقى فراغٌ لا يقول شيئاً.

المسحُ نصّيٌّ على مصدر القالب لا على HTML مرسوم — فما يرسمه وسمٌ (`field`،
`page_header`) لا يُعدّ، وهذا مقصود: الوسمُ هو الطريقُ المحروس.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from collections import Counter
from html.parser import HTMLParser

from tests.design_ratchet import EXTENDS_RE, _includers, _template_file, _template_name

BASELINE = pathlib.Path("tests/a11y_ratchet_baseline.json")
TEMPLATE_ROOTS = (pathlib.Path("templates"),)

METRICS: dict[str, str] = {
    "unnamed_field": "حقلٌ بلا اسمٍ يُقرأ (label[for] / aria-label / التفاف)",
    "label_without_for": "تسميةٌ <label> بلا for ولا حقلٍ داخلها",
    "page_without_h1": "صفحةٌ بلا <h1> ولا page_header",
    "table_without_wrap": "جدولٌ بلا غلافِ تمرير (table-wrap)",
    "partial_without_empty_state": "جزئيّةٌ تدور على قائمةٍ بلا حالةِ فراغ",
}

COMMENT_RE = re.compile(r"\{#.*?#\}|\{% comment %\}.*?\{% endcomment %\}", re.S)
FIELD_RE = re.compile(r"<(input|select|textarea)\b([^>]*)>", re.I | re.S)
LABEL_OPEN_RE = re.compile(r"<label\b([^>]*)>", re.I | re.S)
TAG_RE = re.compile(r"\{%.*?%\}|\{\{.*?\}\}", re.S)
#: أنواعٌ لا تسميةَ لها بطبيعتها: المخفيُّ لا يُرى، والزرُّ اسمُه نصُّه أو `value`.
UNLABELLED_TYPES = frozenset({"hidden", "submit", "button", "reset", "image"})
NAMING_ATTRS = ("aria-label", "aria-labelledby", "title")
#: أسلافٌ تجعل الجدولَ يُمرَّر أفقيّاً بدل أن يُقصّ.
SCROLL_CLASSES = ("table-wrap", "overflow-x-auto", "overflow-auto")
#: وثائقُ الطباعة والبريد لا تُمرَّر ولا تُقرأ في متصفّح المستخدم — الجدولُ فيها على قدر الورقة.
PRINT_PATH_PARTS = ("/pdf/", "/email/")
PRINT_BASES = frozenset(
    {"reports/base_qatar_report.html", "behavior/pdf/base_form.html", "email/_base.html"}
)


def _attr(attrs: str, name: str) -> str | None:
    m = re.search(rf'(?<![\w-]){re.escape(name)}\s*=\s*"([^"]*)"', attrs, re.S)
    if m is None:
        m = re.search(rf"(?<![\w-]){re.escape(name)}\s*=\s*'([^']*)'", attrs, re.S)
    return m.group(1) if m else None


def _clean(text: str) -> str:
    return COMMENT_RE.sub("", text)


def live_templates():
    roots = list(TEMPLATE_ROOTS) + sorted(pathlib.Path(".").glob("*/templates"))
    for root in roots:
        yield from sorted(root.rglob("*.html"))


# ── 1 · حقلٌ بلا اسم ────────────────────────────────────────────────────────


def _label_targets(text: str) -> set[str]:
    return {t for m in LABEL_OPEN_RE.finditer(text) if (t := _attr(m.group(1), "for"))}


def _label_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    for m in LABEL_OPEN_RE.finditer(text):
        end = text.find("</label>", m.end())
        spans.append((m.start(), end if end != -1 else m.end()))
    return spans


def unnamed_fields(text: str) -> int:
    text = _clean(text)
    targets = _label_targets(text)
    spans = _label_spans(text)
    count = 0
    for m in FIELD_RE.finditer(text):
        attrs = m.group(2)
        kind = (_attr(attrs, "type") or "text").lower()
        if m.group(1).lower() == "input" and kind in UNLABELLED_TYPES:
            continue
        if any(_attr(attrs, a) is not None for a in NAMING_ATTRS):
            continue
        field_id = _attr(attrs, "id")
        if field_id and field_id in targets:
            continue
        if any(start <= m.start() < end for start, end in spans):
            continue
        count += 1
    return count


# ── 2 · تسميةٌ بلا for ──────────────────────────────────────────────────────


def labels_without_for(text: str) -> int:
    text = _clean(text)
    count = 0
    for m in LABEL_OPEN_RE.finditer(text):
        if _attr(m.group(1), "for") is not None:
            continue
        end = text.find("</label>", m.end())
        inner = text[m.end() : end] if end != -1 else ""
        if FIELD_RE.search(inner):
            continue
        count += 1
    return count


# ── 3 · صفحةٌ بلا h1 ────────────────────────────────────────────────────────

H1_RE = re.compile(r"<h1\b|\{%\s*page_header\b")
DOCUMENT_RE = re.compile(r"<html\b", re.I)


def _ancestors(text: str, seen: frozenset[str] = frozenset()) -> list[str | None]:
    """نصوصُ الآباء في سلسلة `{% extends %}` — و`None` لأبٍ خارج المستودع."""
    parent = EXTENDS_RE.search(text)
    if not parent or parent.group(1) in seen:
        return []
    path = _template_file(parent.group(1))
    if path is None:
        return [None]
    parent_text = path.read_text(encoding="utf-8")
    return [parent_text] + _ancestors(parent_text, seen | {parent.group(1)})


def _chain_names(text: str, seen: frozenset[str] = frozenset()) -> list[str]:
    parent = EXTENDS_RE.search(text)
    if not parent or parent.group(1) in seen:
        return []
    path = _template_file(parent.group(1))
    names = [parent.group(1)]
    if path is not None:
        names += _chain_names(path.read_text(encoding="utf-8"), seen | {parent.group(1)})
    return names


BASE_BLOCK_RE = re.compile(r"\{%\s*block\s+content\s*%\}")
INCLUDE_RE = re.compile(r"""\{%\s*include\s+["']([^"']+)["']""")


def _includes_h1(text: str) -> bool:
    """`dashboard/main.html` يختار جزئيّةَ الدور ويضمّنها — والعنوانُ فيها."""
    for name in INCLUDE_RE.findall(text):
        path = _template_file(name)
        if path is not None and H1_RE.search(_clean(path.read_text(encoding="utf-8"))):
            return True
    return False


def page_without_h1(path: pathlib.Path, text: str) -> int:
    text = _clean(text)
    if "/email/" in path.as_posix():
        # رسالةُ بريدٍ لا صفحة: عنوانُها سطرُ الموضوع.
        return 0
    if EXTENDS_RE.search(text):
        ancestors = _ancestors(text)
        if None in ancestors:
            # أبٌ من حزمةٍ خارجيّة (لوحةُ إدارة Django) — عنوانُه هناك.
            return 0
    elif DOCUMENT_RE.search(text) and not BASE_BLOCK_RE.search(text):
        # وثيقةٌ كاملةٌ قائمةٌ بنفسها (صفحةُ طباعةٍ بلا أب).
        ancestors = []
    else:
        # جزئيّة، أو أساسٌ يترك `{% block content %}` لأبنائه — العنوانُ عليهم.
        return 0
    if H1_RE.search(text) or any(H1_RE.search(_clean(a)) for a in ancestors) or _includes_h1(text):
        return 0
    return 1


# ── 4 · جدولٌ بلا غلافِ تمرير ────────────────────────────────────────────────


class _TableScan(HTMLParser):
    """يعدّ `<table>` التي لا سلفَ لها من أصناف التمرير — بمكدّس وسومٍ بسيط."""

    VOID = frozenset({"input", "img", "br", "hr", "meta", "link", "source", "col", "wbr"})

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.stack: list[tuple[str, str]] = []
        self.unwrapped = 0

    def handle_starttag(self, tag, attrs):
        classes = dict(attrs).get("class") or ""
        if tag == "table" and not any(
            any(c == s or c.endswith("-" + s) for s in SCROLL_CLASSES)
            for _t, cls in self.stack
            for c in cls.split()
        ):
            self.unwrapped += 1
        if tag not in self.VOID:
            self.stack.append((tag, classes))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break


def _is_print(path: pathlib.Path, text: str) -> bool:
    posix = path.as_posix()
    if any(part in posix for part in PRINT_PATH_PARTS):
        return True
    return bool(set(_chain_names(text)) & PRINT_BASES)


def tables_without_wrap(path: pathlib.Path, text: str) -> int:
    text = _clean(text)
    if _is_print(path, text):
        return 0
    scan = _TableScan()
    scan.feed(TAG_RE.sub(" ", text))
    return scan.unwrapped


# ── 5 · جزئيّةٌ بلا حالةِ فراغ ───────────────────────────────────────────────

LOOP_TOKEN_RE = re.compile(r"\{%\s*(for|empty|endfor)\b(.*?)%\}", re.S)
EMPTY_STATE_RE = re.compile(r"empty_state|empty-state|section_card|\{%\s*empty\s*%\}")


def _is_partial(path: pathlib.Path, text: str, includers: dict[str, list[pathlib.Path]]) -> bool:
    if EXTENDS_RE.search(text) or DOCUMENT_RE.search(text):
        return False
    name = _template_name(path)
    return name in includers or path.name.startswith("_") or "/partials/" in path.as_posix()


def loops_without_empty(text: str) -> int:
    """حلقاتُ المستوى الأوّل بلا `{% empty %}` — وما يدور على `<option>` قائمةُ خياراتٍ لا بيانات."""
    text = _clean(text)
    if EMPTY_STATE_RE.search(text):
        return 0
    count = 0
    depth = 0
    top: dict | None = None
    for m in LOOP_TOKEN_RE.finditer(text):
        kind = m.group(1)
        if kind == "for":
            depth += 1
            if depth == 1:
                top = {"start": m.end(), "empty": False}
        elif kind == "empty" and depth == 1 and top is not None:
            top["empty"] = True
        elif kind == "endfor":
            if depth == 1 and top is not None:
                body = text[top["start"] : m.start()]
                if not top["empty"] and "<option" not in body:
                    count += 1
                top = None
            depth = max(0, depth - 1)
    return count


def partials_without_empty_state(
    path: pathlib.Path, text: str, includers: dict[str, list[pathlib.Path]]
) -> int:
    if not _is_partial(path, text, includers):
        return 0
    return loops_without_empty(text)


# ── القياسُ والمقارنة ────────────────────────────────────────────────────────


def measure() -> dict[str, dict[str, int]]:
    """لكلّ مخالفةٍ: القالبُ ← عددُها فيه (ما كان صفراً لا يُكتب)."""
    counts: dict[str, dict[str, int]] = {name: {} for name in METRICS}
    includers = _includers()
    for path in live_templates():
        text = path.read_text(encoding="utf-8")
        found = {
            "unnamed_field": unnamed_fields(text),
            "label_without_for": labels_without_for(text),
            "page_without_h1": page_without_h1(path, text),
            "table_without_wrap": tables_without_wrap(path, text),
            "partial_without_empty_state": partials_without_empty_state(path, text, includers),
        }
        for name, n in found.items():
            if n:
                counts[name][path.as_posix()] = n
    return counts


def snapshot() -> dict:
    return {"counts": measure()}


def compare(baseline: dict, current: dict) -> tuple[list[str], list[str]]:
    """(ما زاد، ما نقص ولم يُسجَّل) — كلٌّ سطرٌ يُقرأ."""
    worse, stale = [], []
    for name, label in METRICS.items():
        before = baseline["counts"].get(name, {})
        now = current["counts"].get(name, {})
        for path in sorted(set(before) | set(now)):
            was, is_ = before.get(path, 0), now.get(path, 0)
            if is_ > was:
                worse.append(f"{path}: {label} {was} → {is_}")
            elif is_ < was:
                stale.append(f"{path}: {label} {was} → {is_}")
    return worse, stale


def totals(data: dict) -> Counter:
    return Counter({name: sum(files.values()) for name, files in data["counts"].items()})


def main(argv: list[str]) -> int:
    current = snapshot()
    if "--update" in argv:
        BASELINE.write_text(
            json.dumps(current, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for name, total in totals(current).items():
            print(f"{name}: {total}")
        return 0
    if "--totals" in argv:
        for name, total in totals(current).items():
            print(f"{name}: {total}")
        return 0
    worse, stale = compare(json.loads(BASELINE.read_text(encoding="utf-8")), current)
    for line in worse + stale:
        print(line)
    return 1 if worse or stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
