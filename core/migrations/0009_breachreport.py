"""core/migrations/0009_breachreport.py"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_remove_moved_models'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='BreachReport',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('title', models.CharField(max_length=300, verbose_name='عنوان الخرق')),
                ('description', models.TextField(verbose_name='وصف الخرق التفصيلي')),
                ('severity', models.CharField(
                    choices=[('low','منخفضة'),('medium','متوسطة'),('high','عالية'),('critical','حرجة')],
                    default='medium', max_length=10)),
                ('data_type_affected', models.CharField(
                    choices=[('health','بيانات صحية'),('academic','بيانات أكاديمية'),
                             ('personal','بيانات شخصية'),('financial','بيانات مالية'),('all','جميع البيانات')],
                    default='personal', max_length=15, verbose_name='نوع البيانات المتأثرة')),
                ('affected_count', models.PositiveIntegerField(default=0, verbose_name='عدد الأشخاص المتأثرين')),
                ('discovered_at', models.DateTimeField(verbose_name='وقت الاكتشاف')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ncsa_deadline', models.DateTimeField(blank=True, null=True, verbose_name='موعد إشعار NCSA (72 ساعة)')),
                ('ncsa_notified_at', models.DateTimeField(blank=True, null=True, verbose_name='وقت إشعار NCSA الفعلي')),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(
                    choices=[('discovered','مكتشف'),('assessing','قيد التقييم'),
                             ('notified','تم الإشعار'),('resolved','محلول')],
                    default='discovered', max_length=15)),
                ('immediate_action', models.TextField(blank=True, verbose_name='الإجراء الفوري المتخذ')),
                ('containment_action', models.TextField(blank=True, verbose_name='إجراءات الاحتواء')),
                ('notification_text', models.TextField(blank=True, verbose_name='نص الإشعار لـ NCSA')),
                ('evidence_notes', models.TextField(blank=True, verbose_name='الأدلة والملاحظات')),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='breach_reports', to='core.school')),
                ('reported_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='reported_breaches', to=settings.AUTH_USER_MODEL)),
                ('assigned_to', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='assigned_breaches', to=settings.AUTH_USER_MODEL,
                    verbose_name='المسؤول (DPO)')),
            ],
            options={
                'verbose_name': 'تقرير خرق بيانات',
                'verbose_name_plural': 'تقارير خرق البيانات',
                'ordering': ['-discovered_at'],
            },
        ),
        migrations.AddIndex(
            model_name='breachreport',
            index=models.Index(fields=['school', 'status'], name='breach_school_status_idx'),
        ),
        migrations.AddIndex(
            model_name='breachreport',
            index=models.Index(fields=['discovered_at'], name='breach_discovered_idx'),
        ),
    ]
