"""[A11Y] سقّاطةُ الوصوليّة — راجع `tests/a11y_ratchet.py` للسبب والطريقة."""

import json
import pathlib

from tests import a11y_ratchet as ratchet
from tests import design_ratchet

UPDATE = "python -m tests.a11y_ratchet --update"


def _baseline():
    return json.loads(ratchet.BASELINE.read_text(encoding="utf-8"))


def test_no_template_adds_what_a_screen_reader_cannot_read():
    worse, _stale = ratchet.compare(_baseline(), ratchet.snapshot())
    assert not worse, (
        "زادت مخالفاتُ الوصوليّة — استعمل `{% field %}` و`{% filter_bar %}` و`{% page_header %}` "
        "و`table-wrap` بدل ما يلي:\n  " + "\n  ".join(worse)
    )


def test_improvements_are_recorded_so_they_cannot_be_spent_again():
    _worse, stale = ratchet.compare(_baseline(), ratchet.snapshot())
    assert not stale, (
        f"نقصت مخالفاتٌ ولم يُسجَّل نقصُها — أحسنت؛ ثبّته بـ `{UPDATE}` وأودع الملفّ:\n  "
        + "\n  ".join(stale)
    )


def test_the_baseline_is_zero_so_no_violation_can_be_recorded_back():
    """الصفرُ بلغناه في 2026-09-14 في المقاييس الخمسة — فالسجلُّ لا يحمل مخالفةً بعدها.

    السقّاطةُ وحدها تمنع الزيادة، لكنّ `--update` يُثبّت أيَّ عددٍ يُكتب: قالبٌ جديدٌ
    بجدولٍ بلا غلاف ثمّ `--update` كان سيمرّ في طلب دمجٍ لا يُقرأ فيه ملفُّ السجلّ.
    فالسجلُّ صفرٌ بالبناء، والمخالفةُ تُصلَح في القالب — `{% field %}` و`{% page_header %}`
    و`{% empty %}` وغلافٌ يمرِّر — لا تُسجَّل.
    """
    baseline = _baseline()["counts"]
    assert set(baseline) == set(ratchet.METRICS), "السجلُّ يذكر المقاييسَ الخمسةَ كلَّها"
    recorded = {name: files for name, files in baseline.items() if files}
    assert not recorded, (
        "سجلُّ الوصوليّة لا يقبل مخالفة — أصلحها في القالب بدل تسجيلها:\n  "
        + json.dumps(recorded, ensure_ascii=False)
    )


