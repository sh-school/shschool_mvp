"""نموذج 04 «كتاب التماس عذر لغياب طالب»: مقدّمُ الطلب والتعهّد ومراحلُ التنفيذ على AbsenceExcuse (W-20261001-032).

- يحفظ العذرُ اسمَ مقدّم الطلب وصلتَه وهاتفَه (مشفَّراً) وتاريخَ الكتاب وإقرارَ التعهّد.
- المراحلُ الثلاث بعد القبول فقط وبالترتيب ولكلٍّ منفّذٌ وتاريخ، وكلُّها في سجلّ المراجعة.
- أنواعُ العذر لا تُمسّ قبل قرار المالك (تصنيفُ الورقة مقابل قائمة الدليل 2026).
- الهجرةُ توسيعٌ فقط.
"""

import datetime as dt
import pathlib

import pytest
from django.db import connection
from django.test import override_settings

from core.models import AuditLog, ErasureRequest
from governance.erasure_service import ErasureService
from operations.excuses import CLOSED_LIST, ExcuseError, grant_excuse, record_stage
from operations.models import AbsenceExcuse
from tests.conftest import MembershipFactory, RoleFactory
from tests.test_absence_excuses import _absent_day, _report, vice_admin  # noqa: F401
from tests.test_period_register import (  # noqa: F401 — التجهيزاتُ نفسُها
    SUNDAY,
    kids,
    klass,
    subjects,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db

MONDAY = SUNDAY + dt.timedelta(days=1)
PHONE = "+97455512345"


@pytest.fixture
def excuse(school, seeded_calendar, klass, kids, teacher, supervisor):
    _absent_day(school, klass, kids[0], teacher, supervisor)
    return grant_excuse(
        student=kids[0],
        school=school,
        date_from=SUNDAY,
        date_to=SUNDAY,
        kind="medical",
        document=_report(),
        by=supervisor,
        today=MONDAY,
        applicant_name="ولي أمر الطالب",
        applicant_relation="الأب",
        applicant_phone=f" {PHONE} ",
        letter_date=MONDAY,
        pledge_accepted=True,
    )


class TestTheApplicantIsKept:
    def test_name_relation_phone_letter_date_and_pledge_are_saved(self, excuse):
        excuse.refresh_from_db()

        assert excuse.applicant_name == "ولي أمر الطالب" and excuse.applicant_relation == "الأب"
        assert excuse.applicant_phone == PHONE, "الهاتفُ منقّىً من المسافات"
        assert excuse.letter_date == MONDAY and excuse.pledge_accepted is True

    def test_the_phone_is_encrypted_at_rest(self, excuse):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT applicant_phone FROM operations_absenceexcuse WHERE id = %s", [excuse.pk]
            )
            raw = cursor.fetchone()[0]

        assert raw and PHONE not in raw

    def test_the_audit_line_carries_no_name_and_no_phone(self, excuse):
        line = AuditLog.objects.filter(object_id=str(excuse.pk), action="create").get()

        blob = str(line.changes) + line.object_repr
        assert line.changes["applicant_relation"] == "الأب" and line.changes["pledge_accepted"]
        assert "ولي أمر الطالب" not in blob and PHONE not in blob

    def test_an_excuse_recorded_by_hand_has_no_applicant_and_still_works(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[1], teacher, supervisor)

        plain = grant_excuse(
            student=kids[1],
            school=school,
            date_from=SUNDAY,
            date_to=SUNDAY,
            kind="medical",
            document=_report(),
            by=supervisor,
            today=MONDAY,
        )

        assert plain.applicant_name == "" and plain.letter_date is None
        assert plain.pledge_accepted is False

    def test_a_pledge_needs_who_pledged_and_when(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[2], teacher, supervisor)
        base = {
            "student": kids[2],
            "school": school,
            "date_from": SUNDAY,
            "date_to": SUNDAY,
            "kind": "medical",
            "by": supervisor,
            "today": MONDAY,
        }

        with pytest.raises(ExcuseError, match="إقرارُ التعهّد"):
            grant_excuse(**base, document=_report(), pledge_accepted=True)
        with pytest.raises(ExcuseError, match="بعد اليوم"):
            grant_excuse(
                **base,
                document=_report(),
                applicant_name="س",
                applicant_relation="الأب",
                letter_date=MONDAY + dt.timedelta(days=3),
                pledge_accepted=True,
            )
        assert not AbsenceExcuse.objects.filter(student=kids[2]).exists(), "لا يبقى نصفُ عذر"


