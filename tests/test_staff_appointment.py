"""[STAFF] تعيينُ منتسبٍ ومغادرتُه — قرارٌ يُوثَّق لا صفٌّ يُضاف ويُحذف.

الثوابتُ التي تحرسها هذه الاختبارات:

    Appointment ≠ INSERT        مرجعُ القرار لازمٌ كما لزم في المغادرة
    Departure   ≠ DELETE        العضويّةُ تُطفأ ويبقى تاريخُ صاحبها
    شخصٌ واحدٌ حسابٌ واحد        وليُّ أمرٍ عُيّن معلّماً لا يُنشأ له ثانٍ
    القسمُ لأهل التدريس         ولا يخالف المسمّى الوظيفيّ

وأخطرُ ما يُحرَس أنّ المغادرةَ لا تمحو: من نُقل هذا الصيفَ له خمسٌ وعشرون
حصّةً في جدول العام الماضي — ومحوُ عضويّته يقطع تلك الحصص عن صاحبها.
"""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from core.models import CustomUser, Department, Membership
from staff_affairs import appointments

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


# ── تجهيز ────────────────────────────────────────────────────────────


@pytest.fixture
def school(db):
    from core.models import School

    return School.objects.create(name="مدرسة الشحانية", code="SHH-APP")


@pytest.fixture
def maths(db, school):
    return Department.objects.create(school=school, name="الرياضيات", code="math", sort_order=1)


def a_user(school, name, role_name, national_id="10000000001"):
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    role = RoleFactory(school=school, name=role_name)
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def principal(db, school):
    return a_user(school, "المدير", "principal", national_id="10000000002")


def appoint(school, by, **kw):
    fields = {
        "national_id": "29012345678",
        "full_name": "المعلّم الجديد",
        "role_name": "teacher",
        "reference": "قرار تعيين 2026/12",
        "joined_on": timezone.localdate(),
        "by": by,
    }
    fields.update(kw)
    return appointments.appoint(school=school, **fields)


# ══════════════════════════════════════════════════════════════════════
#  التعيينُ قرار
# ══════════════════════════════════════════════════════════════════════


def test_an_appointment_creates_the_account_and_the_membership(school, principal, maths):
    membership = appoint(school, principal, department=maths)

    assert membership.user.full_name == "المعلّم الجديد"
    assert membership.role.name == "teacher"
    assert membership.department_obj == maths
    assert membership.appointment_reference == "قرار تعيين 2026/12"
    assert membership.is_active and membership.left_at is None


def test_the_new_account_has_no_usable_password(school, principal):
    """يُعرَف في النظام ولا يُدخَل به حتّى تُصدَر له كلمةُ مرور."""
    membership = appoint(school, principal)

    assert not membership.user.has_usable_password()


def test_an_appointment_without_a_reference_is_refused(school, principal):
    with pytest.raises(ValidationError) as caught:
        appoint(school, principal, reference="  ")

    assert "reference" in caught.value.message_dict
    assert not CustomUser.objects.filter(national_id="29012345678").exists()


def test_a_department_is_refused_for_a_non_teaching_role(school, principal, maths):
    with pytest.raises(ValidationError):
        appoint(school, principal, role_name="nurse", department=maths)


def test_a_student_role_is_not_an_appointment(school, principal):
    """سجلُّ الطلاب بابُه غيرُ باب الكادر."""
    with pytest.raises(ValidationError):
        appoint(school, principal, role_name="student")


def test_an_existing_person_gets_a_second_membership_not_a_second_account(school, principal):
    """وليُّ أمرٍ عُيّن معلّماً — حسابٌ واحدٌ بعضويّتين."""
    parent = a_user(school, "وليُّ الأمر", "parent", national_id="29099999999")

    membership = appoint(school, principal, national_id="29099999999", full_name="وليُّ الأمر")

    assert membership.user_id == parent.id
    assert CustomUser.objects.filter(national_id="29099999999").count() == 1
    assert Membership.objects.filter(user=parent, school=school, is_active=True).count() == 2


def test_appointing_the_same_role_twice_is_refused(school, principal):
    appoint(school, principal)

    with pytest.raises(ValidationError):
        appoint(school, principal)


# ══════════════════════════════════════════════════════════════════════
#  المغادرةُ تُسجَّل ولا تمحو
# ══════════════════════════════════════════════════════════════════════


