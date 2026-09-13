"""[SORTING] فرزُ الجداول — في المتصفّح لما يُعرض كاملاً، ومن الخادم لما يُقسَّم.

طُلب أن تُفرَز أعمدةُ جداول المنصّة تصاعديّاً وتنازليّاً. والجدولُ المعروضُ
كاملاً يُفرَز في المتصفّح؛ أمّا المقسَّمُ صفحاتٍ فلا: فرزُ خمسٍ وعشرين صفّاً من
ألفٍ يُوهم القارئَ أنّه رأى الأعلى وهو أعلى صفحةٍ واحدة. فالترتيبُ يقع على
الاستعلام كلِّه قبل التقسيم.

وهذه الاختباراتُ تُثبّت الحدَّ الذي يحرس ذلك: `?sort=` نصٌّ يأتي من المستخدم،
فلا يبلغ `order_by` إلّا مصفّى بقائمةٍ مصرَّحةٍ في الشاشة نفسها.
"""

from datetime import date

import pytest
from django.template import Context, Template
from django.test import RequestFactory
from django.urls import reverse

from core.sorting import apply_sort
from student_info.models import StudentNote

YEAR = "2025-2026"


def _get(path="/x/", **params):
    return RequestFactory().get(path, params)


class _FakeQuerySet:
    """يلتقط ما يُمرَّر إلى `order_by` — فالمقصودُ هنا الحقولُ لا النتائج."""

    def __init__(self):
        self.ordering = None

    def order_by(self, *fields):
        self.ordering = fields
        return self


ALLOWED = {
    "date": ("occurred_on", "-created_at"),
    "student": ("student__full_name", "-occurred_on"),
}


def _spec(ordering):
    """يقرأ عباراتِ الترتيب كما تُكتب الحقول: «-حقل» تنازلاً و«حقل» تصاعداً."""
    return tuple(("-" if o.descending else "") + o.expression.name for o in ordering)


# ── الحدّ: لا يبلغ ORM إلّا ما صُرِّح به ───────────────────────────────


def test_an_unknown_sort_key_falls_back_to_the_screens_default():
    """`?sort=password` لا يفتح حقلاً لم تُصرّح به الشاشة."""
    qs, state = apply_sort(_FakeQuerySet(), _get(sort="student__password"), ALLOWED, "date")

    assert _spec(qs.ordering) == ("occurred_on", "-created_at")
    assert state.key == "date"


def test_a_related_field_traversal_is_not_smuggled_through_the_sort_parameter():
    """ولا تُعبَر العلاقاتُ بمفتاحٍ ملفَّق — الفرزُ اختيارٌ من قائمةٍ لا نصٌّ حرّ."""
    qs, _ = apply_sort(_FakeQuerySet(), _get(sort="school__api_key"), ALLOWED, "date")

    assert all("api_key" not in f for f in _spec(qs.ordering))


@pytest.mark.parametrize(
    ("direction", "expected"),
    [("asc", ("occurred_on", "-created_at")), ("desc", ("-occurred_on", "created_at"))],
)
def test_the_direction_flips_every_field_of_the_ordering(direction, expected):
    """التنازليُّ يعكس الحقلَ الفاصلَ أيضاً، فلا يبقى نصفُ الترتيب معكوساً."""
    qs, _ = apply_sort(_FakeQuerySet(), _get(sort="date", dir=direction), ALLOWED, "date")

    assert _spec(qs.ordering) == expected


def test_a_screen_that_opens_on_newest_first_keeps_doing_so_before_any_click():
    """قبل أن يُنقر شيءٌ يبقى ترتيبُ الشاشة كما اعتاده القارئ."""
    qs, state = apply_sort(_FakeQuerySet(), _get(), ALLOWED, "date", default_desc=True)

    assert _spec(qs.ordering) == ("-occurred_on", "created_at")
    assert state.descending


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_the_missing_value_falls_to_the_tail_in_both_directions(direction):
    """ترتيبُ القاعدة للعَدَم يتبع الاتّجاه: أخيراً صعوداً وأوّلاً نزولاً. فمن
    نقر عموداً نصفُ خاناته فارغةٌ ليرى أكبرَه رأى الفراغَ أوّلاً ولم يرَ شيئاً."""
    qs, _ = apply_sort(_FakeQuerySet(), _get(sort="date", dir=direction), ALLOWED, "date")

    assert all(o.nulls_last for o in qs.ordering)


