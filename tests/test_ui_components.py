"""مكوّناتُ الواجهة (`{% load ui %}`) — ترسم القاعدةَ وترفض مخالفتَها.

الوسمُ الذي يرسم ما يُطلب منه كيفما طُلب لا يحرس شيئاً: سابعُ بطاقةٍ في الشريط،
ولونٌ لا رمزَ له، وفقرةٌ في بطاقة الكيان — كلُّها كانت ستُرسم صامتةً كما
رُسمت في مئة صفحة. فهنا يُختبر الرفضُ كما يُختبر الرسم.
"""

import pytest
from django.template import Context, Template, TemplateSyntaxError
from django.urls import reverse


def render(source, **context):
    return Template("{% load ui %}" + source).render(Context(context))


class TestKpiStrip:
    def test_a_card_is_label_then_value_then_detail_on_one_line(self):
        html = render(
            '{% kpi_strip %}{% kpi "الغياب" 12 sub="اليوم" tone="red" %}{% endkpi_strip %}'
        )

        label, value, sub = (
            html.index(c) for c in ("ui-kpi__label", "ui-kpi__value", "ui-kpi__sub")
        )
        assert label < value < sub
        assert 'class="ui-kpi kpi-red"' in html
        assert 'role="list"' in html and 'role="listitem"' in html

    def test_zero_is_a_number_not_a_blank(self):
        html = render('{% kpi_strip %}{% kpi "المتأخّرون" n %}{% endkpi_strip %}', n=0)
        assert '<span class="ui-kpi__value">0</span>' in html

    def test_a_linked_card_is_an_anchor(self):
        html = render('{% kpi_strip %}{% kpi "الغياب" 3 href="/x/" %}{% endkpi_strip %}')
        assert '<a href="/x/" class="ui-kpi kpi-maroon is-link"' in html

    def test_text_is_escaped(self):
        html = render("{% kpi_strip %}{% kpi label 1 %}{% endkpi_strip %}", label="<script>")
        assert "<script>" not in html and "&lt;script&gt;" in html

    def test_a_seventh_card_is_refused(self):
        cards = '{% kpi "x" 1 %}' * 7
        with pytest.raises(TemplateSyntaxError, match="الحدُّ 6"):
            render("{% kpi_strip %}" + cards + "{% endkpi_strip %}")

    def test_six_cards_are_allowed(self):
        html = render("{% kpi_strip %}" + '{% kpi "x" 1 %}' * 6 + "{% endkpi_strip %}")
        assert html.count('role="listitem"') == 6

    def test_a_tone_without_a_token_is_refused(self):
        with pytest.raises(TemplateSyntaxError, match="لا رمزَ له"):
            render('{% kpi_strip %}{% kpi "x" 1 tone="pink" %}{% endkpi_strip %}')

    def test_an_empty_strip_is_refused(self):
        with pytest.raises(TemplateSyntaxError):
            render("{% kpi_strip %}{% endkpi_strip %}")

    def test_a_missing_value_is_refused(self):
        with pytest.raises(TemplateSyntaxError, match="الرقم مطلوب"):
            render('{% kpi_strip %}{% kpi "x" missing %}{% endkpi_strip %}')


class TestSectionCard:
    def test_the_header_is_the_maroon_bar_with_meta_at_its_end(self):
        html = render('{% section_card "الغائبون" meta=3 %}<p>قائمة</p>{% endsection_card %}')
        assert 'class="card-bar"' in html
        assert '<h2 class="ui-section__title">الغائبون</h2>' in html
        assert '<span class="card-bar-sub">3</span>' in html
        assert "<p>قائمة</p>" in html

    def test_empty_content_becomes_the_shared_empty_state(self):
        html = render(
            '{% section_card "المتأخّرون" empty="لم يتأخّر أحد" %}'
            "{% for x in items %}{{ x }}{% endfor %}{% endsection_card %}",
            items=[],
        )
        assert "empty-state-v2" in html and "لم يتأخّر أحد" in html

    def test_a_zero_meta_is_shown(self):
        html = render('{% section_card "x" meta=n %}y{% endsection_card %}', n=0)
        assert '<span class="card-bar-sub">0</span>' in html

    def test_flush_marks_the_card(self):
        html = render('{% section_card "x" flush=True %}y{% endsection_card %}')
        assert "ui-section is-flush" in html


