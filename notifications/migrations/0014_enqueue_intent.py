"""[B4-PRE4] صندوق الصادر — نيّة الطبر تصير دائمة.

`title` و`body` كانا يعيشان في إغلاق `transaction.on_commit` وحده، ولا يحفظهما
`NotificationDispatch`. ففشلُ الطبر ثم انتهاء الطلب يعني ضياع المصدر الوحيد
لهما — ومُصالِحٌ يعرف أن رسالةً لم تخرج ولا يعرف ماذا يُعيد ليس مُصالِحاً.

والقيد المركّب هنا كغيره في السلسلة: `intent(dispatch_id, school_id)` يشير إلى
`dispatch(id, school_id)`، فيستحيل أن تحمل النيّة مدرسةً غير مدرسة واقعتها.
والسياسة صريحة لأن مطابقة 0037 واقعة ماضية.

"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import notifications.models

TENANT_FK_SQL = """
ALTER TABLE public.notifications_notificationenqueueintent
    ADD CONSTRAINT intent_tenant_matches_dispatch
    FOREIGN KEY (dispatch_id, school_id)
    REFERENCES public.notifications_notificationdispatch (id, school_id);
"""

DROP_TENANT_FK_SQL = "ALTER TABLE public.notifications_notificationenqueueintent DROP CONSTRAINT IF EXISTS intent_tenant_matches_dispatch;"

ENABLE_RLS_SQL = """
ALTER TABLE public.notifications_notificationenqueueintent ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS school_isolation ON public.notifications_notificationenqueueintent;

CREATE POLICY school_isolation ON public.notifications_notificationenqueueintent
    USING (school_id = public.app_rls_school())
    WITH CHECK (school_id = public.app_rls_school());
"""

DISABLE_RLS_SQL = """
DROP POLICY IF EXISTS school_isolation ON public.notifications_notificationenqueueintent;
ALTER TABLE public.notifications_notificationenqueueintent DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0038_rls_parent_derived"),
        ("notifications", "0013_delivery_undeliverable"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationEnqueueIntent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=notifications.models._uuid,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "title",
                    models.CharField(blank=True, max_length=300, null=True, verbose_name="العنوان"),
                ),
                ("body", models.TextField(blank=True, null=True, verbose_name="النصّ")),
                (
                    "content_cleared_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="مُسح المحتوى"),
                ),
                (
                    "enqueue_token",
                    models.UUIDField(blank=True, null=True, verbose_name="رمز الطبر"),
                ),
                ("enqueue_expires_at", models.DateTimeField(blank=True, null=True)),
                (
                    "last_enqueue_attempt_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="آخر محاولة طبر"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "dispatch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="enqueue_intents",
                        to="notifications.notificationdispatch",
                        verbose_name="الواقعة",
                    ),
                ),
                (
                    "recipient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="notification_enqueue_intents",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="المستلم",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notification_enqueue_intents",
                        to="core.school",
                        verbose_name="المدرسة",
                    ),
                ),
            ],
            options={
                "verbose_name": "نيّة طبر",
                "verbose_name_plural": "نيّات الطبر",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["school", "last_enqueue_attempt_at"],
                        name="notif_intent_school_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("dispatch", "recipient"),
                        name="uniq_enqueue_intent_per_recipient",
                    ),
                    models.UniqueConstraint(fields=("id", "school"), name="uniq_intent_id_school"),
                ],
            },
        ),
        migrations.RunSQL(sql=TENANT_FK_SQL, reverse_sql=DROP_TENANT_FK_SQL),
        migrations.RunSQL(sql=ENABLE_RLS_SQL, reverse_sql=DISABLE_RLS_SQL),
    ]
