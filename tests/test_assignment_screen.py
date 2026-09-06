"""[ASSIGNMENT] شاشةُ الإسناد الواحدة — بطاقةٌ لكلّ معلّم، ودورةٌ لكلّ خطّة.

الثوابتُ التي تحرسها هذه الاختبارات:

    شاشةٌ واحدة              لا «توزيعاتٌ» تكتب و«إسنادٌ» يعرض
    المنسّقُ قسمُه            والنائبُ والمديرُ كلُّ الأقسام
    الحصصُ من الخطّة          لا من ذاكرة المُدخِل
    مسودّة ← رفعٌ ← مراجعةٌ ← اعتماد   ولا قفزَ فوق مرحلة
    المعتمَدُ لا يُكتب فوقه   يُفتح بإصدارٍ جديد

وأخطرُ ما يُحرَس أنّ الشاشةَ **لا تكتب بيدها**: كلُّ صفٍّ يمرّ بـ
`assignment_service`، فتبقى الفحوصُ والتدقيقُ واحدةً مهما تعدّدت الأبواب.
"""

import pytest
from django.urls import reverse

from academic_management.models import (
    APPROVED,
    DRAFT,
    FROM_MINISTRY_GUIDE,
    REVIEWED,
    SUBMITTED,
    CoursePreparation,
    CurriculumPlan,
    TeacherWorkloadPlan,
)
from operations.models import SubjectClassAssignment

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"
GUIDE = "دليل الخطط الدراسية 2025-2026 ص14"


# ── تجهيز ────────────────────────────────────────────────────────────


@pytest.fixture
def school(db):
    from core.models import School

    return School.objects.create(name="مدرسة الشحانية", code="SHH-SCR")


@pytest.fixture
def departments(db, school):
    from core.models import Department

    return {
        "MAT": Department.objects.create(
            school=school, name="الرياضيات", code="DEP-MAT", sort_order=1
        ),
        "SCI": Department.objects.create(
            school=school, name="العلوم", code="DEP-SCI", sort_order=2
        ),
    }


@pytest.fixture
def subjects(db, school):
    from operations.models import Subject

    return {
        code: Subject.objects.create(school=school, name_ar=name, code=code)
        for code, name in (("MAT", "الرياضيات"), ("SCI", "العلوم"))
    }


def a_user(school, name, role_name, department=None):
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    role = RoleFactory(school=school, name=role_name)
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=role, department_obj=department)
    return user


@pytest.fixture
def maths_teacher(db, school, departments):
    return a_user(school, "معلّم الرياضيات", "teacher", departments["MAT"])


@pytest.fixture
def science_teacher(db, school, departments):
    return a_user(school, "معلّم العلوم", "teacher", departments["SCI"])


@pytest.fixture
def coordinator(db, school, departments):
    return a_user(school, "منسّق الرياضيات", "coordinator", departments["MAT"])


@pytest.fixture
def vice(db, school):
    return a_user(school, "النائب الأكاديميّ", "vice_academic")


@pytest.fixture
def principal(db, school):
    return a_user(school, "المدير", "principal")


@pytest.fixture
def seventh(db, school):
    from core.models import ClassGroup

    return ClassGroup.objects.create(
        school=school, grade="G7", section="1", level_type="prep", academic_year=YEAR
    )


@pytest.fixture
def plan_rows(db, school, subjects):
    for code, periods in (("MAT", 5), ("SCI", 4)):
        CurriculumPlan.objects.create(
            school=school,
            academic_year=YEAR,
            grade="G7",
            track="",
            subject=subjects[code],
            weekly_periods=periods,
            source_kind=FROM_MINISTRY_GUIDE,
            source_reference=GUIDE,
        )


def login(client, user, school):
    """`school` تُشتقّ من العضويّة — والوسيطُ هنا للقراءة لا للكتابة."""
    assert user.get_school() == school
    client.force_login(user)
    return client


def page(client, **params):
    return client.get(reverse("academic_management:assignments"), {"year": YEAR, **params})


def add(client, teacher, class_group, subject, **extra):
    return client.post(
        reverse("academic_management:assignment_add_row", args=[teacher.id]),
        {"year": YEAR, "class_group": class_group.id, "subject": subject.id, **extra},
    )


def move(client, teacher, action, **extra):
    return client.post(
        reverse("academic_management:assignment_move", args=[teacher.id, action]),
        {"year": YEAR, **extra},
    )


