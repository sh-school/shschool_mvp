"""[DESIGN] صنفُ الأداة `text-xs` محذوفٌ من القوالب والأنماط (W-20261010-010).

كان `text-xs` يُلصق في القوالب بلا دور: خليّةُ جدولٍ أو بيانٌ ثانويّ أو عنوانُ
حقل — فيخرج حجمُ الخطّ من الرمز `--text-xs` إلى أداةٍ بحجمٍ حرفيٍّ لا يتبع أيَّ
دورٍ دلاليّ. فاستُبدل في 20 قالباً (57 موضعاً) بالدلاليّ: `cell-sm` للخليّة،
و`ui-meta` للبيان الخافت، و`ui-note` للسطر الصغير، و`btn-sm` للزرّ (وعنوانُ الحقل بلا بديل: يغلبه
`.form-group label` أصلاً فكان الصنفُ ميتاً). والحارسُ يرفض عودتَه في قالبٍ أو سكربت، ويرفض تعريفَه في الأنماط.

الرمزُ `var(--text-xs)` باقٍ ومشروع — يُستثنى بأنّ ما قبل الاسم شرطةٌ.
"""

import pathlib
import re

from tests.css_source import read_css

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: الاسمُ صنفاً: لا تسبقه شرطةٌ (`--text-xs` رمز) ولا يليه حرفٌ أو شرطة (`text-xs-foo`).
CLASS_RE = re.compile(r"(?<![\w-])text-xs(?![\w-])")


def _sources():
    for base, pattern in (("templates", "*.html"), ("static/js", "*.js")):
        yield from (ROOT / base).rglob(pattern)


def test_no_template_or_script_uses_text_xs():
    offenders = []
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            if CLASS_RE.search(line):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{number}")
    assert not offenders, (
        "`text-xs` صنفُ أداةٍ محذوف — استعمل `cell-sm` لخليّة الجدول أو `ui-meta` "
        "للبيان الخافت أو `ui-note` للسطر الصغير أو `btn-sm`:\n" + "\n".join(offenders)
    )


def test_css_does_not_define_text_xs_utility():
    # التعليقاتُ تُحذف أوّلاً: ذكرُ الاسم شرحاً ليس تعريفاً.
    css = re.sub(r"/\*.*?\*/", "", read_css(), flags=re.S)
    assert not re.search(r"\.text-xs\b", css), "تعريفُ `.text-xs` عاد إلى الأنماط"


def test_semantic_replacements_are_defined():
    css = read_css()
    for name in ("cell-sm", "ui-meta"):
        assert re.search(rf"\.{name}\b", css), f"الصنفُ الدلاليّ .{name} غير معرَّف"
