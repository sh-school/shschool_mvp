"""قراءةُ `custom.css` وحسابُ نسبة التباين — أداةٌ يستعملها `test_contrast_ratios`.

هذه قراءةٌ ساكنةٌ للملفّ، لا متصفّحَ فيها. فما تقيسه هو ما يحكمه الملفّ
وحدَه: قاعدةٌ تُعلن `color` و`background` صمّاءَ معاً، فاللونان معلومان
ولا يحتاجان صفحةً تُرسم.

وما لا تقيسه مقصود: الخلفيّةُ الشفّافةُ (`rgba` أو `color-mix … transparent`)
ما تحتها يقرّره ترتيبُ العناصر في الصفحة لا نصُّ الملفّ — فمحاولةُ تخمينها
تُنتج إنذاراً كاذباً أكثرَ ممّا تُنتج كشفاً. تلك يقيسها فحصٌ في المتصفّح.
والتدرّجاتُ (`linear-gradient`) كذلك: لونان لا لون.
"""

from __future__ import annotations

import re

# ── ١) تفكيكُ الملفّ: التعليقاتُ والسلاسلُ تُنزَع أوّلاً ──────────────


def strip_noise(css: str) -> str:
    out, i, n = [], 0, len(css)
    incom = False
    instr = None
    while i < n:
        c = css[i]
        if incom:
            if css.startswith("*/", i):
                incom = False
                i += 2
                continue
            out.append("\n" if c == "\n" else " ")
            i += 1
            continue
        if instr:
            out.append(c)
            if c == "\\":
                if i + 1 < n:
                    out.append(css[i + 1])
                i += 2
                continue
            if c == instr:
                instr = None
            i += 1
            continue
        if css.startswith("/*", i):
            incom = True
            i += 2
            continue
        if c in "\"'":
            instr = c
            out.append(c)
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def iter_rules(css: str):
    """يُخرِج (المُحدِّد، التصريحات، السياق) لكلّ كتلةٍ ورقيّة.

    السياقُ قائمةُ رؤوسِ الكتل الحاوية (`@layer …`، `@media …`) — بها نعرف
    ما يخصّ الطباعةَ فنتركه، وما يخصّ الشاشة فنقيسه.
    """
    s = strip_noise(css)
    stack: list[str] = []
    buf = ""
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == "{":
            head = " ".join(buf.split())
            buf = ""
            if head.startswith("@"):
                stack.append(head)
                i += 1
                continue
            depth = 1
            j = i + 1
            while j < n and depth:
                if s[j] == "{":
                    depth += 1
                elif s[j] == "}":
                    depth -= 1
                j += 1
            body = s[i + 1 : j - 1]
            if "{" not in body:
                yield head, parse_decls(body), list(stack)
            else:
                for sub in iter_rules(body):
                    yield sub[0], sub[1], list(stack) + sub[2]
            i = j
            continue
        if c == "}":
            if stack:
                stack.pop()
            buf = ""
            i += 1
            continue
        buf += c
        i += 1


def parse_decls(body: str) -> dict[str, str]:
    decls: dict[str, str] = {}
    depth = 0
    cur = ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == ";" and depth == 0:
            _add(decls, cur)
            cur = ""
            continue
        cur += ch
    _add(decls, cur)
    return decls


def _add(decls: dict[str, str], text: str) -> None:
    if ":" not in text:
        return
    name, _, value = text.partition(":")
    name = name.strip().lower()
    if name:
        decls[name] = value.strip()


# ── ٢) الرموز ──────────────────────────────────────────────────────


def token_table(css: str) -> tuple[dict[str, str], dict[str, str]]:
    """رموزُ النهار، ورموزُ الليل (النهارُ ثمّ ما يُبدّله `html.dark`)."""
    light: dict[str, str] = {}
    dark_over: dict[str, str] = {}
    for sel, decls, _ctx in iter_rules(css):
        target = None
        if sel == ":root":
            target = light
        elif sel == "html.dark":
            target = dark_over
        if target is None:
            continue
        for k, v in decls.items():
            if k.startswith("--"):
                target[k] = v
    return light, {**light, **dark_over}


# ── ٣) حلُّ القيمة إلى لون ─────────────────────────────────────────

NAMED = {
    "white": (255, 255, 255, 1.0),
    "black": (0, 0, 0, 1.0),
    "transparent": (0, 0, 0, 0.0),
    "red": (255, 0, 0, 1.0),
    "silver": (192, 192, 192, 1.0),
    "gray": (128, 128, 128, 1.0),
    "grey": (128, 128, 128, 1.0),
}
UNRESOLVABLE = {"inherit", "currentcolor", "initial", "unset", "revert", "none", "auto"}


