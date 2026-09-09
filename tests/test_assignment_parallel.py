"""[SCHEDULE] التوازي والازدواج في بطاقة الإسناد.

    مادّتان في خانةٍ واحدة — أو وسمٌ يتيمٌ يكذب على حساب الطاقة.

الشعبةُ تنقسم نصفين: قسمٌ إلى الفنون وقسمٌ إلى الكيمياء في التوقيت نفسه.
فحصّتان تُدرَّسان وخانةٌ واحدةٌ تُستهلك — `InstructionalPeriods ≠ OccupiedSlots`.

وثلاثةُ أشياءَ تُحرَس هنا:

  1. **الوسمُ لا يُمحى** — `apply_assignment` تكتب `parallel_group = tag` في كلّ
     حفظ، وافتراضُها فراغ. فتعديلُ عدد الحصص كان يمحو التوازيَ صامتاً.
  2. **الربطُ ثنائيّ** — الشريكةُ تُختار فيُوسَم الطرفان، ويُفكّ عنهما معاً.
     ومربّعٌ يوسم واحدةً يُولّد اليتيم، واليتيمُ لا يُخصَم من الطلب فيظهر
     «مطلوب 37 والسعة 35» بلا فائضٍ حقيقيّ.
  3. **الازدواجُ قرارُ الشعبة** — `double_period` على الإسناد يعلو إعدادَ
     المادّة: التكنولوجيا متباعدةٌ في السابع ومزدوجةٌ في الحادي عشر/1.
"""

import pytest
from django.urls import reverse

from operations.models import Subject, SubjectClassAssignment
from operations.services import CapacityCheckService
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


@pytest.fixture
def group(school):
    return ClassGroupFactory(school=school, grade="G11", level_type="sec", academic_year=YEAR)


@pytest.fixture
def teacher(school):
    user = UserFactory(full_name="معلّمُ الفنون")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


@pytest.fixture
def principal(school):
    user = UserFactory(full_name="مديرُ المدرسة")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="principal"))
    return user


def assign(school, group, teacher, name, periods, *, code="", tag="", double=None):
    subject, _ = Subject.objects.get_or_create(school=school, name_ar=name, defaults={"code": code})
    return SubjectClassAssignment.objects.create(
        school=school,
        class_group=group,
        subject=subject,
        teacher=teacher,
        weekly_periods=periods,
        academic_year=YEAR,
        parallel_group=tag,
        double_period=double,
    )


# ════════════════════ الطلبُ بالخانات لا بالحصص ════════════════════


def test_a_linked_pair_costs_one_slot_not_two(school, group, teacher):
    """المجموعةُ تستهلك أكبرَ نصابٍ فيها — لا مجموعَ نصابَي عضوَيها."""
    assign(school, group, teacher, "الفنون البصرية", 2, tag="par-11.1")
    assign(school, group, teacher, "الكيمياء", 2, tag="par-11.1")
    rows = list(SubjectClassAssignment.objects.filter(class_group=group))

    assert CapacityCheckService.slot_demand(rows) == 2


def test_an_orphan_tag_is_not_discounted(school, group, teacher):
    """الحاسمُ: وسمٌ بعضوٍ واحدٍ لا يخصم شيئاً — فيظهر فائضٌ سببُه الوسمُ لا النصاب."""
    assign(school, group, teacher, "الفنون البصرية", 2, tag="par-11.1")
    assign(school, group, teacher, "الكيمياء", 2)
    rows = list(SubjectClassAssignment.objects.filter(class_group=group))

    assert CapacityCheckService.slot_demand(rows) == 4


def test_the_warning_names_the_orphan(school, group, teacher):
    """التحذيرُ يقول السببَ لا يتركه للتخمين."""
    assign(school, group, teacher, "الفنون البصرية", 2, tag="par-11.1")
    assign(school, group, teacher, "الرياضيات", 34)
    rows = SubjectClassAssignment.objects.filter(class_group=group).select_related(
        "class_group", "subject"
    )

    over = CapacityCheckService.get_overcapacity_classes(rows)
    assert over and over[0]["orphan_parallels"] == ["الفنون البصرية"]


# ════════════════════ الربطُ ثنائيٌّ من الشاشة ════════════════════


