"""
tests/test_export_button_guard.py — زرُّ التصدير الموحَّد (W-20261021-006)

لا زرَّ تصديرٍ مكتوباً بيدٍ في القوالب: يمرّ كلُّه على الوسم `{% export_button %}` بالأسماء الثلاثة المعتمدة.
القوالبُ التي لم تُرحَّل بعدُ مسجَّلةٌ في `tests/export_button_baseline.txt` (سقّاطةٌ تتناقص: قالبٌ رُحِّل يُحذف
منها، وقالبٌ جديدٌ بزرٍّ يدويٍّ يُرفض).
"""

import pathlib
import re

import pytest
from django.template import Context, Template, TemplateSyntaxError

from core.templatetags.ui import EXPORT_KINDS

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = ROOT / "tests" / "export_button_baseline.txt"
HAND_WRITTEN = re.compile(
    r"data-app-file|تصدير (?:PDF|Excel|CSV)|تحميل PDF|تقرير PDF|الاستمارة PDF|>\s*(?:PDF|Excel)\s*<"
)


def _render(src: str) -> str:
    return Template("{% load ui %}" + src).render(Context({}))


def _hand_written() -> set[str]:
    found = set()
    for path in (ROOT / "templates").rglob("*.html"):
        if HAND_WRITTEN.search(path.read_text(encoding="utf-8")):
            found.add(path.relative_to(ROOT).as_posix())
    return found


def test_only_the_three_approved_names_exist():
    assert [label for _icon, label in EXPORT_KINDS.values()] == [
        "تصدير PDF",
        "تصدير Excel",
        "طباعة",
    ]


def test_no_new_hand_written_export_button():
    baseline = {ln for ln in BASELINE.read_text(encoding="utf-8").splitlines() if ln}
    added = _hand_written() - baseline
    assert not added, f"زرُّ تصديرٍ مكتوبٌ بيدٍ — استعمل {{% export_button %}}: {sorted(added)}"


def test_baseline_only_shrinks():
    baseline = {ln for ln in BASELINE.read_text(encoding="utf-8").splitlines() if ln}
    migrated = baseline - _hand_written()
    assert not migrated, f"رُحِّلت — احذفها من export_button_baseline.txt: {sorted(migrated)}"


def test_pdf_button_has_name_icon_and_file_hook():
    html = _render('{% export_button "pdf" "absence_followup_xlsx" %}?q=1{% endexport_button %}')
    assert "data-app-file" in html and "تصدير PDF" in html and '?q=1"' in html
    assert "btn-secondary btn-sm" in html


def test_primary_and_id_are_applied():
    html = _render(
        '{% export_button "xlsx" "absence_followup_xlsx" primary=True id="x1" %}{% endexport_button %}'
    )
    assert "btn-primary btn-sm" in html and 'id="x1"' in html and "تصدير Excel" in html


def test_print_is_a_button_without_a_link():
    html = _render('{% export_button "print" %}{% endexport_button %}')
    assert "<button" in html and "window.print()" in html and "طباعة" in html and "<a " not in html


def test_unknown_kind_is_refused():
    with pytest.raises(TemplateSyntaxError):
        _render('{% export_button "csv" "absence_followup_xlsx" %}{% endexport_button %}')
