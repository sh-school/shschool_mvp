"""
tests/test_exam_control.py
اختبارات وحدة كنترول الاختبارات
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يغطي:
  - ExamSession نموذج البيانات
  - views: dashboard, session_create, session_detail,
           supervisors, schedule, incidents, grade_sheets
  - صلاحيات: مدير ومدير المدرسة فقط للإنشاء
  - login_required على جميع الـ views
"""

from datetime import date, timedelta

import pytest

from exam_control.models import ExamSession

from .conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory

# ── Factories ──────────────────────────────────────────────────────────


def make_exam_session(school, user):
    return ExamSession.objects.create(
        school=school,
        name="اختبارات نهاية الفصل الأول",
        session_type="final",
        academic_year="2025-2026",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=14),
        created_by=user,
    )


def make_principal(db, school):
    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name="مدير المدرسة")
    MembershipFactory(user=user, school=school, role=role)
    return user


def make_teacher(db, school):
    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(full_name="معلم عادي")
    MembershipFactory(user=user, school=school, role=role)
    return user


# ══════════════════════════════════════════════════════════
#  1. ExamSession — النموذج
# ══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestExamSessionModel:
    def test_create_session(self, school, principal_user):
        session = make_exam_session(school, principal_user)
        assert session.pk is not None
        assert session.name == "اختبارات نهاية الفصل الأول"
        assert session.status == "planned"
        assert session.session_type == "final"

    def test_str(self, school, principal_user):
        session = make_exam_session(school, principal_user)
        assert "2025-2026" in str(session)

    def test_ordering(self, school, principal_user):
        s1 = ExamSession.objects.create(
            school=school, name="A", session_type="mid",
            academic_year="2025-2026",
            start_date=date.today() - timedelta(days=30),
            end_date=date.today() - timedelta(days=20),
            created_by=principal_user,
        )
        s2 = make_exam_session(school, principal_user)
        sessions = list(ExamSession.objects.filter(school=school))
        # أحدث أولاً
        assert sessions[0].pk == s2.pk


# ══════════════════════════════════════════════════════════
#  2. Dashboard View
# ══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestExamDashboard:
    def test_redirect_if_not_logged_in(self, client):
        response = client.get("/exam-control/")
        assert response.status_code in (302, 301)
        assert "/auth/" in response["Location"] or "/login" in response["Location"]

    def test_principal_can_view(self, client_as, school, principal_user):
        client = client_as(principal_user)
        response = client.get("/exam-control/")
        assert response.status_code == 200

    def test_teacher_can_view(self, client_as, school, teacher_user):
        """جميع المستخدمين المسجّلين يمكنهم رؤية اللوحة"""
        client = client_as(teacher_user)
        response = client.get("/exam-control/")
        assert response.status_code == 200

    def test_shows_sessions(self, client_as, school, principal_user):
        make_exam_session(school, principal_user)
        client = client_as(principal_user)
        response = client.get("/exam-control/")
        assert response.status_code == 200
        assert "sessions" in response.context
        assert response.context["sessions"].count() >= 1

    def test_empty_state(self, client_as, school, principal_user):
        client = client_as(principal_user)
        response = client.get("/exam-control/")
        assert response.status_code == 200
        assert "sessions" in response.context


# ══════════════════════════════════════════════════════════
#  3. Session Create
# ══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestExamSessionCreate:
    def test_get_form(self, client_as, school, principal_user):
        client = client_as(principal_user)
        response = client.get("/exam-control/session/create/")
        assert response.status_code == 200

    def test_teacher_forbidden(self, client_as, school, teacher_user):
        client = client_as(teacher_user)
        response = client.post("/exam-control/session/create/", {
            "name": "اختبار",
            "session_type": "final",
            "academic_year": "2025-2026",
            "start_date": str(date.today()),
            "end_date": str(date.today() + timedelta(days=10)),
        })
        assert response.status_code == 403

    def test_principal_can_create(self, client_as, school, principal_user):
        client = client_as(principal_user)
        response = client.post("/exam-control/session/create/", {
            "name": "اختبارات نهاية الفصل",
            "session_type": "final",
            "academic_year": "2025-2026",
            "start_date": str(date.today()),
            "end_date": str(date.today() + timedelta(days=14)),
        })
        assert response.status_code in (302, 200)
        if response.status_code == 302:
            assert ExamSession.objects.filter(
                school=school, name="اختبارات نهاية الفصل"
            ).exists()


