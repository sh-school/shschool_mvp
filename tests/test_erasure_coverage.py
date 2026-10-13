"""[W-20261001-014] المحو (PDPPL م.18) يشمل كلَّ نموذجٍ يربط الطالبَ بـ FK.

المحو يُجهِّل المستخدمَ ولا يحذفه، فلا CASCADE يعمل: ما لم يُدرَج في
`_lazy_student_fk_models` يبقى بعد أن يُعلَن الطلبُ `completed` — ومنه ملاحظاتٌ
نفسيّةٌ وصحّيّةٌ عن قاصرٍ وسجلُّ انتقاله وأرقامُ أوليائه (م.16).

اختبارٌ يثبت الغيابَ بعد `execute`، وحارسٌ يفشل إن ظهر نموذجٌ جديدٌ بحقل
`student` → المستخدم لا يدخل القائمةَ ولا الاستثناءاتِ المعلَّلة.
"""

from datetime import date, time

import pytest
from django.apps import apps
from django.conf import settings
from django.utils import timezone

from core.models import ErasureRequest
from governance.erasure_service import ErasureService, _lazy_student_fk_models

from .conftest import ClassGroupFactory, UserFactory

#: نماذجُ لها FK `student` يعالجها `ErasureService.execute` في خطواتٍ مخصَّصة
#: (لا القائمةُ العامّة) — كلٌّ بسبب.
HANDLED_BY_DEDICATED_STEPS = {
    "core.StudentEnrollment": "الخطوة 6: حذفُ القيد",
    "core.ParentStudentLink": "الخطوة 5: حذفُ روابط الأولياء",
    "core.ConsentRecord": "الخطوة 4: حذفُ سجلّات الموافقة",
    "core.ErasureRequest": "طلبُ المحو نفسُه — دليلُ الامتثال يبقى (SET_NULL)",
    "operations.AbsenceContactLog": "سجلٌّ مضافٌ فقط يُجهَّل بـ`erase_followup_logs` في الخطوة 2.6 (الحذفُ العامّ يرفضه)",
    "operations.AbsenceActionLog": "سجلٌّ مضافٌ فقط يُجهَّل بـ`erase_followup_logs` في الخطوة 2.6 (الحذفُ العامّ يرفضه)",
    "operations.AttendanceEntry": "سجلٌّ ملحقٌ يُمحى بـ`erase_attendance_ledger` في ErasureService قبل جمع الملفّات — ولا حذفَ عاديَّ يمرّ من مُشغِّل القاعدة",
}


def _erase(student, school):
    admin = UserFactory(full_name="مدير التنفيذ", is_superuser=True)
    req = ErasureRequest.objects.create(
        school=school,
        student=student,
        requested_by=admin,
        reason="اختبار تغطية المحو",
        status="approved",
        reviewed_by=admin,
    )
    return ErasureService.execute(req)


@pytest.fixture
def student_with_neglected_rows(db, school, student_user, teacher_user):
    """صفٌّ واحدٌ على الأقلّ في كلٍّ من النماذج الستّة التي كانت مغفَلة."""
    from exam_control.models import ExamIncident, ExamSession
    from notifications.models import NotificationLog
    from operations.models import ClassExit, GuardianContact, Session
    from student_affairs.models import StudentTransfer
    from student_info.models import StudentNote

    cg = ClassGroupFactory(school=school)
    today = date.today()
    session = Session.objects.create(
        school=school,
        class_group=cg,
        teacher=teacher_user,
        date=today,
        start_time=time(8, 0),
        end_time=time(8, 45),
        status="scheduled",
    )
    StudentNote.objects.create(
        school=school,
        student=student_user,
        category="counselor",
        title="ملاحظة",
        body="نصٌّ حسّاس",
        occurred_on=today,
    )
    StudentTransfer.objects.create(
        school=school,
        student=student_user,
        direction="out",
        other_school_name="مدرسة أخرى",
        transfer_date=today,
    )
    GuardianContact.objects.create(
        school=school,
        student=student_user,
        absence_date=today,
        outcome="answered",
        contacted_at=timezone.now(),
    )
    ClassExit.objects.create(
        school=school, session=session, student=student_user, left_at=timezone.now()
    )
    exam_session = ExamSession.objects.create(
        school=school, name="دورة", start_date=today, end_date=today
    )
    ExamIncident.objects.create(session=exam_session, student=student_user, description="واقعة")
    NotificationLog.objects.create(
        school=school, student=student_user, recipient="x@example.test", body="نصّ"
    )
    return student_user


NEGLECTED = [
    ("student_info.StudentNote"),
    ("student_affairs.StudentTransfer"),
    ("operations.GuardianContact"),
    ("operations.ClassExit"),
    ("exam_control.ExamIncident"),
    ("notifications.NotificationLog"),
]


