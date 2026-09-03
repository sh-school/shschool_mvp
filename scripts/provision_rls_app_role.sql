-- ════════════════════════════════════════════════════════════════════
-- provision_rls_app_role.sql — توفير دور تطبيق غير-superuser لـ RLS
-- ════════════════════════════════════════════════════════════════════
-- جزء من إصلاح المخاطر #1/#2/#3 (تقوية Row-Level Security).
--
-- لماذا: سياسات RLS (migration 0033) لا تُطبَّق إلا إذا اتصل التطبيق بدور
-- ليس superuser ولا BYPASSRLS وليس مالك الجداول. المالك (مثل shschool_user)
-- يبقى للترحيل/التعبئة (DDL) ويتجاوز RLS؛ بينما runtime يتصل بهذا الدور.
--
-- الاستخدام (شغّله بدور المالك/superuser):
--   psql -U <owner> -d <db> -v app_password="'STRONG_PASSWORD'" \
--        -f scripts/provision_rls_app_role.sql
--
-- ثم اضبط اتصال runtime على هذا الدور:
--   DB_USER=shschool_app  DB_PASSWORD=STRONG_PASSWORD
-- (في dev يفعل ذلك docker-compose.yml تلقائياً عبر APP_DB_PASSWORD في .env)
-- ════════════════════════════════════════════════════════════════════

\set ON_ERROR_STOP on

-- 1) الدور (idempotent) — غير superuser، غير bypassrls
-- متغيّرات psql (:'app_password') لا تُستبدل داخل كتل $$ … $$، فتُولَّد الكتلةُ
-- كاملةً بـ format() ثمّ تُنفَّذ بـ \gexec. والإنشاءُ والتعديلُ في كتلةٍ واحدةٍ مع
-- التقاط duplicate_object، فلا نافذةَ سباقٍ لو شُغّل السكربت مرّتين بالتوازي.
SELECT format($fmt$
DO $do$
BEGIN
    BEGIN
        CREATE ROLE shschool_app LOGIN PASSWORD %L
            NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
    EXCEPTION WHEN duplicate_object THEN
        ALTER ROLE shschool_app WITH LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS;
    END;
END
$do$
$fmt$, :'app_password', :'app_password')
\gexec

-- 2) الصلاحيات على المخطّط الحالي
GRANT CONNECT ON DATABASE :"DBNAME" TO shschool_app;
GRANT USAGE ON SCHEMA public TO shschool_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO shschool_app;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO shschool_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO shschool_app;

-- 3) صلاحيات افتراضية للكائنات المستقبلية (يُنشئها المالك أثناء الترحيل)
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO shschool_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO shschool_app;

-- 4) تحقّق
SELECT rolname, rolsuper, rolbypassrls, rolcanlogin
FROM pg_roles WHERE rolname = 'shschool_app';
