"""مصادرُ دليل الهويّة — يُقرأ ما يعرضه الدليلُ من ملفّه، لا يُنسخ إليه.

كان الدليلُ القديم يكتب ألوانَ العلامة أرقاماً سداسيّةً في القالب، فتباعد عن
`:root` — الذهبيُّ فيه غيرُ `--gold` في المنصّة. وكانت
صفحةُ الأيقونات تنسخ ثمانيةً وأربعين رسماً بيدها، واسمان منها لا وجودَ لهما في
الملفّ (`bar-chart-3`، `graduation-cap`)، والملفُّ فيه مئةٌ واثنتان.

فالدليلُ هنا نافذة: الرموزُ من `:root` في `static/css/custom.css`، والأيقوناتُ من
`components/sprite.html`. ويُعاد القراءةُ متى تغيّر الملفّ (بتاريخ تعديله)، فلا
يُقرأ القرصُ في كلّ طلب ولا يبقى الدليلُ على نسخةٍ قديمة.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache

from django.contrib.staticfiles import finders
from django.template.loader import get_template

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
#: كتلُ `:root { … }` — ومنها ما في `@media` يعيد تعريفَ رمزٍ قائم فيُطرح بالتكرار.
_ROOT_RE = re.compile(r"(?<![\w.#-]):root\s*\{([^}]*)\}")
_DECL_RE = re.compile(r"--([A-Za-z0-9_-]+)\s*:\s*([^;]+);")
#: قيمةٌ ترسم لوناً — لا ظلٌّ (`0 1px 3px rgba…`) ولا خطٌّ ولا مدّة.
_COLOUR_VALUE_RE = re.compile(r"^(?:#[0-9A-Fa-f]{3,8}|rgba?\(|hsla?\(|color-mix\()")
_ALIAS_RE = re.compile(r"^var\(\s*--([A-Za-z0-9_-]+)\s*\)$")
_SYMBOL_RE = re.compile(r'<symbol\s+id="icon-([a-z0-9-]+)"')

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
def _parse_colour_tokens(path: str, _mtime: float) -> tuple[str, ...]:
    with open(path, encoding="utf-8") as sheet:
        css = _COMMENT_RE.sub("", sheet.read())
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
    path = finders.find("css/custom.css")
    if not path:
        return []
    names = _parse_colour_tokens(path, _mtime(path))
    order = [label for label, _ in _GROUPS] + [_OTHER]
    grouped: dict[str, list[str]] = {label: [] for label in order}
    for name in names:
        grouped[_group_of(name)].append(name)
    return [{"label": label, "tokens": grouped[label]} for label in order if grouped[label]]


@lru_cache(maxsize=4)
def _parse_icons(path: str, _mtime: float) -> tuple[str, ...]:
    with open(path, encoding="utf-8") as sprite:
        return tuple(dict.fromkeys(_SYMBOL_RE.findall(sprite.read())))


def sprite_icons() -> tuple[str, ...]:
    """أسماءُ الأيقونات كما تُمرَّر إلى `components/icon.html` — بترتيب الملفّ."""
    path = get_template("components/sprite.html").origin.name
    return _parse_icons(path, _mtime(path))