def test_a_departure_keeps_the_membership_and_records_its_decision(school, principal):
    membership = appoint(school, principal)
    today = timezone.localdate()

    appointments.depart(
        membership=membership,
        on=today,
        reason="transfer",
        reference="قرار نقل 2026/44",
        note="إلى مدرسة الوكرة",
    )

    membership.refresh_from_db()
    assert membership.is_active is False
    assert membership.left_at == today
    assert membership.departure_reference == "قرار نقل 2026/44"
    assert Membership.objects.filter(pk=membership.pk).exists(), "تُطفأ ولا تُمحى"


def test_a_departure_without_a_reference_is_refused(school, principal):
    membership = appoint(school, principal)

    with pytest.raises(ValidationError):
        appointments.depart(membership=membership, reason="transfer", reference="")

    membership.refresh_from_db()
    assert membership.is_active is True


def test_the_account_is_disabled_when_no_membership_remains(school, principal):
    membership = appoint(school, principal)

    appointments.depart(membership=membership, reason="transfer", reference="قرار 9")

    membership.user.refresh_from_db()
    assert membership.user.is_active is False, "لا بابَ مفتوحٌ لمن غادر"


def test_the_account_stays_open_while_another_membership_lives(school, principal):
    """معلّمٌ ووليُّ أمر: انتهاءُ عضويّة التدريس لا يُغلق حسابَه كوليّ أمر."""
    a_user(school, "وليُّ الأمر", "parent", national_id="29088888888")
    membership = appoint(school, principal, national_id="29088888888", full_name="وليُّ الأمر")

    appointments.depart(membership=membership, reason="transfer", reference="قرار 10")

    membership.user.refresh_from_db()
    assert membership.user.is_active is True


# ══════════════════════════════════════════════════════════════════════
#  الشاشة
# ══════════════════════════════════════════════════════════════════════


def test_the_register_holds_every_staff_category(client_as, school, principal):
    """السجلُّ لكادر المدرسة كلِّه — تدريسيّاً وإداريّاً وخدماتٍ مساندة."""
    a_user(school, "الممرّض", "nurse", national_id="29011111111")
    a_user(school, "أمين مصادر التعلّم", "librarian", national_id="29011111112")
    a_user(school, "مشرف النقل", "bus_supervisor", national_id="29011111113")

    body = client_as(principal).get(reverse("staff_affairs:staff_list")).content.decode()

    for name in ("المدير", "الممرّض", "أمين مصادر التعلّم", "مشرف النقل"):
        assert name in body


def test_students_and_parents_are_not_in_the_staff_register(client_as, school, principal):
    """بابُهم «شؤون الطلبة» — قرارُ المستخدم 2026-09-06."""
    a_user(school, "الطالب", "student", national_id="29022222222")
    a_user(school, "وليُّ الأمر", "parent", national_id="29022222223")

    body = client_as(principal).get(reverse("staff_affairs:staff_list")).content.decode()

    assert "المدير" in body
    assert "الطالب" not in body
    assert "وليُّ الأمر" not in body


def test_the_appointment_screen_writes_through_the_service(client_as, school, principal, maths):
    response = client_as(principal).post(
        reverse("staff_affairs:staff_appoint"),
        {
            "national_id": "29033333333",
            "full_name": "المعلّمة الجديدة",
            "role_name": "teacher",
            "department": str(maths.id),
            "joined_on": timezone.localdate().isoformat(),
            "reference": "قرار تعيين 2026/13",
            "employee_number": "",
            "email": "",
            "phone": "",
            "note": "",
        },
    )

    assert response.status_code == 302
    membership = Membership.objects.get(user__national_id="29033333333")
    assert membership.department_obj == maths
    assert membership.appointment_reference == "قرار تعيين 2026/13"


def test_the_screen_refuses_an_appointment_without_a_reference(client_as, school, principal):
    response = client_as(principal).post(
        reverse("staff_affairs:staff_appoint"),
        {
            "national_id": "29044444444",
            "full_name": "بلا قرار",
            "role_name": "teacher",
            "joined_on": timezone.localdate().isoformat(),
            "reference": "",
        },
    )

    assert response.status_code == 200
    assert not CustomUser.objects.filter(national_id="29044444444").exists()


