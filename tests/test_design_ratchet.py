"""[DESIGN] سقّاطةُ الهويّة البصريّة — راجع `tests/design_ratchet.py` للسبب والطريقة."""

import json
import pathlib

from tests import design_ratchet as ratchet

UPDATE = "python -m tests.design_ratchet --update"


def _baseline():
    return json.loads(ratchet.BASELINE.read_text(encoding="utf-8"))


def test_no_template_adds_what_the_visual_identity_forbids():
    worse, _stale = ratchet.compare(_baseline(), ratchet.snapshot())
    assert not worse, (
        "زادت مخالفاتُ الهويّة البصريّة — استعمل رموزَ المنصّة وأصنافَها بدل ما يلي:\n  "
        + "\n  ".join(worse)
    )


def test_improvements_are_recorded_so_they_cannot_be_spent_again():
    _worse, stale = ratchet.compare(_baseline(), ratchet.snapshot())
    assert not stale, (
        f"نقصت مخالفاتٌ ولم يُسجَّل نقصُها — أحسنت؛ ثبّته بـ `{UPDATE}` وأودع الملفّ:\n  "
        + "\n  ".join(stale)
    )


def test_the_baseline_is_zero_so_no_violation_can_be_recorded_back():
    """الصفرُ بلغناه في 2026-09-13 — فالسجلُّ لا يحمل مخالفةً بعدها.

    السقّاطةُ وحدها تمنع الزيادة، لكنّ `--update` يُثبّت أيَّ عددٍ يُكتب: قالبٌ جديدٌ
    بـ`style=` ثمّ `--update` كان سيمرّ في طلب دمجٍ لا يُقرأ فيه ملفُّ السجلّ. فالسجلُّ
    صفرٌ بالبناء، والمخالفةُ تُصلَح في القالب لا تُسجَّل.
    """
    baseline = _baseline()
    recorded = {name: files for name, files in baseline["counts"].items() if files}
    assert not recorded and not baseline["undefined_classes"], (
        "سجلُّ الهويّة البصريّة لا يقبل مخالفة — أصلحها في القالب بدل تسجيلها:\n  "
        + json.dumps(recorded, ensure_ascii=False)
        + "\n  "
        + ", ".join(baseline["undefined_classes"])
    )


class TestTheRatchetItself:
    """الحارسُ يحرس ما يقول إنّه يحرسه — لا يمرّ صامتاً على ما وُضع له."""

    def test_a_new_inline_style_is_worse(self):
        before = {"counts": {"inline_style": {"a.html": 1}}, "undefined_classes": []}
        after = {"counts": {"inline_style": {"a.html": 2}}, "undefined_classes": []}
        worse, stale = ratchet.compare(before, after)
        assert len(worse) == 1 and not stale

    def test_a_new_template_starts_from_zero(self):
        before = {"counts": {}, "undefined_classes": []}
        after = {"counts": {"hex_colour": {"new.html": 1}}, "undefined_classes": []}
        worse, _ = ratchet.compare(before, after)
        assert worse and "new.html" in worse[0]

    def test_an_improvement_must_be_recorded(self):
        before = {"counts": {"palette_class": {"a.html": 3}}, "undefined_classes": []}
        after = {"counts": {"palette_class": {"a.html": 1}}, "undefined_classes": []}
        worse, stale = ratchet.compare(before, after)
        assert not worse and len(stale) == 1

    def test_an_undefined_class_is_caught(self):
        before = {"counts": {}, "undefined_classes": []}
        after = {"counts": {}, "undefined_classes": ["charts-grid-3"]}
        worse, _ = ratchet.compare(before, after)
        assert worse == ["صنفٌ بلا تعريفٍ في CSS: charts-grid-3"]

    def test_the_patterns_count_what_they_name(self):
        sample = (
            '<div class="bg-red-50 hover:text-blue-600 kpi-mini card-header" '
            'style="color:#dc2626"><a href="#top">x</a></div>'
        )
        found = {name: len(p.findall(sample)) for name, (_l, p) in ratchet.METRICS.items()}
        assert found == {
            "inline_style": 1,
            "palette_class": 2,
            "hex_colour": 1,
            "legacy_header": 1,
            "hand_kpi": 1,
        }

    def test_a_style_that_only_passes_a_custom_property_is_data_not_styling(self):
        count = ratchet.METRICS["inline_style"][1].findall
        assert count('<div style="--progress-w:{{ pct }}%">') == []
        assert count('<div style="--a: 2; --b: 3.5">') == []
        assert len(count('<div style="--a: 2; margin-top: 4px">')) == 1

    def test_dynamic_class_fragments_are_not_reported(self):
        value = ratchet.DYNAMIC_RE.sub("\0", "status-{{ s }}")
        assert [t for t in value.split() if "\0" not in t] == []

    def test_a_class_inside_a_condition_is_still_checked(self):
        """`{% if a %}status-red{% endif %}` كان يُطرح مع الوسم، فمرّ صنفٌ غيرُ معرَّف."""
        source = "{% if a %}status-red{% else %}status-green{% endif %}"
        value = ratchet.DYNAMIC_RE.sub("\0", ratchet.LOGIC_RE.sub(" ", source))
        assert value.split() == ["status-red", "status-green"]

    def test_a_class_defined_by_the_parent_template_is_defined(self):
        """الوثيقةُ ترث `base_qatar_report.html` فتعرف `sig-block` من أبيها."""
        child = '{% extends "reports/base_qatar_report.html" %}'
        assert "sig-block" in ratchet._local_classes(child)

    def test_a_self_extending_chain_does_not_loop(self, tmp_path, monkeypatch):
        (tmp_path / "loop.html").write_text(
            '{% extends "loop.html" %}<style>.x{}</style>', encoding="utf-8"
        )
        monkeypatch.setattr(ratchet, "TEMPLATE_ROOTS", (tmp_path,))
        assert ratchet._local_classes('{% extends "loop.html" %}') == {"x"}

    def test_admin_classes_count_only_under_the_django_admin(self):
        assert ratchet.ADMIN_EXTENDS_RE.search('{% extends "admin/base_site.html" %}')
        assert not ratchet.ADMIN_EXTENDS_RE.search('{% extends "base/base.html" %}')

    def test_an_included_fragment_sees_the_styles_of_the_document_that_includes_it(self):
        """`wings/pdf/signatures.html` ← `section_sheet.html` ← `register_pdf.html` ← أبوها."""
        includers = ratchet._includers()
        assert "sig-block" in ratchet._host_classes("wings/pdf/signatures.html", includers)

    def test_print_and_email_templates_are_inside_the_guard(self):
        names = {p.as_posix() for p in ratchet.live_templates()}
        assert "templates/reports/base_qatar_report.html" in names
        assert any("/email/" in n for n in names)

    def test_hand_written_structure_counts_outside_the_component_library(self):
        """الصفحةُ تكتب `{% page_header %}`؛ والمكوّنُ وحده يرسم `exec-header` و`card-qatar`."""
        pattern = ratchet.METRICS["legacy_header"][1]
        sample = '<div class="exec-header"><section class="card-qatar"><header class="card-bar">'
        assert len(pattern.findall(sample)) == 3
        component = pathlib.Path("templates/components/ui/page_header.html")
        assert component.is_relative_to(ratchet.COMPONENTS_DIR)
        assert "templates/components/ui/page_header.html" not in ratchet.measure()["legacy_header"]
