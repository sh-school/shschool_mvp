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
  // تخزينُ S3 للملفات المرفوعة (البند 11): `production.py` يتطلّبه عند الإقلاع ويرفض
  // الإقلاعَ دونه (`ImproperlyConfigured`)، وكلُّ خدمةٍ تحمّل إعدادات الإنتاج نفسَها —
  // فلولا ذكرُها هنا لحذفها `railway config apply` فسقط الإنتاج. الأسرارُ مرجعيّةٌ بلا قيم.
  // الثلاثةُ الأولى إلزاميّة؛ والإقليمُ ونقطةُ النهاية والنطاقُ المخصّص اختياريّة (لها افتراضات).
  "AWS_ACCESS_KEY_ID",
  "AWS_SECRET_ACCESS_KEY",
  "AWS_STORAGE_BUCKET_NAME",
  "AWS_S3_REGION_NAME",
  "AWS_S3_ENDPOINT_URL",
  "AWS_S3_CUSTOM_DOMAIN",
  "CELERY_ASYNC_ENABLED",
  "DB_HOST",
  "DB_NAME",
  "DB_PORT",
  "DJANGO_SETTINGS_MODULE",
  "EXCEL_PROTECTION_PASSWORD",
  "FERNET_KEY",
  // المفاتيحُ القديمة لكلّ خدمةٍ تقرأ المشفَّر — كانت للعامل وحدَه، فتدويرُ
  // المفتاح يكسر القراءةَ على الويب (حادثة الثنائيّة 2026-09-14). P1-5.
  "FERNET_OLD_KEYS",
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
  // بابُ طوارئ الثنائيّة (قرار 2026-09-14: مجمَّدة مؤقّتاً) — لولا ذكرُه هنا لحذفه `apply` التالي فعاد الإلزامُ فجأة.
  "TWO_FACTOR_REQUIRED_FOR_STAFF",
] as const;

const WORKER_VARIABLES = [
  ...SHARED_VARIABLES,
  // مهمّةُ الاحتفاظ بالبيانات (`core.enforce_data_retention`) تعمل في العامل لا في الويب،
  // فالمدّةُ تُقرأ هنا — وإلّا سرى افتراضُ الإعدادات (730) مهما ضُبط على الويب.
  "PDPPL_DATA_RETENTION_DAYS",
  "SENTRY_PERFORMANCE_ENABLED",
  // Beat مضمَّنٌ في العامل (W-20261031-004): العلمُ يُضبط true بعد إيقاف خدمة celery-beat.
  "CELERY_WORKER_EMBED_BEAT",
  "CELERY_WORKER_CONCURRENCY",
] as const;

/** متغيّراتُ خدمة النسخ (أسماءٌ فقط): الرابطُ الداخليّ للقاعدة، وعبارةُ التشفير، ومراجعُ الحاوية. */
const BACKUP_VARIABLES = [
  "DATABASE_URL",
  "BACKUP_PASSPHRASE",
  "BACKUP_S3_ENDPOINT",
  "BACKUP_S3_BUCKET",
  "BACKUP_S3_ACCESS_KEY_ID",
  "BACKUP_S3_SECRET_ACCESS_KEY",
  "BACKUP_S3_REGION",
] as const;

/** البناءُ من Dockerfile الجذر، وإعادةُ التشغيل عند الفشل ثلاثَ مرّات. */
const DOCKER_BUILD = { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" } as const;
const RESTART_ON_FAILURE = { restartPolicyMaxRetries: 3 } as const;

export default defineRailway(() => {
  const web = service("shschool_mvp", {
    source: github(REPO),
    build: DOCKER_BUILD,
    // preDeploy يُنفَّذ مرّةً واحدةً قبل أن تستقبل أيّ نسخةٍ الحركة: الهجراتُ
    // والبذرُ والثابتُ وتوفيرُ دور RLS. start بعده لكلّ نسخةٍ: حارسٌ ثمّ daphne (P4-1).
    preDeploy: "bash scripts/railway-predeploy.sh",
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

  // Beat مضمَّنٌ في العامل (`celery worker -B` عند CELERY_WORKER_EMBED_BEAT=true، W-20261031-004): لا خدمةَ celery-beat
  // مستقلّة (كانت تحجز ~186MB لإرسال الجدول وحدَه). الجدولُ `shschool/celery.py: beat_schedule`. نسخةٌ واحدةٌ من العامل فقط.

  // نسخٌ احتياطيٌّ يوميٌّ مشفّرٌ داخل Railway (W-20261023-018): pg_dump عبر الشبكة الخاصّة إلى حاوية `db-backups`.
  // خدمةُ cron تخرج بعد الإنجاز. الجدولُ 01:00 UTC. تنبيه: مفتاحُ `cronSchedule` تحت `deploy` لم يُتحقَّق منه
  // بتشغيل `railway config plan` بعد — راجع docs/deployment/railway_backup.md قبل أيّ `apply`.
  const backup = service("db-backup", {
    source: github(REPO),
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile.backup" },
    deploy: { restartPolicyMaxRetries: 0, cronSchedule: "0 1 * * *" },
    variables: keep(BACKUP_VARIABLES),
  });

  // قواعدُ البيانات والحاوية تُدار من Railway نفسِه؛ ذكرُها هنا يمنع `apply` من حذفها.
  const db = postgres("Postgres");
  const cache = redis("Redis");
  const backups = bucket("db-backups", { region: "sjc" });

  return project("shschool_mvp", { resources: [web, worker, backup, db, cache, backups] });
});
