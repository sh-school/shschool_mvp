"""[STUDENT-INFO] مركز معلومات الطلبة — الشُّعبةُ ثمّ الطالب، وملاحظاتُ خمس جهات.

طلبت المدرسة مركزاً يُفتح من الشُّعب: تختار شعبةً فترى طلابها، وتختار طالباً
فترى ملفَّه الجامع — تحصيله بمستواه، وملاحظات كلّ جهةٍ عنه، وأنشطته.

و**قرارُ القراءة قرارُ المدرسة**: كلُّ من يُدرّس الطالب يرى كلَّ ملاحظاته،
بما فيها ملاحظاتُ الأخصائيَّين. عُرض أنّ هذا يوصل ملاحظةً نفسيّةً عن قاصرٍ
إلى عشرة معلّمين، فاعتُمد. وهذه الاختباراتُ تُثبّت ما اعتُمد وتُثبّت حدَّه:
من لا يُدرّس الطالب لا يراه، والكتابةُ في خانةِ جهةٍ لأهلها وحدهم، وكلُّ
قراءةٍ لملاحظةِ أخصائيٍّ تترك أثراً في سجلّ التدقيق.
"""

from datetime import date

import pytest
from django.urls import reverse

from core.models import AuditLog
from student_info.models import StudentNote

YEAR = "2025-2026"


# ── مصانعُ صغيرةٌ للاختبار ─────────────────────────────────────────────


@pytest.fixture
def teaching_slot(db, school, teacher_user, class_group):
    """حصّةٌ تربط المعلّمَ بالشعبة — بها وحدها يصير الطالبُ «طالبَه»."""
    from datetime import time

    from operations.models import ScheduleSlot, Subject

    subject = Subject.objects.create(school=school, name_ar="رياضيات", code="MATH")
    return ScheduleSlot.objects.create(
        school=school,
        teacher=teacher_user,
        class_group=class_group,
        subject=subject,
        day_of_week=0,
        period_number=1,
        start_time=time(7, 0),
        end_time=time(7, 45),
        academic_year=class_group.academic_year,
    )


@pytest.fixture
def note(db, school, student_user, psychologist_user):
    return StudentNote.objects.create(
        school=school,
        student=student_user,
        category="psychologist",
        title="متابعة",
        body="نصٌّ حسّاسٌ عن قاصر.",
        occurred_on=date(2026, 3, 1),
        academic_year=YEAR,
        created_by=psychologist_user,
    )


def _login(client, user):
    client.force_login(user)
    return client


# ── الشريحة تُقاس بعتبات المنصّة نفسها ───────────────────────────────


@pytest.mark.parametrize(
    ("total", "expected"),
    [
        (100, "advanced"),
        (80, "advanced"),
        (79.9, "proficient"),
        (65, "proficient"),
        (64, "basic"),
        (50, "basic"),
        (49, "below"),
        (0, "below"),
    ],
)
def test_the_band_uses_the_thresholds_the_platform_already_colours_by(total, expected):
    """٨٠ و٦٥ و٥٠ هي عتباتُ `grade_color_css` منذ البداية.

    ولو اخترعنا للمركز عتباتٍ أخرى لصار للطالب مستويان مختلفان في شاشتين
    من المنصّة نفسها.
    """
    from student_info.services import band_for

    assert band_for(total) == expected


def test_a_student_without_a_result_has_no_band():
    """لا شريحةَ لمن لم تُرصد له نتيجةٌ — ولا تُنسب إليه «دون المستوى»."""
    from student_info.services import band_for

    assert band_for(None) is None


# ── من يكتب: أهلُ الخانة وحدهم ────────────────────────────────────────


@pytest.mark.parametrize(
    ("fixture_name", "category"),
    [
        ("psychologist_user", "psychologist"),
        ("social_worker_user", "social_worker"),
        ("nurse_user", "nurse"),
        ("teacher_user", "teacher"),
    ],
)
def test_each_specialist_writes_in_their_own_box(request, fixture_name, category):
    from student_info.access import can_write

    user = request.getfixturevalue(fixture_name)

    assert can_write(user, category)


