"""تعليقُ `{# … #}` لا يمتدّ سطرين في Django — وما امتدّ منه يُطبع للمستخدم.

المحلّلُ يغلق التعليقَ عند نهاية السطر، فما بعده نصٌّ عاديّ يظهر في الصفحة.
وقع هذا فعلاً 2026-09-06: تعليقٌ من سطرين في ورقة الطباعة فظهر شرحُ محارف
الاتجاه داخل خانات جدول المعلّم. والملفّ نفسُه كان يحذّر منه في تعليقٍ آخر —
فالتحذيرُ المكتوب لا يكفي، والحارسُ يكفي.

والبديلُ `{% comment %} … {% endcomment %}` لما تعدّى سطراً.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIRS = [ROOT / "templates", *ROOT.glob("*/templates")]


def _unclosed_comment_lines(text: str) -> list[tuple[int, str]]:
    return [
        (number, line.strip())
        for number, line in enumerate(text.splitlines(), 1)
        if line.count("{#") != line.count("#}")
    ]


def _templates() -> list[Path]:
    return sorted({path for directory in TEMPLATE_DIRS for path in directory.rglob("*.html")})


def test_there_are_templates_to_check():
    assert len(_templates()) > 50, "لم يُعثر على القوالب — الحارسُ يمرّ على فراغ"


@pytest.mark.parametrize("template", _templates(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_django_comment_spans_two_lines(template):
    offenders = _unclosed_comment_lines(template.read_text(encoding="utf-8"))

    assert not offenders, (
        f"{template.relative_to(ROOT)}: تعليقٌ لا يُغلق في سطره — "
        f"سيُطبع نصّاً للمستخدم. استعمل {{% comment %}}: {offenders}"
    )
