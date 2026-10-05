"""الحصّةُ المؤقّتة والحقيقيّةُ تلتقيان على مستوى `Session` نفسِها — لا في مولّدٍ بعينه (W-20261005-006، قرارُ المالك D-219م).

«لا أريد خسارةَ كود حصر الغياب مهما كان الجدولُ المعتمَد لاحقاً (والأغلبُ العالميّ)»: فحمايةُ الحقيقيّة من الإسقاط الصامت بقيدَين مشروطَين في القاعدة،
وإغلاقُ المؤقّتة عند حقيقيّةٍ بقاعدةٍ على `Session` (إشارةٌ لما يُحفظ بالـORM، وقراءةٌ لما يُدرَج بـ`bulk_create` من أيّ مولّد)، والمؤقّتةُ تُغلق ولا تُحذف.
"""

import datetime as dt

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from operations.models import ScheduleSlot, Session
from operations.services import provisional_session as provisional
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, _staff
from tests.conftest import ClassGroupFactory
from tests.test_provisional_session import (  # noqa: F401 — التجهيزاتُ نفسُها
    _flag_on_and_today_is_sunday,
    assigned,
    subject,
)

pytestmark = pytest.mark.django_db


def _provisional(school, klass, teacher, subject, start=dt.time(7, 10), period=1, day=SUNDAY):
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        subject=subject,
        date=day,
        start_time=start,
        end_time=dt.time(7, 55),
        period_number=period,
        provisional=True,
        provisional_until=timezone.now() + dt.timedelta(days=14),
    )


def _real(school, klass, teacher, subject, start=dt.time(7, 10), day=SUNDAY, **extra):
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        subject=subject,
        date=day,
        start_time=start,
        end_time=dt.time(7, 55),
        status="scheduled",
        **extra,
    )


def _slot(school, year, klass, teacher, subject):
    return ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=klass,
        subject=subject,
        day_of_week=0,
        period_number=1,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        academic_year=year,
    )


def test_real_rows_keep_exactly_the_old_overlap_protection(school, year, klass, teacher, subject):
    _real(school, klass, teacher, subject)
    other_class = ClassGroupFactory(school=school, grade="G9", section="q", academic_year=year)
    other_teacher = _staff(school, "teacher", "معلّم ثانٍ", "29000001098")

    with pytest.raises(IntegrityError), transaction.atomic():
        _real(school, other_class, teacher, subject)  # المعلّمُ نفسُه في الوقت نفسِه
    with pytest.raises(IntegrityError), transaction.atomic():
        _real(school, klass, other_teacher, subject)  # الشعبةُ نفسُها في الوقت نفسِه
    # مجموعةُ الاختيار تفتح جلستين لشعبةٍ واحدة بمعلّمَين — كما كان
    _real(school, klass, other_teacher, subject, elective_group="art")


def test_a_provisional_row_never_displaces_or_is_displaced_by_a_real_one(
    school, klass, teacher, subject
):
    mine = _provisional(school, klass, teacher, subject)

    real = _real(school, klass, teacher, subject)  # الخانةُ نفسُها: تُقبل ولا تُسقط بصمت

    assert Session.objects.filter(pk__in=[mine.pk, real.pk]).count() == 2


def test_a_week_full_of_provisional_rows_still_generates_the_real_schedule(
    school, year, klass, teacher, subject, band, bells
):
    """بلا `provisional=False` في فحص «الأسبوع كامل» كان أسبوعٌ فيه مؤقّتةٌ كلَّ يومٍ يمنع توليدَ الجدول الحقيقيّ كلِّه."""
    from operations.services import ScheduleService

    for offset in range(5):  # الأحد…الخميس
        _provisional(
            school,
            klass,
            teacher,
            subject,
            period=2,
            day=SUNDAY + dt.timedelta(days=offset),
            start=dt.time(8, 0),
        )
    _slot(school, year, klass, teacher, subject)

    made = ScheduleService.ensure_sessions_for_date(school, SUNDAY)

    assert made >= 1
    assert Session.objects.filter(
        date=SUNDAY, start_time=dt.time(7, 10), provisional=False
    ).exists()


def test_resync_never_deletes_a_provisional_row(school, klass, teacher, subject):
    from operations.services import ScheduleService

    mine = _provisional(school, klass, teacher, subject)

    ScheduleService.resync_sessions_for_date(school, SUNDAY)

    assert Session.objects.filter(pk=mine.pk).exists()


