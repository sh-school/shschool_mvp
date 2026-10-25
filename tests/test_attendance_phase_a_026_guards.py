"""حرّاسُ المرحلة أ٦ من آليّة الغياب (W-20261004-026، D-201م): لا كتابةَ للخروج عند فتح صفحة، والامتدادُ ثابتُ التكرار.

كان الخوفُ أن يُرحَّل خروجُ من لم يعد (`class_exit.carry_over`) عند فتح صفحة المعلّم بطلب GET: كتابةٌ
عند القراءة، وازدواجٌ إن فُتحت الصفحةُ مرّتين. وعلى main اليوم لا يُستدعى الترحيلُ إلّا من الإغلاق عند
الجرس، وسلسلتُه مهمّةٌ مجدولة: `finalize_period_exits_task` ← `finalize_exits_for_day` ←
`reflect_period_exits` ← `close_unreturned` ← `carry_over`. فهذه الاختباراتُ تثبّت ذلك كي لا يعود:

- فتحُ صفحة المعلّم وجدولِ الشعبة ورابطِ الحصّة القديم وغيابِ اليوم لا يُنشئ `ClassExit` ولا يُغلق خروجاً.
- الترحيلُ مرّتين — مباشرةً أو بالإغلاق عند الجرس مكرّراً — يُنشئ الامتدادَ نفسَه مرّةً واحدة.
- سلسلةُ الاستدعاء في الشيفرة الإنتاجيّة هي السلسلةُ أعلاه وحدها (فحصٌ نصّيٌّ بشجرة البناء).

والاستثناءُ المقصود: `ScheduleService.ensure_sessions_for_date` يكتب حصصَ اليوم عند فتح صفحة المعلّم
وغيابِ اليوم. وهو ثابتُ التكرار (الفتحُ الثاني لا يزيد حصّة)، ولا يمسّ الخروجَ ولا الحضور؛ ونقلُه إلى مهمّةٍ
خلفيّة قرارٌ لـ0301 لا تحسمه هذه البطاقة.
"""

import ast
from pathlib import Path

import pytest
from django.urls import reverse

from operations.class_exit import carry_over, close_unreturned
from operations.models import ClassExit, Session
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, at
from tests.test_class_grid import (  # noqa: F401 — التجهيزاتُ نفسُها
    _cells,
    _exit,
    _grid_on,
    _save,
    assigned,
    clock,
    kids,
    subject,
)

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[1]


def _left_in_first_period_and_second_opened(client_as, assigned, teacher, kids, clock):
    """طالبٌ خرج في ح1 ولم يعد ولم يُغلق خروجُه (لم تدُر مهمّةُ الجرس)، وح2 قائمةٌ جارية — حالُ الترحيل."""
    client = client_as(teacher)
    clock(7, 30)
    _exit(client, assigned, kids[0], action="leave", destination="restroom")
    clock(8, 10)
    _save(client, assigned, 2, [_cells(kids[1], "present")])
    first = Session.objects.get(class_group=assigned, date=SUNDAY, period_number=1)
    second = Session.objects.get(class_group=assigned, date=SUNDAY, period_number=2)
    return client, first, second


def _exits():
    return sorted(
        ClassExit.objects.values_list("id", "session_id", "returned_at", "continued_from_id")
    )


class TestOpeningAPageWritesNoExit:
    def test_get_of_every_attendance_page_leaves_the_exits_untouched(
        self, client_as, assigned, teacher, holder, kids, clock
    ):
        client, first, _ = _left_in_first_period_and_second_opened(
            client_as, assigned, teacher, kids, clock
        )
        before = _exits()
        assert len(before) == 1 and before[0][2] is None, "خروجٌ واحدٌ مفتوحٌ قبل الفتح"

        pages = (
            (client, reverse("teacher_schedule"), 200),
            (client, reverse("class_grid", args=[assigned.id]), 200),
            (client, reverse("attendance", args=[first.id]), 302),
            (client_as(holder), reverse("daily_report"), 200),
        )
        for opener, url, expected in pages:
            assert opener.get(url).status_code == expected, url
            assert _exits() == before, f"فتحُ {url} كتب في الخروج"

        assert not ClassExit.objects.filter(continued_from__isnull=False).exists()

    def test_opening_the_teachers_page_twice_adds_no_session(
        self, client_as, assigned, teacher, kids, clock
    ):
        """الاستثناءُ المقصود ثابتُ التكرار: `ensure_sessions_for_date` لا يزيد بالفتح الثاني."""
        client = client_as(teacher)
        clock(8, 10)
        client.get(reverse("teacher_schedule"))
        after_first = Session.objects.filter(date=SUNDAY).count()

        client.get(reverse("teacher_schedule"))

        assert Session.objects.filter(date=SUNDAY).count() == after_first


