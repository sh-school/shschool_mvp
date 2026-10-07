"""حصّةٌ مؤقّتة للمعلّم (W-20261005-006، D-217م/D-218م): حقلان وقيدا تفرّدٍ للمؤقّتة وحدَها — **إضافةٌ لا تغييرَ لقائم**.

- `provisional` بـ`db_default=False` (لا `default` وحده): نسخةُ الكود القديمةُ أثناء النشر المتدحرج تُدرج الصفَّ بلا الحقل فلا يفشل.
  وكلُّ صفٍّ قائمٍ يأخذ `False`، فلا يتغيّر سلوكُ شيءٍ مولَّدٍ من الجدول.
- `provisional_until` يقبل `NULL` (للحقيقيّة).
- قيدا التفرّد **مشروطان بـ`provisional=True`**: لا صفَّ مؤقّتاً الآن فلا يُفحص بهما شيء، ولا يمسّان قيدَي `no_teacher_time_overlap`
  و`no_class_time_overlap` على الحقيقيّة. (استبدالُ هذين القيدين بنسختين مشروطتين — استثناءٌ معلَنٌ للمالك — **ليس في هذه الهجرة**؛ ينتظر تأكيدَه.)
- لا جدولَ جديد فلا RLS ولا محوَ جديد؛ الحقلان للقراءة في `/admin/`.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0069_rls_daily_exit_tally"),
    ]

    operations = [
        migrations.AddField(
            model_name="session",
            name="provisional",
            field=models.BooleanField(db_default=False, default=False, verbose_name="حصّة مؤقّتة"),
        ),
        migrations.AddField(
            model_name="session",
            name="provisional_until",
            field=models.DateTimeField(blank=True, null=True, verbose_name="سريانُ المؤقّتة حتى"),
        ),
        migrations.AddConstraint(
            model_name="session",
            constraint=models.UniqueConstraint(
                condition=models.Q(("provisional", True)),
                fields=("class_group", "date", "period_number"),
                name="provisional_class_period_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="session",
            constraint=models.UniqueConstraint(
                condition=models.Q(("provisional", True)),
                fields=("teacher", "date", "period_number"),
                name="provisional_teacher_period_unique",
            ),
        ),
    ]