def resolve(value: str, tokens: dict[str, str], depth: int = 0):
    """لونٌ بأربعة أعداد، أو `None` لما لا يُقاس (تدرّجٌ أو وراثةٌ أو صورة)."""
    if depth > 12 or not value:
        return None
    v = re.sub(r"\s*!\s*important\s*$", "", value.strip(), flags=re.I).strip()
    low = v.lower()
    if low in UNRESOLVABLE:
        return None
    if low in NAMED:
        return NAMED[low]
    if v.startswith("#"):
        return _hex(v)
    if low.startswith("var("):
        name, fallback = _split_var(v)
        if name in tokens:
            got = resolve(tokens[name], tokens, depth + 1)
            if got is not None:
                return got
        return resolve(fallback, tokens, depth + 1) if fallback else None
    if low.startswith(("rgb(", "rgba(")):
        return _rgb_fn(v)
    if low.startswith("color-mix("):
        return _color_mix(v, tokens, depth)
    # تدرّجٌ أو صورةٌ أو اختصارُ `background` بأكثر من قيمة — لا يُقاس
    if low.startswith(("linear-gradient", "radial-gradient", "url(", "conic-gradient")):
        return None
    parts = v.split()
    if len(parts) > 1:
        for p in parts:
            got = resolve(p, tokens, depth + 1)
            if got is not None:
                return got
    return None


def _hex(v: str):
    h = v[1:]
    if len(h) in (3, 4):
        h = "".join(ch * 2 for ch in h)
    if len(h) not in (6, 8):
        return None
    try:
        r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None
    a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
    return (r, g, b, a)


def _split_var(v: str):
    inner = v[v.index("(") + 1 : v.rindex(")")]
    depth = 0
    for i, ch in enumerate(inner):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            return inner[:i].strip(), inner[i + 1 :].strip()
    return inner.strip(), ""


def _rgb_fn(v: str):
    nums = re.findall(r"[-\d.]+%?", v[v.index("(") + 1 : v.rindex(")")])
    if len(nums) < 3:
        return None
    comp = []
    for x in nums[:3]:
        comp.append(round(float(x[:-1]) * 255 / 100) if x.endswith("%") else int(float(x)))
    a = 1.0
    if len(nums) > 3:
        a = float(nums[3][:-1]) / 100 if nums[3].endswith("%") else float(nums[3])
    return (*comp, a)


def _color_mix(v: str, tokens, depth):
    inner = v[v.index("(") + 1 : v.rindex(")")]
    parts, buf, d = [], "", 0
    for ch in inner:
        if ch == "(":
            d += 1
        elif ch == ")":
            d -= 1
        if ch == "," and d == 0:
            parts.append(buf.strip())
            buf = ""
            continue
        buf += ch
    parts.append(buf.strip())
    if len(parts) < 3 or not parts[0].lower().startswith("in "):
        return None
    a = _with_share(parts[1], tokens, depth)
    b = _with_share(parts[2], tokens, depth)
    if a is None or b is None:
        return None
    (ca, pa), (cb, pb) = a, b
    if pa is None and pb is None:
        pa = pb = 0.5
    elif pa is None:
        pa = 1 - pb
    elif pb is None:
        pb = 1 - pa
    total = pa + pb
    if total <= 0:
        return None
    pa, pb = pa / total, pb / total
    return tuple([round(ca[i] * pa + cb[i] * pb) for i in range(3)] + [ca[3] * pa + cb[3] * pb])


def _with_share(text: str, tokens, depth):
    m = re.search(r"\s([\d.]+)%\s*$", " " + text)
    share = float(m.group(1)) / 100 if m else None
    colour_text = text[: m.start()].strip() if m else text
    colour = resolve(colour_text, tokens, depth + 1)
    return None if colour is None else (colour, share)


# ── ٤) النسبة ──────────────────────────────────────────────────────


def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb) -> float:
    r, g, b = rgb[:3]
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def over(fg, bg):
    """تركيبُ لونٍ شفّافٍ فوق خلفيّةٍ صمّاء."""
    a = fg[3]
    if a >= 1:
        return fg[:3]
    return tuple(round(fg[i] * a + bg[i] * (1 - a)) for i in range(3))


def ratio(fg, bg) -> float:
    """نسبةُ WCAG بين لونَين — الشفّافُ يُركَّب على خلفيّته أوّلاً."""
    f = luminance(over(fg, bg))
    b = luminance(bg[:3])
    hi, lo = (f, b) if f > b else (b, f)
    return (hi + 0.05) / (lo + 0.05)