# ══════════════════════════════════════════════════════════
#  4. Session Detail
# ══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestExamSessionDetail:
    def test_session_detail_loads(self, client_as, school, principal_user):
        session = make_exam_session(school, principal_user)
        client = client_as(principal_user)
        response = client.get(f"/exam-control/session/{session.pk}/")
        assert response.status_code == 200
        assert "session" in response.context
        assert response.context["session"].pk == session.pk

    def test_wrong_school_404(self, client_as, school, principal_user):
        """لا يمكن رؤية دورة مدرسة أخرى"""
        other_school = SchoolFactory()
        other_user = UserFactory()
        other_role = RoleFactory(school=other_school, name="principal")
        MembershipFactory(user=other_user, school=other_school, role=other_role)
        session = make_exam_session(other_school, other_user)

        client = client_as(principal_user)
        response = client.get(f"/exam-control/session/{session.pk}/")
        assert response.status_code == 404

    def test_detail_shows_context(self, client_as, school, principal_user):
        session = make_exam_session(school, principal_user)
        client = client_as(principal_user)
        response = client.get(f"/exam-control/session/{session.pk}/")
        assert "rooms" in response.context
        assert "supervisors" in response.context
        assert "schedules" in response.context
        assert "incidents" in response.context


# ══════════════════════════════════════════════════════════
#  5. Supervisors View
# ══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestExamSupervisors:
    def test_supervisors_page_loads(self, client_as, school, principal_user):
        session = make_exam_session(school, principal_user)
        client = client_as(principal_user)
        response = client.get(f"/exam-control/session/{session.pk}/supervisors/")
        assert response.status_code == 200

    def test_teacher_can_view_supervisors(self, client_as, school, teacher_user, principal_user):
        session = make_exam_session(school, principal_user)
        client = client_as(teacher_user)
        response = client.get(f"/exam-control/session/{session.pk}/supervisors/")
        assert response.status_code == 200


# ══════════════════════════════════════════════════════════
#  6. Incidents View
# ══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestExamIncidents:
    def test_incidents_page_loads(self, client_as, school, principal_user):
        session = make_exam_session(school, principal_user)
        client = client_as(principal_user)
        response = client.get(f"/exam-control/session/{session.pk}/incidents/")
        assert response.status_code == 200

    def test_add_incident_requires_login(self, client, school, principal_user):
        session = make_exam_session(school, principal_user)
        response = client.post(f"/exam-control/session/{session.pk}/incident/add/", {})
        assert response.status_code in (302, 301)

    def test_add_incident_forbidden_for_teacher(self, client_as, school, teacher_user, principal_user):
        session = make_exam_session(school, principal_user)
        client = client_as(teacher_user)
        response = client.post(f"/exam-control/session/{session.pk}/incident/add/", {
            "description": "حادثة غش",
            "incident_type": "cheating",
        })
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════
#  7. Grade Sheets View
# ══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestExamGradeSheets:
    def test_grade_sheets_loads(self, client_as, school, principal_user):
        session = make_exam_session(school, principal_user)
        client = client_as(principal_user)
        response = client.get(f"/exam-control/session/{session.pk}/grade-sheets/")
        assert response.status_code == 200


# ══════════════════════════════════════════════════════════
#  8. PWA Views
# ══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPWAViews:
    def test_manifest_unauthenticated(self, client):
        response = client.get("/manifest.json")
        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"

    def test_manifest_authenticated(self, client_as, teacher_user):
        client = client_as(teacher_user)
        response = client.get("/manifest.json")
        assert response.status_code == 200
        content = response.content.decode()
        assert "SchoolOS" in content

    def test_sw_js(self, client):
        response = client.get("/sw.js")
        assert response.status_code == 200
        assert "javascript" in response["Content-Type"]

    def test_offline_page(self, client):
        response = client.get("/offline/")
        assert response.status_code == 200
        assert "غير متصل" in response.content.decode()

    def test_manifest_teacher_start_url(self, client_as, school, teacher_user):
        client = client_as(teacher_user)
        response = client.get("/manifest.json")
        content = response.content.decode()
        assert "/teacher/schedule/" in content

    def test_manifest_parent_start_url(self, client_as, school, parent_user):
        client = client_as(parent_user)
        response = client.get("/manifest.json")
        content = response.content.decode()
        assert "/parents/" in content