def set_quota(client, teacher, periods):
    return client.post(
        reverse("academic_management:assignment_set_load", args=[teacher.id]),
        {"year": YEAR, "required_weekly_periods": periods},
    )


# ══════════════════════════════════════════════════════════════════════
#  الشاشةُ الواحدة
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "gone",
    [
        "subject_assignments",
        "academic_management:workload",
        "academic_management:teacher_workload",
        "academic_management:plan_editor",
    ],
)
def test_every_old_assignment_screen_is_gone(gone):
    """«توزيعات المواد» و«إسناد الأنصبة» ومحرّرُ الخطّة — شاشةٌ واحدةٌ حلّت محلَّها."""
    from django.urls import NoReverseMatch

    with pytest.raises(NoReverseMatch):
        reverse(gone)


def test_the_page_lists_every_teacher_grouped_by_registry_department(
    client, school, departments, maths_teacher, science_teacher, vice
):
    login(client, vice, school)

    response = page(client)

    assert response.status_code == 200
    body = response.content.decode()
    assert "معلّم الرياضيات" in body and "معلّم العلوم" in body
    assert "الرياضيات" in body and "العلوم" in body


def test_a_teacher_cannot_open_the_screen(client, school, maths_teacher):
    login(client, maths_teacher, school)

    assert page(client).status_code == 403


# ══════════════════════════════════════════════════════════════════════
#  المنسّقُ قسمُه، والنائبُ كلُّ الأقسام
# ══════════════════════════════════════════════════════════════════════


def test_a_coordinator_sees_only_their_own_department(
    client, school, departments, maths_teacher, science_teacher, coordinator
):
    login(client, coordinator, school)

    body = page(client).content.decode()

    assert "معلّم الرياضيات" in body
    assert "معلّم العلوم" not in body, "قسمُ غيرِه لا يظهر له"


def test_a_coordinator_cannot_write_outside_their_department(
    client, school, departments, science_teacher, coordinator, seventh, subjects, plan_rows
):
    login(client, coordinator, school)

    response = add(client, science_teacher, seventh, subjects["SCI"])

    assert response.status_code == 403
    assert not SubjectClassAssignment.objects.filter(teacher=science_teacher).exists()


def test_the_vice_reaches_every_department(
    client, school, departments, science_teacher, vice, seventh, subjects, plan_rows
):
    login(client, vice, school)

    response = add(client, science_teacher, seventh, subjects["SCI"])

    assert response.status_code == 200
    assert SubjectClassAssignment.objects.filter(teacher=science_teacher).count() == 1


# ══════════════════════════════════════════════════════════════════════
#  الحصصُ من الخطّة الوزاريّة
# ══════════════════════════════════════════════════════════════════════


def test_the_periods_come_from_the_ministry_plan_not_from_the_form(
    client, school, departments, maths_teacher, coordinator, seventh, subjects, plan_rows
):
    login(client, coordinator, school)

    add(client, maths_teacher, seventh, subjects["MAT"], weekly_periods=99)

    row = SubjectClassAssignment.objects.get(teacher=maths_teacher)
    assert row.weekly_periods == 5, "الرقمُ من الخطّة — والنموذجُ لا يُملي"


def test_a_subject_without_a_plan_row_is_refused_with_a_reason(
    client, school, departments, maths_teacher, coordinator, seventh, subjects
):
    login(client, coordinator, school)

    response = add(client, maths_teacher, seventh, subjects["MAT"])

    assert response.status_code == 200
    assert "لا خطّةَ دراسيّة" in response.content.decode()
    assert not SubjectClassAssignment.objects.exists()


def test_the_subject_options_are_the_class_plan(
    client, school, departments, coordinator, seventh, subjects, plan_rows
):
    login(client, coordinator, school)

    response = client.get(
        reverse("academic_management:assignment_subject_options"),
        {"year": YEAR, "class_group": seventh.id},
    )

    body = response.content.decode()
    assert "الرياضيات" in body and "5 حصص" in body


def test_the_preparation_box_writes_a_course_preparation(
    client, school, departments, maths_teacher, coordinator, seventh, subjects, plan_rows
):
    login(client, coordinator, school)

    add(client, maths_teacher, seventh, subjects["MAT"], prepares="1")

    assert CoursePreparation.objects.filter(teacher=maths_teacher, grade="G7").count() == 1


# ══════════════════════════════════════════════════════════════════════
#  النصابُ رقمٌ واحد
# ══════════════════════════════════════════════════════════════════════


