"""إذنُ خروج الطالب: الطلبُ والاعتمادُ بدورٍ محدَّد، وحضورُ الوليّ، وتحذيرُ الحصص، واستمارةُ الحارس (W-20261005-010).

- المعلّمُ يطلب لشُعبه؛ وحاملُ الجناح يطلب ويعتمد لأجنحته؛ وغيرُ المخوَّل 404.
- لا اعتمادَ دون تسجيل حضور وليّ الأمر.
- أقلُّ من أربع حصصٍ مكتملة تحذيرٌ لا يمنع، والحضورُ لا يتغيّر.
- نصُّ الاستمارة من الثوابت المركزيّة: تغييرُ ثابتٍ يغيّر الاستمارة دون القالب.
- تدقيقٌ بلا اسم، وحارسُ المحو.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import AuditLog
from operations.models import ExitPermit, Session, Subject, SubjectClassAssignment
from tests.test_absence_file import stranger_wing  # noqa: F401
from tests.test_period_register import (  # noqa: F401
    SUNDAY,
    _periods,
    kids,
    klass,
    subjects,
    supervisor,
    teacher,
    year,
)
from wings import exit_permit as service
from wings import exit_permit_form as form
from wings.exit_permit_print import form_context

pytestmark = pytest.mark.django_db


def _complete(school, klass, teacher, count):
    sessions = _periods(school, klass, teacher, count=count, day=SUNDAY)
    Session.objects.filter(pk__in=[s.pk for s in sessions]).update(status="completed")


@pytest.fixture
def assigned(school, klass, teacher, year):
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MATHX")
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=klass,
        subject=subject,
        teacher=teacher,
        weekly_periods=4,
        academic_year=year,
    )


AT = timezone.make_aware(dt.datetime.combine(SUNDAY, dt.time(11, 0)))


def _request(user, school, student, **kw):
    kw.setdefault("exit_at", AT)
    return service.request_permit(user, school, student, reason="medical", **kw)


class TestRequest:
    def test_wing_holder_requests_with_sequence_and_period_count(
        self, school, klass, kids, teacher, supervisor
    ):
        _complete(school, klass, teacher, 5)
        permit = _request(supervisor, school, kids[0])
        second = _request(supervisor, school, kids[1])
        assert (permit.sequence, second.sequence) == (1, 2)
        assert permit.status == "requested"
        assert permit.completed_periods == 5
        assert permit.class_group == klass

    def test_teacher_requests_only_for_his_own_sections(
        self,
        school,
        klass,
        kids,
        teacher,
        assigned,
        stranger_wing,  # noqa: F811
    ):
        assert _request(teacher, school, kids[0]).requested_by == teacher
        with pytest.raises(service.PermitDeniedError):
            _request(teacher, school, stranger_wing)

    def test_other_wing_holder_is_denied(self, school, klass, kids, supervisor, stranger_wing):  # noqa: F811
        other = stranger_wing.enrollments.first().class_group.wing.supervisor
        with pytest.raises(service.PermitDeniedError):
            _request(other, school, kids[0])

    def test_unknown_reason_is_rejected(self, school, klass, kids, supervisor):
        with pytest.raises(service.PermitError):
            service.request_permit(supervisor, school, kids[0], reason="nonsense")


class TestApprove:
    def test_no_approval_without_the_guardian_present(self, school, klass, kids, supervisor):
        permit = _request(supervisor, school, kids[0])
        with pytest.raises(service.PermitError):
            service.approve_permit(supervisor, school, permit.pk, guardian_present=False)
        permit.refresh_from_db()
        assert permit.status == "requested" and permit.approved_by is None

    def test_wing_holder_approves_and_it_is_audited_without_names(
        self, school, klass, kids, supervisor
    ):
        permit = _request(supervisor, school, kids[0])
        service.approve_permit(supervisor, school, permit.pk, guardian_present=True)
        permit.refresh_from_db()
        assert (permit.status, permit.guardian_present, permit.approved_by) == (
            "approved",
            True,
            supervisor,
        )
        logs = AuditLog.objects.filter(object_id=str(permit.pk))
        assert logs.count() == 2
        assert all(kids[0].full_name not in (log.object_repr or "") for log in logs)

    def test_a_teacher_cannot_approve(self, school, klass, kids, teacher, assigned):
        permit = _request(teacher, school, kids[0])
        with pytest.raises(service.PermitDeniedError):
            service.approve_permit(teacher, school, permit.pk, guardian_present=True)

    def test_a_stranger_wing_holder_cannot_approve(
        self,
        school,
        klass,
        kids,
        supervisor,
        stranger_wing,  # noqa: F811
    ):
        permit = _request(supervisor, school, kids[0])
        other = stranger_wing.enrollments.first().class_group.wing.supervisor
        with pytest.raises(service.PermitDeniedError):
            service.approve_permit(other, school, permit.pk, guardian_present=True)


class TestPeriodsWarning:
    def test_fewer_than_four_completed_warns_and_does_not_block(
        self, school, klass, kids, teacher, supervisor
    ):
        _complete(school, klass, teacher, 2)
        permit = _request(supervisor, school, kids[0])
        assert permit.completed_periods == 2 and service.low_periods(permit)
        service.approve_permit(supervisor, school, permit.pk, guardian_present=True)
        assert form_context(permit)["warning"] == form.LOW_PERIODS_WARNING % 4

    def test_four_or_more_has_no_warning(self, school, klass, kids, teacher, supervisor):
        _complete(school, klass, teacher, 4)
        permit = _request(supervisor, school, kids[0])
        assert not service.low_periods(permit)
        assert form_context(permit)["warning"] == ""


class TestScreens:
    def test_the_stranger_gets_404_on_new_and_pdf(
        self,
        client_as,
        school,
        klass,
        kids,
        supervisor,
        stranger_wing,  # noqa: F811
    ):
        other = stranger_wing.enrollments.first().class_group.wing.supervisor
        assert (
            client_as(other).get(reverse("wings:exit_permit_new", args=[kids[0].id])).status_code
            == 404
        )
        permit = _request(supervisor, school, kids[0])
        service.approve_permit(supervisor, school, permit.pk, guardian_present=True)
        assert (
            client_as(other).get(reverse("wings:exit_permit_pdf", args=[permit.id])).status_code
            == 404
        )

    def test_request_screen_then_list_then_pdf(self, client_as, school, klass, kids, supervisor):
        c = client_as(supervisor)
        assert c.get(reverse("wings:exit_permit_new", args=[kids[0].id])).status_code == 200
        c.post(
            reverse("wings:exit_permit_new", args=[kids[0].id]), {"reason": "family", "note": "x"}
        )
        permit = ExitPermit.objects.get()
        assert c.get(reverse("wings:exit_permit_list")).status_code == 200
        assert c.get(reverse("wings:exit_permit_pdf", args=[permit.id])).status_code == 404
        c.post(reverse("wings:exit_permit_approve", args=[permit.id]), {"guardian_present": "on"})
        response = c.get(reverse("wings:exit_permit_pdf", args=[permit.id]))
        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert response.content[:4] == b"%PDF"


class TestFormFromConstants:
    def test_changing_a_constant_changes_the_form_without_the_template(
        self, school, klass, kids, supervisor, monkeypatch
    ):
        permit = _request(supervisor, school, kids[0])
        service.approve_permit(supervisor, school, permit.pk, guardian_present=True)
        monkeypatch.setattr(form, "FORM_TITLE", "عنوانٌ جديد للاستمارة")
        monkeypatch.setitem(form.FIELD_LABELS, "student", "اسمُ الطالب المعدَّل")
        ctx = form_context(permit)
        assert ctx["title"] == "عنوانٌ جديد للاستمارة"
        assert ctx["rows"][1][0] == "اسمُ الطالب المعدَّل"
