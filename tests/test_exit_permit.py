"""ورقةُ خروج الطالب: إصدارٌ مباشرٌ بلا اعتماد لخمسة أدوار، وطريقةُ موافقة الوليّ، واستمارةُ الحارس (W-20261116-003).

- كلُّ دورٍ من الخمسة يُصدر ويطبع، والمعلّمُ 404؛ ومشرفُ الجناح لجناحه وحدَه.
- الإصدارُ ينجح بلا حصّةٍ جارية؛ ولا طباعةَ بلا طريقة موافقة، ومع الاتّصال بلا رقمٍ ومتّصل.
- الهاتفُ مقنَّعٌ في التدقيق، ولا اسمَ طالبٍ ولا اسمَ متّصل.
- نصُّ الاستمارة من الثوابت المركزيّة؛ وفيها خانةُ توقيع النائب الإداريّ أو المكلَّف وسطرُ التسليم للأمن.
- أذوناتٌ قديمةٌ (`approved`) تبقى مقروءةً ومطبوعة.
"""

import datetime as dt

import pytest
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from core.export_utils import get_export_context_for
from core.models import AuditLog, ParentStudentLink
from operations.models import ExitPermit, Session
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
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
from wings import exit_permit_form as form
from wings import exit_permit_services as service
from wings.exit_permit_pdf_services import TEMPLATE, form_context

pytestmark = pytest.mark.django_db

REGISTERED = "+97455000001"
UNREGISTERED = "+97455000002"


def _complete(school, klass, teacher, count):
    sessions = _periods(school, klass, teacher, count=count, day=SUNDAY)
    Session.objects.filter(pk__in=[s.pk for s in sessions]).update(status="completed")


AT = timezone.make_aware(dt.datetime.combine(SUNDAY, dt.time(11, 0)))


def _issue(user, school, student, **kw):
    kw.setdefault("exit_at", AT)
    kw.setdefault("guardian_method", "present")
    return service.issue_permit(user, school, student, reason="medical", **kw)