def test_the_quota_opens_a_draft_plan_on_first_write(
    client, school, departments, maths_teacher, coordinator
):
    login(client, coordinator, school)

    response = set_quota(client, maths_teacher, 18)

    assert response.status_code == 200
    plan = TeacherWorkloadPlan.objects.get(teacher=maths_teacher)
    assert plan.required_weekly_periods == 18 and plan.status == DRAFT


def test_the_draft_quota_is_measured_against_at_once(
    client, school, departments, maths_teacher, coordinator, seventh, subjects, plan_rows
):
    """قرارُ 2026-09-06: النصابُ يُقاس إليه من فوره — لا ينتظر اعتماداً."""
    from academic_management import load

    login(client, coordinator, school)
    set_quota(client, maths_teacher, 18)
    add(client, maths_teacher, seventh, subjects["MAT"])

    measured = load.load_for(school, YEAR, maths_teacher.id)
    assert measured.target == 18
    assert "من 18" in measured.label()


def test_an_out_of_range_quota_is_refused(
    client, school, departments, maths_teacher, coordinator
):
    login(client, coordinator, school)

    response = set_quota(client, maths_teacher, 99)

    assert "النصابُ بين" in response.content.decode()
    assert not TeacherWorkloadPlan.objects.exists()


# ══════════════════════════════════════════════════════════════════════
#  الدورة: رفعٌ ← مراجعةٌ ← اعتماد
# ══════════════════════════════════════════════════════════════════════


def test_the_coordinator_submits_and_the_vice_reviews_and_the_principal_approves(
    client,
    school,
    departments,
    maths_teacher,
    coordinator,
    vice,
    principal,
    seventh,
    subjects,
    plan_rows,
):
    login(client, coordinator, school)
    set_quota(client, maths_teacher, 5)
    add(client, maths_teacher, seventh, subjects["MAT"])
    move(client, maths_teacher, "submit")
    assert TeacherWorkloadPlan.objects.get(teacher=maths_teacher).status == SUBMITTED

    login(client, vice, school)
    move(client, maths_teacher, "review", comment="موافقٌ عليه")
    plan = TeacherWorkloadPlan.objects.get(teacher=maths_teacher)
    assert plan.status == REVIEWED and plan.reviewed_by == vice

    login(client, principal, school)
    move(client, maths_teacher, "approve")
    plan.refresh_from_db()
    assert plan.status == APPROVED and plan.approved_by == principal


def test_a_coordinator_cannot_review_their_own_submission(
    client, school, departments, maths_teacher, coordinator, seventh, subjects, plan_rows
):
    login(client, coordinator, school)
    set_quota(client, maths_teacher, 5)
    add(client, maths_teacher, seventh, subjects["MAT"])
    move(client, maths_teacher, "submit")

    move(client, maths_teacher, "review")

    assert TeacherWorkloadPlan.objects.get(teacher=maths_teacher).status == SUBMITTED


def test_a_submitted_card_is_locked_under_the_reviewer(
    client, school, departments, maths_teacher, coordinator, seventh, subjects, plan_rows
):
    """ما رُفع للمراجعة لا يُعدَّل من تحت المراجع — يُردّ أوّلاً."""
    login(client, coordinator, school)
    set_quota(client, maths_teacher, 5)
    move(client, maths_teacher, "submit")

    response = add(client, maths_teacher, seventh, subjects["MAT"])

    assert "مرفوعةٌ للمراجعة" in response.content.decode()
    assert not SubjectClassAssignment.objects.exists()


def test_the_vice_may_still_edit_a_submitted_card(
    client, school, departments, maths_teacher, coordinator, vice, seventh, subjects, plan_rows
):
    """صلاحيّةٌ كاملةٌ للنائب — يعدّل ما تحت يده لا يردّه ليعدَّل."""
    login(client, coordinator, school)
    set_quota(client, maths_teacher, 5)
    move(client, maths_teacher, "submit")

    login(client, vice, school)
    response = add(client, maths_teacher, seventh, subjects["MAT"])

    assert response.status_code == 200
    assert SubjectClassAssignment.objects.count() == 1


def test_the_vice_returns_a_card_to_the_coordinator(
    client, school, departments, maths_teacher, coordinator, vice, seventh, subjects, plan_rows
):
    login(client, coordinator, school)
    set_quota(client, maths_teacher, 5)
    move(client, maths_teacher, "submit")

    login(client, vice, school)
    move(client, maths_teacher, "return", comment="النصابُ ناقص")

    plan = TeacherWorkloadPlan.objects.get(teacher=maths_teacher)
    assert plan.status == DRAFT and plan.review_comment == "النصابُ ناقص"


