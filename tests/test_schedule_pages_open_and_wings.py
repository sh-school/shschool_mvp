"""صفحاتُ جداول المعلّمين والشُّعب: الطيُّ للجدول العامّ للمعلّمين وحدَه، وما يختاره المستخدمُ من القائمة يُفتح، وللشُّعب أجنحتُها في القائمة (قرارُ المالك 2026-09-27).

- الجدولُ العامّ للمعلّمين (`kind=teachers&dept=all`): مطويٌّ افتراضاً (عشراتُ الجداول).
- قسمٌ من القائمة (مثلاً الرياضيات)، أو الشُّعب، أو جناحٌ، أو معلّمٌ بعينه: مفتوحٌ.
- الشُّعبُ تُعرض تحت جناحها بترتيب الأجنحة، و«خارج الأجنحة» (التربية الخاصة) أخيراً؛ وقائمةُ الجداول تحمل خيارَ كلّ جناح، ورابطُه يصفّي الصفحةَ والورقةَ والتنزيل.
"""

import re
from datetime import time

import pytest
from django.urls import reverse

from core.models import Department, Membership, Wing
from operations.models import ScheduleSlot, Subject
from tests.conftest import ClassGroupFactory

pytestmark = pytest.mark.django_db
YEAR = "2026-2027"


def _lesson(school, teacher, group, *, day=0, period=1):
    subject, _ = Subject.objects.get_or_create(school=school, name_ar="الرياضيات", code="MAT")
    return ScheduleSlot.objects.create(
        school=school,
        class_group=group,
        teacher=teacher,
        subject=subject,
        day_of_week=day,
        period_number=period,
        start_time=time(7, 30),
        end_time=time(8, 15),
        academic_year=YEAR,
        is_active=True,
    )


def _wing(school, code, name, order):
    return Wing.objects.create(school=school, code=code, name=name, order=order, academic_year=YEAR)


def _details(html: str) -> list[str]:
    return re.findall(r"<details\b[^>]*>", html)


@pytest.fixture
def maths(school, teacher_user):
    dept = Department.objects.create(school=school, name="الرياضيات", code="math", sort_order=1)
    membership = Membership.objects.filter(user=teacher_user, school=school, is_active=True).first()
    membership.department_obj = dept
    membership.save(update_fields=["department_obj"])
    return dept


@pytest.fixture
def wings(school, teacher_user):
    w1, w2 = _wing(school, "w1", "جناح 1", 1), _wing(school, "w2", "جناح 2", 2)
    a = ClassGroupFactory(
        school=school, grade="G7", section="1", level_type="prep", academic_year=YEAR, wing=w1
    )
    b = ClassGroupFactory(
        school=school, grade="G8", section="1", level_type="prep", academic_year=YEAR, wing=w2
    )
    special = ClassGroupFactory(
        school=school, grade="G7", section="9", level_type="prep", academic_year=YEAR, wing=None
    )
    for group in (a, b, special):
        _lesson(school, teacher_user, group, period=1 + [a, b, special].index(group))
    return w1, w2, (a, b, special)


def _get(client, user, **query):
    client.force_login(user)
    return client.get(reverse("schedule_pages"), {"year": YEAR, **query}).content.decode()


# ══════════════════════ الطيّ للعامّ وحدَه ═══════════════════════════════


def test_the_general_teachers_view_is_folded_by_default(
    client, principal_user, teacher_user, maths, wings
):
    html = _get(client, principal_user, kind="teachers", dept="all")
    assert _details(html) and not any(" open" in d for d in _details(html))
    assert 'aria-expanded="false"' in re.search(
        r'<button[^>]*id="pages-fold-all"[^>]*>', html
    ).group(0)


def test_a_chosen_department_is_open(client, principal_user, teacher_user, maths, wings):
    html = _get(client, principal_user, kind="teachers", dept="math")
    tags = _details(html)
    assert len(tags) == 2, "قسمٌ ومعلّمُه"
    assert all(" open" in d for d in tags), "قسمٌ من القائمة يُفتح — لا يُطوى"
    button = re.search(r'<button[^>]*id="pages-fold-all"[^>]*>(.*?)</button>', html, re.S)
    assert 'aria-expanded="true"' in button.group(0) and "طيّ الكلّ" in button.group(1)


def test_a_single_teacher_is_open(client, principal_user, teacher_user, maths, wings):
    html = _get(client, principal_user, kind="teachers", teacher=str(teacher_user.id))
    assert _details(html) and all(" open" in d for d in _details(html))


def test_the_classes_views_are_open(client, principal_user, teacher_user, wings):
    for query in ({"kind": "classes"}, {"kind": "classes", "wing": "w1"}):
        html = _get(client, principal_user, **query)
        assert _details(html) and all(" open" in d for d in _details(html)), query


# ══════════════════════ أجنحةُ الشُّعب ═══════════════════════════════════


