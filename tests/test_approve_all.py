"""اعتمادُ رصد المعلّمين بالحصّة — أمرُ المالك 2026-10-06: لا «اعتمادَ الكلّ» (مفتاحٌ خطير) ولا بطاقةَ لكلّ طالب.

كلُّ حصّةٍ بطاقةٌ؛ اعتمادُها يمرّ بـ`decide_entry` لكلّ إدخالٍ فيُسجَّل قرارُه باسم المعتمِد؛ والرفضُ يبقى بنداً بنداً؛ ومن لا يملك الاعتمادَ لا يستطيع.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from operations.attendance_entries import submit_entry
from operations.models import AttendanceDecision, Session, StudentAttendance
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, at

pytestmark = pytest.mark.django_db


@pytest.fixture
def now_0830(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(8, 30))


@pytest.fixture
def second(school, klass, teacher, session):
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="scheduled",
    )


def test_there_is_no_bulk_approve_button_or_route_anywhere(
    client_as, now_0830, klass, session, teacher, holder, kid
):
    """أمرُ المالك 2026-10-06: «اعتمادُ الكلّ» مفتاحٌ خطير — يعتمد كلَّ الحصص والأجنحة بنقرةٍ دون نظر. فلا زرَّ ولا مسارَ."""
    from django.urls import NoReverseMatch

    submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    pages = [
        reverse("attendance_approvals"),
        reverse("wings:record_index"),
        reverse("daily_report"),
        reverse("wings:record_section", args=[klass.id]),
    ]
    for url in pages:
        body = client_as(holder).get(url, {"date": SUNDAY.isoformat()}).content.decode()
        assert "اعتمادُ الكلّ" not in body, url
    with pytest.raises(NoReverseMatch):
        reverse("attendance_approve_all")


def test_the_supervisor_sheet_opens_with_the_teachers_pending_absence_checked(
    client_as, now_0830, klass, session, teacher, holder, kid
):
    """واقعة «الكلُّ سُجّل حاضراً» 2026-10-05: كان الكشفُ يفتح الجميعَ حاضراً فيكتب تثبيتُه حاضراً فوق غياب المعلّم."""
    submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    body = (
        client_as(holder)
        .get(
            reverse("wings:record_section", args=[klass.id]),
            {"date": SUNDAY.isoformat(), "p": "07:10"},
        )
        .content.decode()
    )
    assert f'name="s-{kid.id}" value="absent" checked' in body
    assert f'name="s-{kid.id}" value="present" checked' not in body


def test_confirming_the_prefilled_sheet_leaves_the_teachers_absence_pending_for_approval(
    client_as, now_0830, klass, session, teacher, holder, kid
):
    """قاموس 2026-10-05: التثبيتُ لا يكتب فوق إدخال المعلّم ولا يرفضه — يبقى معلَّقاً ويقرّره «اعتماد»."""
    submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    client_as(holder).post(
        reverse("wings:record_period", args=[klass.id]),
        {"date": SUNDAY.isoformat(), "start": "07:10", f"s-{kid.id}": "absent"},
    )
    assert not StudentAttendance.objects.filter(session=session, student=kid).exists()
    assert not AttendanceDecision.objects.exists()
    client_as(holder).post(reverse("attendance_approve_session", args=[session.id]))
    assert StudentAttendance.objects.get(session=session, student=kid).status == "absent"


def test_a_special_education_teacher_sees_the_same_shared_sheet_and_the_absence_is_final(
    client_as, now_0830, school, special_klass, teacher, bells
):
    """أمرُ المالك 2026-10-04: تصميمٌ واحد — شعبةُ ESE (بلا جناح) تُرسم بالكشف المشترك نفسِه، وإدخالُها نهائيٌّ مباشر (D-126م)."""
    from tests.attendance_fixtures import ENROLLED
    from tests.conftest import MembershipFactory, RoleFactory, StudentEnrollmentFactory, UserFactory

    pupil = UserFactory(full_name="طالب خاصّ", national_id="29000001077")
    StudentEnrollmentFactory(student=pupil, class_group=special_klass, enrolled_at=ENROLLED)
    MembershipFactory(user=pupil, school=school, role=RoleFactory(school=school, name="student"))
    ese = Session.objects.create(
        school=school,
        class_group=special_klass,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        status="scheduled",
    )
    page = client_as(teacher).get(reverse("attendance", args=[ese.id]))
    body = page.content.decode()
    assert 'class="per-head"' in body and f'name="s-{pupil.id}"' in body
    assert "student_row" not in body and "mark_all_present" not in body  # لا قائمةَ قديمة
    client_as(teacher).post(
        reverse("attendance_period_entries", args=[ese.id]), {f"s-{pupil.id}": "absent"}
    )
    assert StudentAttendance.objects.get(session=ese, student=pupil).status == "absent"


# ── فصلُ «اعتماد الحصّة» عن «تثبيت الحصّة» (قاموس الغياب 2026-10-05 §٣) ──────────────────────────


def _kids(school, klass, n, start=0):
    from tests.attendance_fixtures import ENROLLED
    from tests.conftest import MembershipFactory, RoleFactory, StudentEnrollmentFactory, UserFactory

    out = []
    for i in range(n):
        pupil = UserFactory(full_name=f"طالب {i}", national_id=f"2900002{start + i:04d}")
        StudentEnrollmentFactory(student=pupil, class_group=klass, enrolled_at=ENROLLED)
        MembershipFactory(
            user=pupil, school=school, role=RoleFactory(school=school, name="student")
        )
        out.append(pupil)
    return out


def test_four_absences_then_approve_the_session_then_confirm_keeps_four_absent_and_rejects_nothing(
    client_as, now_0830, school, klass, session, teacher, holder
):
    """القبولُ بنصّ القاموس: 4 غيابات ← اعتماد الحصّة ← 4 غائبين بقراراتٍ approved؛ ثمّ التثبيتُ لا يغيّر منهم أحداً ولا يرفض شيئاً؛ وطالبٌ بلا إدخالٍ يُثبَّت حاضراً."""
    absent = _kids(school, klass, 4)
    plain = _kids(school, klass, 1, start=10)[0]
    for pupil in absent:
        submit_entry(teacher, session, pupil, "absent", now=at(7, 30))
    client_as(holder).post(reverse("attendance_approve_session", args=[session.id]))
    assert StudentAttendance.objects.filter(session=session, status="absent").count() == 4
    assert AttendanceDecision.objects.filter(decision="approved", decided_by=holder).count() == 4
    client_as(holder).post(
        reverse("wings:record_period", args=[klass.id]),
        {"date": SUNDAY.isoformat(), "start": "07:10"},
    )  # تثبيتٌ بلا تغيير: الكلُّ «حاضر» افتراضاً
    assert StudentAttendance.objects.filter(session=session, status="absent").count() == 4
    assert not AttendanceDecision.objects.filter(decision="rejected").exists()
    row = StudentAttendance.objects.get(session=session, student=plain)
    assert (row.status, row.source) == ("present", "supervisor")


def test_confirming_the_period_never_overwrites_nor_rejects_a_pending_teacher_entry(
    client_as, now_0830, school, klass, session, teacher, holder
):
    pupil = _kids(school, klass, 1)[0]
    submit_entry(teacher, session, pupil, "late", tardiness_minutes=7, now=at(7, 30))
    client_as(holder).post(
        reverse("wings:record_period", args=[klass.id]),
        {"date": SUNDAY.isoformat(), "start": "07:10"},
    )
    assert not AttendanceDecision.objects.exists()  # لم يُرفض ولم يُعتمد
    assert not StudentAttendance.objects.filter(
        session=session, student=pupil
    ).exists()  # ولم يُكتب فوقه


def test_no_form_is_nested_inside_another_form_on_the_shared_sheet(
    client_as, now_0830, klass, session, teacher, holder, kid
):
    """واقعةُ 2026-10-05: <form> داخل <form> يُسقطه المتصفّحُ فيُشغّل الزرُّ نموذجَ التثبيت. التحليلُ بالـHTMLParser لا بالنصّ."""
    from html.parser import HTMLParser

    submit_entry(teacher, session, kid, "absent", now=at(7, 30))

    class Depth(HTMLParser):
        def __init__(self):
            super().__init__()
            self.depth = 0
            self.worst = 0

        def handle_starttag(self, tag, attrs):
            if tag == "form":
                self.depth += 1
                self.worst = max(self.worst, self.depth)

        def handle_endtag(self, tag):
            if tag == "form":
                self.depth -= 1

    pages = {
        "supervisor": client_as(holder).get(
            reverse("wings:record_section", args=[klass.id]), {"date": SUNDAY.isoformat()}
        ),
        "teacher": client_as(teacher).get(reverse("attendance", args=[session.id])),
        "approvals": client_as(holder).get(reverse("attendance_approvals")),
        "daily": client_as(holder).get(reverse("daily_report"), {"date": SUNDAY.isoformat()}),
    }
    for name, response in pages.items():
        parser = Depth()
        parser.feed(response.content.decode())
        assert parser.worst <= 1, f"{name}: نموذجٌ داخل نموذج"
    sheet = pages["supervisor"].content.decode()
    assert "approve-all-form" not in sheet  # لا زرَّ جماعيّاً ولا نموذجَه المستقلَّ بعد اليوم


def test_confirming_a_special_education_period_does_not_touch_the_teachers_final_entry(
    client_as, now_0830, school, special_klass, teacher, holder, bells
):
    """استثناءُ D-129م: رصدُ معلّم التربية الخاصّة نهائيٌّ بلا اعتماد، ولا يمسّه التثبيتُ."""
    from operations.period_register import confirm_period

    pupil = _kids(school, special_klass, 1)[0]
    ese = Session.objects.create(
        school=school,
        class_group=special_klass,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        status="scheduled",
    )
    client_as(teacher).post(
        reverse("attendance_period_entries", args=[ese.id]), {f"s-{pupil.id}": "absent"}
    )
    confirm_period(special_klass, SUNDAY, ese.start_time, {}, holder, now=at(8, 30))
    assert StudentAttendance.objects.get(session=ese, student=pupil).status == "absent"


def test_after_approving_the_session_the_supervisor_sheet_shows_the_approved_absences_checked(
    client_as, now_0830, school, klass, session, teacher, holder
):
    """واقعةُ 2026-10-05 بعد الاعتماد: رُسمت الأزرارُ «حاضر» للجميع (cells_of يقرأ رصدَ المشرف وحدَه والمعتمَدُ مصدرُه المعلّم)."""
    absent = _kids(school, klass, 4, start=20)
    plain = _kids(school, klass, 1, start=30)[0]
    for pupil in absent:
        submit_entry(teacher, session, pupil, "absent", now=at(7, 30))
    client_as(holder).post(reverse("attendance_approve_session", args=[session.id]))
    body = (
        client_as(holder)
        .get(
            reverse("wings:record_section", args=[klass.id]),
            {"date": SUNDAY.isoformat(), "p": "07:10"},
        )
        .content.decode()
    )
    for pupil in absent:
        assert f'name="s-{pupil.id}" value="absent" checked' in body
        assert f'name="s-{pupil.id}" value="present" checked' not in body
    assert f'name="s-{plain.id}" value="present" checked' in body


# ── الطابورُ بالحصّة لا بالطالب — أمرُ المالك 2026-10-06 («يعتمد لـ731 طالباً كلَّ حصّة؟ خطأ») ──


def _pupils(klass, count):
    from tests.attendance_fixtures import ENROLLED
    from tests.conftest import StudentEnrollmentFactory, UserFactory

    out = []
    for n in range(count):
        student = UserFactory(full_name=f"حاضرٌ رقم {n}", national_id=f"2900006{n:04d}")
        StudentEnrollmentFactory(student=student, class_group=klass, enrolled_at=ENROLLED)
        out.append(student)
    return out


def test_the_queue_is_one_card_per_session_and_present_students_are_only_a_count(
    client_as, now_0830, klass, session, teacher, holder, kid
):
    present = _pupils(klass, 4)
    for student in present:
        submit_entry(teacher, session, student, "present", now=at(7, 30))
    submit_entry(teacher, session, kid, "absent", now=at(7, 30))

    body = client_as(holder).get(reverse("attendance_approvals")).content.decode()

    assert "اعتمادُ الحصّة (5)" in body  # خمسةُ إدخالاتٍ في بطاقةٍ واحدة
    assert "حاضر 4" in body
    assert "طالب الشعبة" in body  # الغائبُ يُنظر فيه
    assert "حاضرٌ رقم 0" not in body  # والحاضرون عدٌّ لا بطاقاتٌ


def test_approving_a_session_approves_only_its_entries_and_each_decision_is_recorded(
    client_as, now_0830, klass, session, second, teacher, holder, kid
):
    present = _pupils(klass, 3)
    for student in present:
        submit_entry(teacher, session, student, "present", now=at(7, 30))
    submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    other = submit_entry(teacher, second, present[0], "present", now=at(8, 10))

    response = client_as(holder).post(reverse("attendance_approve_session", args=[session.id]))

    assert response.status_code == 302 and response.url == reverse("attendance_approvals")
    assert AttendanceDecision.objects.filter(entry__session=session).count() == 4
    assert AttendanceDecision.objects.filter(decided_by=holder).count() == 4
    assert not AttendanceDecision.objects.filter(entry=other).exists()  # حصّةٌ أخرى تبقى بانتظاره


def test_a_teacher_cannot_approve_a_session(client_as, now_0830, session, teacher, holder, kid):
    submit_entry(teacher, session, kid, "absent", now=at(7, 30))

    response = client_as(teacher).post(reverse("attendance_approve_session", args=[session.id]))

    assert response.status_code == 403 and not AttendanceDecision.objects.exists()