def test_approval_is_refused_while_the_assigned_periods_miss_the_target(
    client,
    school,
    departments,
    maths_teacher,
    coordinator,
    vice,
    principal,
    seventh,
    subjects,
    plan_rows,
):
    """البوّابةُ كما هي: هدفٌ لا يقابله إسنادٌ لا يُعتمد."""
    login(client, coordinator, school)
    set_quota(client, maths_teacher, 18)
    add(client, maths_teacher, seventh, subjects["MAT"])
    move(client, maths_teacher, "submit")

    login(client, vice, school)
    move(client, maths_teacher, "review")

    login(client, principal, school)
    response = move(client, maths_teacher, "approve")

    assert TeacherWorkloadPlan.objects.get(teacher=maths_teacher).status == REVIEWED
    assert "المُسنَدُ فعلاً" in response.content.decode()


def test_an_approved_card_is_not_written_over(
    client,
    school,
    departments,
    maths_teacher,
    coordinator,
    vice,
    principal,
    seventh,
    subjects,
    plan_rows,
):
    login(client, coordinator, school)
    set_quota(client, maths_teacher, 5)
    add(client, maths_teacher, seventh, subjects["MAT"])
    move(client, maths_teacher, "submit")
    login(client, vice, school)
    move(client, maths_teacher, "review")
    login(client, principal, school)
    move(client, maths_teacher, "approve")

    response = set_quota(client, maths_teacher, 12)

    assert "معتمَدةٌ" in response.content.decode()
    assert TeacherWorkloadPlan.objects.get(status=APPROVED).required_weekly_periods == 5


def test_a_new_version_reopens_an_approved_card(
    client,
    school,
    departments,
    maths_teacher,
    coordinator,
    vice,
    principal,
    seventh,
    subjects,
    plan_rows,
):
    login(client, coordinator, school)
    set_quota(client, maths_teacher, 5)
    add(client, maths_teacher, seventh, subjects["MAT"])
    move(client, maths_teacher, "submit")
    login(client, vice, school)
    move(client, maths_teacher, "review")
    login(client, principal, school)
    move(client, maths_teacher, "approve")

    move(client, maths_teacher, "revise")

    versions = TeacherWorkloadPlan.objects.filter(teacher=maths_teacher).order_by("plan_version")
    assert [p.status for p in versions] == [APPROVED, DRAFT]
    assert versions.last().required_weekly_periods == 5, "الإصدارُ الجديدُ يبدأ من المعتمَد"


# ══════════════════════════════════════════════════════════════════════
#  حارسُ المدرسة: المُسنَدُ مقابل ما تطلبه الخطّة
# ══════════════════════════════════════════════════════════════════════


def test_the_guard_says_the_assignment_is_complete_when_it_matches_the_plan(
    client, school, departments, maths_teacher, coordinator, vice, seventh, subjects, plan_rows
):
    """لا يكفي أن يكون حملُ كلّ معلّمٍ سليماً — المدرسةُ كلُّها تُقاس بالخطّة."""
    login(client, vice, school)
    add(client, maths_teacher, seventh, subjects["MAT"])
    add(client, maths_teacher, seventh, subjects["SCI"])

    body = page(client).content.decode()

    assert "الإسنادُ مكتمل" in body
    assert "الخطّةُ تطلب 9 حصّةً، والمُسنَدُ 9" in body


def test_the_guard_names_the_place_of_the_shortfall(
    client, school, departments, maths_teacher, vice, seventh, subjects, plan_rows
):
    """«ناقصٌ أربعٌ» لا تكفي — تُقال الشعبةُ والمادّةُ والرقمان."""
    login(client, vice, school)
    add(client, maths_teacher, seventh, subjects["MAT"])

    body = page(client).content.decode()

    assert "الإسنادُ غيرُ مكتمل" in body
    assert "ناقصٌ 4" in body
    assert "غيرُ مُسنَد" in body, "الحالةُ تُسمّى"
    assert "العلوم" in body, "والمادّةُ الناقصةُ تُسمّى"


