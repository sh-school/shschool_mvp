"""تغطيةُ الجناح — من يحمله في هذا اليوم، لا من يملكه في السجلّ.

الجناحُ نطاقُ مشرفه: غيابُه يوماً يعني خمسَ شُعبٍ لا يرصد غيابَها أحد، وعذراً
لا يعتمده أحد، وصندوقَ مخالفاتٍ لا يفتحه أحد. فلا يكفي حقلٌ بوليٌّ «غائب» —
يلزم **من** يحمله و**إلى متى**.

ولهذا التغطيةُ سجلٌّ زمنيٌّ لا حقلٌ على الجناح: من يقرأ غيابَ الأسبوع الماضي
يحتاج أن يعرف من كان يرصده، وحقلٌ يُكتب فوق سابقه لا يُجيب عن أمسِ. فالحرّاسُ
هنا على ثلاثة: أنّ `current_supervisor` تُجيب بالتاريخ، وأنّ القاعدةَ ترفض
تداخلَ مدّتين، وأنّ من لا يصلح بديلاً يُردّ في حقله لا بخطأٍ من المحرّك.
"""

import datetime as dt
import io

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.urls import reverse

from core.academic_calendar import academic_year_for_school
from core.management.commands.seed_wings import WINGS
from core.models import Wing, WingCoverage
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    UserFactory,
)
from wings.services import coverage_rows, floors_overview, substitute_pool

pytestmark = pytest.mark.django_db

MONDAY = dt.date(2026, 9, 14)
WEDNESDAY = dt.date(2026, 9, 16)
FRIDAY = dt.date(2026, 9, 18)
NEXT_WEEK = dt.date(2026, 9, 21)


def _level(grade):
    return "prep" if grade in ("G7", "G8", "G9") else "sec"


@pytest.fixture
def year(school):
    return academic_year_for_school(school)


@pytest.fixture
def staff(school):
    """طاقمٌ يكفي الحوضَ ومن هو خارجَه."""

    def make(name, role, national_id):
        user = UserFactory(full_name=name, national_id=national_id)
        MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
        return user

    return {
        "own1": make("أصيلُ الأوّل", "admin_supervisor", "29100000001"),
        "own2": make("أصيلُ الثاني", "admin_supervisor", "29100000002"),
        "spare": make("مشرفٌ بلا جناح", "admin_supervisor", "29100000003"),
        "worker": make("عاملُ خدمات", "services_worker", "29100000004"),
        "observer": make("ملاحظُ طلبة", "student_observer", "29100000005"),
        "teacher": make("معلّم", "teacher", "29100000006"),
        "nurse": make("ممرّض", "nurse", "29100000007"),
        "boss": make("المدير", "principal", "29100000008"),
        "deputy": make("النائبُ الأكاديميّ", "vice_academic", "29100000009"),
    }


@pytest.fixture
def wings(school, year, staff):
    for grade, section in [pair for *_head, pairs in WINGS for pair in pairs]:
        ClassGroupFactory(
            school=school,
            grade=grade,
            section=section,
            level_type=_level(grade),
            academic_year=year,
        )
    call_command("seed_wings", "--assign", stdout=io.StringIO())
    made = {w.code: w for w in Wing.objects.filter(school=school, academic_year=year)}
    made["w1"].supervisor = staff["own1"]
    made["w1"].save(update_fields=["supervisor"])
    made["w2"].supervisor = staff["own2"]
    made["w2"].save(update_fields=["supervisor"])
    return made


def _cover(wing, substitute, start=MONDAY, end=None, **extra):
    cover = WingCoverage(wing=wing, substitute=substitute, start_date=start, end_date=end, **extra)
    cover.full_clean()
    cover.save()
    return cover


