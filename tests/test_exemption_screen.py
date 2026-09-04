"""[SCHEDULE] شاشةُ التفريغات: التفريغُ غيابٌ، والقيدُ الدائمُ صفةٌ لازمة.

    «لا أولى ولا سابعة» ليس تفريغاً.

التفريغُ غيابٌ لسببٍ خارجيٍّ له مرجعٌ وتاريخ — دورةٌ في الوزارة، أو اجتماعُ
منسّقين. والمنعُ الدائمُ صفةٌ لازمةٌ لصاحبها لا تنقضي. وقد سكن الاثنان جدولاً
واحداً لأنّ المولّدَ لا يقرأ غيرَه، فامتلأت شاشةُ «تفريغات المعلمين» بعشرة
صفوفٍ لرجلٍ واحدٍ ليس مفرَّغاً في شيء.

فصارت الشاشةُ تعرض التفريغاتِ وحدَها، ويبقى أثرُ القيد في الجدول كاملاً:
`TeacherExemption.objects` هي مصدرُ المولّد، ولم يُمَسّ.
"""

import pytest

from operations.models import TeacherExemption
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


def exempt(school, teacher, *, day, period, reason):
    return TeacherExemption.objects.create(
        school=school,
        teacher=teacher,
        academic_year=YEAR,
        exemption_type="specific_period",
        day_of_week=day,
        period_number=period,
        reason=reason,
        source="school",
        is_active=True,
    )


@pytest.fixture
def teacher(school):
    user = UserFactory(full_name="معلّمٌ مقيَّد")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


def test_a_personal_rule_is_not_listed_as_a_release(school, teacher):
    exempt(school, teacher, day=0, period=1, reason="قرار إدارة المدرسة — لا أولى ولا سابعة")

    assert TeacherExemption.objects.count() == 1
    assert TeacherExemption.objects.releases().count() == 0


def test_a_real_release_is_still_listed(school, teacher):
    exempt(school, teacher, day=0, period=1, reason="اجتماعُ منسّقي المواد بالنائب الأكاديميّ")

    assert TeacherExemption.objects.releases().count() == 1


def test_the_generator_still_sees_the_personal_rule(school, teacher):
    """الحاسمُ: الإخفاءُ من الشاشة لا يرفع القيدَ عن الجدول."""
    row = exempt(school, teacher, day=0, period=7, reason="قرار إدارة المدرسة — لا أولى ولا سابعة")

    #: `objects` بلا `releases()` هو ما يقرؤه المولّد.
    assert row in TeacherExemption.objects.filter(school=school, academic_year=YEAR)


# ── مَن يجوز تفريغُه: كادرُ الجدولة وحدَه ─────────────────────────────


def _form(school, teacher_id):
    from operations.forms import TeacherExemptionForm

    return TeacherExemptionForm(
        {
            "teacher": str(teacher_id),
            "exemption_type": "full_day",
            # الأيّامُ قائمةٌ منذ صار الطلبُ يحمل أيّاماً عدّة.
            "day_of_week": ["0"],
            "reason": "دورةٌ في الوزارة",
            "source": "school",
        },
        school=school,
    )


def test_a_scheduling_staff_member_may_be_released(school, teacher):
    assert _form(school, teacher.id).is_valid()


def test_a_parent_in_the_same_school_may_not_be_released(school):
    """الشاشةُ لا تعرضه، والحدُّ يجب أن يمنعه — فالطلبُ يُبدَّل بيدٍ واحدة."""
    parent = UserFactory(full_name="وليُّ أمر")
    MembershipFactory(user=parent, school=school, role=RoleFactory(school=school, name="parent"))

    form = _form(school, parent.id)

    assert not form.is_valid()
    assert "teacher" in form.errors


def test_a_teacher_of_another_school_may_not_be_released(school):
    """عضويّةٌ مدرِّسةٌ هناك ليست إذناً هنا."""
    from tests.conftest import SchoolFactory

    other = SchoolFactory()
    stranger = UserFactory(full_name="معلّمُ مدرسةٍ أخرى")
    MembershipFactory(user=stranger, school=other, role=RoleFactory(school=other, name="teacher"))

    assert not _form(school, stranger.id).is_valid()


# ── خانةُ الحصّة تظهر حين تُختار «حصة محددة» ─────────────────────────