def test_a_teacher_may_not_write_a_psychologist_note(db, teacher_user):
    """يقرؤها بقرار المدرسة — ولا يكتبها."""
    from student_info.access import can_write

    assert not can_write(teacher_user, "psychologist")


def test_the_principal_writes_in_every_box(db, principal_user):
    from student_info.access import writable_categories

    assert len(writable_categories(principal_user)) == 5


def test_the_form_offers_only_the_boxes_one_may_write_in(db, nurse_user):
    """أداةٌ لا تعمل لا تُعرض — والحارسُ في `clean_category` لا في القائمة."""
    from student_info.forms import StudentNoteForm

    form = StudentNoteForm(user=nurse_user)

    assert [key for key, _ in form.fields["category"].choices] == ["nurse"]


def test_the_form_refuses_a_box_that_is_not_ones_own(db, nurse_user):
    from student_info.forms import StudentNoteForm

    form = StudentNoteForm(
        {
            "category": "psychologist",
            "title": "عنوان",
            "body": "نصّ الملاحظة",
            "occurred_on": "2026-03-01",
        },
        user=nurse_user,
    )

    assert not form.is_valid()
    assert "category" in form.errors


# ── من يقرأ: قرارُ المدرسة وحدُّه ─────────────────────────────────────


def test_a_teacher_reads_the_file_of_a_student_they_teach(
    db, teacher_user, student_user, school, enrolled_student, teaching_slot
):
    from student_info.access import can_read_student

    assert can_read_student(teacher_user, student_user, school, YEAR)


def test_a_teacher_does_not_read_a_student_they_do_not_teach(
    db, teacher_user, student_user, school, enrolled_student
):
    """لا حصّةَ تربطه بشعبة الطالب — فالملفُّ خارج نطاقه."""
    from student_info.access import can_read_student

    assert not can_read_student(teacher_user, student_user, school, YEAR)


@pytest.mark.parametrize(
    "fixture_name",
    ["principal_user", "social_worker_user", "psychologist_user", "nurse_user", "coordinator_user"],
)
def test_care_roles_read_every_student_without_teaching_them(
    request, db, student_user, school, fixture_name
):
    from student_info.access import can_read_student

    user = request.getfixturevalue(fixture_name)

    assert can_read_student(user, student_user, school, YEAR)


def test_the_sections_page_shows_a_teacher_only_the_classes_they_teach(
    db, client, teacher_user, class_group, teaching_slot, school
):
    from core.models.academic import ClassGroup

    other = ClassGroup.objects.create(
        school=school, grade="G8", section="ب", level_type="prep", academic_year=YEAR
    )

    response = _login(client, teacher_user).get(reverse("student_info:sections"))

    shown = {g.id for g in response.context["groups"]}
    assert class_group.id in shown
    assert other.id not in shown


# ── الأثر الذي لا يُمحى ───────────────────────────────────────────────


def test_reading_a_file_with_a_psychologist_note_leaves_an_audit_trail(
    db, client, principal_user, student_user, note
):
    """المادّة ١٩: من قرأ بيانةً ذاتَ طبيعةٍ خاصّةٍ عن قاصرٍ يُعرَف باسمه."""
    _login(client, principal_user).get(
        reverse("student_info:student_file", args=[student_user.id]) + f"?year={YEAR}"
    )

    entry = AuditLog.objects.filter(model_name="StudentNote", user=principal_user).first()
    assert entry is not None
    assert entry.action == "view"
    assert "الأخصائي النفسي" in entry.object_repr


def test_a_file_with_no_sensitive_note_leaves_no_trail(
    db, client, principal_user, student_user, school, nurse_user
):
    """التدقيقُ للحسّاس وحده — ولا يُغرَق السجلُّ بما لا يعني القانون."""
    StudentNote.objects.create(
        school=school,
        student=student_user,
        category="nurse",
        title="صداع",
        body="راجع العيادة.",
        occurred_on=date(2026, 3, 1),
        academic_year=YEAR,
        created_by=nurse_user,
    )

    _login(client, principal_user).get(
        reverse("student_info:student_file", args=[student_user.id]) + f"?year={YEAR}"
    )

    assert not AuditLog.objects.filter(model_name="StudentNote").exists()