def test_the_departure_screen_records_the_decision(client_as, school, principal):
    membership = appoint(school, principal)
    today = timezone.localdate()

    response = client_as(principal).post(
        reverse("staff_affairs:staff_depart", args=[membership.user_id]),
        {
            "on": today.isoformat(),
            "reason": "transfer",
            "reference": "قرار نقل 2026/45",
            "note": "",
        },
    )

    assert response.status_code == 302
    membership.refresh_from_db()
    assert membership.is_active is False and membership.departure_reference == "قرار نقل 2026/45"


# ══════════════════════════════════════════════════════════════════════
#  إلغاءُ مغادرةٍ سُجّلت بالخطأ
# ══════════════════════════════════════════════════════════════════════


def test_a_mistaken_departure_is_undone_and_the_correction_is_recorded(school, principal):
    membership = appoint(school, principal)
    appointments.depart(membership=membership, reason="transfer", reference="قرار نقل 2026/50")

    appointments.reinstate(membership=membership, note="سُجّلت بالخطأ")

    membership.refresh_from_db()
    assert membership.is_active is True and membership.left_at is None
    assert membership.departure_reference == ""
    assert "أُلغيت مغادرة" in membership.appointment_note
    assert "سُجّلت بالخطأ" in membership.appointment_note, "التصحيحُ يُوثَّق كما وُثّق الخطأ"
    membership.user.refresh_from_db()
    assert membership.user.is_active is True


def test_reinstating_a_living_membership_is_refused(school, principal):
    membership = appoint(school, principal)

    with pytest.raises(ValidationError):
        appointments.reinstate(membership=membership)


def test_the_screen_undoes_the_departure(client_as, school, principal):
    membership = appoint(school, principal)
    appointments.depart(membership=membership, reason="transfer", reference="قرار 51")

    response = client_as(principal).post(
        reverse("staff_affairs:staff_reinstate", args=[membership.user_id]), {"note": "خطأ"}
    )

    assert response.status_code == 302
    membership.refresh_from_db()
    assert membership.is_active is True


def test_the_departed_are_listed_when_asked(client_as, school, principal):
    membership = appoint(school, principal)
    appointments.depart(membership=membership, reason="transfer", reference="قرار 52")
    client = client_as(principal)

    current = client.get(reverse("staff_affairs:staff_list")).content.decode()
    departed = client.get(reverse("staff_affairs:staff_list"), {"status": "left"}).content.decode()

    assert "المعلّم الجديد" not in current
    assert "المعلّم الجديد" in departed, "المغادرُ يُوجَد ليُصحَّح لا ليختفي"


# ══════════════════════════════════════════════════════════════════════
#  من له صفتان
# ══════════════════════════════════════════════════════════════════════


def test_the_profile_opens_for_someone_with_two_memberships(client_as, school, principal, maths):
    """موظّفٌ ابنُه في المدرسة له عضويّتان — والربطُ كان يُعيد صفّين فيسقط الطلب."""
    a_user(school, "المعلّم ووليُّ الأمر", "parent", national_id="29055555555")
    membership = appoint(
        school, principal, national_id="29055555555", full_name="المعلّم ووليُّ الأمر"
    )

    response = client_as(principal).get(
        reverse("staff_affairs:staff_profile", args=[membership.user_id])
    )

    assert response.status_code == 200
    assert "معلم" in response.content.decode(), "ويُقرأ دورُه من عضويّة الكادر"


def test_a_departure_does_not_touch_the_parent_membership(client_as, school, principal):
    """مغادرةُ الكادر لا تُخرج ابنَه من المدرسة."""
    a_user(school, "الموظّف ووليُّ الأمر", "parent", national_id="29066666666")
    membership = appoint(
        school, principal, national_id="29066666666", full_name="الموظّف ووليُّ الأمر"
    )

    client_as(principal).post(
        reverse("staff_affairs:staff_depart", args=[membership.user_id]),
        {
            "on": timezone.localdate().isoformat(),
            "reason": "transfer",
            "reference": "قرار 53",
            "note": "",
        },
    )

    assert Membership.objects.filter(
        user_id=membership.user_id, role__name="parent", is_active=True
    ).exists()


# ══════════════════════════════════════════════════════════════════════
#  الملفُّ يُحرَّر — وكلُّ حفظٍ يُعرَف صاحبُه ووقتُه
# ══════════════════════════════════════════════════════════════════════


