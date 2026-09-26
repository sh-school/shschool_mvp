"""صفحةُ جداول المعلّمين والشُّعب: ما على الشاشة يطابق ما في الورقة، والأقسامُ مطويّةٌ افتراضاً (LAY-11).

النمطُ `layout-report` (`docs/design/page_layouts.md` §7.7): وثيقةٌ تُقرأ ثمّ تُطبع، وقبولُها «ما على الشاشة
يطابق ما يُطبع». وكانت الشاشةُ بلا شريط «من هو» (التخصّص والمنسّق والنصاب) ولا عنوان الجدول والعام، فشكا
المالكُ (2026-09-26) أنّ جداولها «ليس فيها معلوماتٌ كافيةٌ مثل PDF» — وأنّ الصفحةَ طويلةٌ بعشراتِ جداولَ مفتوحة.

الحارسُ **يقيس** ولا يُقاس بالنظر: يستخرج حقولَ شريط الورقة من ردّها الفعليّ ويشترط كلَّ قيمةٍ منها في
بطاقة الشاشة لصاحبها؛ ويقرأ القالبين مصدراً فيشترط أن يشتركا في جزئيّةٍ واحدةٍ للشريط (لا نسختين تنحرفان).
ما يخصّ الورقَ وحدَه (ترويسةُ الوزارة والشعارُ وتاريخُ الطباعة وذيلُها) معلَنٌ هنا صراحةً، وكلُّ بندٍ فيه
يُتحقَّق أنّه في الورقة فعلاً — فلا تبقى قائمةُ الاستثناء تكذب.
"""

import re
from datetime import time
from pathlib import Path

import pytest
from django.urls import reverse

from core.models import Department, Membership
from operations.models import ScheduleSlot, Subject
from tests.conftest import ClassGroupFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parent.parent
SCREEN = ROOT / "templates" / "schedule" / "pages_view.html"
SCREEN_BODY = ROOT / "templates" / "schedule" / "partials" / "page_screen_body.html"
PAPER = ROOT / "templates" / "schedule" / "print_pages.html"
CSS = ROOT / "static" / "css" / "custom" / "32-modules-3.css"
WHO = "schedule/partials/page_who.html"
YEAR = "2026-2027"

#: ما يخصّ الورقَ المطبوعَ وحدَه — لا يُطلب على الشاشة (المنصّةُ نفسُها ترويستُها).
PAPER_ONLY = (
    'class="ministry"',  # ترويسةُ الوزارة الرسميّة
    'class="print-emblem"',  # الشعار
    "تاريخ الطباعة:",  # ختمُ الطباعة في الذيل
    'class="page-footer"',
)


@pytest.fixture
def arts(school):
    return Department.objects.create(
        school=school, name="الفنون البصرية", code="art", sort_order=10
    )


def _lesson(school, teacher, group=None, *, day=0, period=1):
    subject, _ = Subject.objects.get_or_create(school=school, name_ar="الرياضيات", code="MAT")
    return ScheduleSlot.objects.create(
        school=school,
        class_group=group
        or ClassGroupFactory(school=school, grade="G8", level_type="prep", academic_year=YEAR),
        teacher=teacher,
        subject=subject,
        day_of_week=day,
        period_number=period,
        start_time=time(7, 30),
        end_time=time(8, 15),
        academic_year=YEAR,
        is_active=True,
    )


def _register(user, school, department, specialty):
    membership = Membership.objects.filter(user=user, school=school, is_active=True).first()
    membership.department_obj = department
    membership.specialty = specialty
    membership.save(update_fields=["department_obj", "specialty"])


