"""
tests/test_on_fill.py
━━━━━━━━━━━━━━━━━━━━━
ما يُكتب فوق الحشو له اسم — `--on-fill` — ولا ينقلب.

كان «225 لوناً حرفيّاً يكرّر رمزاً» بنداً في جدول الديون. فلمّا قِيس ظهر أنّ
أكبرَ صنفٍ فيه `color: #fff` — خمسٌ وسبعون مرّةً — وأنّها كلَّها أبيضُ على
عنّابيٍّ أو حشوِ حالة: ترويسةُ الجدول، وشارةُ الإشعار، وأزرارُ العلامة.

والأبيضُ يساوي `--surface` نهاراً **بالمصادفة**. واستبدالُه به آليّاً — كما
يقترح عدُّ التطابق — يجعل نصَّ كلّ ترويسةٍ عنّابيّةٍ داكناً في الليل.

فالدَّينُ لم يكن تكراراً بل **دوراً بلا اسم**: من يقرأ `color:#fff` لا يعرف
أهو حرفيٌّ منسيٌّ أم قرار. وهذا الحارسُ يُبقي القرارَ مكتوباً.
"""

import pathlib
import re

from tests.css_contrast import dark_overrides, token_table

CSS_PATH = pathlib.Path("static/css/custom.css")

#: تصريحُ `color` بأبيضَ حرفيّ — لا `background-color` ولا `border-color`.
RAW_WHITE_TEXT = re.compile(
    r"(?<![\w-])color\s*:\s*(#fff\b|#ffffff\b|white\b)",
    re.I,
)


def _css_without_comments() -> str:
    src = CSS_PATH.read_text(encoding="utf-8")
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def test_no_text_is_written_white_by_hand():
    """الأبيضُ فوق الحشو يُكتب `var(--on-fill)` — فيُعرف أنّه مقصود."""
    css = _css_without_comments()
    lines = [
        f"  {n}: {line.strip()[:90]}"
        for n, line in enumerate(css.splitlines(), 1)
        if RAW_WHITE_TEXT.search(line)
    ]
    assert not lines, (
        f"{len(lines)} تصريحَ `color` بأبيضَ حرفيّ — استعمل `var(--on-fill)`:\n"
        + "\n".join(lines[:20])
        + "\n\nوإن لم يكن فوق حشوٍ ثابت فهو نصٌّ عاديٌّ يحتاج `--text-*` الذي ينقلب."
    )


def test_on_fill_stays_white_in_both_themes():
    """لو انقلب `--on-fill` لانطفأ نصُّ كلّ ترويسةٍ عنّابيّةٍ في الليل.

    فالحشوُ تحته (`--maroon`، `--status-danger`…) لا ينقلب، والنصُّ فوقه
    يجب ألّا ينقلب كذلك. وهي قاعدةُ «ترويسةُ الجدول العنّابيّة نصُّها أبيض».
    """
    css = CSS_PATH.read_text(encoding="utf-8")
    light, dark = token_table(css)
    assert "--on-fill" in light, "`--on-fill` غيرُ معرَّفٍ في `:root`"
    assert "--on-fill" not in dark_overrides(
        css
    ), "`--on-fill` صار له نظيرٌ ليليّ — فينطفئ النصُّ فوق الحشو الثابت"
    assert light["--on-fill"].lower() in {"#fff", "#ffffff", "white"}


def test_the_role_is_actually_used():
    """حارسُ الحارس: رمزٌ معرَّفٌ لا يُستعمل لا يحرس شيئاً."""
    uses = len(re.findall(r"var\(--on-fill\)", _css_without_comments()))
    assert uses >= 50, f"`--on-fill` مستعمَلٌ {uses} مرّة — الاستبدالُ لم يقع"
