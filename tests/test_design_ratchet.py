"""[DESIGN] سقّاطةُ الهويّة البصريّة — راجع `tests/design_ratchet.py` للسبب والطريقة."""

import json

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
        value = ratchet.DYNAMIC_RE.sub("\0", "status-{{ s }} {% if a %}x{% endif %}")
        assert [t for t in value.split() if "\0" not in t] == []
