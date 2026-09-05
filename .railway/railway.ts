/**
 * إعداداتُ Railway بصيغة Infrastructure as Code — مصدرُ الحقيقة الوحيد منذ 2026-09-05
 * (حلّ محلّ `railway.json` و`railway.worker.json` اللذين أهملهما Railway).
 *
 * كيف يُستعمل:
 *   railway config plan   — يعرض الفرقَ بين هذا الملفّ وحال المشروع على Railway (قراءةٌ فقط)
 *   railway config apply  — يُطبّق الفرق (بيد المستخدم، وبعد خطّةٍ تُظهر صفرَ حذف)
 *
 * قواعدُ هذا الملفّ:
 *   - هو مصدرُ الحقيقة للمشروع كاملاً: كلُّ خدمةٍ أو قاعدةٍ أو حاويةٍ أو متغيّرٍ غيرِ مذكورٍ هنا
 *     يُعدّه `apply` مطلوبَ الحذف. لذلك تُسرَد أسماءُ المتغيّرات كلُّها.
 *   - القيمُ لا تُكتب هنا أبداً (المستودع عامّ): `preserve()` يُبقي القيمةَ المضبوطةَ في Railway.
 *     متغيّرٌ جديدٌ يُضاف في Railway يجب أن يُضاف اسمُه هنا وإلّا حذفه الـ`apply` التالي.
 *   - إقليمُ الحاوية `sjc` ثابتٌ منذ إنشائها ولا يُغيَّر (Railway يرفض تغييره).
 *   - سياسةُ إعادة التشغيل ON_FAILURE هي افتراضُ Railway ويخزّنها فارغةً، فذكرُها هنا
 *     يجعل الخطّة «2 to change» إلى الأبد — يُذكر عددُ المحاولات فقط.
 *   - أقاليمُ الخدمات لا يديرها هذا الملفّ (الخطّة تتجاهل `regions`) — من اللوحة.
 *
 * تشغيلُه على ويندوز داخل Git Bash (المكتبة تستخرج إصدارَ CLI من المتغيّر `_`):
 *   PATH="$APPDATA/npm/node_modules/@railway/cli/bin:$PATH" env -u _ railway.exe config plan
 */
import {
  bucket,
  defineRailway,
  github,
  postgres,
  preserve,
  project,
  redis,
  service,
} from "railway/iac";

const REPO = "sh-school/shschool_mvp";

/** كلُّ اسمٍ يُبقى بقيمته المضبوطة في Railway. */
const keep = (names: readonly string[]) =>
  Object.fromEntries(names.map((name) => [name, preserve()]));

const SHARED_VARIABLES = [
  "ALLOWED_HOSTS",
  "APP_DB_PASSWORD",
  "CELERY_ASYNC_ENABLED",
  "DB_HOST",
  "DB_NAME",
  "DB_PORT",
  "DJANGO_SETTINGS_MODULE",
  "EXCEL_PROTECTION_PASSWORD",
  "FERNET_KEY",
  "REDIS_URL",
  "SECRET_KEY",
  "SENTRY_DSN",
] as const;

const WEB_VARIABLES = [
  ...SHARED_VARIABLES,
  "APP_VERSION",
  "CELERY_BROKER_URL",
  "CELERY_RESULT_BACKEND",
  "CORS_ALLOWED_ORIGINS",
  "CSRF_COOKIE_SECURE",
  "DATABASE_URL",
  "DB_PASSWORD",
  "DB_USER",
  "DEBUG",
  "LANGUAGE_CODE",
  "MEDIA_ROOT",
  "MEDIA_URL",
  "METRICS_ALLOWED_IPS",
  "PDPPL_DATA_RETENTION_DAYS",
  "SECURE_HSTS_SECONDS",
  "SECURE_PROXY_SSL_HEADER",
  "SECURE_SSL_REDIRECT",
  "SESSION_COOKIE_SECURE",
  "STATIC_ROOT",
  "STATIC_URL",
  "TIME_ZONE",
] as const;

const WORKER_VARIABLES = [
  ...SHARED_VARIABLES,
  "FERNET_OLD_KEYS",
  "SENTRY_PERFORMANCE_ENABLED",
] as const;

/** البناءُ من Dockerfile الجذر، وإعادةُ التشغيل عند الفشل ثلاثَ مرّات. */
const DOCKER_BUILD = { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" } as const;
const RESTART_ON_FAILURE = { restartPolicyMaxRetries: 3 } as const;

export default defineRailway(() => {
  const web = service("shschool_mvp", {
    source: github(REPO),
    build: DOCKER_BUILD,
    start: "bash scripts/railway-release.sh",
    healthcheck: "/health/",
    healthcheckTimeout: 100,
    deploy: RESTART_ON_FAILURE,
    variables: keep(WEB_VARIABLES),
  });

  const worker = service("celery-worker", {
    source: github(REPO),
    build: DOCKER_BUILD,
    start: "bash scripts/railway-worker.sh",
    deploy: RESTART_ON_FAILURE,
    variables: keep(WORKER_VARIABLES),
  });

  // قواعدُ البيانات والحاوية تُدار من Railway نفسِه؛ ذكرُها هنا يمنع `apply` من حذفها.
  const db = postgres("Postgres");
  const cache = redis("Redis");
  const pitr = bucket("Postgres-PITR", { region: "sjc" });

  return project("shschool_mvp", { resources: [web, worker, db, cache, pitr] });
});
