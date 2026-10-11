"""طلباتُ الأولياء وشكاواهم والخطُّ الساخن وطلبُ تغيير الرقم وإفادةُ الطالب (W-20261001-019).

المسارُ: مقدَّم ← محوَّل ← تغذيةٌ راجعة ← تواصلٌ مؤكَّد ← مغلق، بمنفِّذٍ وتاريخٍ لكلّ مرحلة؛ وتغييرُ جوّال
الطالب لا يمرّ من شاشة التعديل مباشرةً بل بتدقيق النائب الإداريّ؛ والأثرُ بلا أسماءٍ ولا أرقام.
"""

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone

from core.models import AuditLog
from student_affairs import guardian_requests as flow
from student_affairs.guardian_request_models import GuardianRequest as GR  # noqa: N817
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    SchoolFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

OLD_PHONE = "+97455500001"
NEW_PHONE = "+97455500002"
STUDENT_NAME = "طالبٌ لمسار الطلبات"
NID = "9990000" + "0917"  # رقمٌ اصطناعيّ؛ لا يظهر في أيّ صفحةٍ ولا أثر


@pytest.fixture
def klass(school, seeded_calendar):
    return ClassGroupFactory(school=school, academic_year=seeded_calendar, grade="G10", section="1")


@pytest.fixture
def pupil(school, klass):
    user = UserFactory(full_name=STUDENT_NAME, national_id=NID, phone=OLD_PHONE)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    StudentEnrollmentFactory(student=user, class_group=klass)
    return user


def _staff(school, role, name):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def vice_admin(school):
    return _staff(school, "vice_admin", "النائب الإداري")


@pytest.fixture
def employee(school):
    return _staff(school, "teacher", "الموظف المختص")


def _new(school, actor, student, kind=GR.KIND_REQUEST, **extra):
    return flow.create_request(
        school,
        actor,
        kind=kind,
        student=student,
        guardian_name="وليّ الأمر",
        body="نصّ الطلب",
        **extra,
    )


class TestStageFlow:
    def test_the_full_path_records_actor_and_date_at_each_stage(
        self, school, principal_user, employee, pupil
    ):
        req = _new(school, principal_user, pupil, contact_phone=OLD_PHONE)
        assert req.stage == GR.STAGE_SUBMITTED

        flow.refer(req, principal_user, employee)
        flow.record_feedback(req, employee, "تمّت المعالجة")
        flow.confirm_contact(req, principal_user, GR.CONTACT_DONE)
        flow.close(req, principal_user)

        req.refresh_from_db()
        assert req.stage == GR.STAGE_CLOSED and req.closed_at is not None
        assert req.referred_to == employee and req.referred_at == timezone.localdate()
        assert req.feedback_by == employee and req.feedback_at is not None
        assert req.contact_status == GR.CONTACT_DONE
        assert [e.stage for e in req.events.all()] == [
            "submitted",
            "referred",
            "feedback",
            "contact_confirmed",
            "closed",
        ]
        assert req.events.get(stage="feedback").actor == employee

    @pytest.mark.parametrize(
        "step",
        [
            lambda r, a, e: flow.record_feedback(r, a, "نصّ"),
            lambda r, a, e: flow.confirm_contact(r, a, GR.CONTACT_DONE),
            lambda r, a, e: flow.close(r, a),
        ],
    )
    def test_a_stage_cannot_be_skipped(self, school, principal_user, employee, pupil, step):
        req = _new(school, principal_user, pupil)

        with pytest.raises(flow.TransitionError):
            step(req, principal_user, employee)

        req.refresh_from_db()
        assert req.stage == GR.STAGE_SUBMITTED

    def test_a_stage_cannot_repeat(self, school, principal_user, employee, pupil):
        req = _new(school, principal_user, pupil)
        flow.refer(req, principal_user, employee)

        with pytest.raises(flow.TransitionError):
            flow.refer(req, principal_user, employee)

    def test_feedback_needs_text_and_contact_needs_a_known_status(
        self, school, principal_user, employee, pupil
    ):
        req = _new(school, principal_user, pupil)
        flow.refer(req, principal_user, employee)
        with pytest.raises(flow.TransitionError):
            flow.record_feedback(req, employee, "   ")
        flow.record_feedback(req, employee, "تمّ")
        with pytest.raises(flow.TransitionError):
            flow.confirm_contact(req, principal_user, "maybe")

    def test_the_hotline_is_a_record_closed_after_follow_up(self, school, principal_user):
        call = flow.create_request(
            school,
            principal_user,
            kind=GR.KIND_HOTLINE,
            call_reference="HL-1",
            call_at=timezone.now(),
            caller_capacity=GR.CAPACITY_GUARDIAN,
            directed_to=GR.DIRECT_ACADEMIC,
            receiver_name="المستقبِلة",
            body="سبب الاتصال",
        )
        with pytest.raises(flow.TransitionError):
            flow.refer(call, principal_user, principal_user)

        flow.close(call, principal_user)

        assert call.stage == GR.STAGE_CLOSED

    def test_a_staff_member_of_another_school_cannot_act(self, school, principal_user, pupil):
        req = _new(school, principal_user, pupil)
        stranger = _staff(SchoolFactory(), "principal", "مدير مدرسة أخرى")

        with pytest.raises(PermissionDenied):
            flow.refer(req, stranger, principal_user)


