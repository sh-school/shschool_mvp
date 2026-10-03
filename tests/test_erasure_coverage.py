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
