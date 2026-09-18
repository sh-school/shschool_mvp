"""[SECURITY] مشرفُ الجناح لطلبة جناحه فقط — في الشاشات العابرة للوحدات.

قرارا المستخدم 2026-09-14/15: «المشرفُ لجناحه فقط» في كلّ ما يقرأ فيه عن الطلبة. وهذه
الشاشاتُ ليست في شؤون الطلبة ولا في مركز المعلومات، لكنّها كانت تكشف المدرسةَ كلَّها:

- تقريرُ «غياب اليوم» — غائبو المدرسة ومتأخّروها بالاسم والشعبة لأيّ تاريخ.
- رصدُ حضور طالبٍ واحد — حصّةُ جناحٍ آخر، وطالبٌ ليس في شعبة الحصّة أصلاً.
- محضرُ حادثة الكنترول — قائمةٌ منسدلةٌ بأسماء طلبة المدرسة ومعرّفاتهم، وكتابةٌ على أيّ منهم.
- ملفّاتُ الطلبة في `/dbmedia/` — عذرُ التأخّر ومستندُ عذر الغياب.
- البحثُ العامّ وواجهةُ بحث الطلبة.
- تنبيهاتُ الغياب في لوحته.

والقيادةُ وسائرُ الأدوار كما كانت: المديرُ يرى الجناحين في كلّ حالة.
"""

import datetime as dt

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import Http404
from django.urls import reverse

from core.models import StudentEnrollment, Wing
from core.navigation import can_open
from exam_control.models import ExamIncident, ExamSession
from exam_control.services import ExamControlService
from operations.daily_absence import daily_report
from operations.models import AbsenceAlert, AbsenceExcuse, Session, StudentAttendance
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)
from wings.scope import student_scope

pytestmark = pytest.mark.django_db

SUNDAY = dt.date(2026, 9, 13)
MINE = "طالب الجناح الأول"
THEIRS = "طالب الجناح الثاني"


# ── التجهيز: جناحان، لكلٍّ شعبةٌ وطالب ────────────────────────────────


def _member(school, role, name, national_id):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def year(seeded_calendar):
    return seeded_calendar


@pytest.fixture
def supervisor(school, seeded_calendar):
    return _member(school, "admin_supervisor", "مشرف الجناح الأول", "29400000001")


@pytest.fixture
def klass(school, seeded_calendar, supervisor):
    wing = Wing.objects.create(
        school=school,
        code="w1",
        name="جناح 1",
        academic_year=seeded_calendar,
        supervisor=supervisor,
    )
    return ClassGroupFactory(
        school=school,
        grade="G7",
        section="1",
        level_type="prep",
        academic_year=seeded_calendar,
        wing=wing,
    )


@pytest.fixture
def other_klass(school, seeded_calendar):
    other = _member(school, "admin_supervisor", "مشرف الجناح الثاني", "29400000002")
    wing = Wing.objects.create(
        school=school, code="w2", name="جناح 2", academic_year=seeded_calendar, supervisor=other
    )
    return ClassGroupFactory(
        school=school,
        grade="G7",
        section="2",
        level_type="prep",
        academic_year=seeded_calendar,
        wing=wing,
    )


@pytest.fixture
def mine(klass):
    student = UserFactory(full_name=MINE, national_id="29400000011")
    StudentEnrollmentFactory(student=student, class_group=klass)
    return student


@pytest.fixture
def theirs(other_klass):
    student = UserFactory(full_name=THEIRS, national_id="29400000012")
    StudentEnrollmentFactory(student=student, class_group=other_klass)
    return student


@pytest.fixture
def principal(school):
    return _member(school, "principal", "مدير المدرسة", "29400000003")


def _session(school, klass, national_id, day=SUNDAY):
    teacher = _member(school, "teacher", f"معلّم {national_id}", national_id)
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=day,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        status="scheduled",
    )


def _absent(session, student):
    return StudentAttendance.objects.create(
        session=session, student=student, school=session.school, status="absent"
    )


# ══════════════════════════════════════════════════════════════════
# تقريرُ غياب اليوم
# ══════════════════════════════════════════════════════════════════