class TestWhoHoldsTheWingToday:
    def test_without_coverage_the_holder_is_the_principal(self, wings, staff):
        assert wings["w1"].current_supervisor(MONDAY) == staff["own1"]

    def test_inside_the_period_the_holder_is_the_substitute(self, wings, staff):
        _cover(wings["w1"], staff["spare"], MONDAY, FRIDAY)

        assert wings["w1"].current_supervisor(WEDNESDAY) == staff["spare"]

    def test_the_bounds_are_inside_the_period(self, wings, staff):
        """يومُ البداية ويومُ النهاية من المدّة — فمن غطّى الاثنين غطّاه كلَّه."""
        _cover(wings["w1"], staff["spare"], MONDAY, FRIDAY)

        assert wings["w1"].current_supervisor(MONDAY) == staff["spare"]
        assert wings["w1"].current_supervisor(FRIDAY) == staff["spare"]

    def test_after_the_period_the_principal_returns(self, wings, staff):
        _cover(wings["w1"], staff["spare"], MONDAY, FRIDAY)

        assert wings["w1"].current_supervisor(NEXT_WEEK) == staff["own1"]

    def test_before_the_period_the_principal_still_holds(self, wings, staff):
        _cover(wings["w1"], staff["spare"], WEDNESDAY, FRIDAY)

        assert wings["w1"].current_supervisor(MONDAY) == staff["own1"]

    def test_an_open_period_has_no_horizon(self, wings, staff):
        """غيابٌ طارئٌ لا يُعرف مداه يومَ يقع — والتاريخُ يُكتب حين يعود صاحبُه."""
        _cover(wings["w1"], staff["spare"], MONDAY, None)

        assert wings["w1"].current_supervisor(dt.date(2027, 1, 1)) == staff["spare"]

    def test_a_wing_with_neither_holds_nobody(self, wings, staff):
        assert wings["w3"].supervisor is None
        assert wings["w3"].current_supervisor(MONDAY) is None

    def test_coverage_fills_a_vacant_wing(self, wings, staff):
        """جناحٌ بلا أصيلٍ يُغطّى — وهو أحدُ أسباب التغطية الأربعة."""
        _cover(wings["w3"], staff["spare"], MONDAY, reason="vacancy")

        assert wings["w3"].current_supervisor(MONDAY) == staff["spare"]

    def test_the_record_answers_about_yesterday_too(self, wings, staff):
        """حقلٌ يُكتب فوق سابقه لا يُجيب عن أمسِ — والسجلُّ يُجيب."""
        _cover(wings["w1"], staff["spare"], MONDAY, MONDAY)
        _cover(wings["w1"], staff["worker"], WEDNESDAY, FRIDAY)

        assert wings["w1"].current_supervisor(MONDAY) == staff["spare"]
        assert wings["w1"].current_supervisor(WEDNESDAY) == staff["worker"]
        assert wings["w1"].current_supervisor(NEXT_WEEK) == staff["own1"]


class TestTheDatabaseRefusesOverlap:
    def test_two_overlapping_periods_are_refused_by_postgres(self, wings, staff):
        """`clean()` وحدَه لا يكفي: كتابتان متزامنتان تمرّان عليه معاً ثمّ تقعان.

        فالقيدُ في القاعدة — وتداخلُ مدّتين يعني أنّ اثنين يحملان الجناحَ في
        يومٍ واحد، فيقرأ كلاهما ويكتب كلاهما ولا يُدرى من المسؤول.
        """
        _cover(wings["w1"], staff["spare"], MONDAY, FRIDAY)

        with pytest.raises(IntegrityError), transaction.atomic():
            WingCoverage.objects.create(
                wing=wings["w1"], substitute=staff["worker"], start_date=WEDNESDAY
            )

    def test_touching_periods_do_not_overlap(self, wings, staff):
        """تنتهي واحدةٌ الجمعةَ وتبدأ الأخرى الاثنين — لا تداخل."""
        _cover(wings["w1"], staff["spare"], MONDAY, FRIDAY)

        _cover(wings["w1"], staff["worker"], NEXT_WEEK, None)

        assert WingCoverage.objects.filter(wing=wings["w1"]).count() == 2

    def test_two_wings_may_be_covered_at_once(self, wings, staff):
        _cover(wings["w1"], staff["spare"], MONDAY, FRIDAY)

        _cover(wings["w2"], staff["worker"], MONDAY, FRIDAY)

        assert wings["w1"].current_supervisor(MONDAY) == staff["spare"]
        assert wings["w2"].current_supervisor(MONDAY) == staff["worker"]

    def test_the_end_may_not_precede_the_start(self, wings, staff):
        with pytest.raises(IntegrityError), transaction.atomic():
            WingCoverage.objects.create(
                wing=wings["w1"],
                substitute=staff["spare"],
                start_date=FRIDAY,
                end_date=MONDAY,
            )


