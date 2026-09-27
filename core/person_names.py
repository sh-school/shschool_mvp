"""اختصارُ اسم الشخص للعرض الضيّق (الجدولُ العامّ) — مقطعان: الاسمُ الأوّل والكنية (قرارُ المالك 2026-09-26).

**للعرض وحدَه.** الاسمُ الكاملُ يبقى في القاعدة والتدقيق والتصدير الرسميّ وعنوانِ الجدول الفرديّ وبطاقةِ الخانة؛ فلا تُكتب هذه
النتيجةُ إلى القاعدة ولا تُستعمل مفتاحاً.

القاعدةُ **وحداتٌ لا كلمات**: كلمةٌ تلتصق بجارتها فيكوّنان اسماً واحداً، وإلّا خرج «عبد الكواري» أو «محمد ثاني» من «عبد الله محمد
الكواري» و«محمد سعد آل ثاني».

* تلتصق بما **بعدها**: عبد، أبو/أبي/بو، أمّ، بن/ابن/بنت، آل، ذو — فـ«عبد الله» و«أبو بكر» و«بن علي» و«آل ثاني» وحدةٌ واحدة.
* تلتصق بما **قبلها**: الله، الدين، أوغلو/أوغلي — فـ«لطف الله» و«سيف الدين» و«يلماز أوغلو» وحدةٌ واحدة.
* **ثلاثُ وحداتٍ فأكثر ⇒ الناتجُ أوّلُ وحدةٍ وآخرُ وحدة**؛ ووحدتان فأقلّ تبقى كما هي.

والتصادمُ (معلّمان بالناتج نفسِه) يُعالَج **على القائمة** في `short_names`: يُضاف حرفُ الوحدة الثانية («محمد ع. الكواري»)، فإن بقي
التصادمُ عُرض الاسمُ الكامل — لا وحدةَ ثالثةٌ كاملةٌ أبداً. (الأسماءُ الحقيقيّة لا تدخل المستودعَ: اختباراتُه على أسماءٍ مصطنعة.)
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence

_TASHKEEL = re.compile("[ً-ٰٟـ]")
_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})

#: تلتصق بما بعدها (بعد التطبيع).
_PREFIX = frozenset({"عبد", "ابو", "ابي", "بو", "ام", "بن", "ابن", "بنت", "ال", "ذو"})
#: تلتصق بما قبلها (بعد التطبيع).
_SUFFIX = frozenset({"الله", "الدين", "اوغلو", "اوغلي"})


def _fold(token: str) -> str:
    """صورةٌ للمطابقة فقط: بلا تشكيلٍ ولا تطويلٍ، وأ/إ/آ→ا وى→ي وة→ه. لا يتغيّر بها الاسمُ المعروض."""
    return _TASHKEEL.sub("", token).translate(_FOLD)


def name_units(full_name: str) -> list[str]:
    """وحداتُ الاسم بعد ضمّ المركّبات (عبد الله، أبو بكر، لطف الله، آل ثاني…) بترتيبها."""
    tokens = full_name.split()
    units: list[str] = []
    i = 0
    while i < len(tokens):
        unit = [tokens[i]]
        while _fold(unit[-1]) in _PREFIX and i + 1 < len(tokens):
            i += 1
            unit.append(tokens[i])
        while i + 1 < len(tokens) and _fold(tokens[i + 1]) in _SUFFIX:
            i += 1
            unit.append(tokens[i])
        units.append(" ".join(unit))
        i += 1
    return units


def short_name(full_name: str) -> str:
    """مقطعان (أوّلٌ + آخر) لمن له ثلاثُ وحداتٍ فأكثر؛ وغيرُه كما هو (بمسافاتٍ موحَّدة)."""
    units = name_units(full_name)
    return f"{units[0]} {units[-1]}" if len(units) >= 3 else " ".join(units)


def short_names(full_names: Sequence[str]) -> list[str]:
    """`short_name` لقائمةٍ بالترتيب نفسِه، مع فضِّ التصادم على القائمة.

    معلّمان مختلفان بالناتج نفسِه يأخذ كلٌّ منهما حرفَ وحدته الثانية («محمد ع. الكواري»)؛ فإن بقي التصادمُ (أو لم تكن له
    وحدةٌ ثانية) عُرض اسمُه الكاملُ. والاسمُ المتطابقُ حرفاً (المعلّمُ نفسُه مرّتين) ليس تصادماً.
    """
    shorts = [short_name(name) for name in full_names]
    groups: dict[str, set[str]] = defaultdict(set)
    for name, short in zip(full_names, shorts, strict=True):
        groups[short].add(" ".join(name.split()))
    clashing = {short for short, names in groups.items() if len(names) > 1}
    if not clashing:
        return shorts

    out: list[str] = []
    for name, short in zip(full_names, shorts, strict=True):
        if short in clashing:
            units = name_units(name)
            short = f"{units[0]} {units[1][0]}. {units[-1]}" if len(units) >= 3 else " ".join(units)
        out.append(short)

    # ما بقي متصادماً بعد الحرف يعود إلى اسمه الكامل
    remaining: dict[str, set[str]] = defaultdict(set)
    for name, short in zip(full_names, out, strict=True):
        remaining[short].add(" ".join(name.split()))
    return [
        " ".join(name.split()) if len(remaining[short]) > 1 else short
        for name, short in zip(full_names, out, strict=True)
    ]
