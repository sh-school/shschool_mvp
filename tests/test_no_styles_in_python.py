"""[DESIGN] لا لونَ ولا تنسيقَ داخل الوسم مكتوبٌ في بايثون.

كانت صفحاتُ الرفض تُبنى نصّاً في الديكوريتور وملفّات السلوك بعنوانٍ أحمرَ
لا رمزَ له، ورسائلُ البريد بألوانٍ سداسيّةٍ لا تعرفها المنصّة (`#8B0000`
عنّابيٌّ ليس عنّابيَّها)، وتذييلُ الـPDF برماديّاتٍ ثلاثيّةٍ منسوخة. فالتعديلُ
في `custom.css` لا يصلها، والحارسُ الذي يعدّ القوالبَ لا يراها.

فالقاعدة: اللونُ في بايثون يُقرأ من `core/brand.py` — مرآةِ `:root` المحروسة —
والتنسيقُ صنفٌ في قالبٍ أو في كتلة `<style>`، لا سمةُ `style=` في سلسلةٍ نصّيّة.

ما يُفحص: السلاسلُ النصّيّة وحدها (عبر `tokenize`) — فالتعليقاتُ ووسائطُ
الدوالّ مثل `Side(style="thin")` في openpyxl أو `transaction_style="url"` في
Sentry ليست تنسيقاً.
"""

from __future__ import annotations

import io
import os
import pathlib
import re
import tokenize

from tests.test_design_tokens_resolve import SKIP_ROOTS, _root_colours

#: السداسيُّ والثمانيُّ لونٌ أينما وقع في سلسلة.
LONG_HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6})\b")

#: الثلاثيُّ لا يُعدّ لوناً إلّا في موضع قيمة CSS (`color: #888`، `solid #ddd`) —
#: وإلّا فـ«(#222)» رقمُ طلب دمجٍ و«Client #001» رقمُ عميلٍ في وثيقة.
SHORT_HEX_RE = re.compile(r"(?:[:,]\s*|\bsolid\s+)#(?:[0-9a-fA-F]{3,4})\b")

#: سمةُ تنسيقٍ داخل وسم HTML في سلسلة.
STYLE_ATTR_RE = re.compile(r"(?<![\w-])style\s*=\s*\\?[\"']")

#: استثناءاتٌ مسمّاة — لكلٍّ سببُه. ويسقط الفحصُ إن زال سببُ استثناءٍ ولم يُحذف.
ALLOWED = {
    "core/brand.py": "المصدرُ المسموح لقيم الألوان في بايثون (البريد والـPDF حيث لا تصل var())",
    "reports/views.py": "لونُ حالة «ناجح» في الشهادة — يزول بدمج فرع zero_reports",
}


def _string_tokens(source: str):
    """السلاسلُ النصّيّة وأجزاءُ f-string الحرفيّة — بلا تعليقاتٍ ولا شيفرة."""
    kinds = {tokenize.STRING, getattr(tokenize, "FSTRING_MIDDLE", tokenize.STRING)}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in kinds:
            yield token.start[0], token.string


def violations(source: str) -> list[str]:
    """مخالفاتُ مصدرٍ واحد: `سطر: وصف`."""
    found = []
    for line, text in _string_tokens(source):
        for match in LONG_HEX_RE.finditer(text):
            found.append(f"{line}: لونٌ سداسيّ {match.group()}")
        for match in SHORT_HEX_RE.finditer(text):
            found.append(f"{line}: لونٌ ثلاثيّ {match.group().split('#')[-1]!r}")
        if STYLE_ATTR_RE.search(text):
            found.append(f"{line}: تنسيقٌ داخل الوسم (style=)")
    return found


#: ما لا يُنزل إليه أصلاً — `rglob` كان يمشي `.local` و`.venv` كاملَين ثمّ يطرحهما،
#: وعلى ربط Docker من ويندوز يستغرق ذلك دقائق.
PRUNE = SKIP_ROOTS | {".git", ".cache", ".ruff_cache", "staticfiles", "__pycache__", "migrations"}


