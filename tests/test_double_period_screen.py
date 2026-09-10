"""[SCHEDULE] شاشةُ ازدواج المادّة شعبةً شعبة.

    قرارُ الشعبة يسبق قرارَ المادّة — والتباعدُ يعلوهما.

الحقلُ `SubjectClassAssignment.double_period` قائمٌ منذ 2026-09-02 ويقرؤه
المولّد، لكنّ طريقَه كان لوحةَ الإدارة وحدَها. فمن عمل من المنصّة لم يرَ إلّا
مفتاحَ المادّة العامّ — والحاجةُ إلى التخصيص قائمة: الفنّيّةُ مزدوجةٌ في
الإعداديّ، وتكنولوجيا المعلومات وعلومُ الحاسب في شُعب التكنولوجيّ وحدَها.

وأخطرُ ما يُحرَس هنا أنّ الشاشةَ **لا تَعِد بما لا يقع**: الشعبةُ التي يسري
عليها تباعدُ الأيّام (HC18) تُبنى مفردةً في المولّد مهما كُتب في حقلها، فتُعرض
مُعلَّمةً ولا يُفتح لها اختيار — وزرٌّ لا يُطاع هو خطأُ `ART`/`TECH` نفسُه قبل
إصلاحه.
"""

import pytest
from django.urls import reverse

from operations.models import Subject, SubjectClassAssignment

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


# ── تجهيز ────────────────────────────────────────────────────────────


@pytest.fixture
def school(db):
    from core.models import School

    return School.objects.create(name="مدرسة الشحانية", code="SHH-DBL")


def a_user(school, name, role_name):
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    role = RoleFactory(school=school, name=role_name)
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def vice(db, school):
    return a_user(school, "النائب الأكاديميّ", "vice_academic")


@pytest.fixture
def teacher(db, school):
    return a_user(school, "معلّم الفنّيّة", "teacher")


@pytest.fixture
def art(db, school):
    """الفنّيّةُ مزدوجةٌ بإعداد المادّة، ومتباعدةٌ في الثانويّ وحدَه."""
    return Subject.objects.create(
        school=school,
        name_ar="الفنون البصرية",
        code="ART",
        requires_double_period=True,
        spread_days_scope="sec",
    )


def a_class(school, grade, section, level, track=""):
    from core.models import ClassGroup

    return ClassGroup.objects.create(
        school=school,
        grade=grade,
        section=section,
        level_type=level,
        track=track,
        academic_year=YEAR,
    )


def assign(school, subject, class_group, teacher, **kw):
    return SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        subject=subject,
        class_group=class_group,
        teacher=teacher,
        weekly_periods=2,
        **kw,
    )


@pytest.fixture
def prep_row(db, school, art, teacher):
    return assign(school, art, a_class(school, "G8", "1", "prep"), teacher)


@pytest.fixture
def sec_row(db, school, art, teacher):
    return assign(school, art, a_class(school, "G11", "1", "sec", "technology"), teacher)


def url(subject):
    """الرابطُ بعامه صراحةً — فمدرسةُ الاختبار بلا تقويم، وافتراضُ العام يرتدّ."""
    return f"{reverse('subject_double_periods', args=[subject.id])}?year={YEAR}"


# ── الصلاحيّة ────────────────────────────────────────────────────────


def test_a_teacher_may_not_open_the_screen(client_as, teacher, art):
    assert client_as(teacher).get(url(art)).status_code == 403


def test_the_vice_academic_opens_it(client_as, vice, art, prep_row):
    response = client_as(vice).get(url(art))

    assert response.status_code == 200
    assert "الفنون البصرية" in response.content.decode()


# ── ما تعرضه الشاشة ─────────────────────────────────────────────────


def test_a_row_that_follows_the_subject_shows_the_subject_decision(client_as, vice, art, prep_row):
    """`None` في الحقل ليس «مفردة» بل «اتبع المادّة» — والمادّةُ مزدوجة."""
    rows = client_as(vice).get(url(art)).context["rows"]

    assert prep_row.double_period is None
    assert [r["effective"] for r in rows] == [True]
    assert [r["spread"] for r in rows] == [False]