def test_the_picker_lists_every_wing_and_the_wingless_group_last(client, principal_user, wings):
    html = _get(client, principal_user, kind="classes")
    picker = re.search(r'<select id="schedule-picker".*?</select>', html, re.S).group(0)
    labels = re.findall(
        r"<option[^>]*data-href=\"[^\"]*wing=([^&\"]*)[^\"]*\"[^>]*>\s*([^<]*)</option>", picker
    )
    assert [(code, name.strip()) for code, name in labels] == [
        ("w1", "جناح 1"),
        ("w2", "جناح 2"),
        ("none", "خارج الأجنحة"),
    ]
    assert "جداول شُعب الأجنحة" in picker


def test_all_school_classes_sit_under_their_wings_in_wing_order(client, principal_user, wings):
    html = _get(client, principal_user, kind="classes")
    titles = re.findall(r'<h2 class="ui-section__title">([^<]*)</h2>', html)
    wing_titles = [t for t in titles if t in ("جناح 1", "جناح 2", "خارج الأجنحة")]
    assert wing_titles == ["جناح 1", "جناح 2", "خارج الأجنحة"]


def test_a_wing_shows_only_its_classes_and_the_picker_selects_it(client, principal_user, wings):
    w1, _, (a, b, special) = wings
    html = _get(client, principal_user, kind="classes", wing="w1")
    assert a.label_with_track in html
    assert b.label_with_track not in html and special.label_with_track not in html
    assert "جداول شُعب جناح 1" in html
    option = re.search(r"<option[^>]*wing=w1[^>]*>", html).group(0)
    assert "selected" in option


def test_the_wingless_group_has_its_own_link(client, principal_user, wings):
    _, _, (a, b, special) = wings
    html = _get(client, principal_user, kind="classes", wing="none")
    assert special.label_with_track in html and a.label_with_track not in html


# ══════════════════════ لونُ الجناح — كالقسم، من لوحة الهويّة نفسِها (قرارُ المالك 2026-09-27) ══════


def test_each_wing_card_carries_its_own_color_class_like_a_department(
    client, principal_user, wings
):
    html = _get(client, principal_user, kind="classes")
    assert (
        '<div class="pages-screen__item pages-screen__dept is-full dept-math">' in html
    ), "جناح 1 (order=1) ← مفتاحُ math"
    assert (
        '<div class="pages-screen__item pages-screen__dept is-full dept-chemistry">' in html
    ), "جناح 2 (order=2) ← مفتاحُ chemistry"
    assert (
        '<div class="pages-screen__item pages-screen__dept is-full dept-other">' in html
    ), "خارج الأجنحة — لا لونَ يُخترع"


def test_the_five_wing_colors_are_all_distinct_and_reuse_the_department_palette(
    school, teacher_user
):
    """خمسةُ أجنحةٍ ثابتة (المواصفة)، لكلٍّ لونٌ من لوحة `--dept-*` نفسِها لا لوحةٌ ثانية، وكلُّها متمايزة."""
    from core.dept_colors import DEPT_KEY_OF_CODE, OTHER, WING_KEY_OF_ORDER, wing_key

    known_dept_keys = set(DEPT_KEY_OF_CODE.values()) | {OTHER}
    keys = [wing_key(n) for n in range(1, 6)]
    assert len(set(keys)) == 5, "الأجنحةُ الخمسة يجب أن تتمايز بصريّاً"
    assert OTHER not in keys, "لا جناحَ حقيقيّاً يأخذ لونَ «other» المحايد"
    assert set(keys) <= known_dept_keys, "ألوانُ الأجنحة من لوحة الأقسام نفسِها — لا لوحةٌ مخترَعة"
    assert WING_KEY_OF_ORDER[1] == keys[0]


def test_wing_key_falls_back_to_other_for_anything_outside_one_to_five():
    from core.dept_colors import OTHER, wing_key

    for bad in (0, -1, 6, 99, None, "", "abc"):
        assert wing_key(bad) == OTHER, bad


def test_an_unknown_wing_falls_back_to_the_whole_school_not_an_empty_page(
    client, principal_user, wings
):
    _, _, (a, b, special) = wings
    html = _get(client, principal_user, kind="classes", wing="w9")
    for group in (a, b, special):
        assert group.label_with_track in html


def test_the_wing_filter_reaches_the_paper_and_the_pdf_selection(client, principal_user, wings):
    _, _, (a, b, _special) = wings
    client.force_login(principal_user)
    paper = client.get(
        reverse("schedule_pages_paper"), {"kind": "classes", "wing": "w2", "year": YEAR}
    ).content.decode()
    assert b.label_with_track in paper and a.label_with_track not in paper
    screen = _get(client, principal_user, kind="classes", wing="w2")
    assert "wing=w2" in screen, "رابطُ التنزيل والإطارُ المخفيّ يحملان الجناح"


def test_a_year_without_wings_offers_no_wing_options(client, principal_user, school, teacher_user):
    group = ClassGroupFactory(
        school=school, grade="G8", section="3", level_type="prep", academic_year=YEAR, wing=None
    )
    _lesson(school, teacher_user, group)
    picker = re.search(
        r'<select id="schedule-picker".*?</select>',
        _get(client, principal_user, kind="classes"),
        re.S,
    ).group(0)
    assert "جداول شُعب الأجنحة" in picker and "wing=none" in picker and "wing=w" not in picker
