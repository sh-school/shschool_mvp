"""[SCHEDULE] حذفُ توليدٍ لم يُعتمد من صفحة الجدول الذكي — لا من لوحة الإدارة.

كان النائبُ يدخل الخلفيّةَ ليحذف مسودّةً لم يرضَها، وحذفُها هناك أثناء التشغيل
أسقط توليداً جارياً (2026-09-24). فالزرُّ هنا بجانب «معاينة»، وحارسُه في الخدمة:
المسودّةُ والفاشلُ يُحذفان بحصصهما المطفأة، والمعتمَدُ والمؤرشَفُ والجاري لا يُمسّ.
"""

from datetime import time

import pytest
from django.urls import reverse

from core.models.audit import AuditLog
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

YEAR = "2026-2027"


@pytest.fixture
def principal(school):
    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name="مدير المدرسة")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def assignment(school):
    """الصفحةُ لا ترسم سجلَّ التوليد قبل أن يوجد توزيعٌ واحد."""
    from operations.models import Subject, SubjectClassAssignment

    role = RoleFactory(school=school, name="teacher")
    teacher = UserFactory(full_name="معلّمُ الرياضيات")
    MembershipFactory(user=teacher, school=school, role=role)
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")
    group = ClassGroupFactory(school=school, grade="G9", level_type="prep", academic_year=YEAR)
    return SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=subject,
        weekly_periods=5,
        is_active=True,
    )


def _generation(school, status, assignment=None, *, live=False, periods=2):
    from operations.models import ScheduleGeneration, ScheduleSlot

    gen = ScheduleGeneration.objects.create(school=school, academic_year=YEAR, status=status)
    for period in range(1, periods + 1 if assignment else 1):
        ScheduleSlot.objects.create(
            school=school,
            teacher=assignment.teacher,
            class_group=assignment.class_group,
            subject=assignment.subject,
            day_of_week=0,
            period_number=period,
            start_time=time(7, 0),
            end_time=time(7, 45),
            academic_year=YEAR,
            is_active=live,
            generation=gen,
        )
    return gen


def _discard(client, gen):
    return client.post(reverse("discard_schedule", args=[gen.pk]), follow=True)


@pytest.mark.django_db
def test_a_draft_is_deleted_with_its_slots_and_the_deletion_is_audited(
    client_as, principal, school, assignment
):
    from operations.models import ScheduleGeneration, ScheduleSlot

    gen = _generation(school, "draft", assignment)

    response = _discard(client_as(principal), gen)

    assert not ScheduleGeneration.objects.filter(pk=gen.pk).exists()
    assert not ScheduleSlot.objects.filter(generation_id=gen.pk).exists()
    assert "حُذف التوليد (2 حصّة" in response.content.decode()
    log = AuditLog.objects.get(object_id=str(gen.pk))
    assert log.action == "delete" and log.changes["slots"] == 2


@pytest.mark.django_db
def test_a_failed_generation_is_deleted(client_as, principal, school, assignment):
    from operations.models import ScheduleGeneration

    gen = _generation(school, "failed")

    _discard(client_as(principal), gen)

    assert not ScheduleGeneration.objects.filter(pk=gen.pk).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["approved", "archived", "queued", "running"])
def test_approved_archived_and_running_generations_are_never_deleted(
    client_as, principal, school, assignment, status
):
    """ولو وصل الطلبُ من غير الزرّ: الحارسُ في الخدمة لا في القالب."""
    from operations.models import ScheduleGeneration, ScheduleSlot

    gen = _generation(school, status, assignment, live=status == "approved")

    response = _discard(client_as(principal), gen)

    assert ScheduleGeneration.objects.filter(pk=gen.pk, status=status).exists()
    assert ScheduleSlot.objects.filter(generation_id=gen.pk).count() == 2
    assert not AuditLog.objects.filter(object_id=str(gen.pk)).exists()
    body = response.content.decode()
    assert "لا يُحذف" in body or "ما زال يجري" in body