class TestDailyAbsenceReport:
    @pytest.fixture
    def absences(self, school, klass, other_klass, mine, theirs):
        _absent(_session(school, klass, "29400000101"), mine)
        _absent(_session(school, other_klass, "29400000102"), theirs)

    def test_the_supervisor_sees_only_his_wing(self, client_as, supervisor, absences):
        body = (
            client_as(supervisor)
            .get(reverse("daily_report") + f"?date={SUNDAY.isoformat()}")
            .content.decode()
        )

        assert MINE in body
        assert THEIRS not in body

    def test_the_principal_still_sees_the_whole_school(self, client_as, principal, absences):
        body = (
            client_as(principal)
            .get(reverse("daily_report") + f"?date={SUNDAY.isoformat()}")
            .content.decode()
        )

        assert MINE in body
        assert THEIRS in body

    def test_the_scope_is_the_current_enrollment_not_the_session_class(
        self, school, supervisor, klass, other_klass, theirs
    ):
        """طالبٌ نُقل إلى جناحي: غيابُه في حصّةِ شعبته القديمة يُرى عندي، لا عند جناحه القديم."""
        _absent(_session(school, other_klass, "29400000103"), theirs)
        StudentEnrollment.objects.filter(student=theirs).update(enrolled_at=dt.date(2026, 8, 1))
        StudentEnrollmentFactory(student=theirs, class_group=klass)  # القيدُ الأحدث

        scope = student_scope(supervisor, school)
        report = daily_report(school, SUNDAY, student_ids=scope.student_ids())

        assert [r.student for r in report.rows] == [theirs]

    def test_without_a_scope_the_report_is_unchanged(self, school, absences, mine, theirs):
        report = daily_report(school, SUNDAY)

        assert {r.student for r in report.rows} == {mine, theirs}


# ══════════════════════════════════════════════════════════════════
# رصدُ طالبٍ واحد
# ══════════════════════════════════════════════════════════════════


class TestMarkSingle:
    def test_a_session_outside_his_wing_is_404(
        self, client_as, school, supervisor, other_klass, theirs
    ):
        session = _session(school, other_klass, "29400000201")

        response = client_as(supervisor).post(
            reverse("mark_single", args=[session.id]),
            {"student_id": str(theirs.id), "status": "absent"},
        )

        assert response.status_code == 404
        assert not StudentAttendance.objects.exists()

    def test_a_student_not_enrolled_in_the_session_class_is_404(
        self, client_as, school, supervisor, klass, mine, theirs
    ):
        session = _session(school, klass, "29400000202")

        response = client_as(supervisor).post(
            reverse("mark_single", args=[session.id]),
            {"student_id": str(theirs.id), "status": "absent"},
        )

        assert response.status_code == 404
        assert not StudentAttendance.objects.exists()

    def test_his_own_wing_is_recorded(self, client_as, school, supervisor, klass, mine):
        session = _session(school, klass, "29400000203")

        response = client_as(supervisor).post(
            reverse("mark_single", args=[session.id]),
            {"student_id": str(mine.id), "status": "absent"},
        )

        assert response.status_code == 200
        assert StudentAttendance.objects.get(session=session, student=mine).status == "absent"

    def test_the_principal_records_any_wing_but_only_the_class_students(
        self, client_as, school, principal, klass, other_klass, mine, theirs
    ):
        session = _session(school, other_klass, "29400000204")
        client = client_as(principal)

        ok = client.post(
            reverse("mark_single", args=[session.id]),
            {"student_id": str(theirs.id), "status": "late"},
        )
        stranger = client.post(
            reverse("mark_single", args=[session.id]),
            {"student_id": str(mine.id), "status": "late"},
        )

        assert ok.status_code == 200
        assert stranger.status_code == 404
        assert list(StudentAttendance.objects.values_list("student_id", flat=True)) == [theirs.id]


# ══════════════════════════════════════════════════════════════════
# محضرُ حادثة الكنترول
# ══════════════════════════════════════════════════════════════════


