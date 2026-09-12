"""الأجنحةُ الخمسة — خمسٌ وعشرون شعبةً بلا تكرارٍ ولا فراغ، وثلاثٌ خارجَها بقرار.

الجناحُ نطاقُ مشرفه: عليه تُبنى القراءةُ والكتابةُ واعتمادُ العذر وصندوقُ
المخالفات في المراحل القادمة. فخطأٌ في الجدول هنا لا يظهر خطأً في الجدول —
يظهر مشرفاً يقرأ ملفَّ طالبٍ ليس في ممرّه، أو طالباً لا يقرؤه أحد.

ولذلك يحرس هذا الملفُّ ثلاثةَ أشياءَ لا شيئاً واحداً: أنّ الجدولَ يغطّي
الخمسَ والعشرين، وأنّ المستثنى **يُسمّى** لا يُسكت عنه، وأنّ الخصائصَ
المحسوبة (الجرسان والمرحلتان) تقول الحقيقةَ في الجناحين الشاذّين — فعليهما
ينكسر كلُّ تعميمٍ لاحق.
"""

import io

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction

from core.academic_calendar import academic_year_for_school
from core.management.commands.seed_wings import WINGS, wing_of_section
from core.models import ClassGroup, TimeBand, Wing
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

#: شُعبُ التربية الخاصّة — خارجَ الأجنحة بقرار الإدارة.
ESE_SECTIONS = [("G8", "ESE"), ("G9", "ESE"), ("G10", "ESE")]

#: جرسُ كلّ شعبة كما تنسبه `seed_time_bands` — تاسع 3·4 وحدَهما على جرسهما.
BAND_OF = {
    ("G9", "3"): "ninth",
    ("G9", "4"): "ninth",
}


def _band_code(grade, section):
    if (grade, section) in BAND_OF:
        return "ninth"
    return "ground" if grade in ("G7", "G8", "G9") else "secondary"


def _level(grade):
    return "prep" if grade in ("G7", "G8", "G9") else "sec"


@pytest.fixture
def year(school):
    return academic_year_for_school(school)


@pytest.fixture
def sections(school, year):
    """الثمانُ والعشرون شعبةً كما في المدرسة: خمسٌ وعشرون وثلاثُ تربيةٍ خاصّة."""
    bands = {
        code: TimeBand.objects.create(school=school, code=code, name=code, order=order)
        for order, code in enumerate(("ground", "ninth", "secondary"), start=1)
    }
    made = {}
    for grade, section in [pair for *_head, pairs in WINGS for pair in pairs] + ESE_SECTIONS:
        made[(grade, section)] = ClassGroupFactory(
            school=school,
            grade=grade,
            section=section,
            level_type=_level(grade),
            academic_year=year,
            time_band=bands[_band_code(grade, section)],
            has_own_timetable=section == "ESE",
        )
    return made


def _seed(*args):
    out = io.StringIO()
    call_command("seed_wings", *args, stdout=out)
    return out.getvalue()


def _wing(school, code, year):
    return Wing.objects.get(school=school, code=code, academic_year=year)


class TestTheTableCoversTheSchool:
    def test_the_table_holds_exactly_twenty_five_sections(self):
        assert len(wing_of_section()) == 25, "الجدولُ خمسٌ وعشرون شعبةً — لا أكثرَ ولا أقلّ"

    def test_no_section_sits_in_two_wings(self):
        """`wing_of_section` قاموسٌ يبتلع المكرَّر صامتاً — فيُعدُّ الخامُّ لا هو."""
        pairs = [pair for *_head, pairs in WINGS for pair in pairs]

        assert len(pairs) == len(set(pairs)), "شعبةٌ في جناحين — القاموسُ كان يُخفيها"

    def test_each_wing_holds_five(self):
        for code, _name, _floor, _order, pairs in WINGS:
            assert len(pairs) == 5, f"{code}: خمسُ شُعبٍ لكلّ جناح"