@pytest.mark.django_db
def test_a_draft_holding_live_slots_is_refused(client_as, principal, school, assignment):
    """حصّةٌ حيّةٌ في «مسودّة» جدولٌ نُشر بطريقٍ قديم — فلا يُحذف معها الجدولُ الحيّ."""
    from operations.models import ScheduleGeneration

    gen = _generation(school, "draft", assignment, live=True)

    _discard(client_as(principal), gen)

    assert ScheduleGeneration.objects.filter(pk=gen.pk).exists()


@pytest.mark.django_db
def test_the_delete_button_sits_beside_preview_for_drafts_only(
    client_as, principal, school, assignment
):
    draft = _generation(school, "draft")
    approved = _generation(school, "approved")

    body = client_as(principal).get(reverse("smart_schedule") + f"?year={YEAR}").content.decode()

    assert reverse("discard_schedule", args=[draft.pk]) in body
    assert reverse("discard_schedule", args=[approved.pk]) not in body


@pytest.mark.django_db
def test_another_schools_generation_is_not_found(client_as, principal, school, assignment):
    from operations.models import ScheduleGeneration
    from tests.conftest import SchoolFactory

    other = ScheduleGeneration.objects.create(
        school=SchoolFactory(), academic_year=YEAR, status="draft"
    )

    response = client_as(principal).post(reverse("discard_schedule", args=[other.pk]))

    assert response.status_code == 404
    assert ScheduleGeneration.objects.filter(pk=other.pk).exists()


# ── إيقافُ التوليد الجاري ─────────────────────────────────────────────


def _stop(client, gen):
    return client.post(reverse("stop_schedule_generation", args=[gen.pk]), follow=True)


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["queued", "running"])
def test_stopping_marks_the_generation_failed_and_then_it_can_be_deleted(
    client_as, principal, school, assignment, status
):
    from operations.models import ScheduleGeneration
    from operations.scheduler import GENERATION_STOPPED

    gen = _generation(school, status)
    client = client_as(principal)

    _stop(client, gen)

    gen.refresh_from_db()
    assert gen.status == "failed" and gen.error_message == GENERATION_STOPPED
    assert AuditLog.objects.filter(object_id=str(gen.pk), action="update").exists()
    body = client.get(reverse("smart_schedule") + f"?year={YEAR}").content.decode()
    assert reverse("discard_schedule", args=[gen.pk]) in body, "بعد الإيقاف يظهر الحذف"
    _discard(client, gen)
    assert not ScheduleGeneration.objects.filter(pk=gen.pk).exists()


@pytest.mark.django_db
def test_a_finished_generation_cannot_be_stopped(client_as, principal, school, assignment):
    gen = _generation(school, "draft")

    response = _stop(client_as(principal), gen)

    gen.refresh_from_db()
    assert gen.status == "draft"
    assert "لا توليدَ جارياً" in response.content.decode()


@pytest.mark.django_db
def test_the_stop_button_shows_while_a_generation_runs(client_as, principal, school, assignment):
    gen = _generation(school, "running")

    body = client_as(principal).get(reverse("smart_schedule") + f"?year={YEAR}").content.decode()

    assert reverse("stop_schedule_generation", args=[gen.pk]) in body


@pytest.mark.django_db
def test_a_stopped_generator_writes_nothing(school, assignment):
    """المولّدُ يسأل قبل كلّ محاولة — فإيقافٌ قبل الأولى لا يترك صفّاً ولا حصّة."""
    from operations.models import ScheduleGeneration, ScheduleSlot
    from operations.scheduler import generate_schedule

    result = generate_schedule(school, YEAR, publish=False, should_stop=lambda: True)

    assert result["stopped"] is True and result["generation"] is None
    assert not ScheduleGeneration.objects.exists()
    assert not ScheduleSlot.objects.exists()


@pytest.mark.django_db
def test_a_generation_stopped_while_queued_never_starts(school):
    """العاملُ يلتقط رسالةً لتوليدٍ أُوقف في الانتظار — فلا يبدؤه."""
    from operations.models import ScheduleGeneration
    from operations.tasks import generate_smart_schedule_task

    gen = ScheduleGeneration.objects.create(school=school, academic_year=YEAR, status="failed")

    outcome = generate_smart_schedule_task.run(str(gen.pk))

    gen.refresh_from_db()
    assert outcome["ok"] is False and gen.status == "failed"