class TestExamIncident:
    @pytest.fixture
    def exam(self, school, year, principal):
        return ExamSession.objects.create(
            school=school,
            name="اختبارات نهاية الفصل الأول",
            session_type="final",
            academic_year=year,
            start_date=SUNDAY,
            end_date=SUNDAY + dt.timedelta(days=14),
            created_by=principal,
        )

    def _listed(self, client, exam):
        response = client.get(reverse("exam_control:incident_add", args=[exam.pk]))
        assert response.status_code == 200
        return {e.student for e in response.context["students"]}

    def test_the_student_list_is_his_wing(self, client_as, supervisor, exam, mine, theirs):
        assert self._listed(client_as(supervisor), exam) == {mine}

    def test_the_principal_lists_the_whole_school(self, client_as, principal, exam, mine, theirs):
        assert self._listed(client_as(principal), exam) == {mine, theirs}

    def test_posting_a_student_outside_his_wing_is_404(
        self, client_as, supervisor, exam, mine, theirs
    ):
        response = client_as(supervisor).post(
            reverse("exam_control:incident_add", args=[exam.pk]),
            {"student_id": str(theirs.id), "incident_type": "cheating", "description": "غش"},
        )

        assert response.status_code == 404
        assert not ExamIncident.objects.exists()

    def test_posting_his_own_student_is_recorded(self, client_as, supervisor, exam, mine):
        response = client_as(supervisor).post(
            reverse("exam_control:incident_add", args=[exam.pk]),
            {"student_id": str(mine.id), "incident_type": "other", "description": "إزعاج"},
        )

        assert response.status_code == 302
        assert ExamIncident.objects.get().student == mine

    def test_the_service_refuses_a_student_outside_his_wing(
        self, school, supervisor, exam, mine, theirs
    ):
        with pytest.raises(Http404):
            ExamControlService.add_incident(
                session=exam,
                school=school,
                reported_by=supervisor,
                incident_type="cheating",
                severity=1,
                description="غش",
                student=theirs,
            )
        assert not ExamIncident.objects.exists()

    def _incident(self, exam, school, principal, student):
        return ExamControlService.add_incident(
            session=exam,
            school=school,
            reported_by=principal,
            incident_type="other",
            severity=1,
            description=f"حادثة {student.full_name if student else 'قاعة'}",
            student=student,
        )

    def test_the_incident_list_and_pdf_are_his_wing_and_student_less_incidents(
        self, client_as, school, supervisor, principal, exam, mine, theirs
    ):
        own = self._incident(exam, school, principal, mine)
        other = self._incident(exam, school, principal, theirs)
        room = self._incident(exam, school, principal, None)
        client = client_as(supervisor)

        listed = set(
            client.get(reverse("exam_control:incidents", args=[exam.pk])).context["incidents"]
        )

        assert listed == {own, room}
        assert client.get(reverse("exam_control:incident_pdf", args=[other.pk])).status_code == 404
        assert set(
            client_as(principal)
            .get(reverse("exam_control:incidents", args=[exam.pk]))
            .context["incidents"]
        ) == {own, other, room}

    def test_the_back_to_session_link_hides_for_the_supervisor(self, client_as, supervisor, exam):
        """`exam_control.report_incident` لا يحمل `session_detail` — فرابطُ «رجوع
        إلى الدورة» يُخفى عن مشرف الجناح، لا يُعرض ليؤدّي به إلى 403."""
        session_url = reverse("exam_control:session_detail", args=[exam.pk])
        assert client_as(supervisor).get(session_url).status_code == 403

        body = (
            client_as(supervisor)
            .get(reverse("exam_control:incidents", args=[exam.pk]))
            .content.decode()
        )
        assert f'href="{session_url}"' not in body

    def test_the_back_to_session_link_shows_for_the_principal(self, client_as, principal, exam):
        session_url = reverse("exam_control:session_detail", args=[exam.pk])
        assert client_as(principal).get(session_url).status_code == 200

        body = (
            client_as(principal)
            .get(reverse("exam_control:incidents", args=[exam.pk]))
            .content.decode()
        )
        assert f'href="{session_url}"' in body

    def test_the_exam_control_breadcrumb_hides_for_the_supervisor(
        self, client_as, supervisor, exam
    ):
        """نفسُ الفجوة في محضر تسجيل الحادث: مسارُ التصفّح لا يعِد بلوحةٍ يرفضها الحارس."""
        dashboard_url = reverse("exam_control:dashboard")
        assert client_as(supervisor).get(dashboard_url).status_code == 403

        body = (
            client_as(supervisor)
            .get(reverse("exam_control:incident_add", args=[exam.pk]))
            .content.decode()
        )
        assert f'href="{dashboard_url}"' not in body

    def test_a_student_of_another_school_cannot_be_written_on(
        self, client_as, school, principal, exam
    ):
        from tests.conftest import SchoolFactory

        elsewhere = SchoolFactory()
        stranger_class = ClassGroupFactory(
            school=elsewhere,
            grade="G7",
            section="9",
            level_type="prep",
            academic_year=exam.academic_year,
        )
        stranger = UserFactory(full_name="طالبُ مدرسةٍ أخرى", national_id="29400000099")
        StudentEnrollmentFactory(student=stranger, class_group=stranger_class)

        response = client_as(principal).post(
            reverse("exam_control:incident_add", args=[exam.pk]),
            {"student_id": str(stranger.id), "incident_type": "other", "description": "خطأ"},
        )

        assert response.status_code == 404
        assert not ExamIncident.objects.exists()