class TestPrivacyOfTheRecord:
    def test_phones_are_stored_encrypted_and_read_back(self, school, principal_user, pupil):
        req = _new(school, principal_user, pupil, contact_phone=OLD_PHONE)
        raw = GR.objects.values_list("contact_phone_encrypted", flat=True).get(pk=req.pk)

        assert raw and OLD_PHONE not in raw
        assert GR.objects.get(pk=req.pk).contact_phone == OLD_PHONE

    def test_the_audit_trail_has_no_names_numbers_or_phones(
        self, school, principal_user, employee, pupil
    ):
        req = _new(school, principal_user, pupil, contact_phone=OLD_PHONE)
        flow.refer(req, principal_user, employee)

        trail = AuditLog.objects.filter(object_id=str(req.pk))
        assert trail.count() == 2
        blob = " ".join(f"{t.object_repr} {t.changes}" for t in trail)
        for secret in (STUDENT_NAME, "وليّ الأمر", NID, OLD_PHONE):
            assert secret not in blob

    def test_the_str_of_a_request_carries_no_name(self, school, principal_user, pupil):
        assert STUDENT_NAME not in str(_new(school, principal_user, pupil))


class TestContactChange:
    def _edit_payload(self, klass, phone):
        return {
            "full_name": STUDENT_NAME,
            "phone": phone,
            "email": "",
            "grade": klass.grade,
            "section": klass.section,
        }

    def test_editing_a_student_does_not_change_the_phone_but_opens_a_request(
        self, client_as, principal_user, pupil, klass
    ):
        client = client_as(principal_user)
        url = reverse("student_affairs:student_edit", args=[pupil.pk])

        client.post(url, self._edit_payload(klass, NEW_PHONE))
        client.post(url, self._edit_payload(klass, NEW_PHONE))  # إعادةُ الإرسال لا تكرّر الطلب

        pupil.refresh_from_db()
        assert pupil.get_phone_decrypted() == OLD_PHONE
        request = GR.objects.get(kind=GR.KIND_CONTACT_CHANGE)
        assert request.new_phone == NEW_PHONE and request.current_phone == OLD_PHONE
        assert request.student == pupil and request.created_by == principal_user

    def test_an_unchanged_phone_opens_nothing(self, client_as, principal_user, pupil, klass):
        client_as(principal_user).post(
            reverse("student_affairs:student_edit", args=[pupil.pk]),
            self._edit_payload(klass, OLD_PHONE),
        )

        assert not GR.objects.exists()

    def test_the_vice_admin_verifies_and_the_number_is_applied(
        self, school, principal_user, vice_admin, pupil
    ):
        req = flow.create_request(
            school,
            principal_user,
            kind=GR.KIND_CONTACT_CHANGE,
            student=pupil,
            current_phone=OLD_PHONE,
            new_phone=NEW_PHONE,
        )

        flow.verify_contact_change(req, vice_admin, approve=True)

        pupil.refresh_from_db()
        assert pupil.get_phone_decrypted() == NEW_PHONE
        req.refresh_from_db()
        assert req.stage == GR.STAGE_CLOSED
        assert req.verified_by == vice_admin and req.verified_at and req.applied_at

    def test_a_rejection_leaves_the_number(self, school, principal_user, vice_admin, pupil):
        req = flow.create_request(
            school,
            principal_user,
            kind=GR.KIND_CONTACT_CHANGE,
            student=pupil,
            new_phone=NEW_PHONE,
        )

        flow.verify_contact_change(req, vice_admin, approve=False)

        pupil.refresh_from_db()
        assert pupil.get_phone_decrypted() == OLD_PHONE
        assert req.stage == GR.STAGE_REJECTED and req.applied_at is None

    def test_nobody_verifies_their_own_request(self, school, vice_admin, pupil):
        req = flow.create_request(
            school, vice_admin, kind=GR.KIND_CONTACT_CHANGE, student=pupil, new_phone=NEW_PHONE
        )

        with pytest.raises(flow.TransitionError):
            flow.verify_contact_change(req, vice_admin, approve=True)

    def test_a_clerk_without_the_capability_cannot_verify(
        self, school, principal_user, student_affairs_coordinator_user, pupil
    ):
        req = flow.create_request(
            school, principal_user, kind=GR.KIND_CONTACT_CHANGE, student=pupil, new_phone=NEW_PHONE
        )

        with pytest.raises(PermissionDenied):
            flow.verify_contact_change(req, student_affairs_coordinator_user, approve=True)
        pupil.refresh_from_db()
        assert pupil.get_phone_decrypted() == OLD_PHONE

    def test_the_verify_screen_refuses_the_coordinator(
        self, client_as, school, principal_user, student_affairs_coordinator_user, pupil
    ):
        req = flow.create_request(
            school, principal_user, kind=GR.KIND_CONTACT_CHANGE, student=pupil, new_phone=NEW_PHONE
        )

        resp = client_as(student_affairs_coordinator_user).post(
            reverse("student_affairs:request_verify", args=[req.pk]), {"decision": "approve"}
        )

        assert resp.status_code in (302, 403)
        req.refresh_from_db()
        assert req.stage == GR.STAGE_SUBMITTED


