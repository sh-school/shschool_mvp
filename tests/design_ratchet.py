"""سقّاطةُ الهويّة البصريّة — ما يُعدّ في القوالب لا يزيد، وما نقص يُثبَّت نقصُه.

المنصّةُ تبني بطاقاتِها بخمسِ لغات: خمسةُ أنظمةٍ لبطاقة الرقم، وخمسةُ أشكالٍ
للترويسة، ومئاتُ التنسيقات داخل القوالب، وألوانٌ ثابتةٌ لا تتبع الوضعَ الداكن.
وإصلاحُها صفحةً صفحةً لا يكفي وحدَه: صفحةٌ تُصلَح اليوم، وتُكتب غداً صفحةٌ
جديدةٌ باللغة السادسة. فالحارسُ هنا لا يطلب الصفرَ دفعةً واحدة — مئةُ صفحةٍ
لا تُرحَّل في طلب دمج — بل يمنع الزيادة:

* لكلّ قالبٍ عددُه المسجَّل من كلّ مخالفة. **زاد** → يسقط البناء.
* **نقص** → يسقط كذلك، حتى يُسجَّل العددُ الجديد. فالتحسّنُ لا يبقى هامشاً
  يُملأ بمخالفةٍ أخرى في الملفّ نفسه دون أن يُرى.
* قالبٌ جديدٌ عددُه المسجَّل صفر — فالصفحةُ الجديدة تُكتب نظيفةً من أوّلها.
* الأصنافُ المستعمَلة بلا تعريفٍ في CSS قائمةٌ مسمّاة: صنفٌ جديدٌ بلا تعريفٍ
  يسقط. هكذا كان `charts-grid-3` يُكتب في شؤون الطلاب ولا يُعرَّف، فتتراصّ
  قوائمُها بعرض الصفحة شهوراً ولا خطأَ يُرى.

وتسجيلُ الأعداد بعد تحسينٍ مقصود:

    python -m tests.design_ratchet --update

والملفُّ الناتج يُراجَع في طلب الدمج كأيّ شيفرة: سطرٌ زاد فيه عددٌ هو قرارٌ
يُسأل عنه، لا ضجيج.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from collections import Counter

BASELINE = pathlib.Path("tests/design_ratchet_baseline.json")
CSS_DIR = pathlib.Path("static/css")

#: جذورُ القوالب الحيّة — كما في `test_design_tokens_resolve`.
TEMPLATE_ROOTS = (pathlib.Path("templates"),)

#: كانت قوالبُ الطباعة والبريد خارجَ النطاق بحجّة أنّ WeasyPrint والبريدَ لا يقرآن
#: `var()`. والحجّةُ لا تُلزم بالسداسيّ ولا بـ`style=`: ألوانُهما من `{% brand_color %}`
#: وأنماطُهما أصنافٌ في `<style>` الوثيقة أو أبيها — فدخلت الحارسَ يومَ 2026-09-13
#: بصفرِ مخالفة، ولا قالبَ في المنصّة خارجَه.

_PALETTE = "slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose"
_UTILITY = "bg|text|border(?:-[trblxyse])?|ring|from|via|to|divide|outline|fill|stroke|placeholder|accent|shadow|decoration"


class _InlineStyle:
    """`style="…"` فيه تصريحٌ واحدٌ على الأقلّ ليس متغيّراً مخصَّصاً.

    `style="--progress-w: 40%"` بيانٌ يمرّره القالبُ إلى صنفٍ يقرؤه — والرقمُ
    لا يُعرف قبل التشغيل، فلا مكانَ له في ملفّ الأنماط. أمّا `style="color:red"`
    فتنسيقٌ مكانُه الصنف. والعدُّ الأعمى كان يسوّي بينهما، فيدفع إلى حيلةٍ
    أسوأ من المتغيّر.
    """

    ATTR = re.compile(r'\sstyle="([^"]*)"')
    TAG = re.compile(r"\{%.*?%\}|\{\{.*?\}\}", re.S)

    def findall(self, text: str) -> list[str]:
        found = []
        for value in self.ATTR.findall(text):
            flat = self.TAG.sub("x", value)
            declarations = [d.strip() for d in flat.split(";") if d.strip()]
            if not declarations or any(not d.startswith("--") for d in declarations):
                found.append(value)
        return found


#: المخالفاتُ المعدودة — اسمٌ يُقرأ في رسالة السقوط، ونمطٌ يعدّه.
METRICS: dict[str, tuple[str, re.Pattern | _InlineStyle]] = {
    "inline_style": (
        "تنسيقٌ داخل الوسم (style=)",
        _InlineStyle(),
    ),
    "palette_class": (
        "لونٌ من لوحة Tailwind لا من رموز المنصّة (bg-red-50…)",
        re.compile(
            rf"(?<![\w-])(?:[a-z0-9]+:)*(?:{_UTILITY})-(?:(?:{_PALETTE})-\d{{2,3}}(?:/\d+)?|white|black)(?![\w-])"
        ),
    ),
    "hex_colour": (
        "لونٌ سداسيٌّ ثابت (#dc2626…)",
        re.compile(
            r'(?<![&\w])(?<!href=")#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![\w-])'
        ),
    ),
    "legacy_header": (
        "بنيةٌ مكتوبةٌ باليد (exec-header · card-qatar · card-bar · card-header) بدل مكوّنات ui",
        re.compile(
            r"(?<![\w-])(?:card-header|dash-chart-title|exec-header|card-qatar|card-bar)(?![\w-])"
        ),
    ),
    "hand_kpi": (
        "بطاقةُ رقمٍ مكتوبةٌ باليد (kpi-mini)",
        re.compile(r"(?<![\w-])kpi-mini(?![\w-])"),
    ),
}

CLASS_ATTR_RE = re.compile(r'\sclass="([^"]*)"')
#: ما يُحسب في القالب أو في JS لا يُعرف اسمُه قبل التشغيل — فيُطرح ما يلاصقه.
DYNAMIC_RE = re.compile(r"\{\{.*?\}\}|\$\{.*?\}", re.S)
#: وسومُ المنطق فواصلُ لا أجزاءُ أسماء: `{% if a %}status-red{% endif %}` صنفٌ حرفيٌّ يُفحص.
#: كانت تُطرح مع المتغيّرات، فمرّ `status-green` و`status-red` غيرَ معرَّفين في صفحاتٍ كثيرة
#: وشاراتُها بلا لون.
LOGIC_RE = re.compile(r"\{%.*?%\}", re.S)
CLASS_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_:/.\[\]%-]*")
CSS_CLASS_RE = re.compile(r"\.((?:\\.|[A-Za-z0-9_-])+)")
#: أنماطُ القالب نفسِه: `<style>` أو كتلةُ `extra_styles` في قوالب التقارير المطبوعة.
STYLE_BLOCK_RE = re.compile(
    r"<style[^>]*>(.*?)</style>|\{% block extra_styles %\}(.*?)\{% endblock", re.S
)


#: خطّافُ سلوكٍ لا نمط: صنفٌ تقرؤه JS محدِّداً (`.js-filter-row`) — لا يُعرَّف في CSS
#: عمداً، فتعريفُه يخلط ما يُرى بما يُفعل، وتغييرُ شكله يكسر سلوكاً لا يُرى.
HOOK_PREFIX = "js-"

#: قوالبُ لوحة إدارة Django ترث `admin/…` وتُرسم بأنماط Django نفسها (`admin/css/*.css`
#: في الحزمة) لا بأنماط المنصّة — فهذه الأصنافُ معرَّفةٌ هناك، والحارسُ لا يقرأ حزمَ الطرف الثالث.
ADMIN_EXTENDS_RE = re.compile(r"""\{%\s*extends\s+["']admin/""")
#: وقوالبُ `templates/admin/` التي تنسخ جزءاً من قوالب Django (كـ`app_list.html`) بلا `extends` —
#: أصنافُها كذلك من حزمة Django (`addlink` و`changelink` و`viewlink` و`current-app` و`current-model`
#: و`visually-hidden`) فتُقرأ مثل ما يُقرأ القالبُ الوارثُ لقالبٍ من الإدارة.
ADMIN_CLASSES = frozenset(
    {
        "addlink",
        "aligned",
        "button",
        "cancel-link",
        "changelink",
        "current-app",
        "current-model",
        "deletelink",
        "errornote",
        "module",
        "submit-row",
        "viewlink",
        "visually-hidden",
    }
)
ADMIN_TEMPLATES_DIR = pathlib.Path("templates/admin")
EXTENDS_RE = re.compile(r"""\{%\s*extends\s+["']([^"']+)["']""")


def _template_file(name: str) -> pathlib.Path | None:
    for root in list(TEMPLATE_ROOTS) + sorted(pathlib.Path(".").glob("*/templates")):
        if (root / name).is_file():
            return root / name
    return None


def _local_classes(text: str, seen: frozenset[str] = frozenset()) -> set[str]:
    """أصنافُ `<style>` القالب وآبائه في سلسلة `{% extends %}`.

    الوثائقُ الرسميّة ترث `reports/base_qatar_report.html` الذي يعرّف `sig-block`
    و`report-meta` مرّةً واحدة — فالصنفُ في الابن معرَّفٌ حقّاً، وعدُّه «بلا تعريف»
    كان يدفع إلى نسخ التعريف في كلّ ابن.
    """
    css = "".join("".join(blocks) for blocks in STYLE_BLOCK_RE.findall(text))
    # وأنماطٌ مُدرجةٌ داخل `<style>` (`{% include "schedule/pdf/week_grid_css.html" %}`):
    # ملفُّها CSSٌ خامٌّ بلا وسم، فيُقرأ كلُّه — شبكةٌ واحدةٌ لورقتين لا تُنسخ أنماطُها.
    for included in INCLUDE_RE.findall(css):
        path = _template_file(included)
        if path is not None:
            css += path.read_text(encoding="utf-8")
    names = {re.sub(r"\\(.)", r"\1", m.group(1)) for m in CSS_CLASS_RE.finditer(css)}
    parent = EXTENDS_RE.search(text)
    if parent and parent.group(1) not in seen:
        path = _template_file(parent.group(1))
        if path is not None:
            names |= _local_classes(path.read_text(encoding="utf-8"), seen | {parent.group(1)})
    return names


INCLUDE_RE = re.compile(r"""\{%\s*include\s+["']([^"']+)["']""")


def _includers() -> dict[str, list[pathlib.Path]]:
    """اسمُ القالب ← القوالبُ التي تضمّنه.

    جزءُ الوثيقة (`reports/pdf/_signatures.html`، `wings/pdf/section_sheet.html`)
    لا يرث أحداً: يُضمَّن في وثيقةٍ أنماطُها في رأسها أو في أبيها — فأصنافُه
    معرَّفةٌ هناك.
    """
    found: dict[str, list[pathlib.Path]] = {}
    for root in list(TEMPLATE_ROOTS) + sorted(pathlib.Path(".").glob("*/templates")):
        for path in root.rglob("*.html"):
            for name in INCLUDE_RE.findall(path.read_text(encoding="utf-8")):
                found.setdefault(name, []).append(path)
    return found


def _host_classes(
    name: str, includers: dict[str, list[pathlib.Path]], seen: frozenset[str] = frozenset()
) -> set[str]:
    names: set[str] = set()
    for host in includers.get(name, []):
        host_name = _template_name(host)
        if host_name in seen or host_name == name:
            continue
        names |= _local_classes(host.read_text(encoding="utf-8"))
        names |= _host_classes(host_name, includers, seen | {name})
    return names


def _template_name(path: pathlib.Path) -> str:
    parts = path.as_posix().split("/templates/", 1)
    return parts[1] if len(parts) == 2 else path.as_posix().removeprefix("templates/")


def live_templates():
    roots = list(TEMPLATE_ROOTS) + sorted(pathlib.Path(".").glob("*/templates"))
    for root in roots:
        yield from sorted(root.rglob("*.html"))


#: المكوّناتُ نفسُها هي التي ترسم `exec-header` و`card-qatar` و`card-bar` — فالصفحةُ
#: تكتب `{% page_header %}` و`{% section_card %}` ولا تكتب هذه الأصنافَ بيدها.
COMPONENTS_DIR = pathlib.Path("templates/components")


def measure() -> dict[str, dict[str, int]]:
    """لكلّ مخالفةٍ: القالبُ ← عددُها فيه (ما كان صفراً لا يُكتب)."""
    counts: dict[str, dict[str, int]] = {name: {} for name in METRICS}
    for path in live_templates():
        text = path.read_text(encoding="utf-8")
        for name, (_label, pattern) in METRICS.items():
            if name == "legacy_header" and path.is_relative_to(COMPONENTS_DIR):
                continue
            found = len(pattern.findall(text))
            if found:
                counts[name][path.as_posix()] = found
    return counts


def defined_classes() -> set[str]:
    names = set()
    for sheet in CSS_DIR.rglob("*.css"):
        # مصدرُ Tailwind قبل البناء يذكر الأصنافَ ولا يعرّفها.
        if sheet.name.endswith("_input.css"):
            continue
        for match in CSS_CLASS_RE.finditer(sheet.read_text(encoding="utf-8")):
            names.add(re.sub(r"\\(.)", r"\1", match.group(1)))
    return names


def undefined_classes() -> list[str]:
    """أصنافٌ في القوالب لا يعرّفها أيُّ ملفّ CSS — مرتّبةً بلا تكرار."""
    known = defined_classes()
    includers = _includers()
    missing = set()
    for path in live_templates():
        text = path.read_text(encoding="utf-8")
        # صنفٌ يعرّفه القالبُ أو أحدُ آبائه في `<style>` معرَّف — قوالبُ التقارير تفعل ذلك.
        local = _local_classes(text)
        # وجزءٌ مضمَّنٌ يرى أنماطَ من يضمّنه، ومن يضمّن ذاك (`signatures` ← `section_sheet` ← الوثيقة).
        local |= _host_classes(_template_name(path), includers)
        if ADMIN_EXTENDS_RE.search(text) or path.is_relative_to(ADMIN_TEMPLATES_DIR):
            local |= ADMIN_CLASSES
        for attr in CLASS_ATTR_RE.finditer(text):
            raw = attr.group(1)
            # `kpi-{% if %}green{% endif %}` يلصق الوسمَ باسمٍ فالناتجُ لا يُعرف قبل التشغيل؛
            # وحيث لا لصقَ فالوسمُ فاصلٌ والأسماءُ بين الوسوم حرفيّةٌ تُفحص.
            glued = re.search(r"[\w-]\{%|%\}[\w-]*-\{", raw) and re.search(r"-\{%", raw)
            value = DYNAMIC_RE.sub("\0", LOGIC_RE.sub("\0" if glued else " ", raw))
            for token in value.split():
                if "\0" in token or not CLASS_TOKEN_RE.fullmatch(token):
                    continue
                if token.startswith(HOOK_PREFIX):
                    continue
                if token not in known and token not in local:
                    missing.add(token)
    return sorted(missing)


def snapshot() -> dict:
    return {"counts": measure(), "undefined_classes": undefined_classes()}


def compare(baseline: dict, current: dict) -> tuple[list[str], list[str]]:
    """(ما زاد، ما نقص ولم يُسجَّل) — كلٌّ سطرٌ يُقرأ."""
    worse, stale = [], []
    for name, (label, _pattern) in METRICS.items():
        before = baseline["counts"].get(name, {})
        now = current["counts"].get(name, {})
        for path in sorted(set(before) | set(now)):
            was, is_ = before.get(path, 0), now.get(path, 0)
            if is_ > was:
                worse.append(f"{path}: {label} {was} → {is_}")
            elif is_ < was:
                stale.append(f"{path}: {label} {was} → {is_}")
    listed, found = set(baseline["undefined_classes"]), set(current["undefined_classes"])
    worse += [f"صنفٌ بلا تعريفٍ في CSS: {name}" for name in sorted(found - listed)]
    stale += [f"صنفٌ عُرِّف أو لم يعد مستعمَلاً: {name}" for name in sorted(listed - found)]
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
        print(f"undefined_classes: {len(current['undefined_classes'])}")
        return 0
    worse, stale = compare(json.loads(BASELINE.read_text(encoding="utf-8")), current)
    for line in worse + stale:
        print(line)
    return 1 if worse or stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
