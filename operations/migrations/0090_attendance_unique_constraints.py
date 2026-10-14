"""قيدا الفرادة على الغياب (W-20261004-021): تنبيهٌ واحد لكلّ (مدرسة، طالب، عتبة، فترة)، وخروجٌ مفتوحٌ واحد لطالبٍ في حصّة.

يُبنى الفهرسُ `CONCURRENTLY` فلا يُقفل الجدول (بلا معاملة)، والتنبيهُ يُصرَّح بشرطٍ دائمِ الصدق (`gate` غيرُ فارغٍ بالتعريف) ليكون فهرساً جزئيّاً يُسقطه Django بـ`DROP INDEX` كما يُنشأ — وقيدُ `UNIQUE USING INDEX` يُسقطه المدقّقُ.
والحالةُ في Django `AddConstraint` نفسُه، فلا يظنّ التوليدُ التالي فرقاً.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("operations", "0089_attendance_check_constraints"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="CREATE UNIQUE INDEX CONCURRENTLY unique_absence_alert_per_gate_period "
                    "ON operations_absencealert (school_id, student_id, gate, period_start, period_end) "
                    "WHERE gate IS NOT NULL",
                    reverse_sql="DROP INDEX CONCURRENTLY IF EXISTS unique_absence_alert_per_gate_period",
                ),
            ],
            state_operations=[
                migrations.AddConstraint(
                    model_name="absencealert",
                    constraint=models.UniqueConstraint(
                        condition=models.Q(("gate__isnull", False)),
                        fields=("school", "student", "gate", "period_start", "period_end"),
                        name="unique_absence_alert_per_gate_period",
                    ),
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="CREATE UNIQUE INDEX CONCURRENTLY unique_open_class_exit_per_session_student "
                    "ON operations_classexit (session_id, student_id) WHERE returned_at IS NULL",
                    reverse_sql="DROP INDEX CONCURRENTLY IF EXISTS unique_open_class_exit_per_session_student",
                ),
            ],
            state_operations=[
                migrations.AddConstraint(
                    model_name="classexit",
                    constraint=models.UniqueConstraint(
                        condition=models.Q(("returned_at__isnull", True)),
                        fields=("session", "student"),
                        name="unique_open_class_exit_per_session_student",
                    ),
                ),
            ],
        ),
    ]
