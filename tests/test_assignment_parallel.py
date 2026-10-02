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


#: خطّةٌ دراسيّةٌ لمادّة (لا يقبل `add_row` إلّا موادَّ الخطّة) — أدنى ما يلزم لهذا الملفّ.
def plan_row(school, subject, *, grade, periods=2, track=""):
    from academic_management.models import CurriculumPlan

    return CurriculumPlan.objects.create(
        school=school,
        academic_year=YEAR,
        grade=grade,
        track=track,
        subject=subject,
        weekly_periods=periods,
    )


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
    chem = assign(school, group, a_second_teacher(school, "معلّمُ الكيمياء"), "الكيمياء", 2)
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


# ════════════════════ الربطُ استبدالٌ لا دمج، ووسمٌ يخصّ الزوجَ وحدَه (D-04) ════════════════════


def test_choosing_a_new_partner_replaces_not_merges(client, school, group, teacher, principal):
    """اختيارُ شريكةٍ ثالثة يستبدل الثانية لا يدمج الثلاثَ في مجموعةٍ واحدة."""
    art = assign(school, group, teacher, "الفنون البصرية", 2)
    chem = assign(school, group, a_second_teacher(school, "معلّمُ الكيمياء"), "الكيمياء", 2)
    bio = assign(school, group, a_second_teacher(school, "معلّمُ الأحياء"), "الأحياء", 2)
    client.force_login(principal)
    link(client, art, chem)

    link(client, art, bio)

    art.refresh_from_db(), chem.refresh_from_db(), bio.refresh_from_db()
    assert art.parallel_group and art.parallel_group == bio.parallel_group
    assert chem.parallel_group == "", "الشريكةُ القديمةُ بقيت موسومةً وحدَها — دُمجت لا اسُتبدلت"
    assert art.parallel_group != chem.parallel_group


def test_two_pairs_in_the_same_class_get_different_tags(client, school, group, teacher, principal):
    art = assign(school, group, teacher, "الفنون البصرية", 2)
    chem = assign(school, group, a_second_teacher(school, "معلّمُ الكيمياء"), "الكيمياء", 2)
    other1 = a_second_teacher(school, "معلّمٌ ثانٍ")
    other2 = a_second_teacher(school, "معلّمٌ ثالث")
    tech = assign(school, group, other1, "التكنولوجيا", 2)
    pe = assign(school, group, other2, "التربية البدنية", 2)
    client.force_login(principal)

    link(client, art, chem)
    link(client, tech, pe)

    art.refresh_from_db(), tech.refresh_from_db()
    assert art.parallel_group and tech.parallel_group and art.parallel_group != tech.parallel_group


def test_the_same_teacher_may_not_hold_both_sides(school, group, teacher, principal):
    """F-16/D-08: معلّمٌ واحدٌ لطرفَي التوازي يمرّ صامتاً حتى الاعتماد ثمّ يسقط بخطأٍ لا يُفسَّر."""
    from academic_management import assignment_services as svc

    art = assign(school, group, teacher, "الفنون البصرية", 2)
    chem = assign(school, group, teacher, "الكيمياء", 2)

    with pytest.raises(svc.ValidationError):
        svc.set_parallel(art, chem, by=principal)

    art.refresh_from_db()
    assert art.parallel_group == ""


def test_mismatched_periods_are_refused_for_now(school, group, teacher, principal):
    """D-07: منعٌ مؤقّتٌ حتى يُصلَح حسابُ المولّد لمجموعاتٍ غيرِ متساوية (F-11)."""
    from academic_management import assignment_services as svc

    other = a_second_teacher(school, "معلّمٌ آخر")
    art = assign(school, group, teacher, "الفنون البصرية", 2)
    tech = assign(school, group, other, "التكنولوجيا", 3)

    with pytest.raises(svc.ValidationError):
        svc.set_parallel(art, tech, by=principal)


def test_mismatched_double_period_warns_but_still_links(school, group, teacher, principal):
    """D-06: الازدواجُ يختلف — حالُ 11/1 اليوم — يُحذَّر منه ولا يُمنع."""
    from academic_management import assignment_services as svc

    other = a_second_teacher(school, "معلّمٌ آخر")
    art = assign(school, group, teacher, "الفنون البصرية", 2, double=True)
    tech = assign(school, group, other, "التكنولوجيا", 2, double=False)

    _art, _tech, findings = svc.set_parallel(art, tech, by=principal)

    art.refresh_from_db(), tech.refresh_from_db()
    assert art.parallel_group and art.parallel_group == tech.parallel_group
    assert any(f.code == svc.PARALLEL_DOUBLE_MISMATCH for f in findings)


# ════════════════════ النقلُ عن منافسٍ موسومٍ يَرِث الوسمَ لا يمحوه ════════════════════


