"""[I18N] أداةُ الاختيار بين قائمتين في الإدارة عربيّةٌ كلُّها (OWN-19).

جانغو 5.2 غيّر نصوصَ `SelectFilter2.js` وبقي كتالوجُه العربيّ (`djangojs.po`) على القديمة، فظهرت
«Choose all المجموعات». وتكملتُها في `static/js/admin_i18n.js` (والسببُ مكتوبٌ فيه: لا ‎.po يصل الإنتاج).

فإن رُقّي جانغو فأضاف نصّاً بلا ترجمةٍ عربيّة سقط هذا الحارسُ وسمّاه — لا يظهر إنجليزيّاً صامتاً.
"""

from __future__ import annotations

import pathlib
import re

import django

ADMIN = pathlib.Path(django.__file__).parent / "contrib" / "admin"
SELECT_FILTER = ADMIN / "static" / "admin" / "js" / "SelectFilter2.js"
ARABIC_CATALOGUE = ADMIN / "locale" / "ar" / "LC_MESSAGES" / "djangojs.po"
SUPPLEMENT = pathlib.Path("static/js/admin_i18n.js")

#: `gettext('…')` و`ngettext('…', …)` (المفردُ مفتاحُ الكتالوج) — لا `pgettext` فلا سياقَ في هذه الأداة.
_CALL = re.compile(r"""\b(?:n)?gettext\(\s*(?:'([^']*)'|"((?:[^"\\]|\\.)*)")""")
_QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _widget_strings() -> set[str]:
    text = SELECT_FILTER.read_text(encoding="utf-8")
    return {(a if a else b).replace('\\"', '"') for a, b in _CALL.findall(text)}


def _translated() -> set[str]:
    """ما له ترجمةٌ غيرُ فارغةٍ في كتالوج جانغو العربيّ (بلا سياق)."""
    done = set()
    for block in ARABIC_CATALOGUE.read_text(encoding="utf-8").split("\n\n"):
        if "msgctxt" in block or "msgid" not in block:
            continue
        head, _, tail = block.partition("msgstr")
        msgid = "".join(_QUOTED.findall(head.split("msgid", 1)[1].split("msgid_plural")[0]))
        if msgid and "".join(_QUOTED.findall(tail)):
            done.add(msgid.replace('\\"', '"'))
    return done


def test_the_widget_has_strings_to_check():
    """حارسٌ لا يجد نصّاً ينجح صامتاً — فليُثبت أنّه يقرأ الأداةَ والكتالوج."""
    assert "Choose all %s" in _widget_strings()
    assert "Filter" in _translated()


def test_every_untranslated_widget_string_is_supplied_in_arabic():
    supplement = SUPPLEMENT.read_text(encoding="utf-8")
    missing = sorted(_widget_strings() - _translated())
    unsupplied = [s for s in missing if f"'{s}':" not in supplement]

    assert missing, "لا نصَّ ناقصاً في كتالوج جانغو — فاحذف static/js/admin_i18n.js وحارسَه"
    assert (
        not unsupplied
    ), f"نصوصٌ في SelectFilter2.js بلا ترجمةٍ عربيّة — أضِفها إلى admin_i18n.js: {unsupplied}"


def test_the_supplement_loads_before_the_widget_asks_and_on_every_admin_page():
    base = pathlib.Path("templates/admin/base_site.html").read_text(encoding="utf-8")
    assert "js/admin_i18n.js' %}\" defer" in base
    assert base.index("admin_i18n.js") < base.index("admin_a11y.js")
