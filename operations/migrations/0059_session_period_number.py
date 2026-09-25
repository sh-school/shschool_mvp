from django.db import migrations, models
from django.db.models import OuterRef, Subquery


def backfill_period_number(apps, schema_editor):
    """رقمُ كلّ حصّةٍ قائمة من خانتها النشطة: الشعبةُ والوقتُ ومجموعةُ الاختيار في يوم الأسبوع.

    والمعلّمُ لا يدخل المطابقة: الحصّةُ المبدَّلةُ أو المُشغَلةُ معلّمُها غيرُ صاحب الخانة، وخانةُ
    الشعبة في الوقت الواحد واحدةٌ. وما لا خانةَ نشطةً تطابقه (عامٌ مضى، جدولٌ أُبدل) يبقى فارغاً.
    ويومُ الأسبوع في جانغو `week_day`: الأحد 1 … الخميس 5، ويومُنا 0 … 4.
    """
    Session = apps.get_model("operations", "Session")
    ScheduleSlot = apps.get_model("operations", "ScheduleSlot")
    TimeSlotConfig = apps.get_model("operations", "TimeSlotConfig")
    TimeBand = apps.get_model("core", "TimeBand")
    for our_day in range(5):
        day = Session.objects.filter(date__week_day=our_day + 1)
        period = (
            ScheduleSlot.objects.filter(
                class_group_id=OuterRef("class_group_id"),
                day_of_week=our_day,
                start_time=OuterRef("start_time"),
                elective_group=OuterRef("elective_group"),
                is_active=True,
            )
            .order_by()
            .values("period_number")[:1]
        )
        day.filter(period_number__isnull=True).update(period_number=Subquery(period))

        # حصصٌ ولّدها جدولٌ سابقٌ خانتُه لم تعد نشطة: رقمُها من جرس نطاق شعبتها ليومها.
        kind = "thursday" if our_day == 4 else "regular"
        bell = TimeSlotConfig.objects.filter(
            school_id=OuterRef("school_id"),
            day_type=kind,
            start_time=OuterRef("start_time"),
            is_break=False,
        ).order_by()
        # نطاقٌ نطاقاً بمعرّفٍ ثابت: جانغو لا يقبل مرجعاً عبر علاقةٍ داخل `update`.
        left = day.filter(period_number__isnull=True)
        for band in TimeBand.objects.all():
            left.filter(class_group__time_band_id=band.id).update(
                period_number=Subquery(bell.filter(band_id=band.id).values("period_number")[:1])
            )
        left.filter(class_group__time_band__isnull=True).update(
            period_number=Subquery(bell.filter(band__isnull=True).values("period_number")[:1])
        )


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0058_compensatory_colleague"),
    ]

    operations = [
        migrations.AddField(
            model_name="session",
            name="period_number",
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="الحصّة"),
        ),
        migrations.RunPython(backfill_period_number, migrations.RunPython.noop),
    ]