# ══════════════════════════════════════════════════════════════════
# ملفّاتُ الطلبة في /dbmedia/
# ══════════════════════════════════════════════════════════════════


def _stored(name, content=b"PDF"):
    return default_storage.save(name, ContentFile(content))


def _dbmedia(name):
    return reverse("serve_db_file", kwargs={"name": name})


class TestStudentFiles:
    @pytest.fixture
    def excuse_docs(self, school, mine, theirs):
        docs = {}
        for student in (mine, theirs):
            name = _stored(f"absence_excuses/{student.national_id}.pdf")
            AbsenceExcuse.objects.create(
                school=school,
                student=student,
                date_from=SUNDAY,
                date_to=SUNDAY,
                kind="medical",
                document=name,
            )
            docs[student] = name
        yield docs
        for name in docs.values():
            default_storage.delete(name)

    @pytest.fixture
    def tardiness_files(self, school, klass, other_klass, mine, theirs):
        files = {}
        for student, group, nid in (
            (mine, klass, "29400000301"),
            (theirs, other_klass, "29400000302"),
        ):
            name = _stored(f"tardiness_excuses/{student.national_id}.pdf")
            StudentAttendance.objects.create(
                session=_session(school, group, nid),
                student=student,
                school=school,
                status="late",
                excuse_file=name,
            )
            files[student] = name
        yield files
        for name in files.values():
            default_storage.delete(name)

    def test_absence_excuse_document_outside_his_wing_is_404(
        self, client_as, supervisor, excuse_docs, mine, theirs
    ):
        client = client_as(supervisor)

        assert client.get(_dbmedia(excuse_docs[mine])).status_code == 200
        assert client.get(_dbmedia(excuse_docs[theirs])).status_code == 404

    def test_tardiness_excuse_file_outside_his_wing_is_404(
        self, client_as, supervisor, tardiness_files, mine, theirs
    ):
        client = client_as(supervisor)

        assert client.get(_dbmedia(tardiness_files[mine])).status_code == 200
        assert client.get(_dbmedia(tardiness_files[theirs])).status_code == 404

    def test_the_principal_opens_both_wings(
        self, client_as, principal, excuse_docs, tardiness_files, mine, theirs
    ):
        client = client_as(principal)

        for name in (*excuse_docs.values(), *tardiness_files.values()):
            assert client.get(_dbmedia(name)).status_code == 200

    def test_a_school_wide_reader_is_not_narrowed(
        self, client_as, school, excuse_docs, tardiness_files, theirs
    ):
        coordinator = _member(school, "coordinator", "منسّق", "29400000004")
        client = client_as(coordinator)

        assert client.get(_dbmedia(excuse_docs[theirs])).status_code == 200
        assert client.get(_dbmedia(tardiness_files[theirs])).status_code == 200

    def test_the_student_still_opens_his_own_document(self, client_as, school, excuse_docs, theirs):
        MembershipFactory(
            user=theirs, school=school, role=RoleFactory(school=school, name="student")
        )

        assert client_as(theirs).get(_dbmedia(excuse_docs[theirs])).status_code == 200