class TestEntityCard:
    BODY = (
        '{% entity_chips %}<span class="chip">7.1</span>{% endentity_chips %}'
        '{% entity_status tone="warning" %}الفسحة{% endentity_status %}'
    )

    def test_three_lines_who_and_count_chips_status(self):
        html = render(
            '{% entity_card "جناح 1" who="اسمٌ طويل" count="164 طالباً" %}'
            + self.BODY
            + "{% endentity_card %}"
        )
        assert (
            html.index("ui-entity__head")
            < html.index("ui-entity__chips")
            < html.index("ui-entity__status")
        )
        assert 'title="اسمٌ طويل"' in html
        assert "is-warning" in html

    def test_a_fourth_line_is_refused(self):
        with pytest.raises(TemplateSyntaxError, match="سطرٌ رابع"):
            render('{% entity_card "x" %}' + self.BODY + "<p>شرح</p>{% endentity_card %}")

    def test_two_status_lines_are_refused(self):
        status = "{% entity_status %}a{% endentity_status %}"
        with pytest.raises(TemplateSyntaxError, match="لا أكثر"):
            render('{% entity_card "x" %}' + status * 2 + "{% endentity_card %}")

    def test_an_unknown_status_tone_is_refused(self):
        with pytest.raises(TemplateSyntaxError):
            render(
                '{% entity_card "x" %}{% entity_status tone="gold" %}a{% endentity_status %}{% endentity_card %}'
            )

    def test_the_title_is_required(self):
        with pytest.raises(TemplateSyntaxError, match="العنوان"):
            render('{% entity_card "" %}{% endentity_card %}')


class TestPageHeaderAndEmptyState:
    def test_actions_are_omitted_when_blank(self):
        html = render('{% page_header "العيادة" subtitle="اليوم" %}   {% endpage_header %}')
        assert '<h1 class="exec-title">' in html and "exec-meta" not in html

    def test_actions_are_rendered(self):
        html = render('{% page_header "العيادة" %}<a href="/v/">زيارة</a>{% endpage_header %}')
        assert '<div class="exec-meta"><a href="/v/">زيارة</a></div>' in html

    def test_empty_state_uses_the_shared_component(self):
        html = render('{% empty_state "لا نتائج" sub="جرّب غيرها" icon="search" %}')
        assert "empty-state-v2" in html and "sprite.svg#i-search" in html