class TestTheRatchetItself:
    """الحارسُ يحرس ما يقول إنّه يحرسه — لا يمرّ صامتاً على ما وُضع له."""

    def test_a_new_unnamed_field_is_worse(self):
        before = {"counts": {"unnamed_field": {"a.html": 1}}}
        after = {"counts": {"unnamed_field": {"a.html": 2}}}
        worse, stale = ratchet.compare(before, after)
        assert len(worse) == 1 and not stale

    def test_a_new_template_starts_from_zero(self):
        before = {"counts": {}}
        after = {"counts": {"page_without_h1": {"new.html": 1}}}
        worse, _ = ratchet.compare(before, after)
        assert worse and "new.html" in worse[0]

    def test_an_improvement_must_be_recorded(self):
        before = {"counts": {"label_without_for": {"a.html": 3}}}
        after = {"counts": {"label_without_for": {"a.html": 1}}}
        worse, stale = ratchet.compare(before, after)
        assert not worse and len(stale) == 1

    def test_a_field_is_named_by_label_for_aria_or_wrapping(self):
        assert ratchet.unnamed_fields('<label for="q">بحث</label><input id="q" name="q">') == 0
        assert ratchet.unnamed_fields('<input name="q" aria-label="بحث">') == 0
        assert ratchet.unnamed_fields('<label>بحث <input name="q"></label>') == 0
        assert ratchet.unnamed_fields('<select name="q" title="بحث"></select>') == 0

    def test_an_unnamed_visible_field_is_counted_and_hidden_ones_are_not(self):
        assert ratchet.unnamed_fields('<label>بحث</label><input name="q">') == 1
        assert ratchet.unnamed_fields('<input type="hidden" name="q">') == 0
        assert ratchet.unnamed_fields('<input type="submit" value="حفظ">') == 0
        assert ratchet.unnamed_fields('<textarea name="notes"></textarea>') == 1

    def test_a_label_without_for_is_counted_unless_it_wraps_its_field(self):
        assert ratchet.labels_without_for('<label class="form-label">الاسم</label>') == 1
        assert ratchet.labels_without_for('<label for="x">الاسم</label>') == 0
        assert ratchet.labels_without_for('<label><input type="checkbox"> نعم</label>') == 0

    def test_a_comment_is_not_scanned(self):
        assert ratchet.unnamed_fields('{# <input name="q"> #}') == 0
        assert ratchet.labels_without_for("{% comment %}<label>x</label>{% endcomment %}") == 0

    def test_what_the_field_tag_renders_is_named(self, db):
        """الوسمُ نفسُه يخرج نظيفاً — وإلّا فالطريقُ المحروس هو المخالفة."""
        from django.template import Context, Template

        html = Template(
            '{% load ui %}{% filter_bar "ترشيح" %}{% field "q" "بحث" %}'
            '{% field "g" "الصفّ" type="select" choices=grades %}'
            '{% field "n" "ملاحظات" type="textarea" %}{% field "c" "نعم" type="checkbox" %}{% endfilter_bar %}'
        ).render(Context({"grades": [("7", "السابع")]}))
        assert ratchet.unnamed_fields(html) == 0
        assert ratchet.labels_without_for(html) == 0

    def test_a_page_without_h1_is_counted_unless_a_parent_has_one(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ratchet, "TEMPLATE_ROOTS", (tmp_path,))
        # `_template_file` يحلّ أسماءَ الآباء من جذور design_ratchet — فتُوجَّه هي أيضاً إلى المؤقّت.
        monkeypatch.setattr(design_ratchet, "TEMPLATE_ROOTS", (tmp_path,))
        monkeypatch.chdir(tmp_path)
        (tmp_path / "with_h1.html").write_text("<h1>x</h1>{% block c %}{% endblock %}", "utf-8")
        (tmp_path / "bare.html").write_text("{% block c %}{% endblock %}", "utf-8")
        (tmp_path / "role.html").write_text('{% page_header "x" %}{% endpage_header %}', "utf-8")
        page = pathlib.Path("templates/x/page.html")
        assert ratchet.page_without_h1(page, '{% extends "with_h1.html" %}') == 0
        assert ratchet.page_without_h1(page, '{% extends "bare.html" %}') == 1
        assert (
            ratchet.page_without_h1(
                page, '{% extends "bare.html" %}{% page_header "x" %}{% endpage_header %}'
            )
            == 0
        )
        assert (
            ratchet.page_without_h1(page, '{% extends "bare.html" %}{% include "role.html" %}') == 0
        )
        assert ratchet.page_without_h1(page, '{% extends "admin/base_site.html" %}') == 0
        assert ratchet.page_without_h1(page, "<p>جزئيّة</p>") == 0
        assert (
            ratchet.page_without_h1(page, "<html><body><p>وثيقةٌ بلا عنوان</p></body></html>") == 1
        )
        assert ratchet.page_without_h1(page, "<html>{% block content %}{% endblock %}</html>") == 0
        assert (
            ratchet.page_without_h1(
                pathlib.Path("templates/email/x.html"), '{% extends "bare.html" %}'
            )
            == 0
        )

    def test_a_table_outside_a_scroll_wrapper_is_counted(self):
        path = pathlib.Path("templates/x/list.html")
        assert (
            ratchet.tables_without_wrap(path, '<div class="table-wrap"><table></table></div>') == 0
        )
        assert ratchet.tables_without_wrap(path, '<div class="card"><table></table></div>') == 1
        assert (
            ratchet.tables_without_wrap(pathlib.Path("templates/x/pdf/doc.html"), "<table></table>")
            == 0
        )

    def test_the_wrapper_is_known_by_its_css_not_its_name(self):
        """`quality-table-wrap` يقصّ (`overflow: hidden`) و`quality-table-scroll` يمرِّر — CSS يقول."""
        path = pathlib.Path("templates/x/list.html")
        known = ratchet.scroll_classes()
        assert {
            "table-wrap-scroll",
            "per-grid-wrap",
            "asg-guard-scroll",
            "quality-table-scroll",
        } <= known
        assert "quality-table-wrap" not in known
        assert (
            ratchet.tables_without_wrap(
                path, '<div class="quality-table-scroll"><table></table></div>'
            )
            == 0
        )
        assert (
            ratchet.tables_without_wrap(
                path, '<div class="quality-table-wrap"><table></table></div>'
            )
            == 1
        )

    def test_scrolling_classes_are_read_from_the_last_compound_of_a_scrolling_rule(self):
        css = """
        /* .commented { overflow: auto } */
        .card .grid-scroll { overflow-x: auto; }
        @media (max-width: 640px) { .mobile-only { overflow: scroll } }
        .clips { overflow: hidden; }
        .wrap:has(> .inner) { overflow-x: auto; }
        a, .also-scrolls { overflow-y: auto; overflow: auto }
        """
        assert ratchet._scrolling_classes(css) == {
            "grid-scroll",
            "mobile-only",
            "wrap",
            "also-scrolls",
        }

    def test_the_wrapper_must_be_the_direct_parent_not_the_page_shell(self):
        """`exec-dash` يمرِّر لوحةَ الهاتف كلَّها — ولا يُغني الجدولَ عن غلافه."""
        path = pathlib.Path("templates/x/list.html")
        assert "exec-dash" in ratchet.scroll_classes()
        assert (
            ratchet.tables_without_wrap(
                path, '<div class="exec-dash"><section><table></table></section></div>'
            )
            == 1
        )
        assert (
            ratchet.tables_without_wrap(
                path, '<div class="exec-dash"><div class="table-wrap"><table></table></div></div>'
            )
            == 0
        )

    def test_a_template_may_declare_its_own_scrolling_wrapper_in_style(self):
        path = pathlib.Path("templates/x/list.html")
        text = '<style>.mine { overflow-x: auto }</style><div class="mine"><table></table></div>'
        assert ratchet.tables_without_wrap(path, text) == 0

    def test_a_document_that_owns_its_page_is_paper(self):
        """`data-pdf-own-page` وأساسُ الطباعة نفسُه خارج مقياس الغلاف — الجدولُ على قدر الورقة."""
        text = "<html><body data-pdf-own-page><table></table></body></html>"
        assert ratchet.tables_without_wrap(pathlib.Path("templates/x/sheet.html"), text) == 0
        base = pathlib.Path("templates/reports/base_qatar_report.html")
        assert ratchet._is_print(base, base.read_text(encoding="utf-8"))
        assert not ratchet._is_print(pathlib.Path("templates/x/list.html"), "<table></table>")

    def test_a_loop_without_empty_is_counted_only_at_the_top_level(self):
        assert (
            ratchet.loops_without_empty(
                "{% for r in rows %}<tr>{% for c in r %}<td>{% endfor %}</tr>{% endfor %}"
            )
            == 1
        )
        assert (
            ratchet.loops_without_empty("{% for r in rows %}<tr>{% empty %}<tr>لا شيء{% endfor %}")
            == 0
        )
        assert (
            ratchet.loops_without_empty("<select>{% for v in vals %}<option>{% endfor %}</select>")
            == 0
        )
        assert (
            ratchet.loops_without_empty('{% for r in rows %}x{% endfor %}{% empty_state "لا" %}')
            == 0
        )

    def test_choices_and_inline_chips_are_not_lists_but_delegated_rows_are(self):
        radios = '{% for v, l in levels %}<label><input type="radio" name="l"> {{ l }}</label>{% endfor %}'
        assert ratchet.loops_without_empty(radios) == 0
        chips = '{% for s in sides %}<span class="chip">{% include "components/icon.html" %} {{ s }}</span>{% endfor %}'
        assert ratchet.loops_without_empty(chips) == 0
        heads = "<tr>{% for p in periods %}<th>{{ p }}</th>{% endfor %}</tr>"
        assert ratchet.loops_without_empty(heads) == 0
        rows = '{% for s in students %}{% include "x/row.html" with s=s only %}{% endfor %}'
        assert ratchet.loops_without_empty(rows) == 1
        cards = '{% for s in students %}<a class="chip">{{ s }}</a>{% endfor %}'
        assert ratchet.loops_without_empty(cards) == 1

    def test_components_and_paper_partials_are_outside_the_empty_state_metric(self):
        includers = ratchet._includers()
        assert not ratchet._is_partial(
            pathlib.Path("templates/components/skeleton.html"),
            "{% for i in x %}<div>{% endfor %}",
            includers,
        )
        assert not ratchet._is_partial(
            pathlib.Path("templates/wings/pdf/section_sheet.html"),
            "{% for r in rows %}<tr>{% endfor %}",
            includers,
        )
        assert ratchet._is_partial(
            pathlib.Path("templates/wings/partials/record_panel.html"),
            "{% for r in rows %}<tr>{% endfor %}",
            includers,
        )

    def test_a_manufactured_table_and_list_and_page_defect_fail_the_ratchet(
        self, tmp_path, monkeypatch
    ):
        """عطبٌ مصنوع لكلٍّ من المقاييس الثلاثة الباقية — يسقط، ثمّ يُصلَح بالطريق المحروس فيمرّ."""
        monkeypatch.setattr(ratchet, "TEMPLATE_ROOTS", (tmp_path,))
        monkeypatch.setattr(design_ratchet, "TEMPLATE_ROOTS", (tmp_path,))
        monkeypatch.chdir(tmp_path)
        (tmp_path / "bare.html").write_text("{% block content %}{% endblock %}", "utf-8")
        page = tmp_path / "list.html"
        page.write_text('{% extends "bare.html" %}<div class="card"><table></table></div>', "utf-8")
        partial = tmp_path / "partials" / "rows.html"
        partial.parent.mkdir()
        partial.write_text("{% for r in rows %}<tr><td>{{ r }}</td></tr>{% endfor %}", "utf-8")
        worse, _ = ratchet.compare({"counts": {}}, ratchet.snapshot())
        assert any("list.html" in line and "بلا <h1>" in line for line in worse)
        assert any("list.html" in line and "غلافِ تمرير" in line for line in worse)
        assert any("rows.html" in line and "حالةِ فراغ" in line for line in worse)
        page.write_text(
            '{% extends "bare.html" %}{% page_header "x" %}{% endpage_header %}'
            '<div class="table-wrap"><table></table></div>',
            "utf-8",
        )
        partial.write_text(
            '{% for r in rows %}<tr><td>{{ r }}</td></tr>{% empty %}<tr><td>{% empty_state "لا" %}</td></tr>{% endfor %}',
            "utf-8",
        )
        worse, _ = ratchet.compare({"counts": {}}, ratchet.snapshot())
        assert worse == []

    def test_a_manufactured_defect_in_a_new_template_fails_the_ratchet(self, tmp_path, monkeypatch):
        """عطبٌ مصنوع: قالبٌ جديدٌ بحقلٍ بلا اسم — يسقط، ثمّ يُصلَح بـ`field` فيمرّ."""
        monkeypatch.setattr(ratchet, "TEMPLATE_ROOTS", (tmp_path,))
        # `_template_file` يحلّ أسماءَ الآباء من جذور design_ratchet — فتُوجَّه هي أيضاً إلى المؤقّت.
        monkeypatch.setattr(design_ratchet, "TEMPLATE_ROOTS", (tmp_path,))
        monkeypatch.chdir(tmp_path)
        page = tmp_path / "new_page.html"
        page.write_text('<label class="form-label">بحث</label><input name="q">', "utf-8")
        worse, _ = ratchet.compare({"counts": {}}, ratchet.snapshot())
        assert any("new_page.html" in line and "حقلٌ بلا اسم" in line for line in worse)
        assert any("new_page.html" in line and "بلا for" in line for line in worse)
        page.write_text('{% load ui %}{% field "q" "بحث" %}', "utf-8")
        worse, _ = ratchet.compare({"counts": {}}, ratchet.snapshot())
        assert worse == []