def test_the_department_counts_show_before_any_filter_is_chosen(
    client, school, departments, maths_teacher, science_teacher, vice
):
    """عددُ معلّمي كلّ قسمٍ ظاهرٌ في القائمة دائماً — لا بعد اختياره وحدَه."""
    login(client, vice, school)

    body = page(client, dept=f"reg:{departments['MAT'].id}").content.decode()

    assert "الرياضيات (1)" in body
    assert "العلوم (1)" in body, "وقسمٌ لم يُختَر يبقى رقمُه ظاهراً"


# ══════════════════════════════════════════════════════════════════════
#  قسمُ المعلّم يُدخَل من الشاشة
# ══════════════════════════════════════════════════════════════════════


def move_department(client, teacher, department=""):
    return client.post(
        reverse("academic_management:assignment_set_department", args=[teacher.id]),
        {"year": YEAR, "department": getattr(department, "id", department)},
    )


def test_a_teacher_without_a_department_is_shown_not_hidden(
    client, school, departments, maths_teacher, vice
):
    """متى سُجّلت الأقسامُ صار غيابُ القسم نقصاً يُعالَج لا يُشتقّ."""
    from core.models import Membership

    Membership.objects.filter(user=maths_teacher, school=school).update(department_obj=None)
    login(client, vice, school)

    body = page(client).content.decode()

    assert "بلا قسمٍ مسجَّل" in body
    assert "معلّم الرياضيات" in body


def test_the_vice_moves_a_teacher_to_another_department(
    client, school, departments, maths_teacher, vice
):
    """نقلُ معلّمٍ أو تعيينُ جديدٍ — بابُه في المنصّة لا في لوحة الإدارة."""
    from core.models import Membership

    login(client, vice, school)

    response = move_department(client, maths_teacher, departments["SCI"])

    assert response.status_code == 200
    membership = Membership.objects.get(user=maths_teacher, school=school, role__name="teacher")
    assert membership.department_obj == departments["SCI"]


def test_a_coordinator_may_not_move_teachers_between_departments(
    client, school, departments, maths_teacher, coordinator
):
    from core.models import Membership

    login(client, coordinator, school)

    assert move_department(client, maths_teacher, departments["MAT"]).status_code == 403
    membership = Membership.objects.get(user=maths_teacher, school=school, role__name="teacher")
    assert membership.department_obj == departments["MAT"], "لم يتغيّر شيء"


def test_moving_someone_without_a_teaching_membership_is_refused(
    client, school, departments, vice
):
    """القسمُ الأكاديميُّ لأهل التدريس — ولا يخالف المسمّى الوظيفيّ."""
    nurse = a_user(school, "الممرّض", "nurse")
    login(client, vice, school)

    response = move_department(client, nurse, departments["MAT"])

    assert "لا عضويّةَ تدريس" in response.content.decode()


# ══════════════════════════════════════════════════════════════════════
#  نقلُ المادّة من زميلٍ يُؤكَّد
# ══════════════════════════════════════════════════════════════════════


def test_assigning_a_held_subject_asks_before_it_drops_it_from_the_holder(
    client, school, departments, maths_teacher, science_teacher, vice, seventh, subjects, plan_rows
):
    """المادّةُ لمعلّمٍ واحد — فإسنادُها إلى ثانٍ يُسقطها عن الأوّل، ولا يقع صامتاً."""
    login(client, vice, school)
    add(client, science_teacher, seventh, subjects["MAT"])

    response = add(client, maths_teacher, seventh, subjects["MAT"])

    body = response.content.decode()
    assert "أؤكّد النقل" in body
    assert "معلّم العلوم" in body, "ويُسمّى صاحبُ المادّة الحاليّ"
    row = SubjectClassAssignment.objects.get(class_group=seventh, subject=subjects["MAT"])
    assert row.teacher == science_teacher, "ولم يُنقل شيءٌ بعد"


def test_the_transfer_happens_once_confirmed(
    client, school, departments, maths_teacher, science_teacher, vice, seventh, subjects, plan_rows
):
    login(client, vice, school)
    add(client, science_teacher, seventh, subjects["MAT"])

    add(client, maths_teacher, seventh, subjects["MAT"], confirm_transfer="1")

    row = SubjectClassAssignment.objects.get(class_group=seventh, subject=subjects["MAT"])
    assert row.teacher == maths_teacher
    assert not SubjectClassAssignment.objects.filter(
        class_group=seventh, subject=subjects["MAT"], teacher=science_teacher, is_active=True
    ).exists(), "ولا تبقى نسختان للمادّة نفسها"