class TestScreens:
    def test_a_teacher_cannot_open_the_register(self, client_as, teacher_user):
        resp = client_as(teacher_user).get(reverse("student_affairs:request_list"))

        assert resp.status_code in (302, 403)

    def test_the_whole_path_through_the_screens(
        self, client_as, school, principal_user, employee, pupil
    ):
        client = client_as(principal_user)
        created = client.post(
            reverse("student_affairs:request_create", args=[GR.KIND_COMPLAINT]),
            {
                "student_id": str(pupil.pk),
                "guardian_name": "وليّ الأمر",
                "body": "نصّ الشكوى",
                "contact_phone": OLD_PHONE,
            },
        )
        req = GR.objects.get()
        assert created.status_code == 302 and created["Location"].endswith(f"/{req.pk}/")

        def post(name, **data):
            return client.post(reverse(f"student_affairs:request_{name}", args=[req.pk]), data)

        post("refer", employee=str(employee.pk))
        post("feedback", text="تمّت المعالجة")
        post("contact", status="done")
        post("close")

        req.refresh_from_db()
        assert req.stage == GR.STAGE_CLOSED
        page = client.get(reverse("student_affairs:request_detail", args=[req.pk])).content.decode()
        assert STUDENT_NAME in page and NID not in page and NID[-4:] not in page

    def test_an_out_of_order_post_is_a_message_not_a_crash(
        self, client_as, school, principal_user, pupil
    ):
        req = _new(school, principal_user, pupil)

        resp = client_as(principal_user).post(
            reverse("student_affairs:request_close", args=[req.pk]), {}
        )

        assert resp.status_code == 302
        req.refresh_from_db()
        assert req.stage == GR.STAGE_SUBMITTED

    def test_a_request_of_another_school_is_not_found(self, client_as, principal_user):
        other = SchoolFactory()
        outsider = _staff(other, "principal", "مدير آخر")
        foreign = flow.create_request(
            other, outsider, kind=GR.KIND_HOTLINE, call_reference="X", receiver_name="س", body="س"
        )

        resp = client_as(principal_user).get(
            reverse("student_affairs:request_detail", args=[foreign.pk])
        )

        assert resp.status_code == 404

    def test_the_forms_render_without_the_national_id(self, client_as, principal_user, pupil):
        client = client_as(principal_user)
        for kind in GR.KIND_CHOICES:
            resp = client.get(reverse("student_affairs:request_create", args=[kind[0]]))
            body = resp.content.decode()
            assert resp.status_code == 200
            assert NID not in body and NID[-4:] not in body

    def test_an_unknown_kind_goes_back_to_the_register(self, client_as, principal_user):
        resp = client_as(principal_user).get(
            reverse("student_affairs:request_create", args=["nonsense"])
        )

        assert resp.status_code == 302

    def test_the_hotline_form_requires_its_fields_and_an_explanation_for_other(
        self, client_as, principal_user
    ):
        resp = client_as(principal_user).post(
            reverse("student_affairs:request_create", args=[GR.KIND_HOTLINE]),
            {"caller_capacity": "other", "directed_to": "other"},
        )

        assert resp.status_code == 200 and not GR.objects.exists()
        form = resp.context["form"]
        assert {"call_reference", "call_at", "receiver_name", "body"} <= set(form.errors)
        assert {"caller_capacity_note", "directed_note"} <= set(form.errors)