def test_handing_over_a_slot_ignores_a_provisional_row_in_it(
    school, year, klass, teacher, other_teacher, subject, band, bells
):
    from operations.services import SubstituteService

    mine = _provisional(school, klass, teacher, subject)
    slot = _slot(school, year, klass, teacher, subject)

    handed = SubstituteService.hand_over_session(school, slot, SUNDAY, other_teacher)

    assert handed.provisional is False and handed.pk != mine.pk
    mine.refresh_from_db()
    assert mine.teacher_id == teacher.id, "المؤقّتةُ لم تُسلَّم ولم تُلمس"


def test_only_an_identical_real_session_closes_the_provisional_one_whoever_created_it(
    school, klass, teacher, other_teacher, subject
):
    """النسخةُ المكرَّرةُ فقط (الشعبةُ والمعلّمُ نفسُهما) تُغلق المؤقّتة — بالإشارة (ORM) وبالقراءة لما أُدرج بـbulk_create؛ وحقيقيّةُ معلّمٍ آخر لا تُغلقها (D-229م)."""
    mine = _provisional(school, klass, teacher, subject)

    _real(
        school, klass, other_teacher, subject
    )  # معلّمٌ آخر: جدولُ المنصّة غيرُ المعتمد لا يُقدَّم على رصد المعلّم

    mine.refresh_from_db()
    assert mine.provisional_until > timezone.now()

    _real(school, klass, teacher, subject, start=dt.time(9, 0))  # لا علاقةَ بوقتها
    mine.refresh_from_db()
    assert mine.provisional_until > timezone.now()

    twin = _provisional(school, klass, teacher, subject, start=dt.time(8, 0), period=2)
    Session.objects.bulk_create(  # لا إشارة هنا: كمولّدٍ يُدرج دفعةً — النسخةُ المكرَّرة
        [
            Session(
                school=school,
                class_group=klass,
                teacher=teacher,
                subject=subject,
                date=SUNDAY,
                start_time=dt.time(8, 0),
                end_time=dt.time(8, 45),
            )
        ]
    )
    assert provisional.close_shadowed(school, SUNDAY) == 1
    twin.refresh_from_db()
    assert twin.provisional_until <= timezone.now()
    assert Session.objects.filter(pk=twin.pk).exists(), "تُغلق ولا تُحذف"


def test_the_signal_is_silent_with_the_switch_off(
    settings, school, klass, teacher, other_teacher, subject
):
    mine = _provisional(school, klass, teacher, subject)
    settings.PROVISIONAL_SESSIONS_ENABLED = False

    _real(school, klass, other_teacher, subject)

    mine.refresh_from_db()
    assert mine.provisional_until > timezone.now(), "مطفأً لا يُغلق شيءٌ ولا استعلامَ إضافيّ"


@pytest.mark.django_db(transaction=True)
def test_the_overlap_migration_is_reversible_and_blocks_on_a_clash(school, klass, teacher, subject):
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    def indexes():
        with connection.cursor() as cursor:
            cursor.execute(
                "select indexname from pg_indexes where tablename = 'operations_session'"
            )
            return {row[0] for row in cursor.fetchall()}

    forward = [("operations", "0071_session_overlap_real_only")]
    back = [("operations", "0070_session_provisional")]
    assert "no_teacher_time_overlap_real" in indexes()
    _provisional(school, klass, teacher, subject)
    _real(school, klass, teacher, subject)  # مؤقّتةٌ وحقيقيّةٌ في خانةٍ واحدة: يمنع العكسَ

    with pytest.raises(RuntimeError, match="لا يُعكس 0071"):
        MigrationExecutor(connection).migrate(back)

    Session.objects.filter(provisional=True).delete()
    MigrationExecutor(connection).migrate(back)
    assert {"no_teacher_time_overlap", "no_class_time_overlap"} <= indexes()
    assert "no_teacher_time_overlap_real" not in indexes()

    MigrationExecutor(connection).migrate(forward)
    assert {"no_teacher_time_overlap_real", "no_class_time_overlap_real"} <= indexes()
    assert "no_teacher_time_overlap" not in indexes()


def test_attempts_are_throttled_even_when_they_are_refused(
    school, klass, teacher, subject, assigned, settings
):
    """سقفُ معدّل الطلبات يعدّ المحاولاتِ لا الصفوفَ فقط: تكرارُ رقمٍ مرفوضٍ لا يجري بلا حدّ (مراجعة 0104، 3)."""
    from django.core.cache import cache

    cache.clear()
    for _ in range(provisional.ATTEMPTS_PER_HOUR):
        with pytest.raises(provisional.ProvisionalRefusedError):
            provisional.create(teacher, school, assigned.id, 99)

    with pytest.raises(provisional.ProvisionalRefusedError, match="كثيرة"):
        provisional.create(teacher, school, assigned.id, 1)
