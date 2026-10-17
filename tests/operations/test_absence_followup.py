"""شاشةُ «متابعة الغياب» (W-20261013-011) — سجلّان مضافان فقط، وأدوارٌ بنطاقها، وخصوصيّةٌ لا تُخرق.

- الأدوار: المدير والنائبُ الإداريّ ومنسّقُ شؤون الطلبة على المدرسة، ومشرفُ الجناح على جناحه (طالبٌ خارجه 404)،
  والنائبُ الأكاديميّ يرى ولا يسجّل، والمعلّمُ لا يبلغ الشاشة.
- الإضافةُ فقط: لا تعديلَ ولا حذف، والتصحيحُ سجلٌّ جديدٌ يشير إلى السابق.
- الخصوصيّة (D-431م): رقمُ وليّ الأمر يظهر لكلّ من بلغ الشاشة، **واسمُ الوليّ واسمُ الأمّ لا يظهران في أيّ مخرج**؛
  والتغذية الراجعة من وليّ الأمر مشفَّرةٌ في القاعدة ولا يقرؤها إلّا حاملُ قدرتها، وفتحُها سطرُ تدقيقٍ بلا نصّ ولا رقم.
"""

import io

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from core.models import AuditLog, ParentStudentLink, Wing
from operations.models import (
    AbsenceActionLog,
    AbsenceContactLog,
    AbsenceExcuse,
)
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)
from tests.test_absence_excuses import MONDAY, _absent_day  # noqa: F401
from tests.test_period_register import (  # noqa: F401
    SUNDAY,
    kids,
    klass,
    other_teacher,
    subjects,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db

DAY = f"{SUNDAY:%Y-%m-%d}"
FATHER_NAME = "وليٌّ سرّيُّ الاسم"
MOTHER_NAME = "أمٌّ سرّيّةُ الاسم"
FATHER_PHONE = "55512345"
MOTHER_PHONE = "55598765"
FEEDBACK = "قالت الأسرةُ إنّ الطالب مريضٌ منذ يومين"


def _staff(school, role, name, national_id):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _family(school, kid):
    """أبٌ وأمٌّ باسميهما ورقميهما — لتثبت الشاشةُ أنّها لا تُخرج إلّا الرقمَ."""
    for name, phone, relation, nid in (
        (FATHER_NAME, FATHER_PHONE, "father", "29300000082"),
        (MOTHER_NAME, MOTHER_PHONE, "mother", "29300000083"),
    ):
        parent = UserFactory(full_name=name, national_id=nid, phone=phone)
        MembershipFactory(
            user=parent, school=school, role=RoleFactory(school=school, name="parent")
        )
        ParentStudentLink.objects.create(
            school=school, parent=parent, student=kid, relationship=relation
        )


@pytest.fixture(autouse=True)
def _calendar_first(seeded_calendar):
    """التقويمُ يُبذر قبل العام والجناح: وإلّا اختلف عامُ الشعبة عن عام نطاق المشرف فخلا نطاقُه."""


@pytest.fixture
def staff(school):
    return {
        "principal": _staff(school, "principal", "المدير", "29300000101"),
        "vice_admin": _staff(school, "vice_admin", "النائب الإداري", "29300000102"),
        "coordinator": _staff(
            school, "student_affairs_coordinator", "منسق شؤون الطلبة", "29300000103"
        ),
        "vice_academic": _staff(school, "vice_academic", "النائب الأكاديمي", "29300000104"),
    }


@pytest.fixture
def second_wing(school, year):
    """جناحٌ ثانٍ بمشرفه وطالبٍ غائبٍ فيه."""
    sup = _staff(school, "admin_supervisor", "مشرف الجناح الثاني", "29300000105")
    wing = Wing.objects.create(
        school=school, code="w2", name="جناح 2", academic_year=year, supervisor=sup
    )
    klass2 = ClassGroupFactory(
        school=school, grade="G8", section="1", level_type="prep", academic_year=year, wing=wing
    )
    kid2 = UserFactory(full_name="طالب الجناح الثاني", national_id="29300000110")
    StudentEnrollmentFactory(student=kid2, class_group=klass2)
    return {"supervisor": sup, "klass": klass2, "kid": kid2}


@pytest.fixture
def absent_both(
    school, seeded_calendar, klass, kids, teacher, other_teacher, supervisor, second_wing
):
    """طالبٌ غائبٌ في كلّ جناح (يومَ الأحد)."""
    _absent_day(school, klass, kids[0], teacher, supervisor)
    _absent_day(
        school, second_wing["klass"], second_wing["kid"], other_teacher, second_wing["supervisor"]
    )
    return kids[0], second_wing["kid"]


def _get(client_as, user, name="daily_report", **params):
    return client_as(user).get(reverse(name), {"date": DAY, **params})


def _post_contact(client_as, user, student, **extra):
    data = {"student": str(student.id), "date": DAY, "outcome": "no_excuse", **extra}
    return client_as(user).post(reverse("absence_contact_save"), data)


def _post_action(client_as, user, student, **extra):
    data = {"student": str(student.id), "date": DAY, "status": "done", **extra}
    return client_as(user).post(reverse("absence_action_save"), data)


class TestRolesAndScope:
    def test_each_allowed_role_reaches_the_screen(self, client_as, staff, supervisor, absent_both):
        for user in (*staff.values(), supervisor):
            assert _get(client_as, user).status_code == 200

    def test_a_teacher_does_not(self, client_as, teacher, absent_both):
        assert _get(client_as, teacher).status_code == 403

    def test_principal_sees_both_wings_and_the_supervisor_only_his_own(
        self, client_as, staff, supervisor, second_wing, absent_both
    ):
        both = _get(client_as, staff["principal"]).content.decode()
        assert "طالب 0" in both and "طالب الجناح الثاني" in both

        mine = _get(client_as, supervisor).content.decode()
        assert "طالب 0" in mine and "طالب الجناح الثاني" not in mine

    def test_the_supervisor_cannot_write_for_a_student_outside_his_wing(
        self, client_as, supervisor, second_wing, absent_both
    ):
        kid2 = second_wing["kid"]
        assert _post_contact(client_as, supervisor, kid2).status_code == 404
        assert _post_action(client_as, supervisor, kid2).status_code == 404
        assert not AbsenceContactLog.objects.exists()
        assert not AbsenceActionLog.objects.exists()

    def test_the_academic_deputy_monitors_without_recording(self, client_as, staff, absent_both):
        deputy = staff["vice_academic"]
        body = _get(client_as, deputy).content.decode()
        assert reverse("absence_contact_save") not in body
        assert reverse("absence_action_save") not in body
        assert _post_contact(client_as, deputy, absent_both[0]).status_code == 403
        assert _post_action(client_as, deputy, absent_both[0]).status_code == 403
        assert _get(client_as, deputy, "absence_followup_print").status_code == 403


class TestAppendOnly:
    def test_recording_a_contact_and_an_action(self, client_as, staff, absent_both):
        kid = absent_both[0]
        assert _post_contact(client_as, staff["principal"], kid).status_code == 302
        assert _post_action(client_as, staff["principal"], kid).status_code == 302
        assert AbsenceContactLog.objects.get().contacted_by == staff["principal"]
        assert AbsenceActionLog.objects.get().acted_by == staff["principal"]

    def test_no_edit_and_no_delete(self, client_as, staff, absent_both):
        kid = absent_both[0]
        _post_contact(client_as, staff["principal"], kid)
        _post_action(client_as, staff["principal"], kid)
        for log in (AbsenceContactLog.objects.get(), AbsenceActionLog.objects.get()):
            with pytest.raises(PermissionDenied):
                log.save()
            with pytest.raises(PermissionDenied):
                log.delete()
        with pytest.raises(PermissionDenied):
            AbsenceContactLog.objects.all().update(outcome="no_reply")
        with pytest.raises(PermissionDenied):
            AbsenceActionLog.objects.all().delete()

    def test_a_correction_is_a_new_linked_record_and_becomes_the_head(
        self, client_as, staff, absent_both
    ):
        kid = absent_both[0]
        _post_contact(client_as, staff["principal"], kid, outcome="no_reply")
        first = AbsenceContactLog.objects.get()
        _post_contact(client_as, staff["principal"], kid, outcome="medical", corrects=str(first.id))
        second = AbsenceContactLog.objects.exclude(pk=first.pk).get()
        assert second.corrects_id == first.id
        first.refresh_from_db()
        assert first.outcome == "no_reply"
        body = _get(client_as, staff["principal"]).content.decode()
        assert "غياب بعذر طبي" in body

        # لا يُصحَّح سجلٌّ صُحِّح قبلُ: السلسلةُ خطٌّ لا شجرة.
        _post_contact(client_as, staff["principal"], kid, corrects=str(first.id))
        assert AbsenceContactLog.objects.count() == 2

    def test_no_record_for_a_day_the_student_did_not_miss(
        self, client_as, staff, absent_both, kids
    ):
        _post_contact(client_as, staff["principal"], kids[1])
        assert not AbsenceContactLog.objects.exists()

    def test_receiving_a_sick_leave_links_the_existing_excuse(
        self, client_as, school, staff, absent_both
    ):
        kid = absent_both[0]
        excuse = AbsenceExcuse.objects.create(
            school=school,
            student=kid,
            date_from=SUNDAY,
            date_to=SUNDAY,
            kind="medical",
            granted_by=staff["principal"],
        )
        _post_action(client_as, staff["principal"], kid, status="sick_leave_received")
        assert AbsenceActionLog.objects.get().excuse_id == excuse.id


class TestPrivacy:
    def test_phones_show_to_every_role_but_never_a_guardian_or_mother_name(
        self, client_as, school, staff, supervisor, absent_both
    ):
        _family(school, absent_both[0])
        for user in (*staff.values(), supervisor):
            body = _get(client_as, user).content.decode()
            assert FATHER_PHONE in body and MOTHER_PHONE in body
            assert FATHER_NAME not in body and MOTHER_NAME not in body

    def test_the_print_sheet_and_the_audit_trail_never_carry_the_names_or_numbers(
        self, client_as, school, staff, absent_both
    ):
        _family(school, absent_both[0])
        body = _get(
            client_as, staff["principal"], "absence_followup_print", embed="1"
        ).content.decode()
        assert FATHER_PHONE in body
        assert FATHER_NAME not in body and MOTHER_NAME not in body
        trail = " ".join(
            f"{a.object_repr} {a.changes}" for a in AuditLog.objects.filter(action="view")
        )
        assert FATHER_NAME not in trail and FATHER_PHONE not in trail

    def test_the_admin_never_shows_a_guardian_name(self, client_as, school, staff, absent_both):
        _family(school, absent_both[0])
        root = UserFactory(full_name="مشرف عام", national_id="29300000199", is_superuser=True)
        root.is_staff = True
        root.save()
        _post_contact(client_as, staff["principal"], absent_both[0], feedback=FEEDBACK)
        for name in ("operations_absencecontactlog", "operations_absenceactionlog"):
            page = client_as(root).get(reverse(f"admin:{name}_changelist"))
            assert page.status_code == 200
            assert FATHER_NAME not in page.content.decode()
        log = AbsenceContactLog.objects.get()
        change = client_as(root).get(
            reverse("admin:operations_absencecontactlog_change", args=[log.pk])
        )
        assert change.status_code == 200
        assert FATHER_NAME not in change.content.decode()

    def test_the_admin_offers_no_add_edit_or_delete(self, client_as, staff, absent_both):
        root = UserFactory(full_name="مشرف عام", national_id="29300000199", is_superuser=True)
        root.is_staff = True
        root.save()
        _post_contact(client_as, staff["principal"], absent_both[0])
        log = AbsenceContactLog.objects.get()
        assert (
            client_as(root).get(reverse("admin:operations_absencecontactlog_add")).status_code
            == 403
        )
        delete = reverse("admin:operations_absencecontactlog_delete", args=[log.pk])
        assert client_as(root).post(delete, {"post": "yes"}).status_code == 403
        assert AbsenceContactLog.objects.filter(pk=log.pk).exists()


class TestFeedback:
    def test_it_is_encrypted_at_rest_and_audited_without_the_text(
        self, client_as, staff, absent_both
    ):
        from django.db import connection

        kid = absent_both[0]
        _post_contact(client_as, staff["principal"], kid, feedback=FEEDBACK)
        with connection.cursor() as cur:
            cur.execute("SELECT feedback FROM operations_absencecontactlog")
            raw = cur.fetchone()[0]
        assert FEEDBACK not in raw

        body = _get(client_as, staff["principal"]).content.decode()
        assert FEEDBACK in body
        opened = AuditLog.objects.filter(
            action="view",
            object_repr__contains="التغذية الراجعة من وليّ الأمر",
            user=staff["principal"],
        )
        assert opened.exists()
        assert FEEDBACK not in " ".join(f"{a.object_repr} {a.changes}" for a in opened)

    def test_a_role_without_the_capability_never_sees_the_text(self, client_as, staff, absent_both):
        _post_contact(client_as, staff["principal"], absent_both[0], feedback=FEEDBACK)
        body = _get(client_as, staff["vice_academic"]).content.decode()
        assert FEEDBACK not in body


class TestPrintSheet:
    def test_pdf_embeds_tajawal_and_keeps_the_footer_at_eight_points_or_more(
        self, client_as, school, staff, absent_both
    ):
        fitz = pytest.importorskip("fitz")
        _family(school, absent_both[0])
        response = _get(client_as, staff["principal"], "absence_followup_print", format="pdf")
        assert response.status_code == 200
        assert response["Content-Type"].startswith("application/pdf")
        doc = fitz.open(stream=io.BytesIO(response.content), filetype="pdf")
        fonts = {font[3] for page in doc for font in page.get_fonts()}
        assert any("Tajawal" in name for name in fonts), fonts
        sizes = [
            span["size"]
            for page in doc
            for block in page.get_text("dict")["blocks"]
            for line in block.get("lines", [])
            for span in line["spans"]
            if span["text"].strip()
        ]
        assert sizes and min(sizes) >= 8.0
        text = "".join(page.get_text() for page in doc)
        assert FATHER_NAME not in text and MOTHER_NAME not in text


class TestServiceContract:
    def test_the_service_itself_denies_without_the_capability_and_outside_the_wing(
        self, staff, supervisor, second_wing, absent_both
    ):
        from django.http import Http404

        from operations.services import absence_followup as svc

        with pytest.raises(PermissionDenied):
            svc.record_contact(staff["vice_academic"], absent_both[0].id, SUNDAY, "no_excuse")
        with pytest.raises(Http404):
            svc.record_action(supervisor, second_wing["kid"].id, SUNDAY, "إنذار", "done")
        rows = svc.followup_rows(supervisor, SUNDAY)
        assert [r["student"].id for r in rows] == [absent_both[0].id]
        assert svc.guardian_phone(absent_both[0]) == []