# ── النصّ مشفَّرٌ في القاعدة ──────────────────────────────────────────


def test_the_note_body_is_not_stored_in_the_clear(db, note):
    """`EncryptedTextField` لا مُساعِدَي `get_`/`set_`: العيبُ الذي وقع في
    السجلّ الصحّي — قالبٌ يطبع الحقلَ الخام — مستحيلٌ هنا بالبناء."""
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("SELECT body FROM student_info_studentnote WHERE id = %s", [str(note.id)])
        raw = cur.fetchone()[0]

    assert "نصٌّ حسّاس" not in raw
    assert StudentNote.objects.get(pk=note.pk).body == "نصٌّ حسّاسٌ عن قاصر."


# ── الشاشاتُ تعمل ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url_name", ["student_info:sections", "student_info:levels", "student_info:activities"]
)
def test_the_main_screens_answer(db, client, principal_user, url_name):
    response = _login(client, principal_user).get(reverse(url_name))

    assert response.status_code == 200


@pytest.mark.parametrize(
    "category", ["teacher", "social_worker", "psychologist", "nurse", "student_affairs"]
)
def test_every_note_screen_answers(db, client, principal_user, category):
    """البنودُ الخمسةُ في القائمة تفتح شاشاتِها — لا رابطاً معطوباً."""
    response = _login(client, principal_user).get(reverse("student_info:notes", args=[category]))

    assert response.status_code == 200


def test_an_unknown_category_is_turned_away(db, client, principal_user):
    response = _login(client, principal_user).get(reverse("student_info:notes", args=["nobody"]))

    assert response.status_code == 302


def test_a_student_may_not_enter_the_centre(db, client, student_user):
    """الطالبُ ليس من أهل الوحدة — ولا يقرأ ما يُكتب عنه من هنا."""
    response = _login(client, student_user).get(reverse("student_info:sections"))

    assert response.status_code in (302, 403)


def test_writing_a_note_stores_the_author_and_the_school(
    db, client, school, psychologist_user, student_user
):
    _login(client, psychologist_user).post(
        reverse("student_info:note_create", args=[student_user.id]) + f"?year={YEAR}",
        {
            "category": "psychologist",
            "title": "متابعة أولى",
            "body": "نصّ الملاحظة.",
            "occurred_on": "2026-03-01",
        },
    )

    saved = StudentNote.objects.get(student=student_user)
    assert saved.created_by == psychologist_user
    assert saved.school == school
    assert saved.academic_year == YEAR


# ── الوحدةُ موصولةٌ بالمنصّة ──────────────────────────────────────────


def test_the_module_gate_matches_its_own_access_rules():
    """بوّابةُ الوسيط تسبق حرّاسَ الشاشات: دورٌ مسموحٌ في `access` ومحجوبٌ
    في `apps` يُردّ قبل أن تُقرأ صلاحيتُه — وهو عطبٌ وقع في وحدة الجودة."""
    from core.module_registry import get_module
    from student_info.access import MODULE_ROLES

    assert set(get_module("student_info").allowed_roles) == set(MODULE_ROLES)


def test_the_seven_items_are_in_the_main_menu():
    """ما طلبته المدرسة بنداً بنداً — ووجودُه في القالب يُقاس لا يُفترض."""
    import pathlib

    nav = pathlib.Path("templates/base/base.html").read_text(encoding="utf-8")

    assert 'id="m-student-info"' in nav
    assert "مركز معلومات الطلبة" in nav
    for item in (
        "student_info:levels",
        "'teacher'",
        "'social_worker'",
        "'psychologist'",
        "'nurse'",
        "'student_affairs'",
        "student_info:activities",
    ):
        assert item in nav, item


def test_the_note_table_is_isolated_in_the_database():
    """الجدولُ يحمل نصَّ ملاحظةٍ نفسيّةٍ عن قاصر — فسياستُه في القاعدة لا في
    الكود وحده. (وثلاثون جدولاً في المنصّة بلا سياسةٍ حتى اليوم.)"""
    import pathlib

    sql = pathlib.Path("student_info/migrations/0002_rls_student_note.py").read_text(
        encoding="utf-8"
    )

    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "app_rls_school()" in sql
