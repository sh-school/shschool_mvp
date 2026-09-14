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


def test_migrated_templates_are_at_zero_and_stay_there():
    """ما رُحِّل إلى `field` يوم 2026-09-14 صفرٌ في السجلّ — ولا يُسجَّل له عددٌ بعدها."""
    baseline = _baseline()["counts"]
    for name in ("unnamed_field", "label_without_for"):
        assert not baseline.get(name), (
            f"{name}: السجلُّ لا يقبل حقلاً بلا اسمٍ بعد الترحيل — استعمل `{{% field %}}` بدل تسجيله:\n  "
            + json.dumps(baseline.get(name), ensure_ascii=False)
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
        assert (
            ratchet.tables_without_wrap(
                path, '<div class="quality-table-wrap"><table></table></div>'
            )
            == 0
        )
        assert ratchet.tables_without_wrap(path, '<div class="card"><table></table></div>') == 1
        assert (
            ratchet.tables_without_wrap(pathlib.Path("templates/x/pdf/doc.html"), "<table></table>")
            == 0
        )

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