def test_the_service_refuses_an_unconfirmed_transfer(
    client, school, departments, maths_teacher, science_teacher, vice, seventh, subjects, plan_rows
):
    """الحارسُ في الخدمة لا في الشاشة — فلا يمرّ نقلٌ من بابٍ آخر."""
    from academic_management import assignment_service as svc

    login(client, vice, school)
    add(client, science_teacher, seventh, subjects["MAT"])

    with pytest.raises(svc.AssignmentError) as caught:
        svc.apply_assignment(
            school=school,
            academic_year=YEAR,
            class_group=seventh,
            subject=subjects["MAT"],
            teacher=maths_teacher,
            weekly_periods=5,
            by=vice,
        )

    assert svc.SUBJECT_HELD_BY_OTHER in {f.code for f in caught.value.findings}


# ══════════════════════════════════════════════════════════════════════
#  المراجعةُ والاعتماد — والعربيّةُ تصل كما كُتبت
# ══════════════════════════════════════════════════════════════════════


def test_an_arabic_review_comment_survives_the_round_trip(
    client, school, departments, maths_teacher, coordinator, vice, seventh, subjects, plan_rows
):
    """ملاحظةُ المراجعة تُقرأ كما كُتبت — لا علاماتِ استفهامٍ ولا محارفَ بديلة."""
    login(client, coordinator, school)
    set_quota(client, maths_teacher, 5)
    add(client, maths_teacher, seventh, subjects["MAT"])
    move(client, maths_teacher, "submit")

    login(client, vice, school)
    move(client, maths_teacher, "review", comment="يُعتمد بعد ضبط نصاب الاثنين")

    plan = TeacherWorkloadPlan.objects.get(teacher=maths_teacher)
    assert plan.review_comment == "يُعتمد بعد ضبط نصاب الاثنين"
    assert "�" not in plan.review_comment
    body = page(client).content.decode()
    assert "يُعتمد بعد ضبط نصاب الاثنين" in body


def test_an_approved_plan_that_diverges_says_so(
    client,
    school,
    departments,
    maths_teacher,
    science_teacher,
    coordinator,
    vice,
    principal,
    seventh,
    subjects,
    plan_rows,
):
    """وُقّع على إسنادٍ ثمّ تبدّل تحته — فيُقال إنّ الموقَّعَ غيرُ المعروض."""
    login(client, coordinator, school)
    set_quota(client, maths_teacher, 5)
    add(client, maths_teacher, seventh, subjects["MAT"])
    move(client, maths_teacher, "submit")
    login(client, vice, school)
    move(client, maths_teacher, "review")
    login(client, principal, school)
    move(client, maths_teacher, "approve")

    # نُقلت المادّةُ إلى زميلٍ بعد الاعتماد — فتباعد الواقعُ عن التوقيع.
    add(client, science_teacher, seventh, subjects["MAT"], confirm_transfer="1")

    body = page(client).content.decode()
    assert "تبدّل الإسنادُ بعد الاعتماد" in body


def test_the_transfer_warns_when_the_holder_plan_is_approved(
    client,
    school,
    departments,
    maths_teacher,
    science_teacher,
    coordinator,
    vice,
    principal,
    seventh,
    subjects,
    plan_rows,
):
    login(client, coordinator, school)
    set_quota(client, maths_teacher, 5)
    add(client, maths_teacher, seventh, subjects["MAT"])
    move(client, maths_teacher, "submit")
    login(client, vice, school)
    move(client, maths_teacher, "review")
    login(client, principal, school)
    move(client, maths_teacher, "approve")

    response = add(client, science_teacher, seventh, subjects["MAT"])

    assert "وخطّةُ نصابه معتمَدة" in response.content.decode()


def test_the_guard_never_claims_a_hundred_while_short(
    client, school, departments, maths_teacher, vice, seventh, subjects, plan_rows
):
    """866 من 870 تُقرَّب إلى مئةٍ — فتقول الشاشةُ «غيرُ مكتملٍ 100%» في سطر."""
    login(client, vice, school)
    add(client, maths_teacher, seventh, subjects["MAT"])  # 5 من 9

    body = page(client).content.decode()

    assert "الإسنادُ غيرُ مكتمل" in body
    assert "غيرُ مكتمل — 100%" not in body, "لا تُقال المئةُ إلّا عند التطابق"
    assert "غيرُ مكتمل — 55%" in body, "5 من 9 خمسةٌ وخمسون"