def link(client, row, partner):
    return client.post(
        reverse("academic_management:assignment_set_parallel", args=[row.id]),
        {"partner": str(partner.id) if partner else "", "year": YEAR},
        HTTP_HOST="localhost",
    )


def test_choosing_a_partner_tags_both_rows(client, school, group, teacher, principal):
    art = assign(school, group, teacher, "الفنون البصرية", 2)
    chem = assign(school, group, teacher, "الكيمياء", 2)
    client.force_login(principal)

    link(client, art, chem)

    art.refresh_from_db(), chem.refresh_from_db()
    assert art.parallel_group and art.parallel_group == chem.parallel_group


def test_unlinking_clears_both_so_no_orphan_is_born(client, school, group, teacher, principal):
    """الحاسمُ: فكُّ الربط يرفع الوسمَ عن الطرفين — وإلّا بقي الآخرُ يتيماً."""
    art = assign(school, group, teacher, "الفنون البصرية", 2, tag="par-11.1")
    chem = assign(school, group, teacher, "الكيمياء", 2, tag="par-11.1")
    client.force_login(principal)

    link(client, art, None)

    art.refresh_from_db(), chem.refresh_from_db()
    assert (art.parallel_group, chem.parallel_group) == ("", "")


def test_a_partner_outside_the_class_is_refused(client, school, group, teacher, principal):
    art = assign(school, group, teacher, "الفنون البصرية", 2)
    other = ClassGroupFactory(school=school, grade="G12", level_type="sec", academic_year=YEAR)
    stranger = assign(school, other, teacher, "الأحياء", 2)
    client.force_login(principal)

    link(client, art, stranger)

    art.refresh_from_db(), stranger.refresh_from_db()
    assert (art.parallel_group, stranger.parallel_group) == ("", "")


def test_a_teacher_may_not_link(client, school, group, teacher):
    art = assign(school, group, teacher, "الفنون البصرية", 2)
    chem = assign(school, group, teacher, "الكيمياء", 2)
    client.force_login(teacher)

    link(client, art, chem)

    art.refresh_from_db()
    assert art.parallel_group == ""


# ════════════════════ الوسمُ لا يُمحى بتعديل الحصص ════════════════════


def test_editing_periods_keeps_the_parallel_tag(client, school, group, teacher, principal):
    """كان كلُّ تعديلٍ لعدد الحصص يمحو التوازيَ صامتاً."""
    art = assign(school, group, teacher, "الفنون البصرية", 2, tag="par-11.1")
    assign(school, group, teacher, "الكيمياء", 2, tag="par-11.1")
    client.force_login(principal)

    # العيبُ كان في المحو لا في الرقم: أيُّ حفظٍ يمرّ من هذا الباب كان يكتب
    # فراغاً فوق الوسم. فحفظٌ بالقيمة نفسِها يكفي لكشفه.
    client.post(
        reverse("academic_management:assignment_update_periods", args=[art.id]),
        {"weekly_periods": "2", "year": YEAR},
        HTTP_HOST="localhost",
    )

    art.refresh_from_db()
    assert art.parallel_group == "par-11.1"


# ════════════════════ الازدواجُ قرارُ الشعبة ════════════════════


def test_the_row_box_overrides_the_subject_default(client, school, group, teacher, principal):
    """`double_period` على الإسناد يعلو `Subject.requires_double_period`."""
    tech = assign(school, group, teacher, "التكنولوجيا", 2, code="TECH")
    tech.subject.requires_double_period = False
    tech.subject.save(update_fields=["requires_double_period"])
    client.force_login(principal)

    client.post(
        reverse("academic_management:assignment_toggle_double", args=[tech.id]),
        {"double": "1", "year": YEAR},
        HTTP_HOST="localhost",
    )

    tech.refresh_from_db()
    assert tech.double_period is True


def test_unticking_writes_false_not_none(client, school, group, teacher, principal):
    """يُكتب صريحاً: ما يراه المستخدمُ مطفأً يجب أن يُقرأ مطفأً، لا «اتبع المادّة»."""
    tech = assign(school, group, teacher, "التكنولوجيا", 2, code="TECH", double=True)
    client.force_login(principal)

    client.post(
        reverse("academic_management:assignment_toggle_double", args=[tech.id]),
        {"year": YEAR},
        HTTP_HOST="localhost",
    )

    tech.refresh_from_db()
    assert tech.double_period is False
