"""الجدولُ العامّ على الشاشة (قرارُ المالك 2026-09-25): جدولٌ أصيلٌ في الصفحة لا ورقةٌ في إطار.

كان الجدولُ العامّ (كلّ المعلّمين) الوحيدَ الباقيَ ورقةَ طباعةٍ ظاهرةً داخل إطار (استثناءُ قرار 2026-09-18 الذي فصل المعلّمَ
والشعبةَ)، فظهرت ترويستُها وسطرُها في المنصّة، وزحم الشريطَ ورقٌ واتّجاهٌ لا يغيّران ما يُرى، وسبق الحسابَ المزدوجُ للمصفوفة
(الصفحةُ ثمّ الإطار)، ولوحُ المعلّم والبحثُ يتراسلان بين وثيقتين. صار العرضُ جدولاً بمكوّنات المنصّة، والطباعةُ ورقتَها كما هي.

والحارسُ الجوهريّ: علاماتُ المصفوفة جزئيّةٌ واحدة (`pdf/matrix_table.html`) تقرؤها الورقةُ والصفحةُ معاً، وما تعرضه الصفحةُ
خانةً بخانة هو ما تطبعه الورقة (D-16 7.7).
"""

import pathlib
import re

import pytest
from django.urls import reverse

from core.dept_colors import DEPT_KEY_OF_CODE, OTHER
from tests.test_week_page import (  # noqa: F401 — `world` fixture مشتركةٌ مع اختبارات الصفحة
    SUNDAY,
    YEAR,
    world,
)
from tests.test_week_paper import _paper, _swap

pytestmark = pytest.mark.django_db

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates" / "schedule"
STATIC_JS = ROOT / "static" / "js" / "schedule-matrix.js"

_ROW = re.compile(r'<tr class="dept-[^"]*" data-teacher="([^"]*)".*?</tr>', re.S)
_CELL = re.compile(
    r'<td class="(m-cell[^"]*)" data-col="(\d+)"((?: data-c="[^"]*" data-s="[^"]*")?)>\s*(.*?)\s*</td>',
    re.S,
)


def _page(client, w, **params) -> str:
    client.force_login(w["principal"])
    return client.get(
        reverse("weekly_schedule"),
        {"view": "all_teachers", "year": YEAR, **params},
        HTTP_HOST="localhost",
    ).content.decode()


def _grid(html: str) -> list:
    """(المعلّم، خاناتُه: الصنفُ والعمودُ والبياناتُ والنصّ) لكلّ صفٍّ في جدول المصفوفة."""
    table = html.split('<table class="schedule-matrix">', 1)[1].split("</table>", 1)[0]
    body = table.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    return [(m.group(1), _CELL.findall(m.group(0))) for m in _ROW.finditer(body)]


class TestTheGeneralScheduleIsARealTable:
    def test_the_page_shows_the_table_itself_not_a_frame(self, world, client):
        body = _page(client, world)

        assert '<table class="schedule-matrix">' in body
        assert "sheet-scroll" in body and "schedule-sheet-frame" not in body
        # إطارٌ واحدٌ فحسب: إطارُ الطباعة المخفيّ.
        assert body.count("<iframe") == 1
        assert "schedule-print-frame-hidden" in body.split("<iframe", 1)[1].split(">", 1)[0]

    def test_the_print_frame_loads_only_when_asked(self, world, client):
        """يُحمَّل عند أوّل طلبِ طباعة (`data-src`) — فالورقةُ لا تُحسب مرّةً ثانيةً عند فتح الصفحة."""
        body = _page(client, world, source="actual", week="2026-10-18")

        frame = body.split('id="schedule-print-frame"', 1)[1].split(">", 1)[0]
        assert " src=" not in frame and "data-src=" in frame
        assert "embed=1" in frame and "view=all_teachers" in frame
        assert "source=actual" in frame and "week=2026-10-18" in frame

    def test_the_toolbar_names_paper_and_orientation_for_print(self, world, client):
        body = _page(client, world)

        assert 'title="حجم ورق الطباعة"' in body and 'title="اتّجاه ورق الطباعة"' in body

    def test_the_page_loads_the_interaction_layer_and_its_panel(self, world, client):
        body = _page(client, world)

        assert "js/schedule-matrix.js" in body
        assert 'id="teacher-panel"' in body and 'id="schedule-unpin"' in body
        assert 'id="schedule-search"' in body

    def test_teacher_and_class_views_do_not_load_it(self, world, client):
        client.force_login(world["principal"])
        body = client.get(
            reverse("weekly_schedule"),
            {"view": "teacher", "teacher": str(world["t1"].id), "year": YEAR},
            HTTP_HOST="localhost",
        ).content.decode()

        assert "js/schedule-matrix.js" not in body
        assert "week-grid" in body

    def test_a_week_without_lessons_shows_an_empty_state(self, world, client):
        body = _page(client, world, source="actual", week="2026-10-25")  # أسبوعُ إجازةٍ مغلق

        assert '<table class="schedule-matrix">' not in body
        assert "لا حصصَ في هذا الأسبوع" in body
        assert "js/schedule-matrix.js" not in body


class TestThePageShowsWhatThePaperPrints:
    def test_same_cells_for_the_plan(self, world, client):
        page = _grid(_page(client, world, source="plan"))
        paper = _grid(_paper(client, world, view="all_teachers", source="plan"))

        assert page and page == paper

    def test_same_cells_for_a_moved_week(self, world, client):
        _swap(world)
        query = {"source": "actual", "week": str(SUNDAY)}

        page = _grid(_page(client, world, **query))
        paper = _grid(_paper(client, world, view="all_teachers", **query))

        assert page == paper
        kinds = {classes for _t, cells in page for classes, *_ in cells}
        assert any("mk-swap" in c for c in kinds), "الخانةُ المحوَّلةُ ظاهرةٌ في الاثنتين"

    def test_screen_rows_use_the_central_department_key(self, world, client):
        body = _page(client, world)

        keys = set(re.findall(r'<tr class="dept-([^"]+)" data-teacher', body))
        assert keys and keys <= set(DEPT_KEY_OF_CODE.values()) | {OTHER}

    def test_the_paper_keeps_its_own_department_class(self, world, client):
        """الورقةُ تصبغ بأصنافها هي (`tr.dept-{كود}` في قالبها) — لا تُمسّ."""
        body = _paper(client, world, view="all_teachers")

        assert re.search(r'<tr class="dept-[a-z_]+" data-teacher', body)


class TestOneSourceForTheMatrixMarkup:
    def test_both_templates_include_the_shared_partial_and_neither_copies_it(self):
        sheet = (TEMPLATES / "print_schedule.html").read_text(encoding="utf-8")
        page = (TEMPLATES / "print_view.html").read_text(encoding="utf-8")

        for html in (sheet, page):
            assert 'include "schedule/pdf/matrix_table.html"' in html
            assert '<table class="schedule-matrix">' not in html, "نسخةٌ ثانيةٌ من علامات الجدول"

    def test_the_interaction_layer_talks_to_no_other_document(self):
        """لا رسائلَ بين وثيقتين: اللوحُ والبحثُ في المستند نفسِه."""
        js = STATIC_JS.read_text(encoding="utf-8")

        assert "postMessage" not in js and "window.parent" not in js
