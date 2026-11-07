"""
tests/test_class_grid_mobile.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
جدولُ الشعبة على الهاتف (W-20261012-028): الرصدُ من الجوّال كان «صعباً جداً» — سبعةُ أعمدةٍ في الأفقيّ وأربعةُ أزرارٍ في كلّ صفّ.

حارسٌ نصّيٌّ لا يُشغّل متصفّحاً: يثبّت أنّ **عتبةَ الوضع واحدةٌ** (في CSS، يقرؤها JS) فلا يختلف العرضُ عن السلوك، وأنّ بنيةَ
القالب تحمل الورقةَ السفليّةَ وشريطَ المفاتيح. والقياسُ المرئيُّ (8 طلابٍ على 375×667، أهدافُ اللمس ≥44px) في المتصفّح لا هنا.
"""

import re

from tests.css_source import ROOT, read_css

JS = (ROOT / "static" / "js" / "class-grid.js").read_text(encoding="utf-8")
TEMPLATE = (ROOT / "templates" / "teacher" / "class_grid.html").read_text(encoding="utf-8")
CSS = read_css()

#: عتبةُ وضع الهاتف: الهاتفُ العموديُّ ≤640px، والأفقيُّ بمؤشّرٍ لمسيٍّ حتى 900px.
NARROW_QUERY = "@media (max-width: 640px), (pointer: coarse) and (max-width: 900px)"


def test_the_phone_mode_threshold_is_declared_once_in_css():
    assert CSS.count(NARROW_QUERY) == 1


def test_the_script_reads_the_threshold_from_css_and_declares_none_of_its_own():
    # الاستعلامُ في CSS وحدَه؛ JS يقرأ `--cg-narrow` المحسوبَ فلا نسخةَ ثانيةً للرقم 640 تنحرف عن الأولى.
    assert "--cg-narrow" in JS
    assert "matchMedia" not in JS
    assert not re.search(r"max-width|\b640\b|\b900\b", JS)


def test_the_flag_defaults_off_and_is_set_on_inside_the_single_query():
    assert re.search(r"\[data-class-grid\]\s*\{\s*--cg-narrow:\s*0;", CSS)
    block = CSS[CSS.index(NARROW_QUERY) :]
    assert re.search(r"\[data-class-grid\]\s*\{[^}]*--cg-narrow:\s*1;", block)


def test_each_row_carries_one_actions_sheet_and_one_open_button():
    assert TEMPLATE.count("data-acts-open=") == 1
    assert TEMPLATE.count('<dialog class="cg-sheet"') == 1
    # الدورُ «مجموعةٌ» على الحاسوب حيث تُرسم الورقةُ مضمَّنةً؛ و«حوارٌ» لا يُعيَّن إلا عند الفتح (JS).
    assert 'role="group" data-acts-sheet=' in TEMPLATE
    assert "setAttribute('role', 'dialog')" in JS


def test_the_actions_stay_inline_on_desktop_so_the_layout_is_unchanged():
    assert re.search(r"\.cg-sheet:not\(\[open\]\)\s*\{\s*display:\s*contents;", CSS)
    assert re.search(
        r"\.cg-acts__open,\s*\.cg-sheet__head,\s*\.cg-keytop,\s*\.cg-savebar\s*\{\s*display:\s*none;",
        CSS,
    )


def test_the_phone_keys_have_full_labels_not_symbols():
    for label in ("الكلُّ حاضر", "الكلُّ غائب", "حفظ ح"):
        assert label in TEMPLATE
    bar = TEMPLATE[TEMPLATE.index("data-keytop") : TEMPLATE.index("data-grid-status")]
    assert "✓" not in bar and "✗" not in bar


def test_phone_keys_are_above_the_table_and_save_is_below_it():
    # W-20261108-001: المفاتيح أعلى الصفحة والحفظ أسفلها، ولا شريطَ cg-keybar القديم.
    assert "cg-keybar" not in TEMPLATE and "cg-keybar" not in CSS
    assert (
        TEMPLATE.index("data-keytop") < TEMPLATE.index("cg-table") < TEMPLATE.index("data-savebar")
    )


def test_desktop_summary_row_is_sticky_and_save_stays_in_the_sticky_footer():
    head = TEMPLATE[TEMPLATE.index("<thead>") : TEMPLATE.index("</thead>")]
    foot = TEMPLATE[TEMPLATE.index("<tfoot>") : TEMPLATE.index("</tfoot>")]
    assert 'data-bulk="all_present"' in head and 'data-bulk="all_absent"' in head
    assert "data-bulk" not in foot and "data-save-col" in foot
    assert "غير مرصود" in head and "منهم" in head and "غير محفوظ" in head
    assert re.search(r"\.cg-summary\s*>\s*\*\s*\{[^}]*position:\s*sticky", CSS)
    assert re.search(r"\.cg-table tfoot > tr > \*\s*\{[^}]*position:\s*sticky", CSS)


def test_counts_treat_late_as_present_and_show_unrecorded():
    assert "if (st === 'late') n.present += 1;" in JS
    assert "n[st || 'none'] += 1;" in JS


def test_bulk_offers_an_eight_second_undo_and_unsaved_leave_is_warned():
    assert "8000" in JS and "undoBulk" in JS
    assert "beforeunload" in JS


def test_the_tab_state_is_reapplied_after_a_row_or_table_is_swapped_from_the_server():
    # العيبُ: بعد «متأخّر/خروج» يُستبدل الصفُّ بنسخةٍ كاملةِ الأعمدة فتظهر كلُّ أعمدته على الهاتف.
    assert JS.count("showTab(activeCol);") >= 3
    assert JS.count("restoreDraft(") >= 3


def test_the_hidden_tabs_bar_is_not_overridden_by_its_display_rule():
    assert re.search(r"\[data-tabs\]\[hidden\]\s*\{\s*display:\s*none;", CSS)


def test_the_student_name_is_one_line_with_an_ellipsis_on_the_phone():
    assert re.search(
        r"\.cg-name__btn\s*\{[^}]*white-space:\s*nowrap;[^}]*text-overflow:\s*ellipsis;", CSS
    )


def test_double_click_on_a_cell_opens_nothing_and_history_has_its_own_button():
    # W-20261013-021: النقرُ المزدوج على خليّةٍ = نقرتان للتبديل لا نافذةُ سجلّ؛ والسجلُّ بزرّه.
    assert "dblclick" not in JS
    assert "data-history-open" in JS


def test_a_cell_returned_to_its_saved_state_loses_its_dirty_mark_and_draft():
    assert "saved[col + ':' + student] === status" in JS
    assert "classList.remove('is-dirty')" in JS
    assert "delete draft[col][student]" in JS
