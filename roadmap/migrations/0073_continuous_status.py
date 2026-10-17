"""حالةُ «مستمر» للبنود الدائمة: خياراتُ الحالة + إيقاعُ المراجعة + تاريخُ آخر مراجعة (W-20261009-025).

هجرةُ **توسيعٍ** بحتة: عمودان اختياريّان بلا قيدٍ ولا إعادةِ كتابةِ صفوف (`blank` + قيمةٌ افتراضيّةٌ فارغة / `NULL`)،
وتعديلُ `choices` لا يمسّ القاعدة. لا حذفَ ولا إعادةَ تسمية (قواعدُ `migrations.md`).

**الترقيمُ لـ0701 وحدَها**: حجزت 0073 لهذه الهجرة (0072 لمزامنتها في الطلب #935)؛ فهي تعتمد على
`0072_sync_items_2026_10_10b`، ولا يُدمج طلبُها قبل #935.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0072_sync_items_2026_10_10b"),
    ]

    operations = [
        migrations.AddField(
            model_name="roadmapitem",
            name="review_cadence",
            field=models.CharField(
                blank=True,
                choices=[("weekly", "أسبوعيّ"), ("monthly", "شهريّ")],
                default="",
                max_length=8,
                verbose_name="إيقاع المراجعة",
            ),
        ),
        migrations.AddField(
            model_name="roadmapitem",
            name="last_reviewed",
            field=models.DateField(blank=True, null=True, verbose_name="آخر مراجعة"),
        ),
        migrations.AlterField(
            model_name="roadmapitem",
            name="status",
            field=models.CharField(
                choices=[
                    ("todo", "لم يبدأ"),
                    ("doing", "قيد التنفيذ"),
                    ("done", "مُغلَق"),
                    ("blocked", "محجوب"),
                    ("deferred", "مؤجّل"),
                    ("continuous", "مستمر"),
                ],
                default="todo",
                max_length=16,
                verbose_name="الحالة",
            ),
        ),
    ]