def test_the_period_field_hides_by_attribute_not_by_inline_style():
    """كانت الخانةُ مخفيّةً بـ`display:none` داخليّ، والسكربتُ يرفع `hidden` وحدَها —
    والنمطُ الداخليّ أقوى، فبقيت مخفيّةً ولم يجد المستخدمُ أين يختار الحصّة."""
    import pathlib
    import re

    html = pathlib.Path("templates/schedule/schedule_settings.html").read_text(encoding="utf-8")
    field = re.search(r'<div[^>]*id="period-field"[^>]*>', html).group(0)

    assert "hidden" in field
    assert "display:none" not in field

    js = pathlib.Path("static/js/actions.js").read_text(encoding="utf-8")
    assert (
        "DOMContentLoaded" in js.split('on("change", "data-show-when"')[1].split("/* ──")[0]
    ), "والحالةُ تُقيَّم عند التحميل — المتصفّحُ يعيد قيمةَ القائمة بلا حدث"


# ── أيّامٌ عدّةٌ بطلبٍ واحد، والمنسّقون مجموعةً ──────────────────────


def _principal(school):
    from django.test import Client

    user = UserFactory(full_name="المدير")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="principal"))
    client = Client()
    client.force_login(user)
    return client


def _post(client, **data):
    from django.urls import reverse

    base = {
        "year": YEAR,
        "exemption_type": "specific_period",
        "period_number": 1,
        "reason": "اجتماع",
        "source": "school",
    }
    return client.post(
        reverse("add_exemption"), {**base, **data}, follow=True, HTTP_HOST="localhost"
    )


def test_several_days_in_one_request(school, teacher):
    """الحصّةُ الأولى الأحدَ والثلاثاءَ: تفريغان بطلبٍ واحد لا طلبين."""
    response = _post(_principal(school), teacher=str(teacher.pk), day_of_week=[0, 2])

    rows = TeacherExemption.objects.filter(teacher=teacher).order_by("day_of_week")
    assert [(r.day_of_week, r.period_number) for r in rows] == [(0, 1), (2, 1)]
    assert "2 أيّام" in response.content.decode()


def test_several_periods_in_one_request(school, teacher):
    """الأولى والسابعةُ يومَ الأحد: تفريغان بطلبٍ واحد — الحصصُ مربّعاتٌ كالأيّام."""
    _post(_principal(school), teacher=str(teacher.pk), day_of_week=[0], period_number=[1, 7])

    rows = TeacherExemption.objects.filter(teacher=teacher).order_by("period_number")
    assert [(r.day_of_week, r.period_number) for r in rows] == [(0, 1), (0, 7)]


def test_a_full_day_ignores_the_ticked_periods(school, teacher):
    _post(
        _principal(school),
        teacher=str(teacher.pk),
        exemption_type="full_day",
        day_of_week=[3],
        period_number=[1, 2],
    )

    row = TeacherExemption.objects.get(teacher=teacher)
    assert (row.exemption_type, row.day_of_week, row.period_number) == ("full_day", 3, None)


def test_all_coordinators_as_one_choice(school, teacher):
    """«كلّ منسّقي المواد» خيارٌ في القائمة — فاجتماعُهم تفريغٌ واحدٌ لا اثنا عشر."""
    coordinator_role = RoleFactory(school=school, name="coordinator")
    coordinators = [UserFactory(full_name=f"منسّق {i}") for i in range(3)]
    for user in coordinators:
        MembershipFactory(user=user, school=school, role=coordinator_role)

    client = _principal(school)
    _post(client, teacher="coordinators", day_of_week=[0])

    assert TeacherExemption.objects.filter(day_of_week=0, period_number=1).count() == 3
    assert not TeacherExemption.objects.filter(teacher=teacher).exists(), "المعلّمُ ليس منسّقاً"

    # الإعادةُ بعد أن استجدّ منسّقٌ: يُضاف هو وحدَه ولا يُكرَّر القدماء.
    newcomer = UserFactory(full_name="منسّقٌ جديد")
    MembershipFactory(user=newcomer, school=school, role=coordinator_role)
    response = _post(client, teacher="coordinators", day_of_week=[0])

    assert TeacherExemption.objects.filter(day_of_week=0, period_number=1).count() == 4
    assert "3 مكرَّرٌ" in response.content.decode()


def test_the_screen_offers_the_group_and_the_days_and_no_reference(school):
    from django.urls import reverse

    body = (
        _principal(school)
        .get(reverse("schedule_settings") + f"?year={YEAR}", HTTP_HOST="localhost")
        .content.decode()
    )

    assert 'value="coordinators"' in body
    assert body.count('type="checkbox" name="day_of_week"') == 5
    assert body.count('type="checkbox" name="period_number"') == 7
    assert "source_reference" not in body and "مرجع القرار" not in body