class TestWhoMayStandIn:
    @pytest.mark.parametrize("who", ["spare", "worker", "observer"])
    def test_the_three_titles_the_principal_named(self, wings, staff, who):
        """مشرفٌ إداريٌّ · عاملُ خدماتٍ · ملاحظُ طلبة (قرار المدير 2026-09-12)."""
        _cover(wings["w1"], staff[who], MONDAY)

        assert wings["w1"].current_supervisor(MONDAY) == staff[who]

    @pytest.mark.parametrize("who", ["teacher", "nurse"])
    def test_whoever_is_outside_the_pool_is_refused(self, wings, staff, who):
        cover = WingCoverage(wing=wings["w1"], substitute=staff[who], start_date=MONDAY)

        with pytest.raises(ValidationError) as err:
            cover.full_clean()
        assert "substitute" in err.value.message_dict

    def test_the_principal_of_the_wing_is_not_its_own_substitute(self, wings, staff):
        cover = WingCoverage(wing=wings["w1"], substitute=staff["own1"], start_date=MONDAY)

        with pytest.raises(ValidationError) as err:
            cover.full_clean()
        assert "الأصيلُ نفسُه" in err.value.message_dict["substitute"][0]

    def test_nobody_covers_two_wings_at_once(self, wings, staff):
        """نقطةُ فشلٍ مضاعفةٌ في يومٍ واحد — ومن حمل جناحين لم يحمل أيّاً منهما."""
        _cover(wings["w1"], staff["spare"], MONDAY, FRIDAY)
        cover = WingCoverage(wing=wings["w2"], substitute=staff["spare"], start_date=WEDNESDAY)

        with pytest.raises(ValidationError) as err:
            cover.full_clean()
        assert "ولا تغطيتين لشخصٍ واحد" in err.value.message_dict["substitute"][0]

    def test_the_same_person_may_cover_twice_in_sequence(self, wings, staff):
        """المنعُ للتداخل لا للتكرار."""
        _cover(wings["w1"], staff["spare"], MONDAY, FRIDAY)

        _cover(wings["w2"], staff["spare"], NEXT_WEEK, None)

        assert WingCoverage.objects.filter(substitute=staff["spare"]).count() == 2

    def test_a_principal_of_one_wing_may_cover_another(self, wings, staff):
        """واقعٌ يقع: مشرفٌ يحمل جناحه وجناحَ زميلٍ غائب. يُسمح ويُوسَم."""
        _cover(wings["w2"], staff["own1"], MONDAY, FRIDAY)

        assert wings["w2"].current_supervisor(MONDAY) == staff["own1"]
        assert wings["w1"].current_supervisor(MONDAY) == staff["own1"]


class TestThePoolIsShownNotHidden:
    def test_the_pool_is_read_by_role_not_by_the_title_text(self, school, wings, staff):
        """المسمّى نصٌّ حرٌّ يُكتب «ملاحظ طلبه» بهاءٍ و«طلبة» بتاءٍ."""
        names = {row["user"].full_name for row in substitute_pool(school, on_date=MONDAY)}

        assert {"مشرفٌ بلا جناح", "عاملُ خدمات", "ملاحظُ طلبة"} <= names
        assert "معلّم" not in names
        assert "ممرّض" not in names

    def test_the_canteen_supervisor_is_not_in_the_pool(self, school, wings, staff):
        """يحمل لفظَ «مشرف» وليس من الحوض — فحوضٌ بمطابقةِ كلمةٍ كان سيضمّه."""
        canteen = UserFactory(full_name="مشرفُ المقصف", national_id="29100000010")
        MembershipFactory(
            user=canteen,
            school=school,
            role=RoleFactory(school=school, name="canteen_supervisor"),
        )

        names = {row["user"].full_name for row in substitute_pool(school, on_date=MONDAY)}

        assert "مشرفُ المقصف" not in names

    def test_the_busy_are_shown_busy_not_hidden(self, school, wings, staff):
        """الحجبُ يُخفي السبب: من لا يجد زميلَه يظنّه غيرَ مؤهّل وهو مشغول."""
        _cover(wings["w1"], staff["spare"], MONDAY, FRIDAY)

        row = next(
            r for r in substitute_pool(school, on_date=WEDNESDAY) if r["user"] == staff["spare"]
        )

        assert row["busy_with"] == wings["w1"].name

    def test_a_wings_own_principal_is_flagged_in_its_own_list(self, school, wings, staff):
        row = next(
            r
            for r in substitute_pool(school, wing=wings["w1"], on_date=MONDAY)
            if r["user"] == staff["own1"]
        )

        assert row["is_own_supervisor"] is True

    def test_a_principal_of_another_wing_is_flagged_as_such(self, school, wings, staff):
        row = next(
            r
            for r in substitute_pool(school, wing=wings["w2"], on_date=MONDAY)
            if r["user"] == staff["own1"]
        )

        assert row["principal_of"] == wings["w1"].name
        assert row["is_own_supervisor"] is False