class TestField:
    """الحقلُ بتسميته: `label[for]` و`id` من اسمٍ واحد — و`name` والقيمُ كما هي."""

    def test_a_text_field_has_a_label_bound_to_its_id(self):
        html = render('{% field "q" "بحث" value="أحمد" placeholder="اسم…" %}')
        assert '<label for="f-q" class="ui-field__label">بحث</label>' in html
        assert '<input type="text" id="f-q" name="q" class="form-control" value="أحمد"' in html
        assert 'placeholder="اسم…"' in html

    def test_the_id_is_derived_from_the_name_or_given(self):
        assert 'id="f-date-from"' in render('{% field "date from" "من" %}')
        assert 'for="q2"' in render('{% field "q" "بحث" id="q2" %}')

    def test_a_select_marks_the_chosen_option_and_keeps_values(self):
        html = render(
            '{% field "grade" "الصفّ" type="select" choices=grades value=7 blank="— الكل —" %}',
            grades=[(7, "السابع"), (8, "الثامن")],
        )
        assert '<select id="f-grade" name="grade" class="form-control">' in html
        assert '<option value="">— الكل —</option>' in html
        assert '<option value="7" selected>السابع</option>' in html
        assert '<option value="8">الثامن</option>' in html

    def test_flat_choices_and_dicts_are_accepted(self):
        assert '<option value="أ">أ</option>' in render(
            '{% field "x" "س" type="select" choices=c %}', c=["أ"]
        )
        assert '<option value="a">ألف</option>' in render(
            '{% field "x" "س" type="select" choices=c %}', c={"a": "ألف"}
        )

    def test_literal_choices_are_written_as_a_string_in_the_template(self):
        html = render(
            '{% field "p" "وليّ الأمر" type="select" choices="linked=مرتبط|unlinked=غير مرتبط|A4" value="unlinked" %}'
        )
        assert '<option value="linked">مرتبط</option>' in html
        assert '<option value="unlinked" selected>غير مرتبط</option>' in html
        assert '<option value="A4">A4</option>' in html

    def test_a_textarea_carries_its_value_as_content(self):
        html = render('{% field "notes" "ملاحظات" type="textarea" rows=2 value=v %}', v="<b>")
        assert (
            '<textarea id="f-notes" name="notes" class="form-control" rows="2">&lt;b&gt;</textarea>'
            in html
        )

    def test_a_checkbox_puts_the_label_after_the_box(self):
        html = render('{% field "notify" "إشعار" type="checkbox" checked=True value="yes" %}')
        assert html.index("<input") < html.index("<label")
        assert 'type="checkbox" id="f-notify" name="notify"' in html
        assert 'value="yes" checked' in html

    def test_htmx_and_data_attributes_pass_through_with_hyphens(self):
        html = render(
            '{% field "q" "بحث" hx_get="/s/" hx_trigger="input changed delay:400ms" '
            "data_autosubmit=True min=1 maxlength=60 required=True %}"
        )
        assert 'hx-get="/s/"' in html and 'hx-trigger="input changed delay:400ms"' in html
        assert " data-autosubmit" in html and 'min="1"' in html and 'maxlength="60"' in html
        assert " required" in html and '<span class="req-star" aria-hidden="true">*</span>' in html

    def test_false_and_empty_attributes_are_dropped(self):
        html = render(
            '{% field "q" "بحث" required=False data_autosubmit=flag hx_get="" %}', flag=None
        )
        assert "required" not in html and "data-autosubmit" not in html and "hx-get" not in html

    def test_help_and_error_are_linked_by_aria_describedby(self):
        html = render('{% field "phone" "الجوّال" type="tel" help="بصيغة دوليّة" error="غيرُ صالح" %}')
        assert 'aria-describedby="f-phone-help f-phone-error"' in html
        assert 'aria-invalid="true"' in html
        assert '<p id="f-phone-help" class="ui-field-hint">بصيغة دوليّة</p>' in html
        assert '<p id="f-phone-error" class="field-error" role="alert">غيرُ صالح</p>' in html
        assert "ui-field has-error" in html

    def test_a_hidden_label_stays_for_the_reader(self):
        html = render('{% field "q" "بحث" hide_label=True %}')
        assert 'class="ui-field__label sr-only">بحث</label>' in html

    def test_values_are_escaped(self):
        html = render('{% field "q" label value=v %}', label="<i>", v='"><script>')
        assert "<i>" not in html and "&lt;i&gt;" in html
        assert "<script>" not in html and "&quot;&gt;&lt;script&gt;" in html

    def test_a_field_without_a_label_is_refused(self):
        with pytest.raises(TemplateSyntaxError, match="التسمية"):
            render('{% field "q" "" %}')

    def test_an_unknown_type_is_refused(self):
        with pytest.raises(TemplateSyntaxError, match="غيرُ معروف"):
            render('{% field "q" "بحث" type="color" %}')

    def test_a_select_without_choices_is_refused(self):
        with pytest.raises(TemplateSyntaxError, match="بلا choices"):
            render('{% field "g" "الصفّ" type="select" %}')

    def test_an_attribute_that_is_not_an_html_name_is_refused(self):
        with pytest.raises(TemplateSyntaxError, match="سمةٌ لا تصلح"):
            render('{% field "q" "بحث" _x="1" %}')


class TestFilterBar:
    def test_it_is_a_get_form_with_a_search_role_and_a_name(self):
        html = render('{% filter_bar "ترشيحُ الطلاب" %}{% field "q" "بحث" %}{% endfilter_bar %}')
        assert html.startswith(
            '<form method="get" class="filter-bar" role="search" aria-label="ترشيحُ الطلاب">'
        )
        assert html.rstrip().endswith("</form>")

    def test_live_filtering_is_a_search_region_not_a_form(self):
        html = render(
            '{% filter_bar "بحث" live=True id="x" css="att-toolbar" %}{% field "q" "بحث" %}{% endfilter_bar %}'
        )
        assert html.startswith(
            '<div class="filter-bar att-toolbar" role="search" aria-label="بحث" id="x">'
        )
        assert "<form" not in html

    def test_htmx_attributes_pass_through(self):
        html = render(
            '{% filter_bar "ترشيح" id="f" action="/l/" hx_get="/l/" hx_target="#t" %}{% field "q" "بحث" %}{% endfilter_bar %}'
        )
        assert 'id="f" action="/l/" hx-get="/l/" hx-target="#t"' in html

    def test_a_bar_without_a_field_is_refused(self):
        with pytest.raises(TemplateSyntaxError, match="بلا حقل"):
            render('{% filter_bar "ترشيح" %}<a href="/">x</a>{% endfilter_bar %}')

    def test_the_name_is_required(self):
        with pytest.raises(TemplateSyntaxError, match="المعلَن"):
            render('{% filter_bar "" %}{% field "q" "بحث" %}{% endfilter_bar %}')


