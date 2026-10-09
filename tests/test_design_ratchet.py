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


#: الخمسةُ التي بلغت الصفرَ — والسبعةُ الجديدةُ (W-20261009-009) تسجّل الحالَ بأعدادٍ غير صفريّة.
ZERO_METRICS = ("inline_style", "palette_class", "hex_colour", "legacy_header", "hand_kpi")
SEVEN = (
    "style_block",
    "max_w",
    "important",
    "button_no_type",
    "transition_all",
    "physical_side",
    "inline_script",
)


def test_the_baseline_is_zero_so_no_violation_can_be_recorded_back():
    """الصفرُ بلغناه في 2026-09-13 — فالسجلُّ لا يحمل مخالفةً بعدها.

    السقّاطةُ وحدها تمنع الزيادة، لكنّ `--update` يُثبّت أيَّ عددٍ يُكتب: قالبٌ جديدٌ
    بـ`style=` ثمّ `--update` كان سيمرّ في طلب دمجٍ لا يُقرأ فيه ملفُّ السجلّ. فالسجلُّ
    صفرٌ بالبناء، والمخالفةُ تُصلَح في القالب لا تُسجَّل.
    """
    baseline = _baseline()
    recorded = {
        name: files for name, files in baseline["counts"].items() if files and name in ZERO_METRICS
    }
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
            "style_block": 0,
            "max_w": 0,
            "button_no_type": 0,
            "inline_script": 0,
            "important": 0,
            "transition_all": 0,
            "physical_side": 0,
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


class TestTheSevenGaps:
    """السبعةُ تعدّ ما تسمّيه وتسقط بمخالفةٍ مُدخَلة (W-20261009-009)."""

    def _count(self, name, text):
        return len(ratchet.METRICS[name][1].findall(text))

    def test_all_seven_are_registered_and_in_the_baseline(self):
        counts = _baseline()["counts"]
        for name in SEVEN:
            assert name in ratchet.METRICS and name in counts

    def test_the_five_original_metrics_are_still_zero(self):
        counts = ratchet.measure()
        assert all(not counts[name] for name in ZERO_METRICS)

    def test_template_metrics(self):
        assert self._count("style_block", "<style>a{}</style><style media=print>") == 2
        assert self._count("max_w", '<div class="max-w-md md:max-w-lg max-width">') == 2
        assert self._count("button_no_type", '<button class="a">x</button>') == 1
        assert self._count("button_no_type", '<button type="button">x</button>') == 0
        assert self._count("button_no_type", '<button {% if a %}type="submit"{% endif %}>x') == 0
        assert self._count("button_no_type", "<button {% if a > 1 %}disabled{% endif %}>x") == 1
        assert self._count("inline_script", "<script>alert(1)</script>") == 1
        assert self._count("inline_script", '<script src="a.js" defer></script>') == 0
        assert (
            self._count("inline_script", '<script type="application/json" id="d">{}</script>') == 0
        )

    def test_css_metrics(self):
        assert self._count("important", "a{color:red !important}/* !important */") == 1
        allowed = "@media print{a{color:red!important}@media (x){b{c:d}}}"
        assert self._count("important", allowed + "a{b:c!important}") == 1
        reduced = "@media (prefers-reduced-motion: reduce){*{transition:none!important}}"
        assert self._count("important", reduced) == 0
        assert (
            self._count("transition_all", "a{transition: all .2s}b{transition-property:all}") == 2
        )
        assert (
            self._count("transition_all", "a{transition: all-items .2s;transition:opacity .2s}")
            == 0
        )
        physical = "a{margin-left:1px;padding-right:2px;text-align:left;float:right;left:0}"
        assert self._count("physical_side", physical) == 5
        logical = "a{margin-inline-start:1px;text-align:start;inset-inline-end:0;--left:1}"
        assert self._count("physical_side", logical) == 0

    def test_a_new_violation_in_a_temp_template_or_sheet_fails(self, tmp_path, monkeypatch):
        tpl, css = tmp_path / "templates", tmp_path / "custom"
        tpl.mkdir()
        css.mkdir()
        (tpl / "new.html").write_text("<button>x</button><script>1</script>", encoding="utf-8")
        (css / "x.css").write_text("a{transition:all 1s;margin-left:1px}", encoding="utf-8")
        monkeypatch.setattr(ratchet, "TEMPLATE_ROOTS", (tpl,))
        monkeypatch.setattr(ratchet, "CUSTOM_CSS_DIR", css)
        monkeypatch.setattr(ratchet, "live_templates", lambda: sorted(tpl.rglob("*.html")))
        current = {"counts": ratchet.measure(), "undefined_classes": []}
        worse, _ = ratchet.compare({"counts": {}, "undefined_classes": []}, current)
        assert any("new.html" in line for line in worse)
        assert any("x.css" in line for line in worse)
        assert len(worse) == 4

    def test_a_decrease_must_be_recorded_for_a_css_file(self):
        before = {"counts": {"important": {"static/css/custom/a.css": 3}}, "undefined_classes": []}
        after = {"counts": {"important": {"static/css/custom/a.css": 2}}, "undefined_classes": []}
        worse, stale = ratchet.compare(before, after)
        assert not worse and len(stale) == 1