def _python_modules():
    for root, dirs, files in os.walk("."):
        dirs[:] = sorted(d for d in dirs if d not in PRUNE)
        for name in sorted(files):
            if name.endswith(".py"):
                yield pathlib.Path(root, name).relative_to(".")


def test_no_python_module_writes_a_colour_or_an_inline_style():
    offenders = {}
    for module in _python_modules():
        if module.as_posix() in ALLOWED:
            continue
        found = violations(module.read_text(encoding="utf-8"))
        if found:
            offenders[module.as_posix()] = found
    assert not offenders, (
        "ألوانٌ أو تنسيقاتٌ مكتوبةٌ في بايثون — اللونُ من core.brand، والتنسيقُ صنفٌ في قالب:\n"
        + "\n".join(f"  {path}:{hit}" for path, hits in sorted(offenders.items()) for hit in hits)
    )


def test_every_exception_is_still_needed():
    """استثناءٌ زال سببُه يُحذف — وإلّا صار بابًا مفتوحاً لمخالفةٍ جديدة في الملفّ."""
    stale = [
        path
        for path in ALLOWED
        if path != "core/brand.py"
        and pathlib.Path(path).exists()
        and not violations(pathlib.Path(path).read_text(encoding="utf-8"))
    ]
    stale += [path for path in ALLOWED if not pathlib.Path(path).exists()]
    assert not stale, "استثناءاتٌ لم يعد لها سبب — احذفها من ALLOWED:\n  " + "\n  ".join(stale)


def test_the_scanner_catches_what_it_should_and_nothing_else():
    """الحارسُ نفسُه يُختبر: ما يسقط به وما لا يسقط."""
    caught = violations(
        "a = \"<h2 style='color:red'>x</h2>\"\n"
        'b = f"<p>{x}</p><div style=\\"margin:0\\">"\n'
        'c = "#B91C1C"\n'
        'd = f"""\n.x {{ color: #888; border-top: 1px solid #ddd; }}\n"""\n'
    )
    assert len(caught) == 5, caught

    clean = violations(
        "# تعليقٌ فيه style='x' و#B91C1C\n"
        'side = Side(style="thin", color="D9D9D9")\n'
        'init(transaction_style="url")\n'
        '"""(#222) و Client #001"""\n'
        'e = "<style>.x { color: var(--maroon); }</style>"\n'
    )
    assert clean == [], clean


def _brand_colour_constants():
    from core import brand

    return {
        name: value
        for name, value in vars(brand).items()
        if name.isupper() and isinstance(value, str) and value.startswith("#")
    }


def test_every_brand_colour_is_named_after_its_token():
    """كلُّ لونٍ في `core/brand.py` اسمُه اسمُ رمزه — `STATUS_DANGER_BG` ← `--status-danger-bg`.

    `TOKEN_OF` كان جدولاً يُملأ باليد: ثابتٌ يُضاف ولا يُسجَّل فيه يفلت من
    مقارنة القيمة. فهنا يُشتقّ الرمزُ من الاسم، ويُقارَن بـ`:root` النهاريّ.
    """
    from core import brand

    root = _root_colours()
    problems = []
    for name, value in sorted(_brand_colour_constants().items()):
        token = name.lower().replace("_", "-")
        if brand.TOKEN_OF.get(name) != token:
            problems.append(
                f"{name}: TOKEN_OF يقول {brand.TOKEN_OF.get(name)!r} والاسمُ يقتضي {token!r}"
            )
        if token not in root:
            problems.append(f"{name}: لا رمزَ اسمُه --{token} في :root")
        elif root[token] != value.lower():
            problems.append(f"{name}: بايثون {value} و--{token} {root[token]}")
    for name in sorted(brand.DARK):
        if name not in brand.TOKEN_OF:
            problems.append(f"DARK[{name!r}]: لا ثابتَ نهاريَّ بهذا الاسم")
    assert not problems, "core/brand.py لا يطابق :root:\n  " + "\n  ".join(problems)