class TestTheApplicantInputIsBounded:
    """حكمُ 0104: سقفٌ للهاتف، وتقصيرُ الاسم والصلة بحدّ الحقل، ولا هاتفَ نصّاً خامّاً بلا مفتاح تشفير."""

    @staticmethod
    def _base(school, kid, supervisor):
        return {
            "student": kid,
            "school": school,
            "date_from": SUNDAY,
            "date_to": SUNDAY,
            "kind": "medical",
            "document": _report(),
            "by": supervisor,
            "today": MONDAY,
        }

    def test_a_long_name_and_relation_are_cut_to_the_field_limits(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[3], teacher, supervisor)

        made = grant_excuse(
            **self._base(school, kids[3], supervisor),
            applicant_name="س" * 400,
            applicant_relation="ص" * 90,
        )

        made.refresh_from_db()
        assert len(made.applicant_name) == 150 and len(made.applicant_relation) == 40

    def test_a_phone_longer_than_the_cap_is_refused_without_a_half_made_excuse(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[3], teacher, supervisor)

        with pytest.raises(ExcuseError, match="الهاتف"):
            grant_excuse(**self._base(school, kids[3], supervisor), applicant_phone="9" * 21)

        assert not AbsenceExcuse.objects.filter(student=kids[3]).exists()

    @override_settings(FERNET_KEY="")
    def test_without_an_encryption_key_the_phone_is_refused_not_stored_raw(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[3], teacher, supervisor)

        with pytest.raises(ExcuseError, match="الهاتف"):
            grant_excuse(**self._base(school, kids[3], supervisor), applicant_phone=PHONE)
        assert not AbsenceExcuse.objects.filter(student=kids[3]).exists()

        made = grant_excuse(**self._base(school, kids[3], supervisor), applicant_name="ولي")
        assert made.applicant_phone == "", "العذرُ بلا هاتفٍ يُقبل كما كان"


class TestErasureRemovesTheApplicant:
    def test_erasing_the_student_removes_the_excuse_with_the_applicant_data(
        self, excuse, school, principal_user, django_capture_on_commit_callbacks
    ):
        # حقُّ المحو لعضو المدرسة؛ والطلبةُ في تجهيزات الحضور بتسجيلٍ بلا عضويّة.
        MembershipFactory(
            user=excuse.student, school=school, role=RoleFactory(school=school, name="student")
        )
        request = ErasureRequest.objects.create(
            school=school,
            student=excuse.student,
            requested_by=principal_user,
            reviewed_by=principal_user,
            reason="محو شامل لبيانات الطالب",
        )

        with django_capture_on_commit_callbacks(execute=True):
            ErasureService.execute(request)

        assert not AbsenceExcuse.objects.filter(pk=excuse.pk).exists()
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM operations_absenceexcuse WHERE applicant_name <> ''"
            )
            assert cursor.fetchone()[0] == 0


class TestTheThreeExecutionStages:
    def test_each_stage_records_who_and_when_in_order(self, excuse, vice_admin):
        for stage in ("internal", "national", "audit"):
            record_stage(excuse, stage, by=vice_admin)

        excuse.refresh_from_db()
        for stage in ("internal", "national", "audit"):
            assert getattr(excuse, f"stage_{stage}_by") == vice_admin
            assert getattr(excuse, f"stage_{stage}_at") is not None
        stamps = [excuse.stage_internal_at, excuse.stage_national_at, excuse.stage_audit_at]
        assert stamps == sorted(stamps)
        events = AuditLog.objects.filter(object_id=str(excuse.pk), changes__stage__isnull=False)
        assert events.count() == 3

    def test_a_stage_cannot_jump_ahead(self, excuse, vice_admin):
        with pytest.raises(ExcuseError, match="قبلها"):
            record_stage(excuse, "national", by=vice_admin)
        record_stage(excuse, "internal", by=vice_admin)
        with pytest.raises(ExcuseError, match="قبلها"):
            record_stage(excuse, "audit", by=vice_admin)

    def test_a_stage_is_recorded_once(self, excuse, vice_admin):
        record_stage(excuse, "internal", by=vice_admin)

        with pytest.raises(ExcuseError, match="من قبل"):
            record_stage(excuse, "internal", by=vice_admin)

    def test_no_stage_before_acceptance(self, excuse, vice_admin):
        for status in ("pending", "rejected"):
            AbsenceExcuse.objects.filter(pk=excuse.pk).update(status=status)
            with pytest.raises(ExcuseError, match="بعد قبول"):
                record_stage(excuse, "internal", by=vice_admin)

        excuse.refresh_from_db()
        assert excuse.stage_internal_at is None

    def test_an_unknown_stage_is_refused(self, excuse, vice_admin):
        with pytest.raises(ExcuseError, match="غيرُ معروفة"):
            record_stage(excuse, "bogus", by=vice_admin)


class TestWhatDoesNotChange:
    def test_the_excuse_kinds_are_untouched_pending_the_owners_decision(self):
        """تصنيفُ الورقة (سفر/أسري/اجتماعي/مرافقة مريض) مقابل قائمة الدليل قرارُ المالك: لا يحسمه المنفّذ."""
        assert set(CLOSED_LIST) == {
            "medical",
            "bereavement",
            "family",
            "state_representation",
            "official",
        }
        assert {k for k, _ in AbsenceExcuse.KINDS} >= set(CLOSED_LIST)

    def test_the_migration_is_expansion_only(self):
        text = (
            pathlib.Path(__file__).resolve().parent.parent
            / "operations"
            / "migrations"
            / "0081_absence_excuse_form04.py"
        ).read_text(encoding="utf-8")

        assert text.count("migrations.AddField(") == 11
        for forbidden in ("RemoveField", "DeleteModel", "RenameField", "AlterField", "RunSQL"):
            assert forbidden not in text
        assert 'model_name="absenceexcuse"' in text
