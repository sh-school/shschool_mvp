"""[CALENDAR] لا تاريخَ مكتوبٌ حرفياً في المنطق — موضعه البذر وحده.

عضّنا هذا مرّةً في التزامٍ قانونيّ: عتبة الغياب (المادة ٧ من قانون التعليم
الإلزامي ٢٥/٢٠٠١) كانت تُحسب على نافذةٍ مكتوبة:

    year_start = date(2025, 9, 1)
    year_end   = date(2026, 6, 30)

فلمّا بدأ عام ٢٠٢٦-٢٠٢٧ في ٢٣ أغسطس ٢٠٢٦ خلت النافذة من كل حصّة: لا حصص
تُعدّ، ولا غيابَ يُحسب، ولا تنبيهَ ينطلق لأيّ طالب — صامتاً، بلا خطأ ولا سطرٍ
في السجلّ. أُصلح في [#73].

ومسحتُ المنصّة بعده فلم أجد نظيراً: كل تاريخٍ حرفيّ باقٍ يقع في أمر البذر،
وهو موضعه الصحيح — تلك تواريخ تقويم الوزارة نفسها، بياناتٌ لا منطق.

فهذا الحارس يُثبّت النتيجة السالبة: لا يمنع شيئاً قائماً، ويمنع عودته.
"""

import ast
import pathlib

#: الموضع الوحيد الذي تُكتب فيه التواريخ حرفياً — تقويم الوزارة بيانات.
ALLOWED = {"core/management/commands/seed_academic_calendar.py"}

SKIP = (
    "/.venv/",
    # أيُّ بيئةٍ مثبَّتةٍ داخلَ المشروع، لا `.venv` وحدَها: مجلَّدُ `.local/` من
    # بناءٍ سابقٍ حمل `site-packages` لبايثون 3.11 فاشتكى الاختبارُ من تواريخَ
    # في `_pytest/timing.py` و`faker` — مكتباتٌ ليست لنا. وهو مُستثنًى من git
    # فلا يظهر في CI، ويسقط عند كلّ من يبني بيئةً في المجلَّد.
    "/site-packages/",
    "/node_modules/",
    "/.claude/",
    "/.mypy_cache/",
    "/migrations/",
    "/tests/",
    "/_archive/",
    "/scripts/",
)


def _literal_dates():
    for f in sorted(pathlib.Path(".").rglob("*.py")):
        if any(x in "/" + f.as_posix() for x in SKIP):
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            fn = n.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name not in ("date", "datetime"):
                continue
            args = [a for a in n.args if isinstance(a, ast.Constant) and isinstance(a.value, int)]
            if len(args) >= 3 and args[0].value >= 2000:
                yield f.as_posix(), n.lineno, ast.unparse(n)


def test_the_sweep_still_finds_the_seed_data():
    """حارسٌ يمسح لا شيء يمرّ دائماً — والبذر مليءٌ بها عمداً."""
    seeded = [x for x in _literal_dates() if x[0] in ALLOWED]

    assert len(seeded) > 50, "أين تواريخ التقويم؟"


def test_no_literal_date_lives_outside_the_seed_command():
    """تاريخٌ في المنطق يتجاوزه الزمن بصمت — ولا شيء يكشفه."""
    stray = [f"{p}:{line}  {src[:50]}" for p, line, src in _literal_dates() if p not in ALLOWED]

    assert not stray, "تاريخٌ حرفيّ في المنطق:\n" + "\n".join(stray)