def _text(html: str) -> str:
    """نصُّ المقطع بلا وسوم — للمقارنة بالقيمة لا بالتنسيق."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _who_of_paper(paper_html: str) -> str:
    return _text(re.search(r'<div class="who[^"]*">(.*?)</div>', paper_html, re.S).group(1))


def _cards(screen_html: str) -> list[str]:
    """كلُّ بطاقةٍ على الشاشة: ما بين ابتداء `<details` وانتهائها."""
    return re.findall(r"<details\b.*?</details>", screen_html, re.S)


@pytest.fixture
def teacher_page(client, school, principal_user, teacher_user, arts):
    arts.head = principal_user
    arts.save(update_fields=["head"])
    _register(teacher_user, school, arts, "إدارة الأعمال")
    _lesson(school, teacher_user)
    client.force_login(principal_user)
    query = {"kind": "teachers", "year": YEAR}
    screen = client.get(reverse("schedule_pages"), query).content.decode()
    paper = client.get(reverse("schedule_pages_paper"), query).content.decode()
    return screen, paper, teacher_user


# ══════════════════════ تكافؤ الحقول ═════════════════════════════════════


def test_the_two_surfaces_share_one_who_bar_partial():
    """لا نسختان للشريط: من كتب حقلاً في إحداهما دون الأخرى انحرفت الشاشةُ عن الورق كما كانت."""
    assert WHO in PAPER.read_text(encoding="utf-8")
    assert WHO in SCREEN_BODY.read_text(encoding="utf-8")
    for template in (SCREEN, SCREEN_BODY, PAPER):
        assert 'class="who' not in template.read_text(
            encoding="utf-8"
        ), f"{template.name}: الشريطُ يُكتب في {WHO} وحدَه"


def test_every_field_of_the_papers_who_bar_is_on_the_screen_card(teacher_page):
    screen, paper, teacher = teacher_page
    fields = [
        teacher.full_name,
        "إدارة الأعمال",
        "الفنون البصرية",
        "المنسّق:",
        "النصاب الأسبوعيّ: 1 حصة",
    ]
    bar = _who_of_paper(paper)
    card = _text(next(c for c in _cards(screen) if teacher.full_name in c))
    for field in fields:
        assert field in bar, f"الحقلُ «{field}» غيرُ موجودٍ في شريط الورقة — حدِّث القائمة"
        assert field in card, f"الحقلُ «{field}» في الورقة ومفقودٌ من بطاقة الشاشة"


def test_the_class_bar_carries_the_class_and_its_lesson_count_on_both(
    client, school, principal_user, teacher_user
):
    group = ClassGroupFactory(school=school, grade="G8", level_type="prep", academic_year=YEAR)
    _lesson(school, teacher_user, group)
    client.force_login(principal_user)
    query = {"kind": "classes", "year": YEAR}

    screen = client.get(reverse("schedule_pages"), query).content.decode()
    paper = client.get(reverse("schedule_pages_paper"), query).content.decode()

    bar, card = _who_of_paper(paper), _text(_cards(screen)[0])
    for field in ("عدد الحصص: 1", group.label_with_track):
        assert field in bar and field in card


def test_the_document_title_school_and_year_are_on_the_screen_once(teacher_page, school):
    screen, paper, _ = teacher_page
    title = "الجدول الأسبوعي للمعلّم"
    assert title in paper and title in _text(screen)
    assert school.name in _text(screen) and YEAR in screen
    assert screen.count(title) == 1, "العنوانُ الرسميّ مرّةً في الصفحة لا في كلّ بطاقة"


def test_the_paper_only_list_is_true_and_stays_off_the_screen(teacher_page):
    screen, paper, _ = teacher_page
    for item in PAPER_ONLY:
        assert item in paper, f"«{item}» ليس في الورقة — احذفه من PAPER_ONLY"
        assert item not in screen, f"«{item}» مخصَّصٌ للورق فلا يتكرّر على الشاشة"


# ══════════════════════ الطيّ والألوان ═══════════════════════════════════


def test_every_card_starts_folded_and_the_toggle_is_wired(teacher_page):
    screen, _, _ = teacher_page
    assert _cards(screen), "لا بطاقات"
    assert not re.search(r"<details[^>]*\bopen\b", screen), "الافتراضُ مطويّ (قرار 2026-09-26)"
    button = re.search(r'<button[^>]*id="pages-fold-all"[^>]*>', screen).group(0)
    assert 'aria-expanded="false"' in button and 'aria-controls="pages-list"' in button
    assert 'id="pages-list"' in screen


def test_the_screen_writes_no_details_by_hand():
    """الطيُّ من `section_card foldable` — `<details>` يدويّاً تمنعه سقّاطةُ الهويّة."""
    for template in (SCREEN, SCREEN_BODY):
        assert "<details" not in template.read_text(encoding="utf-8")
    assert "foldable=True" in SCREEN.read_text(encoding="utf-8")


def test_a_teacher_card_takes_the_department_color_token_not_a_local_hex(teacher_page):
    screen, _, _ = teacher_page
    # كودُ القسم `art` يُترجَم إلى مفتاح لونٍ مركزيّ (core/dept_colors.py) لا إلى صنفٍ محلّيّ.
    assert 'class="pages-screen__item is-full dept-arts"' in screen
    rules = "".join(
        re.findall(r"\.pages-screen__item[^{]*\{[^}]*\}", CSS.read_text(encoding="utf-8"))
    )
    assert rules and not re.search(r"#[0-9a-fA-F]{3,8}\b", rules), "لونٌ حرفيٌّ — استعمل رموز الهويّة"


def test_the_department_tint_keeps_the_text_readable_in_both_themes():
    """المزيجُ `--t` (22% من لون القسم مع السطح) خلفيّةُ شريط «من هو» وعمودِ الأيّام — والنصُّ فوقه ≥ 4.5:1
    لكلّ الأقسام الخمسة عشر نهاراً وليلاً (قيس 2026-09-26: الأدنى 6.32 لـ`--maroon-fg` ليلاً على biology).
    وهذا لا يقيسه `test_contrast_ratios` لأنّه لا يقرأ خلفيّةً هي `color-mix` بمتغيّرٍ يُكتب على العنصر."""
    from core.dept_colors import DEPT_KEY_OF_CODE, OTHER
    from tests import css_contrast as contrast
    from tests.css_source import read_css

    css = read_css()
    light, _ = contrast.token_table(css)
    dark = {**light, **contrast.dark_overrides(css)}
    keys = set(DEPT_KEY_OF_CODE.values()) | {OTHER}
    for theme, tokens in (("نهاراً", light), ("ليلاً", dark)):
        for key in sorted(keys):
            tint = contrast.resolve(
                f"color-mix(in srgb, var(--dept-{key}) 22%, var(--surface))", tokens
            )
            for text in ("--text-primary", "--maroon-fg"):
                fg = contrast.resolve(f"var({text})", tokens)
                assert contrast.ratio(fg, tint) >= 4.5, f"{theme}: {text} على قسم {key}"