class TestTheSeedIsIdempotent:
    def test_the_five_wings_appear(self, school, sections, year):
        _seed()

        wings = Wing.objects.filter(school=school, academic_year=year)
        assert [w.code for w in wings.order_by("order")] == ["w1", "w2", "w3", "w4", "w5"]
        assert [w.floor for w in wings.order_by("order")] == [
            "ground",
            "ground",
            "first",
            "first",
            "first",
        ]

    def test_seeding_twice_changes_nothing(self, school, sections, year):
        _seed("--assign")
        before = (
            dict(ClassGroup.objects.filter(school=school).values_list("id", "wing_id")),
            set(Wing.objects.values_list("id", flat=True)),
        )

        second = _seed("--assign")

        after = (
            dict(ClassGroup.objects.filter(school=school).values_list("id", "wing_id")),
            set(Wing.objects.values_list("id", flat=True)),
        )
        assert after == before
        assert "created=0 updated=0 unchanged=5" in second

    def test_a_dry_run_writes_nothing(self, school, sections):
        report = _seed("--assign", "--dry-run")

        assert "DRY-RUN" in report
        assert not Wing.objects.exists(), "جفافُ التشغيل يعني قاعدةً كما كانت"
        assert not ClassGroup.objects.exclude(wing=None).exists()

    def test_without_assign_the_wings_exist_but_no_section_moves(self, school, sections):
        _seed()

        assert Wing.objects.count() == 5
        assert not ClassGroup.objects.exclude(wing=None).exists(), "النسبةُ تحتاج --assign"


class TestTheTwentyFiveAreAssigned:
    def test_every_regular_section_lands_in_its_wing(self, school, sections, year):
        _seed("--assign")

        table = wing_of_section()
        for (grade, section), klass in sections.items():
            if section == "ESE":
                continue
            klass.refresh_from_db()
            assert klass.wing is not None, f"{grade}/{section} بلا جناح"
            assert klass.wing.code == table[(grade, section)]

    def test_twenty_five_and_not_one_more(self, school, sections):
        _seed("--assign")

        assert ClassGroup.objects.exclude(wing=None).count() == 25


class TestTheExcludedAreNamedNotSilenced:
    """الفارغُ المقصودُ والفارغُ المنسيُّ يبدوان سواءً في القاعدة — فيُفرَّقان بالقول."""

    def test_special_education_keeps_no_wing(self, school, sections):
        _seed("--assign")

        for pair in ESE_SECTIONS:
            sections[pair].refresh_from_db()
            assert sections[pair].wing is None

    def test_the_report_names_each_excluded_section(self, school, sections):
        report = _seed("--assign")

        assert "خارجَ الأجنحة بقرار" in report
        for grade, _section in ESE_SECTIONS:
            assert f"{grade.removeprefix('G')}/ESE" in report

    def test_a_section_missing_from_the_table_is_flagged_loudly(self, school, sections, year):
        """شعبةٌ جديدةٌ تُفتح ولا تُضاف إلى الجدول — لا تُنسب بحدسٍ ولا تُبتلع."""
        ClassGroupFactory(
            school=school, grade="G7", section="9", level_type="prep", academic_year=year
        )

        report = _seed("--assign")

        assert "شعبةٌ بلا جناحٍ في الجدول: 7/9" in report
        assert "وبلا جناح 1" in report


class TestTheOddWingsBreakEveryGeneralisation:
    def test_wing_three_rings_two_bells(self, school, sections, year):
        """9/3 و9/4 على جرس التاسع و10/1–3 على الثانويّ — فلا يُقال فيه رقمُ حصّة."""
        _seed("--assign")

        wing = _wing(school, "w3", year)
        assert [b.code for b in wing.time_bands] == ["ninth", "secondary"]
        assert wing.is_split_band is True

    def test_a_single_bell_wing_says_so(self, school, sections, year):
        _seed("--assign")

        assert _wing(school, "w1", year).is_split_band is False

    def test_wing_three_spans_two_stages(self, school, sections, year):
        _seed("--assign")

        assert _wing(school, "w3", year).levels == {"prep", "sec"}

    def test_wing_five_is_wholly_secondary(self, school, sections, year):
        _seed("--assign")

        assert _wing(school, "w5", year).levels == {"sec"}

    def test_wing_one_is_wholly_preparatory(self, school, sections, year):
        _seed("--assign")

        assert _wing(school, "w1", year).levels == {"prep"}


class TestTheCountIsTheEnrolled:
    def test_only_active_enrolments_count(self, school, sections, year):
        _seed("--assign")
        klass = sections[("G7", "1")]
        StudentEnrollmentFactory(student=UserFactory(), class_group=klass)
        StudentEnrollmentFactory(student=UserFactory(), class_group=klass, is_active=False)

        assert _wing(school, "w1", year).student_count == 1

    def test_a_wing_with_nobody_counts_zero(self, school, sections, year):
        _seed("--assign")

        assert _wing(school, "w2", year).student_count == 0