# ══════════════════════════════════════════════════════════════════
# البحث
# ══════════════════════════════════════════════════════════════════


class TestSearch:
    def _global(self, client):
        response = client.get(reverse("global_search"), {"q": "طالب الجناح"})
        return {r["title"] for r in response.json()["results"] if r["type"] == "student"}

    def _api(self, client):
        response = client.get(reverse("api_student_search"), {"q": "طالب الجناح"})
        assert response.status_code == 200
        return {r["full_name"] for r in response.json()["results"]}

    def test_global_search_finds_only_his_wing(self, client_as, supervisor, mine, theirs):
        assert self._global(client_as(supervisor)) == {MINE}

    def test_student_search_api_finds_only_his_wing(self, client_as, supervisor, mine, theirs):
        assert self._api(client_as(supervisor)) == {MINE}

    def test_a_student_outside_his_wing_by_national_id_is_empty_not_403(
        self, client_as, supervisor, mine, theirs
    ):
        response = client_as(supervisor).get(
            reverse("api_student_search"), {"q": theirs.national_id}
        )

        assert response.status_code == 200
        assert response.json()["results"] == []

    def test_the_principal_finds_both_wings(self, client_as, principal, mine, theirs):
        client = client_as(principal)

        assert self._global(client) == {MINE, THEIRS}
        assert self._api(client) == {MINE, THEIRS}


# ══════════════════════════════════════════════════════════════════
# لوحتُه: تنبيهاتُ الغياب
# ══════════════════════════════════════════════════════════════════


class TestRecentAlerts:
    @pytest.fixture
    def alerts(self, school, mine, theirs):
        for student in (mine, theirs):
            AbsenceAlert.objects.create(
                school=school,
                student=student,
                absence_count=5,
                period_start=SUNDAY,
                period_end=SUNDAY,
            )

    def _alerted(self, user, school, role):
        from core.views_dashboard import _get_admin_ops_ctx

        ctx = _get_admin_ops_ctx(user, school, SUNDAY, role)
        return {a.student for a in ctx["recent_alerts"]}

    def test_the_supervisor_sees_his_wing_alerts(self, school, supervisor, alerts, mine):
        assert self._alerted(supervisor, school, "admin_supervisor") == {mine}

    def test_the_admin_role_is_not_narrowed(self, school, alerts, mine, theirs):
        admin = _member(school, "admin", "الإداري", "29400000005")

        assert self._alerted(admin, school, "admin") == {mine, theirs}


# ══════════════════════════════════════════════════════════════════
# قائمتُه
# ══════════════════════════════════════════════════════════════════


FOLLOW_UP_LINKS = (
    "student_affairs:dashboard",
    "student_affairs:student_list",
    "student_affairs:attendance_overview",
    "student_affairs:tardiness_list",
    "student_affairs:behavior_overview",
    "student_info:sections",
)
CLOSED_LINKS = (
    "student_affairs:student_add",
    "student_affairs:transfer_list",
    "student_affairs:activity_list",
)


class TestSupervisorMenu:
    def test_every_follow_up_link_he_can_open_is_in_his_menu(self, client_as, supervisor, klass):
        body = client_as(supervisor).get(reverse("dashboard")).content.decode()

        for name in FOLLOW_UP_LINKS:
            if can_open(supervisor, name):
                assert f'href="{reverse(name)}"' in body, name
        assert can_open(supervisor, "student_affairs:student_list"), "قائمةُ طلبة جناحه مفتوحة"

    def test_the_menu_offers_nothing_closed_to_him(self, client_as, supervisor, klass):
        body = client_as(supervisor).get(reverse("dashboard")).content.decode()

        for name in CLOSED_LINKS:
            assert not can_open(supervisor, name), name
            assert f'href="{reverse(name)}"' not in body, name
