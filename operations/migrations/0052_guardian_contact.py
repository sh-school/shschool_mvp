"""إخطارُ وليّ الأمر بغياب ابنه — ومعه عزلُ المدرسة (كما في 0049)."""


import django.db.models.deletion
import operations.models
from django.conf import settings
from django.db import migrations, models



TABLE = "operations_guardiancontact"
PREDICATE = f"{TABLE}.school_id = public.app_rls_school()"
ENABLE = f"""
ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS school_isolation ON public.{TABLE};
CREATE POLICY school_isolation ON public.{TABLE} USING ({PREDICATE}) WITH CHECK ({PREDICATE});
"""
DISABLE = f"""
DROP POLICY IF EXISTS school_isolation ON public.{TABLE};
ALTER TABLE public.{TABLE} DISABLE ROW LEVEL SECURITY;
"""

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0066_auditlog_failed_login_actions'),
        ('operations', '0051_absence_excuse'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='GuardianContact',
            fields=[
                ('id', models.UUIDField(default=operations.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('absence_date', models.DateField(verbose_name='يومُ الغياب')),
                ('outcome', models.CharField(choices=[('answered', 'ردّ'), ('no_answer', 'لم يردّ'), ('will_excuse', 'سيُحضر عذراً')], max_length=12, verbose_name='النتيجة')),
                ('channel', models.CharField(choices=[('phone', 'هاتف'), ('sms', 'رسالة نصّيّة')], default='phone', max_length=6)),
                ('note', models.CharField(blank=True, max_length=200, verbose_name='ملاحظة')),
                ('contacted_at', models.DateTimeField(verbose_name='وقتُ الاتّصال')),
                ('contacted_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='guardian_contacts_made', to=settings.AUTH_USER_MODEL)),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='guardian_contacts', to='core.school')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='guardian_contacts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'إخطارُ وليّ أمر',
                'verbose_name_plural': 'إخطاراتُ أولياء الأمور',
                'ordering': ['-contacted_at'],
                'indexes': [models.Index(fields=['school', 'student'], name='operations__school__be619a_idx'), models.Index(fields=['student', 'absence_date'], name='operations__student_494fc4_idx')],
            },
        ),
        migrations.RunSQL(sql=ENABLE, reverse_sql=DISABLE),
    ]