def test_a_column_declared_desc_first_starts_at_its_natural_direction():
    """عمودُ التاريخ يبدأ بالأحدث ولو جاء الرابطُ بلا اتّجاه."""
    _, state = apply_sort(
        _FakeQuerySet(), _get(sort="date"), ALLOWED, "student", desc_first=("date",)
    )

    assert state.descending


# ── الترويسة: رابطٌ يحفظ ما قبله ──────────────────────────────────────


def _render(request, state, key="student", label="الطالب"):
    template = Template('{% load sorting %}{% sort_th sort "' + key + '" "' + label + '" %}')
    return template.render(Context({"request": request, "sort": state}))


def test_sorting_keeps_the_filters_the_reader_already_chose():
    """نقرةُ الفرز لا تُلغي بحثاً ولا سنةً — الرابطُ يحمل ما كان معه."""
    request = _get(q="أحمد", year=YEAR, page="4")
    _, state = apply_sort(_FakeQuerySet(), request, ALLOWED, "date")

    html = _render(request, state)

    assert "q=%D8%A3%D8%AD%D9%85%D8%AF" in html or "q=" in html
    assert "year=" + YEAR in html
    assert "page=" not in html  # الترتيبُ تغيّر كلُّه فيعود القارئُ إلى أوّله


def test_clicking_the_active_column_offers_the_opposite_direction():
    """العمودُ المفروزُ تصاعديّاً يعرض رابطاً تنازليّاً — وإلّا فلا سبيل للعكس."""
    request = _get(sort="student", dir="asc")
    _, state = apply_sort(_FakeQuerySet(), request, ALLOWED, "date")

    html = _render(request, state)

    assert 'aria-sort="ascending"' in html
    assert "dir=desc" in html


def test_an_idle_column_announces_itself_unsorted_to_a_screen_reader():
    request = _get(sort="date")
    _, state = apply_sort(_FakeQuerySet(), request, ALLOWED, "date")

    html = _render(request, state, key="student")

    assert 'aria-sort="none"' in html


# ── على الشاشة: الفرزُ يسبق التقسيم ───────────────────────────────────


@pytest.fixture
def teaching_slot(db, school, teacher_user, class_group):
    """حصّةٌ تربط المعلّمَ بالشعبة — بها وحدها يصير الطالبُ «طالبَه» فيرى ملاحظاته."""
    from datetime import time

    from operations.models import ScheduleSlot, Subject

    subject = Subject.objects.create(school=school, name_ar="رياضيات", code="MATH")
    return ScheduleSlot.objects.create(
        school=school,
        teacher=teacher_user,
        class_group=class_group,
        subject=subject,
        day_of_week=0,
        period_number=1,
        start_time=time(7, 0),
        end_time=time(7, 45),
        academic_year=class_group.academic_year,
    )


@pytest.fixture
def three_notes(db, school, student_user, teacher_user):
    for day, title in ((3, "جيم"), (1, "ألف"), (2, "باء")):
        StudentNote.objects.create(
            school=school,
            student=student_user,
            category="teacher",
            title=title,
            body="نصّ",
            occurred_on=date(2026, 3, day),
            academic_year=YEAR,
            created_by=teacher_user,
        )


def test_the_notes_screen_orders_the_whole_list_not_the_visible_page(
    client, three_notes, teacher_user, teaching_slot
):
    """ترتيبُ الصفحة يأتي من ترتيب القائمة كلِّها، والعنوانُ يُفرَز أبجديّاً."""
    client.force_login(teacher_user)
    url = reverse("student_info:notes", args=["teacher"])

    response = client.get(url, {"year": YEAR, "sort": "title", "dir": "asc"})

    titles = [n.title for n in response.context["page"]]
    assert titles == sorted(titles)


def test_the_notes_screen_still_opens_on_the_newest_note(
    client, three_notes, teacher_user, teaching_slot
):
    """بلا نقرةٍ يبقى الأحدثُ أوّلاً كما كانت الشاشةُ قبل الفرز."""
    client.force_login(teacher_user)
    url = reverse("student_info:notes", args=["teacher"])

    response = client.get(url, {"year": YEAR})

    dates = [n.occurred_on for n in response.context["page"]]
    assert dates == sorted(dates, reverse=True)


# ── نقرةُ الفرز تُبدّل الجدول لا الصفحة ───────────────────────────────