def test_saving_the_person_records_who_changed_what(client_as, school, principal):
    from staff_affairs import profile_service

    membership = appoint(school, principal)
    user = membership.user

    client_as(principal).post(
        reverse("staff_affairs:staff_profile_save", args=[user.id, "person"]),
        {
            "full_name": user.full_name,
            "employee_number": "12345",
            "email": "new@education.qa",
            "phone": "",
            "nationality": "",
            "professional_license_number": "",
            "professional_license_expiry": "",
        },
    )

    user.refresh_from_db()
    assert user.employee_number == "12345" and user.email == "new@education.qa"
    trail = profile_service.history(user, membership)
    assert any("الرقم الوظيفي" in line for row in trail for line in row["lines"])
    assert trail[0]["who"] == principal.full_name, "ويُختم باسم من حفظ"


def test_saving_nothing_writes_nothing(client_as, school, principal):
    from core.models import AuditLog

    membership = appoint(school, principal)
    user = membership.user
    before = AuditLog.objects.filter(object_id=str(user.id), action="update").count()

    client_as(principal).post(
        reverse("staff_affairs:staff_profile_save", args=[user.id, "person"]),
        {
            "full_name": user.full_name,
            "employee_number": user.employee_number,
            "email": user.email,
            "phone": user.phone,
            "nationality": user.nationality,
            "professional_license_number": "",
            "professional_license_expiry": "",
        },
    )

    after = AuditLog.objects.filter(object_id=str(user.id), action="update").count()
    assert after == before, "حفظٌ بلا تغييرٍ لا يُلوّث السجلّ"


def test_the_employment_section_saves_the_ministry_title(client_as, school, principal, maths):
    membership = appoint(school, principal, department=maths)

    client_as(principal).post(
        reverse("staff_affairs:staff_profile_save", args=[membership.user_id, "employment"]),
        {
            "job_title": "معلم رياضيات",
            "department": str(maths.id),
            "joined_at": membership.joined_at.isoformat(),
            "appointment_reference": membership.appointment_reference,
            "appointment_note": "",
        },
    )

    membership.refresh_from_db()
    assert membership.job_title == "معلم رياضيات"


def test_the_schedule_button_is_only_for_those_who_teach(client_as, school, principal):
    """ملاحظُ الطلبة والمحاسبُ لا حصصَ لهما — فلا مفتاحَ جدولٍ في ملفَّيهما."""
    observer = appoint(
        school,
        principal,
        national_id="29077777777",
        full_name="ملاحظ الطلبة",
        role_name="student_observer",
    )
    teacher = appoint(school, principal)
    client = client_as(principal)

    watcher_page = client.get(
        reverse("staff_affairs:staff_profile", args=[observer.user_id])
    ).content.decode()
    teacher_page = client.get(
        reverse("staff_affairs:staff_profile", args=[teacher.user_id])
    ).content.decode()

    assert "الجدول الأسبوعي" not in watcher_page
    assert "الجدول الأسبوعي" in teacher_page


def test_every_role_reads_in_arabic(client_as, school, principal):
    """الأسماءُ من قائمة الأدوار الرسميّة — لا رموزَ إنجليزيّةً في شاشةٍ عربيّة."""
    import re

    appoint(
        school,
        principal,
        national_id="29099000001",
        full_name="ملاحظ الطلبة",
        role_name="student_observer",
    )
    appoint(
        school,
        principal,
        national_id="29099000002",
        full_name="محضّر المختبر",
        role_name="lab_technician",
    )
    client = client_as(principal)

    for url in (reverse("staff_affairs:dashboard"), reverse("staff_affairs:staff_list")):
        body = client.get(url).content.decode()
        table = "\n".join(re.findall(r"<tbody[\s\S]*?</tbody>", body))
        for code in ("student_observer", "lab_technician", "services_worker", "messenger"):
            assert code not in table, f"{code} ظهر خاماً في {url}"
    assert "ملاحظ طلبة" in client.get(reverse("staff_affairs:dashboard")).content.decode()


def test_the_register_counts_people_not_memberships(client_as, school, principal):
    """من كان معلّماً ومنسّقاً رجلٌ واحد — لا سطران ولا رقمان."""
    from tests.conftest import MembershipFactory, RoleFactory

    membership = appoint(school, principal)
    MembershipFactory(
        user=membership.user, school=school, role=RoleFactory(school=school, name="coordinator")
    )

    body = client_as(principal).get(reverse("staff_affairs:staff_list")).content.decode()

    assert body.count(membership.user.full_name) == 1
