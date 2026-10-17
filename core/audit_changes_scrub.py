"""
core/audit_changes_scrub.py — مسحُ اسمٍ شخصيٍّ من قيمة JSON لعمود `AuditLog.changes` (W-20261010-053).

قرارُ المالك بصفته DPO (D-342م): عند محو مستخدمٍ يُمسح اسمُه من `changes` أيضاً لا من `object_repr` وحدَه
(W-20261004-002)، فيبقى الصفُّ بكلّ ما عدا الاسم. والمسحُ **في Python على القيمة المفكوكة** (حكم 0104): لا SQL
ولا regex على نصّ JSON، لأنّ الهروبَ (`\\"` و`\\\\`) يُخفي الاسمَ في النصّ ولا يخفيه في القيمة.

القواعد:
- كلُّ `str` في المفاتيح والقيم بأيّ عمقٍ يُستبدل فيه **كلُّ** ظهورٍ للاسم بالمعرّف المقنَّع.
- الأعدادُ والمنطقيّاتُ و`null` لا تُمسّ، والبنيةُ والأنواعُ وترتيبُ المفاتيح كما هي.
- تصادمُ مفتاحين بعد الاستبدال يُحلّ **بلاحقةِ ترقيم** (`_2` ثمّ `_3`…) لا بدمجٍ ولا بحذف.
- عمقٌ فوق `MAX_DEPTH` لا يُمسح ولا يُفشل المحو: يرمي `TooDeepError` فيعدّه المستدعي للإبلاغ اليدويّ.
"""

from __future__ import annotations

from typing import Any

#: أقصى عمقٍ معقولٍ لقيمة `changes`؛ ما فوقه يُبلَّغ يدوياً ولا يُعدَّل.
MAX_DEPTH = 20


class TooDeepError(Exception):
    """قيمةٌ متداخلةٌ فوق `MAX_DEPTH` — لا تُعدَّل."""


def _unique_key(key: str, taken: set[str]) -> str:
    """أوّلُ `key_N` (N ≥ 2) لا يصطدم بمفتاحٍ مأخوذ."""
    n = 2
    while f"{key}_{n}" in taken:
        n += 1
    return f"{key}_{n}"


def _scrub_dict(value: dict[str, Any], name: str, masked: str, depth: int) -> tuple[dict, bool]:
    renamed = {
        key: key.replace(name, masked) for key in value if isinstance(key, str) and name in key
    }
    # مفاتيحٌ لا تتغيّر تحتفظ بأسمائها، فلا يأخذها مفتاحٌ مُعاد تسميتُه ولو جاء قبلها في الترتيب.
    reserved = {key for key in value if key not in renamed}
    out: dict[str, Any] = {}
    changed = bool(renamed)
    for key, item in value.items():
        new_item, item_changed = _scrub(item, name, masked, depth + 1)
        changed = changed or item_changed
        new_key = renamed.get(key, key)
        if key in renamed and (new_key in out or new_key in reserved):
            new_key = _unique_key(new_key, set(out) | reserved | set(renamed.values()))
        out[new_key] = new_item
    return out, changed


def _scrub(value: Any, name: str, masked: str, depth: int) -> tuple[Any, bool]:
    if depth > MAX_DEPTH:
        raise TooDeepError
    if isinstance(value, str):
        return (value.replace(name, masked), True) if name in value else (value, False)
    if isinstance(value, dict):
        return _scrub_dict(value, name, masked, depth)
    if isinstance(value, list):
        out, changed = [], False
        for item in value:
            new_item, item_changed = _scrub(item, name, masked, depth + 1)
            out.append(new_item)
            changed = changed or item_changed
        return out, changed
    return value, False


def scrub_name(value: Any, name: str, masked: str) -> tuple[Any, bool]:
    """يُرجع `(القيمةُ بعد المسح، هل تغيّرت)`؛ ويرمي `TooDeepError` فوق `MAX_DEPTH`."""
    return _scrub(value, name, masked, 0)