class TestCarryOverIsIdempotent:
    def test_carrying_over_twice_makes_one_extension(
        self, client_as, assigned, teacher, kids, clock
    ):
        _, first, second = _left_in_first_period_and_second_opened(
            client_as, assigned, teacher, kids, clock
        )
        origin = ClassExit.objects.get()

        assert carry_over(second, now=at(8, 10)) == 1
        assert carry_over(second, now=at(8, 20)) == 0

        extension = ClassExit.objects.get(continued_from=origin)
        assert (extension.session_id, extension.student_id) == (second.id, kids[0].id)
        assert ClassExit.objects.count() == 2

    def test_the_bell_closing_twice_makes_one_extension(
        self, client_as, assigned, teacher, kids, clock
    ):
        _, first, second = _left_in_first_period_and_second_opened(
            client_as, assigned, teacher, kids, clock
        )
        bell = at(first.end_time.hour, first.end_time.minute)

        assert close_unreturned(first, now=bell) == 1
        assert close_unreturned(first, now=bell) == 0
        carry_over(second, now=at(8, 20))

        assert ClassExit.objects.filter(continued_from__isnull=False).count() == 1
        assert ClassExit.objects.count() == 2


# ── فحصٌ نصّيّ: من يستدعي الترحيلَ في الشيفرة الإنتاجيّة ──────────────────────────

#: السلسلةُ الوحيدةُ المسموحة: {الدالّةُ المستدعاة: {(الملفّ، الدالّةُ المستدعية)}}.
CHAIN = {
    "carry_over": {("operations/class_exit.py", "close_unreturned")},
    "close_unreturned": {("operations/exit_reflection.py", "reflect_period_exits")},
    "reflect_period_exits": {("operations/exit_reflection.py", "finalize_exits_for_day")},
    "finalize_exits_for_day": {("operations/tasks.py", "finalize_period_exits_task")},
}
SKIPPED = {"tests", "migrations", "node_modules", "staticfiles", "tools", "scripts"}


def _production_files():
    for path in ROOT.rglob("*.py"):
        parts = path.relative_to(ROOT).parts
        if any(part.startswith(".") or part in SKIPPED for part in parts):
            continue
        yield path


class _Calls(ast.NodeVisitor):
    """يجمع استدعاءاتِ اسمٍ واحد منسوبةً إلى أقرب دالّةٍ تحيط بها («<الوحدة>» خارج كلّ دالّة)."""

    def __init__(self, name: str):
        self.names = {name}  # والاسمُ المستعار (`import … as`) يُضاف حين يُرى
        self.stack = ["<الوحدة>"]
        self.owners: set[str] = set()

    def visit_ImportFrom(self, node):  # noqa: N802
        self.names |= {a.asname for a in node.names if a.name in self.names and a.asname}

    def _scope(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node):  # noqa: N802 — اسمٌ يفرضه ast.NodeVisitor
        self._scope(node)

    def visit_AsyncFunctionDef(self, node):  # noqa: N802
        self._scope(node)

    def visit_Call(self, node):  # noqa: N802
        func = node.func
        called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if called in self.names:
            self.owners.add(self.stack[-1])
        self.generic_visit(node)


def _callers(name: str) -> set[tuple[str, str]]:
    """كلُّ (ملفّ، دالّة) تستدعي `name` في الشيفرة الإنتاجيّة."""
    found = set()
    for path in _production_files():
        text = path.read_text(encoding="utf-8")
        if name not in text:
            continue
        calls = _Calls(name)
        calls.visit(ast.parse(text))
        found |= {(path.relative_to(ROOT).as_posix(), owner) for owner in calls.owners}
    return found


@pytest.mark.parametrize("name", sorted(CHAIN))
def test_the_carry_over_chain_has_no_other_caller_in_production(name):
    assert _callers(name) == CHAIN[name]