def _staff(school, role, national_id):
    user = UserFactory(full_name=f"موظف {role}", national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _phone_call(user, school, student, **kw):
    kw.setdefault("call_phone", REGISTERED)
    kw.setdefault("caller_name", "ولي الأمر")
    kw.setdefault("caller_relation", "الأب")
    return _issue(user, school, student, guardian_method="phone", **kw)


class TestIssue:
    def test_wing_holder_issues_with_sequence_and_period_count(
        self, school, klass, kids, teacher, supervisor
    ):
        _complete(school, klass, teacher, 5)
        permit = _issue(supervisor, school, kids[0])
        second = _issue(supervisor, school, kids[1])
        assert (permit.sequence, second.sequence) == (1, 2)
        assert permit.status == "issued" and permit.requested_by == supervisor
        assert permit.completed_periods == 5
        assert permit.class_group == klass

    def test_issue_succeeds_without_a_running_session(self, school, klass, kids, supervisor):
        assert not Session.objects.filter(class_group=klass).exists()
        permit = _issue(supervisor, school, kids[0])
        assert permit.completed_periods == 0 and service.is_printable(permit)

    @pytest.mark.parametrize(
        "role", ["student_affairs_coordinator", "vice_admin", "vice_academic", "principal"]
    )
    def test_school_wide_roles_issue_and_print(
        self, client_as, school, klass, kids, supervisor, role
    ):
        user = _staff(school, role, "29000000001")
        permit = _issue(user, school, kids[0])
        response = client_as(user).get(reverse("wings:exit_permit_pdf", args=[permit.id]))
        assert response.status_code == 200 and response.content[:4] == b"%PDF"

    def test_wing_supervisor_issues_and_prints(self, client_as, school, klass, kids, supervisor):
        permit = _issue(supervisor, school, kids[0])
        response = client_as(supervisor).get(reverse("wings:exit_permit_pdf", args=[permit.id]))
        assert response.status_code == 200 and response.content[:4] == b"%PDF"

    def test_other_wing_holder_is_denied(self, school, klass, kids, supervisor, stranger_wing):  # noqa: F811
        other = stranger_wing.enrollments.first().class_group.wing.supervisor
        with pytest.raises(service.PermitDeniedError):
            _issue(other, school, kids[0])

    def test_teacher_cannot_issue_or_print(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        with pytest.raises(service.PermitDeniedError):
            _issue(teacher, school, kids[0])
        permit = _issue(supervisor, school, kids[0])
        c = client_as(teacher)
        # الخدمةُ تحوّل المنعَ إلى 404؛ وقد يردّه بوّابُ الوحدة أو القدرةُ قبلها بـ403 — لا 200 في الحالتين.
        for url in (
            reverse("wings:exit_permit_new", args=[kids[0].id]),
            reverse("wings:exit_permit_pdf", args=[permit.id]),
        ):
            response = c.get(url)
            assert response.status_code in (403, 404)
            assert response.content[:4] != b"%PDF"

    def test_unknown_reason_is_rejected(self, school, klass, kids, supervisor):
        with pytest.raises(service.PermitError):
            service.issue_permit(
                supervisor, school, kids[0], reason="nonsense", guardian_method="present"
            )


class TestGuardianMethod:
    def test_the_method_is_mandatory(self, school, klass, kids, supervisor):
        for method in ("", "sms"):
            with pytest.raises(service.PermitError):
                _issue(supervisor, school, kids[0], guardian_method=method)
        assert not ExitPermit.objects.exists()

    @pytest.mark.parametrize("kw", [{"call_phone": ""}, {"caller_name": ""}, {"call_phone": "abc"}])
    def test_a_call_needs_a_phone_and_a_caller(self, school, klass, kids, supervisor, kw):
        with pytest.raises(service.PermitError):
            _phone_call(supervisor, school, kids[0], **kw)
        assert not ExitPermit.objects.exists()

    def test_registered_and_manual_numbers_are_flagged(self, school, klass, kids, supervisor):
        parent = UserFactory(full_name="ولي الأمر", national_id="29000000003", phone=REGISTERED)
        ParentStudentLink.objects.create(parent=parent, student=kids[0], school=school)
        assert service.registered_phones(school, kids[0]) == [REGISTERED]
        known = _phone_call(supervisor, school, kids[0])
        manual = _phone_call(supervisor, school, kids[0], call_phone=UNREGISTERED)
        assert known.call_phone_registered and not manual.call_phone_registered
        assert known.call_phone == REGISTERED and known.caller_name == "ولي الأمر"

    def test_card_presence_stores_no_call_data(self, school, klass, kids, supervisor):
        permit = _issue(supervisor, school, kids[0], call_phone=REGISTERED, caller_name="س")
        assert (permit.call_phone, permit.caller_name) == ("", "")
        assert permit.guardian_present and permit.guardian_method == "present"

    def test_an_incomplete_row_is_never_printed(self, client_as, school, klass, kids, supervisor):
        bare = _issue(supervisor, school, kids[0])
        ExitPermit.objects.filter(pk=bare.pk).update(guardian_method="")
        broken = _phone_call(supervisor, school, kids[1])
        ExitPermit.objects.filter(pk=broken.pk).update(caller_name="")
        c = client_as(supervisor)
        for permit in (bare, broken):
            permit.refresh_from_db()
            assert not service.is_printable(permit)
            assert c.get(reverse("wings:exit_permit_pdf", args=[permit.id])).status_code == 404

    def test_the_audit_masks_the_phone_and_has_no_names(self, school, klass, kids, supervisor):
        permit = _phone_call(supervisor, school, kids[0], caller_name="اسم المتصل السري")
        text = " ".join(
            f"{log.object_repr} {log.changes}"
            for log in AuditLog.objects.filter(object_id=str(permit.pk))
        )
        assert REGISTERED not in text and "اسم المتصل السري" not in text
        assert kids[0].full_name not in text
        log = AuditLog.objects.get(object_id=str(permit.pk), action="create")
        assert log.changes["call_phone"].endswith(REGISTERED[-4:])
        assert log.changes["call_phone"] != REGISTERED


class TestPeriodsWarning:
    def test_fewer_than_four_completed_warns_and_does_not_block(
        self, school, klass, kids, teacher, supervisor
    ):
        _complete(school, klass, teacher, 2)
        permit = _issue(supervisor, school, kids[0])
        assert permit.completed_periods == 2 and service.low_periods(permit)
        assert service.is_printable(permit)
        assert form_context(permit)["warning"] == form.LOW_PERIODS_WARNING % 4

    def test_four_or_more_has_no_warning(self, school, klass, kids, teacher, supervisor):
        _complete(school, klass, teacher, 4)
        permit = _issue(supervisor, school, kids[0])
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
        permit = _issue(supervisor, school, kids[0])
        assert (
            client_as(other).get(reverse("wings:exit_permit_pdf", args=[permit.id])).status_code
            == 404
        )

    def test_issue_screen_then_list_then_pdf_with_no_approval_step(
        self, client_as, school, klass, kids, supervisor
    ):
        c = client_as(supervisor)
        url = reverse("wings:exit_permit_new", args=[kids[0].id])
        assert c.get(url).status_code == 200
        refused = c.post(url, {"reason": "family", "note": "x"})
        assert refused.status_code == 200 and not ExitPermit.objects.exists()
        c.post(
            url,
            {"reason": "family", "note": "x", "guardian_method": "present", "has_disability": "no"},
        )
        permit = ExitPermit.objects.get()
        assert c.get(reverse("wings:exit_permit_list")).status_code == 200
        response = c.get(reverse("wings:exit_permit_pdf", args=[permit.id]))
        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert response.content[:4] == b"%PDF"
        # كلُّ تصديرٍ يُدوَّن (W-20261021-005): الاستمارةُ تحمل بياناتِ طالب.
        log = AuditLog.objects.get(action="export", changes__kind="wings.exit_permit_pdf")
        assert log.object_id == str(permit.id)

    def test_the_phone_call_posts_through_the_screen(
        self, client_as, school, klass, kids, supervisor
    ):
        c = client_as(supervisor)
        c.post(
            reverse("wings:exit_permit_new", args=[kids[0].id]),
            {
                "reason": "family",
                "has_disability": "no",
                "guardian_method": "phone",
                "call_phone_choice": "other",
                "call_phone_manual": UNREGISTERED,
                "caller_name": "الأم",
                "caller_relation": "أم",
            },
        )
        permit = ExitPermit.objects.get()
        assert permit.call_phone == UNREGISTERED and not permit.call_phone_registered

    def test_the_form_is_one_portrait_page(self, client_as, school, klass, kids, supervisor):
        """أمر المالك 2026-10-18: الاستمارةُ صفحةٌ واحدةٌ راسيّةٌ فقط — وأطولُها طريقةُ الاتّصال بملاحظةٍ قصوى."""
        from io import BytesIO

        from pypdf import PdfReader

        permit = _phone_call(supervisor, school, kids[0], note=("ملاحظة طويلة " * 20)[:200])
        pdf = client_as(supervisor).get(reverse("wings:exit_permit_pdf", args=[permit.id])).content
        pages = PdfReader(BytesIO(pdf)).pages
        assert len(pages) == 1
        assert pages[0].mediabox.height > pages[0].mediabox.width

    def test_a_legacy_approved_permit_is_still_readable_and_printable(
        self, client_as, school, klass, kids, supervisor
    ):
        permit = _issue(supervisor, school, kids[0])
        ExitPermit.objects.filter(pk=permit.pk).update(
            status="approved", guardian_method="", guardian_present=True, approved_by=supervisor
        )
        c = client_as(supervisor)
        assert c.get(reverse("wings:exit_permit_list")).status_code == 200
        assert c.get(reverse("wings:exit_permit_pdf", args=[permit.id])).status_code == 200


class TestFormFromConstants:
    def test_changing_a_constant_changes_the_form_without_the_template(
        self, school, klass, kids, supervisor, monkeypatch
    ):
        permit = _issue(supervisor, school, kids[0])
        monkeypatch.setattr(form, "FORM_TITLE", "عنوانٌ جديد للاستمارة")
        monkeypatch.setitem(form.FIELD_LABELS, "student", "اسمُ الطالب المعدَّل")
        ctx = form_context(permit)
        assert ctx["title"] == "عنوانٌ جديد للاستمارة"
        assert ctx["rows"][1][0] == "اسمُ الطالب المعدَّل"

    def test_the_form_carries_the_signature_box_the_delivery_line_and_the_call(
        self, school, klass, kids, supervisor
    ):
        permit = _phone_call(supervisor, school, kids[0], call_phone=UNREGISTERED)
        ctx = get_export_context_for(supervisor, form.FORM_TITLE)
        ctx.update(form_context(permit))
        ctx["school"] = school
        html = render_to_string(TEMPLATE, ctx)
        assert "النائب الإداري أو المكلَّف بعمله" in html
        assert "تُسلَّم للأمن عند الخروج، ولا يخرج الطالب بلا توقيعها" in html
        assert form.GUARDIAN_PHONE in html and UNREGISTERED.lstrip("+") in html
        assert UNREGISTERED not in html and form.SIGNATORY_NAME_LABEL in html
        assert form.UNREGISTERED_PHONE in html and "الأب" in html


class TestGuardianSignatureBox:
    def test_card_presence_adds_the_guardian_signature_and_a_call_does_not(
        self, school, klass, kids, supervisor
    ):
        present = form_context(_issue(supervisor, school, kids[0]))["signatories"]
        called = form_context(_phone_call(supervisor, school, kids[1]))["signatories"]
        assert form.GUARDIAN_SIGNATURE in present and form.GUARDIAN_SIGNATURE not in called
        assert list(form.SIGNATORIES) == present[1:] == called


class TestDisabilityRestriction:
    """المادة 3.7.3.4: ذوو الإعاقة يخرجون بحضور وليّ الأمر وتوقيعه؛ والجوابُ للتحقّق لحظةَ الإصدار ولا يُحفظ."""

    def _post(self, client, student, **kw):
        data = {"reason": "family", "guardian_method": "present", "has_disability": "yes"}
        data.update(kw)
        return client.post(reverse("wings:exit_permit_new", args=[student.id]), data)

    def _phone(self, **kw):
        return {
            "guardian_method": "phone",
            "call_phone_choice": "other",
            "call_phone_manual": REGISTERED,
            "caller_name": "الأب",
            **kw,
        }

    def test_the_answer_is_mandatory(self, client_as, school, klass, kids, supervisor):
        response = self._post(client_as(supervisor), kids[0], has_disability="")
        assert response.status_code == 200 and not ExitPermit.objects.exists()

    def test_yes_rejects_phone_in_the_server(self, client_as, school, klass, kids, supervisor):
        response = self._post(client_as(supervisor), kids[0], **self._phone())
        assert response.status_code == 200 and not ExitPermit.objects.exists()
        assert "3.7.3.4" in response.content.decode()
        with pytest.raises(service.PermitError, match="3.7.3.4"):
            _phone_call(supervisor, school, kids[0], restricted=True)

    def test_no_keeps_phone_working(self, client_as, school, klass, kids, supervisor):
        self._post(client_as(supervisor), kids[0], **self._phone(has_disability="no"))
        assert ExitPermit.objects.get().guardian_method == "phone"

    def test_yes_sheet_has_signature_and_line_without_disability(
        self, client_as, school, klass, kids, supervisor
    ):
        response = self._post(client_as(supervisor), kids[0])
        permit = ExitPermit.objects.get()
        assert response.status_code == 302 and "guardian_only" not in response.url
        ctx = form_context(permit)
        assert form.GUARDIAN_SIGNATURE in ctx["signatories"]
        assert ctx["guardian_only_line"] == form.GUARDIAN_ONLY_LINE
        html = render_to_string(TEMPLATE, {**get_export_context_for(supervisor, "x"), **ctx})
        assert form.GUARDIAN_ONLY_LINE in html and "إعاقة" not in html
        pdf = client_as(supervisor).get(response.url)
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

    def test_the_line_follows_the_method_on_every_print(
        self, client_as, school, klass, kids, supervisor
    ):
        """السطر وخانة التوقيع لكل ورقة «حضر ببطاقته» (ولو قديمة بلا طريقة)، لا لورقة الاتصال."""
        present = _issue(supervisor, school, kids[0])
        called = _phone_call(supervisor, school, kids[1])
        legacy = _issue(supervisor, school, kids[2])
        ExitPermit.objects.filter(pk=legacy.pk).update(guardian_method="", guardian_present=True)
        legacy.refresh_from_db()
        for permit, shown in ((present, True), (legacy, True), (called, False)):
            ctx = form_context(permit)
            assert (ctx["guardian_only_line"] == form.GUARDIAN_ONLY_LINE) is shown
            assert (form.GUARDIAN_SIGNATURE in ctx["signatories"]) is shown
        url = reverse("wings:exit_permit_pdf", args=[present.id])
        assert "guardian_only" not in url
        assert client_as(supervisor).get(url).status_code == 200

    def test_the_caller_is_encrypted_at_rest(self, school, klass, kids, supervisor):
        from django.db import connection

        permit = _phone_call(supervisor, school, kids[0], caller_name="اسم المتصل السري")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT caller_name, caller_relation FROM operations_exitpermit WHERE id = %s",
                [permit.pk],
            )
            raw = cursor.fetchone()
        permit.refresh_from_db()
        assert (permit.caller_name, permit.caller_relation) == ("اسم المتصل السري", "الأب")
        assert "اسم المتصل السري" not in raw[0] and "الأب" not in raw[1]

    def test_the_answer_is_stored_nowhere(self, client_as, school, klass, kids, supervisor):
        self._post(client_as(supervisor), kids[0])
        permit = ExitPermit.objects.get()
        assert not [f for f in permit._meta.get_fields() if "disab" in f.name]
        text = " ".join(f"{log.object_repr} {log.changes}" for log in AuditLog.objects.all())
        assert "disab" not in text and "إعاقة" not in text


class TestWhoMayIssue:
    """قرارُ المالك 2026-11-16: خمسةُ أدوارٍ تُصدر وتطبع، والمعلّمُ ومن يرثه خارجَها."""

    FIVE = {
        "admin_supervisor",
        "student_affairs_coordinator",
        "vice_admin",
        "vice_academic",
        "principal",
    }

    def test_exactly_the_five_roles_hold_the_capability(self):
        from core.capabilities import registry

        roles = registry()[service.REQUEST_CAP].expanded_roles
        assert self.FIVE <= roles
        assert "teacher" not in roles

    def test_erasure_covers_the_permit_rows_with_the_call_data(self):
        from governance.erasure_service import _lazy_student_fk_models

        assert any(model is ExitPermit for model, _, _ in _lazy_student_fk_models())