class TestTheScreens:
    def test_the_wings_page_shows_the_substitute_as_the_holder(self, wings, staff, school, year):
        _cover(wings["w1"], staff["spare"], MONDAY, FRIDAY)

        panels = floors_overview(school, year, dt.datetime.combine(WEDNESDAY, dt.time(9, 45)))
        card = next(c for p in panels for c in p.wings if c.wing.code == "w1")

        assert card.holder == staff["spare"]
        assert card.coverage is not None

    def test_the_wings_page_shows_the_principal_when_uncovered(self, wings, staff, school, year):
        panels = floors_overview(school, year, dt.datetime.combine(WEDNESDAY, dt.time(9, 45)))
        card = next(c for p in panels for c in p.wings if c.wing.code == "w1")

        assert card.holder == staff["own1"]
        assert card.coverage is None

    def test_the_coverage_rows_separate_the_active_from_the_past(self, school, wings, staff, year):
        _cover(wings["w1"], staff["spare"], MONDAY, MONDAY)
        _cover(wings["w1"], staff["worker"], WEDNESDAY, FRIDAY)

        row = next(r for r in coverage_rows(school, year, WEDNESDAY) if r["wing"].code == "w1")

        assert row["coverage"].substitute == staff["worker"]
        assert [c.substitute for c in row["history"]] == [staff["spare"]]

    def test_the_deputies_reach_the_screen(self, client_as, wings, staff):
        """لوحةُ جانغو مقصورةٌ على المدير والمطوّر — فبلا هذه الشاشة لا يستطيع
        النائبان تعيينَ بديل، وهما اثنان من الأربعة الذين أذن لهم المدير."""
        response = client_as(staff["deputy"]).get(reverse("wings:coverage"))

        assert response.status_code == 200

    def test_a_supervisor_may_not_appoint_his_own_substitute(self, client_as, wings, staff):
        response = client_as(staff["own1"]).get(reverse("wings:coverage"))

        assert response.status_code in (302, 403)

    def test_assigning_through_the_screen_moves_the_scope(self, client_as, wings, staff):
        client = client_as(staff["boss"])

        client.post(
            reverse("wings:coverage_assign", args=["w1"]),
            {
                "substitute": str(staff["worker"].id),
                "reason": "absence",
                "start_date": MONDAY.isoformat(),
                "end_date": FRIDAY.isoformat(),
                "note": "إجازةٌ اضطراريّة",
            },
        )

        assert wings["w1"].current_supervisor(WEDNESDAY) == staff["worker"]

    def test_the_screen_refuses_an_ineligible_substitute(self, client_as, wings, staff):
        client = client_as(staff["boss"])

        client.post(
            reverse("wings:coverage_assign", args=["w1"]),
            {"substitute": str(staff["teacher"].id), "start_date": MONDAY.isoformat()},
        )

        assert not WingCoverage.objects.exists()

    def test_ending_closes_the_period_and_keeps_the_record(self, client_as, wings, staff):
        """الحذفُ يمحو من حمل الجناحَ أمسِ — فتُغلق المدّةُ ويبقى السجلّ."""
        cover = _cover(wings["w1"], staff["spare"], MONDAY, None)

        client_as(staff["boss"]).post(
            reverse("wings:coverage_end", args=[cover.id]), {"end_date": WEDNESDAY.isoformat()}
        )

        cover.refresh_from_db()
        assert cover.end_date == WEDNESDAY
        assert cover.ended_by == staff["boss"]
        assert WingCoverage.objects.count() == 1

    def test_ending_today_keeps_the_substitute_until_the_day_is_out(self, client_as, wings, staff):
        """قرارُ الخارطة §2: الإنهاءُ يسري بنهاية اليوم لا لحظتَه، كي لا يُقطع
        عملٌ نصفَ منجَز."""
        cover = _cover(wings["w1"], staff["spare"], MONDAY, None)

        client_as(staff["boss"]).post(
            reverse("wings:coverage_end", args=[cover.id]), {"end_date": WEDNESDAY.isoformat()}
        )

        assert wings["w1"].current_supervisor(WEDNESDAY) == staff["spare"]
        assert wings["w1"].current_supervisor(WEDNESDAY + dt.timedelta(days=1)) == staff["own1"]

    def test_ending_never_moves_the_end_before_the_start(self, client_as, wings, staff):
        cover = _cover(wings["w1"], staff["spare"], WEDNESDAY, None)

        client_as(staff["boss"]).post(
            reverse("wings:coverage_end", args=[cover.id]), {"end_date": MONDAY.isoformat()}
        )

        cover.refresh_from_db()
        assert cover.end_date == WEDNESDAY