class TestTheSupervisorIsNotAnyUser:
    def test_an_admin_supervisor_passes(self, school, admin_supervisor_user, year):
        wing = Wing(
            school=school,
            code="w1",
            name="جناح 1",
            academic_year=year,
            supervisor=admin_supervisor_user,
        )

        wing.full_clean()  # لا يرفع

    def test_the_admin_deputy_passes_too(self, school, year):
        """النائبُ الإداريُّ يرث المشرف في الصلاحيّات — فيصحّ أن يحمل جناحاً عند النقص."""
        user = UserFactory(full_name="النائب الإداريّ")
        MembershipFactory(
            user=user, school=school, role=RoleFactory(school=school, name="vice_admin")
        )

        Wing(
            school=school, code="w1", name="جناح 1", academic_year=year, supervisor=user
        ).full_clean()

    def test_a_teacher_is_refused(self, school, teacher_user, year):
        wing = Wing(
            school=school, code="w1", name="جناح 1", academic_year=year, supervisor=teacher_user
        )

        with pytest.raises(ValidationError) as err:
            wing.full_clean()
        assert "supervisor" in err.value.message_dict

    def test_a_supervisor_of_another_school_is_refused(self, school, year):
        from tests.conftest import SchoolFactory

        other = SchoolFactory(code="OTHER")
        stranger = UserFactory(full_name="مشرفُ مدرسةٍ أخرى")
        MembershipFactory(
            user=stranger, school=other, role=RoleFactory(school=other, name="admin_supervisor")
        )

        with pytest.raises(ValidationError):
            Wing(
                school=school, code="w1", name="جناح 1", academic_year=year, supervisor=stranger
            ).full_clean()

    def test_a_wing_without_a_supervisor_is_saveable(self, school, year):
        """جناحٌ بلا مشرفٍ حالةٌ تُعرض وتُنبَّه، لا حالةٌ يُمنع حفظُها."""
        Wing(school=school, code="w1", name="جناح 1", academic_year=year).full_clean()


class TestOnePersonOneWing:
    def test_nobody_holds_two_wings_in_one_year(self, school, admin_supervisor_user, year):
        Wing.objects.create(
            school=school,
            code="w1",
            name="جناح 1",
            academic_year=year,
            supervisor=admin_supervisor_user,
        )

        with pytest.raises(IntegrityError), transaction.atomic():
            Wing.objects.create(
                school=school,
                code="w2",
                name="جناح 2",
                academic_year=year,
                supervisor=admin_supervisor_user,
            )

    def test_two_wings_may_both_await_a_supervisor(self, school, year):
        """`NULL` لا يساوي `NULL` — ولو ساواه لتعذّر بذرُ خمسةٍ بلا أسماء."""
        Wing.objects.create(school=school, code="w1", name="جناح 1", academic_year=year)
        Wing.objects.create(school=school, code="w2", name="جناح 2", academic_year=year)

        assert Wing.objects.filter(supervisor=None).count() == 2

    def test_the_same_code_returns_next_year(self, school, year):
        """«جناح 1» سجلُّ عامٍ لا سجلُّ مبنى — وقيدٌ بلا عامٍ يمنع فتحَ القادم."""
        Wing.objects.create(school=school, code="w1", name="جناح 1", academic_year=year)

        Wing.objects.create(school=school, code="w1", name="جناح 1", academic_year="2099-2100")

        assert Wing.objects.filter(school=school, code="w1").count() == 2

    def test_the_same_code_twice_in_one_year_is_refused(self, school, year):
        Wing.objects.create(school=school, code="w1", name="جناح 1", academic_year=year)

        with pytest.raises(IntegrityError), transaction.atomic():
            Wing.objects.create(school=school, code="w1", name="جناح آخر", academic_year=year)

    def test_the_holder_may_move_to_another_wing(self, school, admin_supervisor_user, year):
        """القيدُ يمنع الجمعَ لا النقل — وإلّا تعذّر تبديلُ المشرفين بين الممرّات."""
        first = Wing.objects.create(
            school=school,
            code="w1",
            name="جناح 1",
            academic_year=year,
            supervisor=admin_supervisor_user,
        )
        second = Wing.objects.create(school=school, code="w2", name="جناح 2", academic_year=year)

        first.supervisor = None
        first.save(update_fields=["supervisor"])
        second.supervisor = admin_supervisor_user
        second.save(update_fields=["supervisor"])

        assert _wing(school, "w2", year).supervisor == admin_supervisor_user