def _render_targeted(request, state, target, key="student", label="الطالب"):
    template = Template(
        '{% load sorting %}{% sort_th sort "' + key + '" "' + label + '" '
        '"" target="' + target + '" %}'
    )
    return template.render(Context({"request": request, "sort": state}))


def test_a_header_without_a_target_stays_a_plain_link():
    """الشاشاتُ التي لم تُهيّئ جزءاً يُستبدَل تبقى على الملاحة الكاملة كما كانت."""
    request = _get(sort="student", dir="asc")
    _, state = apply_sort(_FakeQuerySet(), request, ALLOWED, "date")

    html = _render(request, state)

    assert "hx-get" not in html
    assert 'href="?' in html


def test_a_targeted_header_swaps_the_table_and_leaves_the_link_working():
    """الفرزُ يُبدّل اللوحَ وحدَه — والرابطُ يبقى رابطاً لمن لا جافاسكربت عنده."""
    request = _get(sort="student", dir="asc")
    _, state = apply_sort(_FakeQuerySet(), request, ALLOWED, "date")

    html = _render_targeted(request, state, "#notif-log-panel")

    assert 'hx-get="?sort=student&amp;dir=desc"' in html
    assert 'hx-target="#notif-log-panel"' in html
    assert 'hx-swap="outerHTML"' in html
    assert 'hx-push-url="true"' in html
    assert 'href="?sort=student&amp;dir=desc"' in html


def test_the_notifications_log_returns_the_panel_alone_when_htmx_asks_for_it(
    client, principal_user
):
    """طلبُ HTMX يعود باللوح وحدَه: لا ترويسةَ صفحةٍ تُعاد ولا إحصاءاتٍ تُحسَب."""
    client.force_login(principal_user)

    response = client.get(
        reverse("notifications_dashboard"),
        {"sort": "student", "dir": "asc"},
        headers={"hx-request": "true", "hx-target": "notif-log-panel"},
    )

    body = response.content.decode()
    assert response.status_code == 200
    assert body.lstrip().startswith('<div id="notif-log-panel">')
    assert "<html" not in body


def test_the_notifications_log_still_renders_the_whole_page_for_a_plain_visit(
    client, principal_user, school
):
    """الزيارةُ العاديّةُ — أو المتصفّحُ بلا HTMX — تُعيد الصفحةَ كاملةً وفيها اللوح."""
    from notifications.models import NotificationLog

    NotificationLog.objects.create(
        school=school,
        recipient="wali@example.com",
        channel="email",
        notif_type="custom",
        status="sent",
    )
    client.force_login(principal_user)

    response = client.get(reverse("notifications_dashboard"), {"sort": "student", "dir": "asc"})

    body = response.content.decode()
    assert response.status_code == 200
    assert "<html" in body
    assert 'id="notif-log-panel"' in body


# ── رابطُ الصفحة: يحمل ما اختاره القارئُ قبله ─────────────────────────


def _page_link(request, number):
    template = Template("{% load sorting %}{% page_query " + str(number) + " %}")
    return template.render(Context({"request": request}))


def test_the_page_link_keeps_the_filter_the_reader_chose():
    """كان `?page=2` وحدَه: يختار السابعَ ثمّ ينقر «2» فتُفتح كلُّ المدرسة —
    والقائمةُ المنسدلةُ ما زالت تقول «السابع». شاشةٌ تكذب ولا تقول."""
    link = _page_link(_get(grade="G7", status="enrolled"), 2)

    assert "grade=G7" in link
    assert "status=enrolled" in link
    assert "page=2" in link


def test_the_page_link_keeps_the_sort_too():
    """وإلّا عاد الترتيبُ إلى أصله في الصفحة الثانية — فيتكرّر صفٌّ ويسقط آخر."""
    link = _page_link(_get(sort="student", dir="desc"), 3)

    assert "sort=student" in link
    assert "dir=desc" in link


def test_the_page_number_is_replaced_not_repeated():
    """`?page=2&page=5` رقمان لصفحةٍ واحدة — والقاعدةُ تأخذ أحدَهما بلا قاعدة."""
    link = _page_link(_get(page="2"), 5)

    assert link.count("page=") == 1
    assert "page=5" in link


def test_an_arabic_filter_survives_the_link():
    link = _page_link(_get(q="أحمد"), 2)

    assert "q=" in link and "page=2" in link