def test_a_section_decision_overrides_the_subject(client_as, vice, school, art, teacher):
    row = assign(school, art, a_class(school, "G8", "2", "prep"), teacher, double_period=False)

    (shown,) = client_as(vice).get(url(art)).context["rows"]

    assert shown["assignment"].pk == row.pk
    assert shown["effective"] is False, "قرارُ الشعبة يسبق قرارَ المادّة"


def test_spread_days_beat_both_decisions(client_as, vice, school, art, teacher):
    """الثانويُّ متباعدٌ — فلا ازدواجَ فيه ولو كُتب في حقل الشعبة صراحةً."""
    assign(school, art, a_class(school, "G12", "1", "sec"), teacher, double_period=True)

    (shown,) = client_as(vice).get(url(art)).context["rows"]

    assert shown["spread"] is True
    assert shown["effective"] is False, "القيدُ الصلبُ يعلو الترجيح"


def test_the_screen_marks_the_spread_row_so_the_button_does_not_lie(client_as, vice, sec_row, art):
    page = client_as(vice).get(url(art)).content.decode()

    assert "التباعدُ يعلوه" in page
    assert "disabled" in page, "لا يُفتح اختيارٌ لا أثرَ له"


# ── الحفظ ────────────────────────────────────────────────────────────


def test_saving_writes_the_three_states(client_as, vice, school, art, teacher):
    follow = assign(school, art, a_class(school, "G7", "1", "prep"), teacher, double_period=True)
    single = assign(school, art, a_class(school, "G7", "2", "prep"), teacher)

    client_as(vice).post(
        url(art),
        {"year": YEAR, f"dp_{follow.id}": "", f"dp_{single.id}": "0"},
    )

    follow.refresh_from_db()
    single.refresh_from_db()
    assert follow.double_period is None, "الفارغُ يعني «اتبع المادّة» لا «مفردة»"
    assert single.double_period is False


def test_saving_records_who_decided(client_as, vice, prep_row, art):
    client_as(vice).post(url(art), {"year": YEAR, f"dp_{prep_row.id}": "1"})

    prep_row.refresh_from_db()
    assert prep_row.double_period is True
    assert prep_row.updated_by_id == vice.id, "قرارٌ بلا صاحبٍ لا يُراجَع"


def test_an_unknown_value_is_ignored_not_written(client_as, vice, prep_row, art):
    client_as(vice).post(url(art), {"year": YEAR, f"dp_{prep_row.id}": "ربما"})

    prep_row.refresh_from_db()
    assert prep_row.double_period is None


def test_the_generator_reads_what_the_screen_wrote(client_as, vice, school, art, teacher):
    """الحاسمُ: ما يُحفظ من الشاشة هو ما يبني به المولّدُ مهمّتَه.

    والمزدوجةُ مهمّةٌ واحدةٌ تشغل خانتين، والمفردةُ مهمّتان — فالفرقُ يُرى
    في عدد المهامّ لا في الرايةِ وحدَها.
    """
    from operations.scheduler import build_tasks

    row = assign(school, art, a_class(school, "G9", "1", "prep"), teacher)

    before = [t for t in build_tasks(school, YEAR) if t.subject_code == "ART"]
    assert [t.prefers_double for t in before] == [True], "اتبع المادّة: مهمّةٌ مزدوجةٌ واحدة"
    assert before[0].span == 2

    client_as(vice).post(url(art), {"year": YEAR, f"dp_{row.id}": "0"})

    after = [t for t in build_tasks(school, YEAR) if t.subject_code == "ART"]
    assert [t.prefers_double for t in after] == [
        False,
        False,
    ], "المادّةُ مزدوجةٌ والشعبةُ قالت لا — فالقولُ للشعبة، وحصّتان مفردتان"
