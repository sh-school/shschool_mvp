"""مصادرُ دليل الهويّة — يُقرأ ما يعرضه الدليلُ من ملفّه، لا يُنسخ إليه.

كان الدليلُ القديم يكتب ألوانَ العلامة أرقاماً سداسيّةً في القالب، فتباعد عن
`:root` — الذهبيُّ فيه غيرُ `--gold` في المنصّة. وكانت صفحةُ الأيقونات تعرض
ورقةَ Lucide القديمة (`components/sprite.html`، مئةٌ واثنتان رسماً بلا معنى
واحدٍ منها في الكود) لا قاموسَ المعنى الفعليّ الذي تستعمله المنصّة — فصارت
تعرض `core/icons.py` نفسَه: كلُّ مفتاحٍ دلاليٍّ برسمه ومجموعته.

فالدليلُ هنا نافذة: الرموزُ من `:root` في `static/css/custom/`، والأيقوناتُ
من قاموس `core/icons.py`. ويُعاد قراءةُ الألوان متى تغيّر الملفّ (بتاريخ
تعديله)، فلا يُقرأ القرصُ في كلّ طلب ولا يبقى الدليلُ على نسخةٍ قديمة.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache

from core.css_files import find_paths
from core.icons import GROUPS, ICONS

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
#: كتلُ `:root { … }` — ومنها ما في `@media` يعيد تعريفَ رمزٍ قائم فيُطرح بالتكرار.
_ROOT_RE = re.compile(r"(?<![\w.#-]):root\s*\{([^}]*)\}")
_DECL_RE = re.compile(r"--([A-Za-z0-9_-]+)\s*:\s*([^;]+);")
#: قيمةٌ ترسم لوناً — لا ظلٌّ (`0 1px 3px rgba…`) ولا خطٌّ ولا مدّة.
_COLOUR_VALUE_RE = re.compile(r"^(?:#[0-9A-Fa-f]{3,8}|rgba?\(|hsla?\(|color-mix\()")
_ALIAS_RE = re.compile(r"^var\(\s*--([A-Za-z0-9_-]+)\s*\)$")

#: مجموعاتُ اللوحة بالبادئة — والرمزُ الذي لا بادئةَ له هنا يقع في «أخرى».
_GROUPS = (
    ("الهويّة", ("maroon", "gold", "skyline", "palm", "sea")),
    ("النصُّ والأسطح", ("text", "border", "surface", "page-bg", "on-fill", "focus-color")),
    ("الحالات", ("status", "neutral-solid")),
    ("ألوانُ التمييز", ("accent",)),
    ("الرسومُ البيانيّة", ("chart", "ring-track")),
    ("الأدوارُ والوحدات", ("role", "q", "swap")),
)
_OTHER = "أخرى"


def _mtime(path: str | None) -> float:
    try:
        return os.path.getmtime(path) if path else 0.0
    except OSError:
        return 0.0


@lru_cache(maxsize=4)
def _parse_colour_tokens(sheets: tuple[tuple[str, float], ...]) -> tuple[str, ...]:
    """`sheets` = (مسار، وقتُ التعديل) بترتيب التحميل؛ الأوّلُ ظهوراً يحسم قيمةَ الرمز."""
    parts = []
    for path, _mtime in sheets:
        with open(path, encoding="utf-8") as sheet:
            parts.append(sheet.read())
    css = _COMMENT_RE.sub("", "\n".join(parts))
    values: dict[str, str] = {}
    for block in _ROOT_RE.findall(css):
        for name, value in _DECL_RE.findall(block):
            values.setdefault(name, value.strip())

    def is_colour(name: str, seen: frozenset = frozenset()) -> bool:
        value = values.get(name, "")
        if _COLOUR_VALUE_RE.match(value):
            return True
        alias = _ALIAS_RE.match(value)
        if not alias or alias.group(1) in seen:
            return False
        return is_colour(alias.group(1), seen | {name})

    return tuple(name for name in values if is_colour(name))


def _group_of(name: str) -> str:
    for label, prefixes in _GROUPS:
        if any(name == p or name.startswith(p + "-") for p in prefixes):
            return label
    return _OTHER


def colour_token_groups() -> list[dict]:
    """ألوانُ `:root` بأسمائها، مجموعةً بالبادئة وبترتيب ورودها في الملفّ.

    القيمةُ لا تُحمل: الصفحةُ تقرؤها من المتصفّح، فتُرى قيمةُ الوضع الذي فيه القارئ.
    """
    paths = find_paths()
    if not paths:
        return []
    names = _parse_colour_tokens(tuple((path, _mtime(path)) for path in paths))
    order = [label for label, _ in _GROUPS] + [_OTHER]
    grouped: dict[str, list[str]] = {label: [] for label in order}
    for name in names:
        grouped[_group_of(name)].append(name)
    return [{"label": label, "tokens": grouped[label]} for label in order if grouped[label]]


def icon_dictionary_groups() -> list[dict]:
    """مفاتيحُ `core/icons.py` مجموعةً بمجموعتها الدلاليّة، بترتيب الملفّ.

    القيمةُ من المصدر مباشرةً — لا نسخةَ منها تتباعد عنه.
    """
    grouped: dict[str, list[dict]] = {group: [] for group in GROUPS}
    for key, spec in ICONS.items():
        grouped[spec.group].append({"key": key, "label": spec.label})
    return [
        {"group": group, "label": label, "icons": grouped[group]}
        for group, label in GROUPS.items()
        if grouped[group]
    ]
