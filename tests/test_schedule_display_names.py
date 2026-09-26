"""الجدولُ العامّ: اسمُ المعلّم مقطعان وعمودُ القسم كلماتٌ متراصّة (قرارُ المالك 2026-09-26).

الموضعُ الجزئيّةُ المشتركة `pdf/matrix_table.html` التي تقرؤها ورقةُ الطباعة وصفحةُ المنصّة — فالتعديلُ فيها يصل الاثنتين (D-16 7.7).
الاسمُ الكاملُ يبقى في `title` و`data-teacher` (بطاقةُ الخانة والبحثُ)؛ والمعروضُ في الخانة المقطعان. الأسماءُ هنا مصطنعة.
"""

import pytest
from django.template import Context, Template

from operations.services.schedule import ScheduleService
from operations.templatetags.week_tags import stack_words
from tests.test_schedule_general_screen import _grid, _page  # noqa: F401
from tests.test_week_page import YEAR, world  # noqa: F401

pytestmark = pytest.mark.django_db

FULL = "عبد الله محمد احمد الكواري"


class TestTheStackedDepartmentName:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("التربية الإسلامية", "التربية<br>الإسلامية"),
            ("الرياضيات", "الرياضيات"),
            ("التكنولوجيا وعلوم الحاسب", "التكنولوجيا<br>وعلوم<br>الحاسب"),
            ("المهارات الحياتية والمهنية", "المهارات<br>الحياتية<br>والمهنية"),
            ("العلوم — إعدادي", "العلوم<br>إعدادي"),  # الشرطةُ تسقط
            ("العلوم و الآداب", "العلوم<br>والآداب"),  # «و» المفصولةُ تلتصق بما بعدها
            ("", ""),
            (None, ""),
        ],
    )
    def test_each_word_on_its_own_line(self, text, expected):
        assert stack_words(text) == expected

    def test_every_word_is_escaped(self):
        assert stack_words("<b>x</b> y") == "&lt;b&gt;x&lt;/b&gt;<br>y"

    def test_it_is_a_template_filter_of_week_tags(self):
        rendered = Template("{% load week_tags %}{{ name|stack_words }}").render(
            Context({"name": "اللغة العربية"})
        )

        assert rendered == "اللغة<br>العربية"


class TestTheMatrixRowsCarryADisplayName:
    def test_the_display_name_is_short_and_the_teacher_stays_full(self, world):
        world["t1"].full_name = FULL
        world["t1"].save(update_fields=["full_name"])

        rows = ScheduleService.get_teachers_matrix(world["school"], YEAR)

        row = next(r for r in rows if r["teacher"].pk == world["t1"].pk)
        assert row["display_name"] == "عبد الله الكواري"
        assert row["teacher"].full_name == FULL

    def test_a_two_unit_name_is_shown_as_it_is(self, world):
        rows = ScheduleService.get_teachers_matrix(world["school"], YEAR)

        assert {r["teacher"].full_name: r["display_name"] for r in rows}["معلّمٌ ثانٍ"] == "معلّمٌ ثانٍ"


class TestThePageShowsTheShortNameAndKeepsTheFullOne:
    def test_the_name_cell_is_short_while_the_title_and_the_data_attribute_are_full(
        self, world, client
    ):
        world["t1"].full_name = FULL
        world["t1"].save(update_fields=["full_name"])

        body = _page(client, world)

        assert f'data-teacher="{FULL}"' in body
        assert f'title="{FULL} — قسم' in body
        cell = body.split(f'data-teacher="{FULL}"', 1)[1].split('<td class="m-name', 1)[1]
        cell = cell.split(">", 1)[1].split("</td>", 1)[0].strip()
        assert cell == "عبد الله الكواري"
        assert "عبد الله محمد احمد الكواري</td>" not in body

    def test_the_department_cell_stacks_its_words_and_keeps_the_full_name_as_a_title(
        self, world, client
    ):
        body = _page(client, world)

        assert 'title="العلوم — ثانوي">العلوم<br>ثانوي</td>' in body

    def test_the_paper_uses_the_same_partial(self, world, client):
        """الورقةُ تقرأ الجزئيّةَ نفسَها فالمعروضُ هو المطبوع."""
        world["t1"].full_name = FULL
        world["t1"].save(update_fields=["full_name"])
        client.force_login(world["principal"])

        from django.urls import reverse

        body = client.get(
            reverse("schedule_print"), {"view": "all_teachers", "year": YEAR}, HTTP_HOST="localhost"
        ).content.decode()

        assert "عبد الله الكواري" in body and "العلوم<br>ثانوي" in body
