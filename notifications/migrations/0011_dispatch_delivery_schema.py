"""[B4-0] The dormant dispatch/delivery schema — created, constrained, unused.

Nothing writes to these tables yet and no flag turns them on. This migration
exists so that the constraints can be reviewed and the guards can see them
before any code depends on them; connecting the current notification path is a
later, separately authorised step.

Three things here are not expressible in Django and are therefore raw SQL.

The first is the tenant-consistency constraint. `school_id` is duplicated onto
`NotificationDelivery` on purpose — operator screens query by school, and a
local column lets the policy be a plain predicate instead of a subquery — but a
duplicate can disagree with its parent. Django 5.2 has no composite foreign
key: `CompositePrimaryKey` addresses a different problem, and `ForeignObject`
creates no database constraint at all. So the invariant is declared directly:

    delivery (dispatch_id, school_id) -> dispatch (id, school_id)
    log      (delivery_id, school_id) -> delivery (id, school_id)
    dlq      (delivery_id, school_id) -> delivery (id, school_id)

alongside the ordinary foreign keys Django manages, which stay for the ORM.
Default `MATCH SIMPLE` semantics mean a row whose `delivery_id` is NULL
satisfies the constraint, which is exactly what the historical rows need — they
predate the pipeline and are not required to point at anything.

The autodetector cannot see these, so `makemigrations --check` will not report
drift on them; a future migration altering those columns will meet them without
a warning from Django. That is the price of an invariant the ORM cannot hold.

The second is row-level security. Both new tables carry `school_id`, so the
coverage guard will demand a policy — but migration 0037's reconcile loop is a
past event and will not run again. The guard reports the absence; only this
migration can prevent it.

The third is the ordering. Each composite key needs its target's UNIQUE(id,
school_id) to exist first, so the raw statements follow every AddConstraint.
All of it is DDL with no DML in between, which keeps the deferred foreign-key
triggers that once broke migration 0008 out of the picture.
"""

import django.db.models.deletion
import notifications.models
from django.conf import settings
from django.db import migrations, models

DISPATCH = "notifications_notificationdispatch"
DELIVERY = "notifications_notificationdelivery"
LOG = "notifications_notificationlog"
DLQ = "notifications_deadlettermessage"


def _tenant_fk(child, child_column, parent, name):
    """The child may only carry the school its parent carries."""
    return f"""
ALTER TABLE public.{child}
    ADD CONSTRAINT {name}
    FOREIGN KEY ({child_column}, school_id)
    REFERENCES public.{parent} (id, school_id);
"""


def _drop_constraint(table, name):
    return f"ALTER TABLE public.{table} DROP CONSTRAINT IF EXISTS {name};"


def _enable_rls(table):
    return f"""
ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS school_isolation ON public.{table};

CREATE POLICY school_isolation ON public.{table}
    USING (school_id = public.app_rls_school())
    WITH CHECK (school_id = public.app_rls_school());
"""


def _disable_rls(table):
    return f"""
DROP POLICY IF EXISTS school_isolation ON public.{table};
ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0038_rls_parent_derived"),
        ("notifications", "0010_notification_log_channels"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationDelivery",
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
                    "channel",
                    models.CharField(
                        choices=[
                            ("email", "بريد إلكتروني"),
                            ("sms", "SMS"),
                            ("whatsapp", "WhatsApp"),
                            ("push", "Push"),
                        ],
                        max_length=10,
                        verbose_name="القناة",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "معلّق"),
                            ("in_progress", "قيد التنفيذ"),
                            ("sent", "سُلّم"),
                            ("retry_wait", "بانتظار إعادة المحاولة"),
                            ("dead_lettered", "استنفد المحاولات"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=15,
                        verbose_name="الحالة",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "recipient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="notification_deliveries",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="المستلم",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notification_deliveries",
                        to="core.school",
                        verbose_name="المدرسة",
                    ),
                ),
            ],
            options={
                "verbose_name": "تسليم إشعار",
                "verbose_name_plural": "تسليمات الإشعار",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="deadlettermessage",
            name="delivery",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="dead_letter",
                to="notifications.notificationdelivery",
                verbose_name="التسليم",
            ),
        ),
        migrations.AddField(
            model_name="notificationlog",
            name="delivery",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="attempts",
                to="notifications.notificationdelivery",
                verbose_name="التسليم",
            ),
        ),
        migrations.CreateModel(
            name="NotificationDispatch",
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
                    "event_type",
                    models.CharField(
                        db_index=True, max_length=40, verbose_name="نوع الحدث"
                    ),
                ),
                (
                    "related_object_id",
                    models.CharField(
                        blank=True, max_length=64, verbose_name="كائن الأعمال (سياق)"
                    ),
                ),
                (
                    "related_url",
                    models.CharField(blank=True, max_length=500, verbose_name="الرابط"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notification_dispatches",
                        to="core.school",
                        verbose_name="المدرسة",
                    ),
                ),
                (
                    "sent_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="notification_dispatches",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="أطلقها",
                    ),
                ),
            ],
            options={
                "verbose_name": "واقعة إشعار",
                "verbose_name_plural": "وقائع الإشعار",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="notificationdelivery",
            name="dispatch",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="deliveries",
                to="notifications.notificationdispatch",
                verbose_name="الواقعة",
            ),
        ),
        migrations.AddIndex(
            model_name="notificationdispatch",
            index=models.Index(
                fields=["school", "event_type", "created_at"], name="notif_dispatch_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="notificationdispatch",
            constraint=models.UniqueConstraint(
                fields=("id", "school"), name="uniq_dispatch_id_school"
            ),
        ),
        migrations.AddIndex(
            model_name="notificationdelivery",
            index=models.Index(
                fields=["school", "status", "created_at"], name="notif_delivery_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="notificationdelivery",
            constraint=models.UniqueConstraint(
                fields=("dispatch", "recipient", "channel"),
                name="uniq_delivery_dispatch_recipient_channel",
            ),
        ),
        migrations.AddConstraint(
            model_name="notificationdelivery",
            constraint=models.UniqueConstraint(
                fields=("id", "school"), name="uniq_delivery_id_school"
            ),
        ),
        # ── tenant consistency, enforced by the database ─────────────────────
        migrations.RunSQL(
            sql=_tenant_fk(DELIVERY, "dispatch_id", DISPATCH, "delivery_tenant_matches_dispatch"),
            reverse_sql=_drop_constraint(DELIVERY, "delivery_tenant_matches_dispatch"),
        ),
        migrations.RunSQL(
            sql=_tenant_fk(LOG, "delivery_id", DELIVERY, "notificationlog_tenant_matches_delivery"),
            reverse_sql=_drop_constraint(LOG, "notificationlog_tenant_matches_delivery"),
        ),
        migrations.RunSQL(
            sql=_tenant_fk(DLQ, "delivery_id", DELIVERY, "dlq_tenant_matches_delivery"),
            reverse_sql=_drop_constraint(DLQ, "dlq_tenant_matches_delivery"),
        ),
        # ── isolation, stated here because 0037's reconcile is in the past ───
        migrations.RunSQL(sql=_enable_rls(DISPATCH), reverse_sql=_disable_rls(DISPATCH)),
        migrations.RunSQL(sql=_enable_rls(DELIVERY), reverse_sql=_disable_rls(DELIVERY)),
    ]
