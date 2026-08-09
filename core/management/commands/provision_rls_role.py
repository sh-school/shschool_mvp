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
                    f"ALTER ROLE {ROLE} WITH LOGIN PASSWORD %s "
                    f"NOSUPERUSER NOBYPASSRLS NOINHERIT "
                    f"NOCREATEDB NOCREATEROLE",
                    [pw],
                )
                action = "updated"
            else:
                cur.execute(
                    f"CREATE ROLE {ROLE} LOGIN PASSWORD %s "
                    f"NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEDB NOCREATEROLE",
                    [pw],
                )
                action = "created"

            # الصلاحيات (idempotent — GRANT لا يفشل عند التكرار)
            cur.execute(f"GRANT CONNECT ON DATABASE {dbname_quoted} TO {ROLE}")
            cur.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
            # [SEC-06] لا CREATE على المخطّط: أي جدول يُنشئه الدور يملكه، والمالك
            # يتجاوز RLS على جداوله. PostgreSQL 15+ يُلغيها افتراضياً — نؤكّدها
            # صراحةً لتغطية القواعد المُرقّاة من إصدارات أقدم.
            # السحب من الدور وحده لا يكفي: المنحة القديمة كانت لـPUBLIC ويرثها كل
            # دور ضمناً، وhas_schema_privilege يحتسبها — فيرفض الفاحص الإقلاع بلا
            # سبيل للشفاء الذاتي ما لم تُسحب من PUBLIC أيضاً.
            cur.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            cur.execute(f"REVOKE CREATE ON SCHEMA public FROM {ROLE}")
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

            # ── [SEC-07] هوية المستأجر تأتي من دور الاتصال ─────────────
            # المنح الشاملة أعلاه تشمل جدول الربط، أي أن الدور كان سيستطيع
            # إعادة كتابة هويته — نفس الثغرة في موضع جديد. يجب أن يأتي السحب
            # **بعد** المنح الشاملة، وإلا أعادها الإطلاق التالي.
            cur.execute(
                "REVOKE INSERT, UPDATE, DELETE, TRUNCATE " f"ON app_rls_role_school FROM {ROLE}"
            )
            cur.execute(
                "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON app_rls_role_school FROM PUBLIC"
            )
            cur.execute(f"GRANT SELECT ON app_rls_role_school TO {ROLE}")

            school_id = self._resolve_school_id(cur)
            cur.execute(
                "INSERT INTO app_rls_role_school (db_role, school_id) VALUES (%s, %s) "
                "ON CONFLICT (db_role) DO UPDATE SET school_id = EXCLUDED.school_id",
                [ROLE, school_id],
            )

            cur.execute(
                "SELECT rolsuper, rolbypassrls, rolcanlogin, rolinherit, "
                "rolcreatedb, rolcreaterole "
                "FROM pg_roles WHERE rolname = %s",
                [ROLE],
            )
            su, bypass, login, inherit, createdb, createrole = cur.fetchone()

            # [SEC-06] العضوية في دور آخر تفتح SET ROLE رغم NOINHERIT — نرصدها
            # ولا نُلغيها تلقائياً حتى لا نكسر منحاً مقصوداً بلا علم المشغّل.
            # pg_has_role يحلّ الرسم البياني للعضوية تعدّياً — عدّ pg_auth_members
            # المباشر يُفوّت السلسلة: الدور ← وسيط ← دور مميّز.
            cur.execute(
                "SELECT COUNT(*) FROM pg_roles AS r "
                "WHERE r.rolname <> %s AND pg_has_role(%s, r.oid, 'MEMBER')",
                [ROLE, ROLE],
            )
            memberships = cur.fetchone()[0]

        if memberships:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠ {ROLE} عضو في {memberships} دور — SET ROLE ممكن رغم NOINHERIT. "
                    f"راجعها: verify_runtime_db_role سيرفض الإقلاع."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"✓ {ROLE} {action} | super={su} bypassrls={bypass} "
                f"login={login} inherit={inherit} createdb={createdb} "
                f"createrole={createrole} memberships={memberships} "
                f"tenant_binding=db_role (db={dbname})"
            )
        )

    def _resolve_school_id(self, cur):
        """
        [SEC-07] يحدّد المدرسة المربوطة بدور التشغيل — fail-closed.

        المصدر الصريح APP_DB_ROLE_SCHOOL_ID يسبق أي استنتاج. بدونه نقبل
        الاستنتاج فقط حين تكون هناك مدرسة واحدة لا لبس فيها؛ ومع أكثر من
        مدرسة نرفض بدل أن نخمّن — تخمين خاطئ هنا يعني ربط الإنتاج بمستأجر
        خاطئ، وهو أسوأ من رفض الإقلاع.
        """
        configured = os.environ.get("APP_DB_ROLE_SCHOOL_ID", "").strip()
        if configured:
            cur.execute("SELECT 1 FROM core_school WHERE id = %s", [configured])
            if cur.fetchone() is None:
                raise CommandError(f"APP_DB_ROLE_SCHOOL_ID={configured!r} لا يطابق أي مدرسة.")
            return configured

        cur.execute("SELECT id FROM core_school")
        schools = cur.fetchall()

        if len(schools) == 1:
            return str(schools[0][0])

        raise CommandError(
            f"عدد المدارس = {len(schools)} — لا يمكن استنتاج مدرسة الدور. "
            f"اضبط APP_DB_ROLE_SCHOOL_ID صراحةً."
        )
