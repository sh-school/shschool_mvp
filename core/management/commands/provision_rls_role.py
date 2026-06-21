"""
core/management/commands/provision_rls_role.py

ينشئ/يحدّث دور التطبيق غير-superuser **shschool_app** ويمنحه الصلاحيات اللازمة
(idempotent). يُشغَّل بدور المالك/superuser (اتصال DATABASE_URL الافتراضي) أثناء
مرحلة الإطلاق — جزء من تفعيل RLS الحقيقي في الإنتاج (المخاطر #1/#2/#3).

السبب: سياسات RLS (migration 0033) لا تُفرَض إلا إذا اتصل runtime بدور ليس
superuser ولا BYPASSRLS. المالك يبقى للترحيل (DDL، يتجاوز RLS)، وruntime (daphne)
يتصل بـ shschool_app.

يقرأ كلمة المرور من البيئة: APP_DB_PASSWORD.
"""

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

ROLE = "shschool_app"


class Command(BaseCommand):
    help = "توفير/تحديث دور التطبيق غير-superuser shschool_app + صلاحياته (idempotent)."

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            self.stdout.write("ليس PostgreSQL — تخطّي توفير دور RLS.")
            return

        pw = os.environ.get("APP_DB_PASSWORD", "").strip()
        if not pw:
            raise CommandError("APP_DB_PASSWORD غير مضبوط — لا يمكن توفير الدور.")

        dbname = connection.settings_dict["NAME"]
        # اسم قاعدة البيانات معرّف — نقتبسه بأمان (لا يحتمل مدخلات خارجية، لكن احتياطاً)
        dbname_quoted = '"' + dbname.replace('"', '""') + '"'

        with connection.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [ROLE])
            exists = cur.fetchone() is not None

            if exists:
                cur.execute(
                    f"ALTER ROLE {ROLE} WITH LOGIN PASSWORD %s NOSUPERUSER NOBYPASSRLS",
                    [pw],
                )
                action = "updated"
            else:
                cur.execute(
                    f"CREATE ROLE {ROLE} LOGIN PASSWORD %s "
                    f"NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE",
                    [pw],
                )
                action = "created"

            # الصلاحيات (idempotent — GRANT لا يفشل عند التكرار)
            cur.execute(f"GRANT CONNECT ON DATABASE {dbname_quoted} TO {ROLE}")
            cur.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
            cur.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {ROLE}"
            )
            cur.execute(f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {ROLE}")
            cur.execute(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {ROLE}")
            # صلاحيات افتراضية للكائنات المستقبلية (يُنشئها المالك في الترحيلات)
            cur.execute(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {ROLE}"
            )
            cur.execute(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                f"GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {ROLE}"
            )

            cur.execute(
                "SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = %s",
                [ROLE],
            )
            su, bypass, login = cur.fetchone()

        self.stdout.write(
            self.style.SUCCESS(
                f"✓ {ROLE} {action} | super={su} bypassrls={bypass} login={login} (db={dbname})"
            )
        )