def test_transferring_a_parallel_subject_makes_the_new_teacher_inherit_the_tag(
    client, school, group, teacher, principal
):
    """حادثة 12/2 (2026-09-27): نقلُ التكنولوجيا عن معلّمٍ لآخر كان يكتب وسماً فارغاً فيُيتّم الفنّيّة."""
    art_subject = Subject.objects.create(school=school, name_ar="الفنون البصرية", code="ART")
    tech_subject = Subject.objects.create(school=school, name_ar="التكنولوجيا", code="TECH")
    plan_row(school, art_subject, grade=group.grade)
    plan_row(school, tech_subject, grade=group.grade)
    art = assign(school, group, teacher, "الفنون البصرية", 2, tag="par-11.1")
    tech = assign(school, group, teacher, "التكنولوجيا", 2, tag="par-11.1")
    new_teacher = UserFactory(full_name="معلّمٌ آخر")
    MembershipFactory(
        user=new_teacher, school=school, role=RoleFactory(school=school, name="teacher")
    )
    client.force_login(principal)
    before_demand = CapacityCheckService.slot_demand(
        list(SubjectClassAssignment.objects.filter(class_group=group))
    )

    client.post(
        reverse("academic_management:assignment_add_row", args=[new_teacher.id]),
        {
            "class_group": str(group.id),
            "subject": str(tech_subject.id),
            "confirm_transfer": "1",
            "year": YEAR,
        },
        HTTP_HOST="localhost",
    )

    art.refresh_from_db()
    tech.refresh_from_db()  # الآن غيرُ فعّال — نُقلت مادّتُه
    new_row = SubjectClassAssignment.objects.get(
        class_group=group, subject=tech_subject, teacher=new_teacher, is_active=True
    )
    assert new_row.parallel_group == "par-11.1", "المعلّمُ الجديدُ لم يرث وسمَ من نُقلت عنه المادّة"
    assert art.parallel_group == "par-11.1", "الشريكةُ يُتّمت رغم أنّها لم تُمسّ"
    after_demand = CapacityCheckService.slot_demand(
        list(SubjectClassAssignment.objects.filter(class_group=group))
    )
    assert after_demand == before_demand == 2, "النقلُ لا يغيّر طلبَ الشعبة بالخانات"


# ════════════════════ الحذفُ يرفع الوسمَ عن العضو الباقي وحدَه ════════════════════


def remove(client, row):
    return client.post(
        reverse("academic_management:assignment_remove_row", args=[row.id]),
        {"year": YEAR},
        HTTP_HOST="localhost",
    )


def test_deleting_one_of_a_pair_clears_the_survivors_tag_and_notes_it(
    client, school, group, teacher, principal
):
    """D-05: حذفُ أحد الطرفين كان يترك الآخرَ موسوماً وحدَه فيُجدول للشعبة كاملةً في خانة."""
    art = assign(school, group, teacher, "الفنون البصرية", 2, tag="par-11.1")
    tech = assign(school, group, teacher, "التكنولوجيا", 2, tag="par-11.1")
    client.force_login(principal)

    response = remove(client, tech)

    art.refresh_from_db()
    assert art.parallel_group == ""
    assert "رُفع وسمُ التوازي" in response.content.decode()


def a_second_teacher(school, name):
    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=role)
    return user


def test_deleting_one_of_a_group_of_three_does_not_clear_the_other_two(
    school, group, teacher, principal
):
    """المجموعةُ التي تبقى أكثرَ من عضوين بعد الحذف تبقى مجموعةً — ليست الوسمَ الأخير."""
    from academic_management import assignment_services as svc

    art = assign(school, group, teacher, "الفنون البصرية", 2, tag="par-11.1")
    other1 = a_second_teacher(school, "معلّمٌ ثانٍ")
    other2 = a_second_teacher(school, "معلّمٌ ثالث")
    tech = assign(school, group, other1, "التكنولوجيا", 2, tag="par-11.1")
    chem = assign(school, group, other2, "الكيمياء", 2, tag="par-11.1")

    svc.remove_assignment(assignment=tech, by=principal, reason="اختبار")

    art.refresh_from_db(), chem.refresh_from_db()
    assert art.parallel_group == "par-11.1" and chem.parallel_group == "par-11.1"


def test_deleting_an_untagged_row_clears_nothing(school, group, teacher, principal):
    from academic_management import assignment_services as svc

    row = assign(school, group, teacher, "الرياضيات", 2)

    _obj, cleared = svc.remove_assignment(assignment=row, by=principal, reason="اختبار")

    assert cleared is None


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


def test_editing_periods_through_the_screen_actually_writes_the_new_value(
    client, school, group, teacher, principal
):
    """W-20260928-001: حارسُ التزامن كان يرفض كلَّ كتابةٍ طازجةٍ خطأً (isoformat() مقابل str())،
    فيبدو التعديلُ من الشاشة ناجحاً بلا أثر — لم يكشفه اختبارٌ من قبل لأنّه لم يتحقّق من الرقم نفسِه."""
    art = assign(school, group, teacher, "الفنون البصرية", 2)
    client.force_login(principal)

    client.post(
        reverse("academic_management:assignment_update_periods", args=[art.id]),
        {"weekly_periods": "3", "year": YEAR},
        HTTP_HOST="localhost",
    )

    art.refresh_from_db()
    assert art.weekly_periods == 3


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
