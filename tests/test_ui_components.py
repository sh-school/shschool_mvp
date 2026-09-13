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
        assert "empty-state-v2" in html and "#icon-search" in html


@pytest.mark.django_db
def test_the_components_page_renders_every_component(client_as, principal_user):
    body = client_as(principal_user).get(reverse("ui_components")).content.decode()

    for marker in ("ui-kpis", "ui-section", "ui-entity", "empty-state-v2", "ui-page-header"):
        assert marker in body
