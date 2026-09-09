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


def test_the_screen_shades_a_grid_instead_of_multiplying_days_by_periods():
    """الاستمارةُ صارت شبكةً (2026-09-09): «نوعُ التفريغ × الأيّام × الحصص»
    كان ضرباً يعجز عن خانتين متفرّقتين، فحلّ محلَّه تظليلٌ يُرسَل في حقلٍ واحد.

    وكان هنا اختبارٌ يحرس إخفاءَ خانة «الحصص» بـ`hidden` لا بنمطٍ داخليّ —
    والخانةُ نفسُها لم تعد قائمة، فيحرس مكانَها ما حلّ محلَّها.
    """
    import pathlib

    html = pathlib.Path("templates/schedule/schedule_settings.html").read_text(encoding="utf-8")

    assert 'id="exemption-grid"' in html, "موضعُ الشبكة يُحمَّل عند اختيار المعلّم"
    assert 'name="slots"' in html, "والمظلَّلُ يُرسَل في حقلٍ واحد"
    assert 'id="period-field"' not in html, "ولا تبقى خانةُ الحصص القديمة"

    partial = pathlib.Path("templates/schedule/partials/exemption_grid.html").read_text(
        encoding="utf-8"
    )
    assert 'data-slot="{{ cell.key }}"' in partial
    assert 'class="exg-all"' in partial, "وزرُّ اليوم الكامل عند رأس كلّ صفّ"


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

    assert 'value="coordinators"' in body, "والمجموعةُ تبقى: اجتماعُ المنسّقين طلبٌ واحد"
    # الأيّامُ والحصصُ لم تعودا مربّعاتٍ تُضرب: الشبكةُ تحملهما خانةً خانة.
    assert 'type="checkbox" name="day_of_week"' not in body
    assert 'type="checkbox" name="period_number"' not in body
    assert 'id="exemption-grid"' in body
    assert "source_reference" not in body and "مرجع القرار" not in body


# ── الحذفُ الجماعيّ: مربّعٌ لكلّ سطرٍ وزرٌّ واحد ──────────────────────


def _remove_selected(client, ids):
    from django.urls import reverse

    return client.post(
        reverse("remove_exemptions"),
        {"year": YEAR, "exemption_id": [str(i) for i in ids]},
        follow=True,
        HTTP_HOST="localhost",
    )


def test_selected_releases_are_cancelled_together(school, teacher):
    """عشرون تفريغاً فعلٌ واحدٌ في ذهن النائب — فلا عشرون نقرةً وتأكيداً."""
    rows = [exempt(school, teacher, day=0, period=p, reason="اجتماع") for p in (1, 2, 3)]

    _remove_selected(_principal(school), [rows[0].pk, rows[2].pk])

    for row in rows:
        row.refresh_from_db()
    assert [row.is_active for row in rows] == [False, True, False]


def test_a_release_of_another_school_is_untouched(school, teacher):
    """المعرِّفُ ليس إذناً: قيدُ المدرسة يمنع ولو حُزر."""
    from tests.conftest import SchoolFactory

    other = SchoolFactory()
    stranger = UserFactory(full_name="معلّمُ مدرسةٍ أخرى")
    MembershipFactory(user=stranger, school=other, role=RoleFactory(school=other, name="teacher"))
    theirs = exempt(other, stranger, day=0, period=1, reason="اجتماع")

    _remove_selected(_principal(school), [theirs.pk])

    theirs.refresh_from_db()
    assert theirs.is_active is True


def test_a_malformed_id_does_not_break_the_request(school, teacher):
    """نصٌّ ليس بـUUID كان يُسقط الاستعلامَ خطأَ خادمٍ لا رسالةً."""
    row = exempt(school, teacher, day=0, period=1, reason="اجتماع")

    response = _remove_selected(_principal(school), ["ليس-معرِّفاً", row.pk])

    assert response.status_code == 200
    row.refresh_from_db()
    assert row.is_active is False


def test_nothing_selected_says_so(school):
    response = _remove_selected(_principal(school), [])

    assert response.status_code == 200
    assert "لم يُحدَّد" in response.content.decode()


def test_a_teacher_may_not_cancel_releases(school, teacher):
    """البابُ للنائب والمدير — والمعلّمُ لا يرفع قيدَ نفسِه."""
    from django.test import Client

    row = exempt(school, teacher, day=0, period=1, reason="اجتماع")
    client = Client()
    client.force_login(teacher)

    _remove_selected(client, [row.pk])

    row.refresh_from_db()
    assert row.is_active is True


# ── تفضيلاتُ المعلّمين: تُحذف مختارةً كما تُلغى التفريغات ─────────────


def _preference(school, teacher):
    from operations.models import TeacherPreference

    return TeacherPreference.objects.create(
        school=school, teacher=teacher, academic_year=YEAR, max_daily_periods=3
    )


def _remove_preferences(client, ids):
    from django.urls import reverse

    return client.post(
        reverse("remove_preferences"),
        {"year": YEAR, "preference_id": [str(i) for i in ids]},
        follow=True,
        HTTP_HOST="localhost",
    )


def test_selected_preferences_are_deleted(school, teacher):
    from operations.models import TeacherPreference

    row = _preference(school, teacher)

    _remove_preferences(_principal(school), [row.pk])

    assert not TeacherPreference.objects.filter(pk=row.pk).exists()


def test_the_teacher_may_record_a_preference_again_after_deletion(school, teacher):
    """الحذفُ حذفٌ لا إطفاء: قيدُ التفرّد يمنع صفّاً ثانياً لو بقي الأوّل."""
    from operations.models import TeacherPreference

    _remove_preferences(_principal(school), [_preference(school, teacher).pk])

    assert TeacherPreference.objects.create(school=school, teacher=teacher, academic_year=YEAR).pk


def test_a_preference_of_another_school_is_untouched(school):
    from operations.models import TeacherPreference
    from tests.conftest import SchoolFactory

    other = SchoolFactory()
    stranger = UserFactory(full_name="معلّمُ مدرسةٍ أخرى")
    MembershipFactory(user=stranger, school=other, role=RoleFactory(school=other, name="teacher"))
    theirs = _preference(other, stranger)

    _remove_preferences(_principal(school), [theirs.pk])

    assert TeacherPreference.objects.filter(pk=theirs.pk).exists()


def test_a_teacher_may_not_delete_preferences(school, teacher):
    from django.test import Client

    from operations.models import TeacherPreference

    row = _preference(school, teacher)
    client = Client()
    client.force_login(teacher)

    _remove_preferences(client, [row.pk])

    assert TeacherPreference.objects.filter(pk=row.pk).exists()