@pytest.mark.django_db
def test_the_components_page_renders_every_component(client_as, developer_user):
    body = client_as(developer_user).get(reverse("ui_components")).content.decode()

    for marker in (
        "ui-kpis",
        "ui-section",
        "ui-entity",
        "empty-state-v2",
        "ui-page-header",
        'role="search"',
        'for="f-sg_phone"',
    ):
        assert marker in body


class TestCallout:
    """خمسةُ أنواعٍ لا يخلط أحدُها بغيره — تلميحٌ ومعلومةٌ أيقونتان، وتحذيرٌ وخطأٌ ونجاحٌ أسطر."""

    def test_error_and_success_are_visible_rows_with_their_roles(self):
        for kind, role in (("error", "alert"), ("success", "status")):
            html = render(f'{{% callout "{kind}" %}}نصّ{{% endcallout %}}')
            assert f"ui-callout--{kind}" in html and f'role="{role}"' in html
            assert "نصّ" in html and "ui-tip" not in html

    def test_hint_info_and_warning_are_icons_whose_text_is_in_a_panel(self):
        html = render('{% callout "hint" %}كيف تُحتسب المهلة؟{% endcallout %}')
        assert 'class="ui-tip ui-tip--hint"' in html
        assert 'role="tooltip"' in html and 'aria-controls="tip-' in html
        assert "ui-callout" not in html
        assert "ui-tip--info" in render('{% callout "info" %}س{% endcallout %}')
        assert "ui-tip--warning" in render('{% callout "warning" %}س{% endcallout %}')

    def test_show_makes_any_kind_a_visible_row(self):
        """حالةٌ تقول للمستخدم شيئاً لا يجوز إخفاؤه («لا دوامَ اليوم») تُطلب ظاهرةً."""
        html = render('{% callout "warning" show=True %}لا دوام{% endcallout %}')
        assert "ui-callout--warning" in html and "ui-tip" not in html and "لا دوام" in html

    def test_tips_are_ordered_hint_then_warning_then_info_everywhere(self):
        html = render(
            '{% section_card "س" %}{% callout "info" %}أ{% endcallout %}{% callout "warning" %}ب{% endcallout %}'
            '{% callout "hint" %}ج{% endcallout %}{% endsection_card %}'
        )
        assert (
            html.index("ui-tip--hint") < html.index("ui-tip--warning") < html.index("ui-tip--info")
        )

    def test_an_unknown_kind_is_an_error_not_a_silent_default(self):
        with pytest.raises(TemplateSyntaxError, match="غيرُ معروف"):
            render('{% callout "danger" %}س{% endcallout %}')

    def test_empty_content_at_render_time_draws_nothing(self):
        assert render('{% callout "warning" %}{% if x %}س{% endif %}{% endcallout %}').strip() == ""

    def test_a_tip_moves_to_the_section_card_bar_and_leaves_the_body(self):
        html = render(
            '{% section_card "العنوان" %}{% callout "hint" %}شرح{% endcallout %}<p id="b">جسم</p>{% endsection_card %}'
        )
        bar, body = html.split('class="ui-section__body"')
        assert "ui-tip" in bar and "ui-tip" not in body
        assert '<p id="b">جسم</p>' in body

    def test_a_tip_moves_beside_the_page_title_and_actions_stay_html(self):
        html = render(
            '{% page_header "العنوان" %}{% callout "hint" %}شرح{% endcallout %}<a href="#">رابط</a>{% endpage_header %}'
        )
        assert html.index("ui-tip") < html.index("exec-meta")
        assert '<a href="#">رابط</a>' in html and "&lt;a" not in html

    def test_a_folded_card_keeps_the_tip_in_its_body(self):
        html = render(
            '{% section_card "س" foldable=True %}{% callout "hint" %}شرح{% endcallout %}ب{% endsection_card %}'
        )
        assert html.index("ui-section__body") < html.index("ui-tip")