@pytest.mark.django_db
class TestErasureCoversNeglectedModels:
    @pytest.mark.parametrize("label", NEGLECTED)
    def test_rows_exist_before_and_are_gone_after(self, student_with_neglected_rows, school, label):
        Model = apps.get_model(label)
        student = student_with_neglected_rows
        assert Model.objects.filter(student=student).exists(), "الضبطُ الموجب: الصفُّ مزروع"

        _erase(student, school)

        assert not Model.objects.filter(student=student).exists(), f"{label}: بقيت صفوفٌ بعد المحو"

    def test_summary_counts_the_neglected_models(self, student_with_neglected_rows, school):
        summary = _erase(student_with_neglected_rows, school)

        for label in NEGLECTED:
            assert label.split(".")[1] in summary["models"], label


@pytest.mark.django_db
def test_every_student_fk_model_is_in_the_erasure_list():
    """حارسٌ: نموذجٌ جديدٌ بـ FK `student` → المستخدم لا يغيب عن المحو.

    أضِفه إلى `_lazy_student_fk_models` أو سمِّه في `HANDLED_BY_DEDICATED_STEPS`
    مع سبب — ولا تُسكِت الحارسَ بغير ذلك.
    """
    user_model = apps.get_model(settings.AUTH_USER_MODEL)
    covered = {(Model, field) for Model, field, _ in _lazy_student_fk_models()}

    missing = []
    for model in apps.get_models():
        for field in model._meta.concrete_fields:
            if field.name != "student" or field.related_model is not user_model:
                continue
            if (model, field.name) in covered:
                continue
            if model._meta.label in HANDLED_BY_DEDICATED_STEPS:
                continue
            missing.append(model._meta.label)

    assert missing == [], f"نماذجُ بـ FK student غائبةٌ عن ErasureService: {missing}"


def test_dedicated_step_exemptions_still_exist():
    """الاستثناءاتُ لا تتقادم: نموذجٌ حُذف أو غُيّر حقلُه يُزال من القائمة."""
    for label in HANDLED_BY_DEDICATED_STEPS:
        assert apps.get_model(label)._meta.get_field("student")


def _seed_followup(school, student_user, teacher_user):
    from operations.models import AbsenceActionLog, AbsenceContactLog

    day = date.today()
    first = AbsenceContactLog.objects.create(
        school=school,
        student=student_user,
        absence_date=day,
        outcome="answered",
        feedback="نصٌّ حسّاس",
        contacted_by=teacher_user,
    )
    AbsenceContactLog.objects.create(
        school=school, student=student_user, absence_date=day, outcome="no_answer", corrects=first
    )
    AbsenceActionLog.objects.create(
        school=school,
        student=student_user,
        absence_date=day,
        status="done",
        note="ملاحظةٌ شخصيّة",
        acted_by=teacher_user,
    )
    return day


def test_followup_logs_are_anonymised_not_deleted(db, school, student_user, teacher_user):
    """قرارُ المالك: أثرٌ مجهَّل — الصفوفُ تبقى للإحصاء بلا ربطٍ بالطالب ولا محتوًى حرٍّ ولا عذرٍ مرتبط."""
    from operations.models import AbsenceActionLog, AbsenceContactLog

    day = _seed_followup(school, student_user, teacher_user)

    summary = _erase(student_user, school)

    assert summary["models"]["AbsenceContactLog"] == 2
    assert summary["models"]["AbsenceActionLog"] == 1
    assert not AbsenceContactLog.objects.filter(student=student_user).exists()
    assert not AbsenceActionLog.objects.filter(student=student_user).exists()
    contacts = list(AbsenceContactLog.objects.filter(school=school, absence_date=day))
    actions = list(AbsenceActionLog.objects.filter(school=school, absence_date=day))
    assert len(contacts) == 2 and len(actions) == 1, "تبقى الصفوفُ للإحصاء"
    assert {c.outcome for c in contacts} == {"answered", "no_answer"}
    assert actions[0].status == "done"
    assert all(c.student_id is None and c.feedback == "" for c in contacts)
    assert actions[0].student_id is None and actions[0].note == "" and actions[0].excuse_id is None


def test_followup_erasure_audits_counts_only(db, school, student_user, teacher_user):
    from core.models import AuditLog

    _seed_followup(school, student_user, teacher_user)

    _erase(student_user, school)

    entry = AuditLog.objects.filter(object_repr__startswith="متابعةُ الغياب — تجهيلُ").get()
    assert entry.changes == {"contacts": 2, "actions": 1}
    assert "حسّاس" not in str(entry.changes) and "شخصيّة" not in entry.object_repr


def test_followup_erasure_refuses_another_schools_role(
    db, school, student_user, teacher_user, monkeypatch
):
    """دورُ مدرسةٍ أخرى يرى صفراً تحت RLS فلا يُقال «تمّ» — يُرفض ابتداءً والصفوفُ على حالها."""
    import pytest

    from operations.attendance_entries import EntryError
    from operations.models import AbsenceContactLog
    from operations.services.absence_followup import erase_followup_logs

    _seed_followup(school, student_user, teacher_user)
    monkeypatch.setattr("operations.attendance_entries._role_tenant", lambda: "مدرسةٌ-أخرى")

    with pytest.raises(EntryError) as exc:
        erase_followup_logs(student_user, school=school)

    assert exc.value.code == "erasure_wrong_tenant"
    assert AbsenceContactLog.objects.filter(student=student_user).exists()
