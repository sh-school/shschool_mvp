#!/usr/bin/env python3
"""طلبٌ وثائقيٌّ فقط؟ ومن يقرأ الوثائقَ من الاختبارات؟ — W-20261002-031.

`classify BASE_SHA` يطبع `docs_only=true|false` لـ`$GITHUB_OUTPUT`. والقاعدةُ بالإيجاب (0105):
`.md` حصراً **تحت docs/ وAAdocs/** فقط؛ أيُّ ملفٍّ آخر (README جذريّ، CLAUDE.md، yml/json/txt، شيءٌ تحت
.github/ أو scripts/) ⇒ false ⇒ تشغيلٌ كاملٌ. وأيُّ خطأٍ أو خروجٍ فارغٍ ⇒ false (الفشلُ آمن).

`readers` يطبع مسارات الاختبارات التي تقرأ docs/ أو AAdocs/ أو ملفَّ md بأيّ شكل (مطابقةٌ واسعةٌ
عمداً: تُخطئ نحو التشغيل الأكثر لا الأقلّ). والقراءةُ الديناميكيّةُ التي لا تُرى بالمطابقة يلتقطها
merge_group (تشغيلٌ كاملٌ دائماً) — فهي «تُلتقط على الأكثر عند الطابور».
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

DOC_ROOTS = ("docs/", "AAdocs/")
# أيُّ استعمالٍ لمجلّدَي الوثائق أو لاسم md: سلسلةٌ نصّيّة، Path(...)/"docs"، glob، iterdir.
_READER = re.compile(r"""AAdocs|\bdocs/|["']docs["']|/\s*["']docs|\.md\b|docs_viewer""")


def is_docs_only(paths: list[str]) -> bool:
    if not paths:
        return False
    return all(p.endswith(".md") and p.startswith(DOC_ROOTS) for p in paths)


def changed_paths(base: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", f"{base}...HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def docs_readers(root: Path) -> list[str]:
    found: list[str] = []
    for path in sorted(root.rglob("test*.py")):
        rel = path.relative_to(root).as_posix()
        if "/tests/" not in f"/{rel}" or "node_modules" in rel:
            continue
        if _READER.search(path.read_text(encoding="utf-8", errors="ignore")):
            found.append(rel)
    return found


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "classify":
        try:
            verdict = is_docs_only(changed_paths(argv[1]))
        except Exception:  # noqa: BLE001 — أيُّ فشلٍ ⇒ تشغيلٌ كامل
            verdict = False
        print(f"docs_only={'true' if verdict else 'false'}")
        return 0
    if argv and argv[0] == "readers":
        print(" ".join(docs_readers(Path(__file__).resolve().parent.parent)))
        return 0
    print("usage: ci_docs_only.py classify BASE_SHA | readers", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

# تجربةُ W-031 (لا يُدمج): تعديلُ كودٍ بسيط لقياس المسار الكامل.
