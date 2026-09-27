"""[IDENTITY] لا «SchoolOS-SAMM» في تذييلات التصدير (أمرُ المالك 2026-09-27).

كان تذييلُ ثلاثةِ مخرجاتٍ مطبوعةٍ (نماذجُ السلوك PDF، وتقاريرُ `base_qatar_report`، وكشفُ الشعبة في `wings/register.py`) يختم بـ
`· SchoolOS-SAMM © السنة`؛ فأزاله المالكُ من كلّ التصديرات. والحارسُ يقرأ المصدرَ (قوالبَ وشيفرةَ Python) فيرفض عودةَ الاسم إلى مخرجٍ
مطبوع — والهجراتُ والوثائقُ والاختباراتُ خارج النطاق (تذكره في سياق قراراتٍ لا في مخرج).
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
NAME = "SchoolOS-SAMM"
SKIP_DIRS = {
    "tests",
    "migrations",
    "docs",
    "AAdocs",
    "node_modules",
    "staticfiles",
    "static",
    ".git",
    "venv",
    ".venv",
}


def _sources():
    for path in ROOT.rglob("*"):
        if path.suffix not in {".html", ".py", ".txt", ".js"} or not path.is_file():
            continue
        if SKIP_DIRS & set(path.relative_to(ROOT).parts[:-1]):
            continue
        yield path


def test_no_export_footer_carries_the_samm_name():
    offenders = [
        str(path.relative_to(ROOT))
        for path in _sources()
        if NAME in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert (
        not offenders
    ), f"«{NAME}» عاد إلى مخرجٍ مطبوع (قرارُ المالك 2026-09-27: حُذف من التذييلات): {offenders}"


def test_the_guard_scans_a_meaningful_number_of_sources():
    assert sum(1 for _ in _sources()) > 300
