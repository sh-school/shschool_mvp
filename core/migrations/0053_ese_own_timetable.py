"""شُعبُ التربية الخاصّة جدولُها مستقلّ — استثناءٌ يُكتب لا تجاهلٌ صامت.

قرارُ الإدارة (2026-09-05): «التربية الخاصة لهم جدول خاص بهم ولا يتبع لهذا
الجدول». ودليلُ الخطط الدراسيّة الوزاريّ يفرد لمدارس التربية الخاصّة خططاً
مستقلّةً عن خطط التعليم العامّ.

وبلا هذا العلم تظهر الشُّعبُ الثلاث (8/ESE و9/ESE و10/ESE) «بلا إسناد» في كلّ
فحصِ تغطيةٍ إلى الأبد، فيتعوّد القارئُ على فجوةٍ حمراءَ دائمة — وأخطرُ ما في
التنبيه أن يُعتاد. والاستثناءُ المقصودُ يُسجَّل في البيانات، فيُقرأ بعد سنةٍ
قراراً لا خللاً.

والترحيلُ متعادل: يضبط العلمَ للشُّعب التي رمزُها يحوي `ESE` ولا يمسّ غيرَها،
ويُعيدها إلى الافتراض عند التراجع.
"""

from django.db import migrations


def mark(apps, schema_editor):
    ClassGroup = apps.get_model("core", "ClassGroup")
    ClassGroup.objects.filter(section__icontains="ESE").update(has_own_timetable=True)


def unmark(apps, schema_editor):
    ClassGroup = apps.get_model("core", "ClassGroup")
    ClassGroup.objects.filter(section__icontains="ESE").update(has_own_timetable=False)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0052_classgroup_has_own_timetable"),
    ]

    operations = [
        migrations.RunPython(mark, unmark),
    ]
