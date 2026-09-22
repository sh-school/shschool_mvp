"""يقسم `static/css/custom.css` إلى ثمانية ملفّاتٍ على حدود الطبقات (ADR-0003).

تشغيلٌ واحدٌ عند التقسيم، لا أداةُ صيانةٍ دائمة: بعد الدمج لا يبقى الأصلُ.
يقرأ النصَّ الأصليّ (افتراضاً من ``git show origin/main:static/css/custom.css``
حتى لا يتأثّر بنسخةٍ قديمةٍ في الشجرة) ويكتب الملفّات، ويثبت أنّ إعادةَ ضمّ
المقاطع بترتيب المصدر تعيد الأصلَ بايتاً ببايت.

    python scripts/split_custom_css.py            # يكتب static/css/custom/*.css
    python scripts/split_custom_css.py --check    # يتحقّق دون كتابة
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "css" / "custom"

#: ترتيبُ الكتل العليا في الأصل ← الملفّ. `modules` أربعُ كتلٍ بحفظ تسلسلها.
LAYOUT = (
    ("@layer reset", "10-foundation.css"),
    ("@layer base", "10-foundation.css"),
    ("@layer tokens", "10-foundation.css"),
    ("@layer layout", "10-foundation.css"),
    ("@layer components", "20-components.css"),
    ("@layer modules#1", "30-modules-1.css"),
    ("@layer themes", "40-themes.css"),
    ("@layer utilities", "50-utilities.css"),
    ("@layer modules#2", "31-modules-2.css"),
    ("@layer modules#3", "32-modules-3.css"),
    ("@layer modules#4", "33-modules-4.css"),
)


def top_level_blocks(src: str) -> list[tuple[str, int, int]]:
    """(رأسُ الكتلة، بدايةُ المقطع، نهايتُه) بمحلِّل أقواسٍ يتجاوز التعليقاتِ والنصوص.

    المقطعُ يبدأ بعد الكتلة السابقة (فتلتصق التعليقاتُ الفاصلةُ بالتي بعدها)
    ويمتدّ إلى قوسها الأخير.
    """
    blocks: list[tuple[str, int, int]] = []
    depth = 0
    i, n = 0, len(src)
    seg_start = 0
    head_from = 0
    in_comment = False
    quote = ""
    while i < n:
        ch = src[i]
        if in_comment:
            if ch == "*" and src[i + 1 : i + 2] == "/":
                in_comment = False
                i += 1
        elif quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch == "/" and src[i + 1 : i + 2] == "*":
            in_comment = True
            i += 1
        elif ch in "\"'":
            quote = ch
        elif ch == "{":
            if depth == 0:
                head = re.sub(r"/\*.*?\*/", "", src[head_from:i], flags=re.S).strip()
                head = head.splitlines()[-1].strip() if head else ""
                blocks.append((head, seg_start, -1))
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                head, start, _ = blocks[-1]
                blocks[-1] = (head, start, i + 1)
                seg_start = head_from = i + 1
        elif ch == ";" and depth == 0:
            head_from = i + 1
        i += 1
    return blocks


def split(src: str) -> dict[str, str]:
    blocks = top_level_blocks(src)
    heads = [h for h, _, _ in blocks]
    if any(not h.startswith("@layer ") for h in heads):
        raise SystemExit(f"كتلةٌ عليا خارج @layer: {[h for h in heads if not h.startswith('@layer ')]}")
    seen: dict[str, int] = {}
    keys = []
    for h in heads:
        seen[h] = seen.get(h, 0) + 1
        keys.append(f"{h}#{seen[h]}" if h == "@layer modules" else h)
    expected = [k for k, _ in LAYOUT]
    if keys != expected:
        raise SystemExit(f"تسلسلُ الكتل تغيّر عمّا في ADR-0003:\n  وُجد   {keys}\n  المتوقَّع {expected}")
    files: dict[str, str] = {}
    for (_, start, end), (_, name) in zip(blocks, LAYOUT, strict=True):
        files[name] = files.get(name, "") + src[start:end]
    # ما بعد آخر كتلةٍ (تعليقٌ ختاميّ أو سطرٌ فارغ) يلتحق بآخر ملفٍّ في المصدر.
    tail = src[blocks[-1][2] :]
    files[LAYOUT[-1][1]] += tail
    return files


def rebuild(src: str, files: dict[str, str]) -> str:
    """يضمّ المقاطعَ بترتيب المصدر لا ترتيب الملفّات — دليلُ ألّا حرفَ ضاع."""
    blocks = top_level_blocks(src)
    per_file_pos = dict.fromkeys(files, 0)
    parts = []
    for (_, start, end), (_, name) in zip(blocks, LAYOUT, strict=True):
        length = end - start
        pos = per_file_pos[name]
        parts.append(files[name][pos : pos + length])
        per_file_pos[name] = pos + length
    parts.append(src[blocks[-1][2] :])
    return "".join(parts)


#: الملفّاتُ الجديدة مستوىً أعمق (`static/css/custom/`)، فكلُّ مسارٍ نسبيٍّ يصعد مستوىً أكثر.
#: بدونه تُحلّ `../fonts/x` إلى `/static/css/fonts/x` (404) وتسقط الخطوطُ صامتةً — قِيس فرقُ الأنماط
#: المحسوبة فلم يرَه، والذي رآه سجلُّ الشبكة. ويسقط معه `collectstatic` في الإنتاج
#: (`ManifestStaticFilesStorage` يرفض ملفّاً مرجعيّاً غيرَ موجود).
URL_REWRITES = (("url('../fonts/", "url('../../fonts/"),)


def rewrite(text: str) -> str:
    for old, new in URL_REWRITES:
        text = text.replace(old, new)
    return text


def normalise(files: dict[str, str]) -> dict[str, str]:
    """فراغُ حدود الملفّ يُنظَّف (سطرٌ فارغٌ في أوّله، ونهايةٌ بسطرٍ واحد) ومسارُ الخطّ يصعد مستوىً — لا غير."""
    return {name: rewrite(text.strip("\n").rstrip()) + "\n" for name, text in files.items()}


def verify(src: str, files: dict[str, str]) -> None:
    """يعيد تحليلَ الملفّات المكتوبة ويقارن كلَّ مقطعٍ بمقطعه في الأصل نصّاً — بلا فراغ الحدود."""
    want: dict[str, list[str]] = {name: [] for name in files}
    for (_, start, end), (_, name) in zip(top_level_blocks(src), LAYOUT, strict=True):
        want[name].append(rewrite(src[start:end].strip()))
    for name, text in files.items():
        got = [text[s:e].strip() for _, s, e in top_level_blocks(text)]
        if got != want[name]:
            raise SystemExit(f"المقاطعُ في {name} لا تطابق الأصلَ نصّاً")


def original() -> str:
    out = subprocess.run(
        ["git", "show", "origin/main:static/css/custom.css"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return out.stdout.decode("utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--from-file", help="بدل git show origin/main")
    args = ap.parse_args()
    src = pathlib.Path(args.from_file).read_text(encoding="utf-8") if args.from_file else original()
    files = split(src)
    if rebuild(src, files) != src:
        sys.exit("فشل التكافؤ: إعادةُ الضمّ لا تطابق الأصلَ بايتاً ببايت")
    files = normalise(files)
    verify(src, files)
    total = sum(len(t.encode("utf-8")) for t in files.values())
    print(f"تكافؤٌ — الأصل {len(src.encode('utf-8')):,} بايت، المقاطع {total:,} (فراغُ الحدود فقط يختلف)")
    for name in sorted(files):
        print(f"  {name:20s} {files[name].count(chr(10)) + 1:5d} سطراً")
    if args.check:
        return
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
