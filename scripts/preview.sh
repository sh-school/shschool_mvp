#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  المعاينةُ المركزيّة — خادمٌ واحدٌ يعرض main وما أودعته الجلساتُ ولم يُدمج، بوضع الإنتاج
# ══════════════════════════════════════════════════════════════
#  كان لكلّ جلسةٍ خادمُها لِيراها صاحبُ القرار، فاجتمعت خوادمُ مقيمةٌ أكثرُها خاملٌ على
#  جهازٍ ذاكرتُه 16 غيغا. فهنا خادمٌ واحد (`docker-compose.preview.yml`، منفذ 8500):
#
#    • الافتراضيّ (follow): شجرةُ `main-preview` على رأس main مضموماً إليه ما أودعته الجلساتُ ولم يُدمج
#      بعدُ (التكامل)، بإعدادات الإنتاج (shschool.settings.preview) — تتحدّث بعد أن يسكن ذلك بضعَ دقائق،
#      فيرى المالكُ عملَ الجلسات مجتمعاً قبل دمجه ودفعه (قرارُ المالك 2026-09-26). `integrate off` يعيدها
#      إلى main وحدَه.
#    • التثبيتُ المؤقّت (pin): شجرةُ جلسةٍ بإعدادات التطوير لمعاينة عملٍ لم يصر طلبَ دمجٍ
#      بعدُ (أو لم يُودَع)، ثمّ يعود إلى main وحدَه بعد مدّةٍ (120 دقيقةً افتراضاً) أو بـ`release`.
#
#  الأوامر (bash scripts/preview.sh <أمر>):
#    up [--lan]            أوّلَ مرّة: الشجرةُ والقاعدةُ ثمّ الإقلاع (متساوي الأثر). `--lan` يفتحه لشبكة
#                          الجهاز (لمعاينة الجوال)، وبلا `--lan` يعود إلى الحلقة المحلّيّة فقط.
#    sync [--now]          دورةٌ واحدة: إن تقدّم main أو ما أودعته الجلساتُ وسكن طُبّق. `--now` بلا انتظار السكون.
#    watch                 حلقةٌ تستدعي sync كلّ دقيقة (تبقى في تبويب طرفيّةٍ أو مهمّةٍ مجدولة).
#    pin <شجرة> [دقائق]    حوّل الخادمَ إلى شجرة جلسة (اسمُ مجلّدها، انظر list). لا يُنتزع تثبيتُ غيرك
#                          ما دامت مدّتُه قائمة إلّا بـ`--force` (بإذن المالك).
#    release               ارجع إلى main (والتكامل) الآن.
#    integrate [plan|on|off|exclude <شجرة>|include <شجرة>]
#                          ما يدخل التكاملَ الآن (plan، وهو الافتراضيّ)، وتشغيلُه وإطفاؤه، واستثناءُ شجرةٍ منه.
#    list                  الأشجارُ التي يمكن تثبيتُها.
#    status                ما يخدمه الخادمُ، ومقارنتُه بـmain وبالإنتاج (commit من /health/).
#    down                  أوقف الخادمَ والعامل (لا يحذف شيئاً).
#
#  قبل أن تصل هذه الشيفرةُ إلى main (إعداداتُ preview.py ليست فيه فلا يُقلع عليه) تُجرَّب على إيداعها:
#      PREVIEW_REF=<sha> bash scripts/preview.sh up        (أو PREVIEW_REF=origin/<فرع>)
#  وبعد دمجها: `up` بلا PREVIEW_REF من شجرة main-preview نفسِها. (والتكاملُ لا يعمل مع PREVIEW_REF: مرجعٌ صريحٌ = تجربة.)
#
#  لِمَ فحصٌ دوريّ لا خطّاف؟ طابورُ الدمج يدمج على GitHub بلا حدثٍ محلّيّ، والفحصُ يلتقط أيضاً
#  دمجاً يدويّاً وأيَّ تراجعٍ للإنتاج. ولِمَ السكون (3 دقائق)؟ الدمجُ يأتي دفعات (81 إيداعاً في
#  يومٍ)، فتحديثٌ لكلّ إيداعٍ هدرٌ؛ وله سقفُ انتظارٍ (15 دقيقة) كي لا يجوع التحديثُ. وإن سقط
#  تطبيقُ إيداعٍ (هجرةٌ مثلاً) عاد إلى آخر نسخةٍ سليمةٍ كي لا تسقط المعاينة، ولا يعيد المحاولةَ
#  على الإيداع نفسِه — وسقوطُه على بياناتٍ مزروعةٍ إنذارٌ مبكّرٌ بأنّ هجرةَ الإنتاج ستسقط.
#
#  التكامل: يُبنى من main ثمّ يُضَمّ رأسُ كلّ شجرةِ جلسةٍ (ما أُودع في فرعها، لا ما لم يُودَع) ثمّ رأسُ كلّ طلبٍ
#  مفتوحٍ غيرِ مسوّدةٍ وغيرِ آليّ (من GitHub بـgh؛ لجلسةٍ بدّلت فرعَها بين طلباتها فلا يظهر منها إلّا رأسُ شجرتها) بـ`git merge-tree`
#  و`git commit-tree` — أشياءُ وسيطةٌ في مخزن غيت لا تلمس شجرةً ولا فهرساً ولا فرعاً. يُتخطّى ويُذكر في `status`:
#  فرعٌ يتعارض (مع main أو مع فرعٍ ضُمّ قبله)، وفرعٌ خاملٌ (لا إيداعَ جديداً منذ 48 ساعة)، وفرعٌ تصادم
#  ترقيمُ هجرته هجرةً سابقةً (فيسقط migrate)، وفرعٌ يعدّل آلةَ المعاينة نفسَها
#  (تُنفَّذ من شجرة main-preview كلَّ دقيقةٍ فلا تُعطَب). وقاعدةُ المعاينة لا تحمل هجرةً ليست في الشجرة المعروضة:
#  إن اختفت هجرةٌ مطبَّقةٌ (سُحب فرعُها) أُنشئت قاعدةٌ جديدةٌ من الأصل المزروع (ss_main_preview_g<N>) — وإلّا
#  سقطت الصفحاتُ بـ«column … does not exist» كما في حادثة 2026-09-11. وإخفاقان متتاليان للتكامل يطفئانه.
#
#  عقدُ الأمان (يحرسه tests/test_preview_setup.py): لا يكتب في شجرة جلسةٍ ولا يبدّل فرعَها ولا
#  يدفع إلى غيت ولا يحذف قاعدةً أو شجرةً، ولا يمسّ حاوياتٍ غيرَ مشروعه `schoolos-main-preview`.
#  يكتب في شجرة `main-preview` وقاعدتِها وحدَهما، ويقرأ من غيرهما.
# ══════════════════════════════════════════════════════════════
set -euo pipefail

# مسارُ هذا الملفّ (بصيغة ويندوز `D:/…` حين يتاح) — منه يُؤخذ ملفُّ الإنشاء وسكربتُ القاعدة.
SELF_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && (pwd -W 2>/dev/null || pwd))"

ROOT="${SCHOOLOS_ROOT:-D:/shschool_mvp}"          # الجذرُ الأصليّ: منه .env وحده
WORKTREES="$ROOT/.claude/worktrees"
PREVIEW_DIR="${PREVIEW_DIR:-$WORKTREES/main-preview}"
PROJECT="schoolos-main-preview"
PORT="${PREVIEW_PORT:-8500}"
QUIET="${PREVIEW_QUIET_SECONDS:-180}"             # سكونُ main قبل التطبيق
MAX_WAIT="${PREVIEW_MAX_WAIT_SECONDS:-900}"       # سقفُ الانتظار
PIN_MINUTES="${PREVIEW_PIN_MINUTES:-120}"
INTERVAL="${PREVIEW_INTERVAL_SECONDS:-60}"
PROD_URL="${PRODUCTION_URL:-https://shschoolmvp-production.up.railway.app}"
COMPOSE_FILE="$SELF_ROOT/docker-compose.preview.yml"
DRY="${PREVIEW_DRY_RUN:-0}"                       # 1: يطبع ما سيفعله ولا يُغيّر شيئاً
# ما تتبعه المعاينةُ: main افتراضاً. ولتجربة شيفرةٍ لم تُدمج بعدُ (وأوّلُها هذه المعاينةُ نفسُها: preview.py
# ليس في main قبل دمجها فلا يُقلع عليه) يُمرَّر إيداعٌ أو فرعٌ: PREVIEW_REF=<sha> أو PREVIEW_REF=origin/<فرع>.
REF="${PREVIEW_REF:-origin/main}"
# التكامل: main مضموماً إليه ما أودعته الجلساتُ في أشجارها ولم يُدمج بعدُ (قرارُ المالك 2026-09-26: تلقائيّ).
# `integrate on|off` يحفظ اختيارَه في الحالة فيغلب هذا الافتراضَ.
INTEGRATE="${PREVIEW_INTEGRATE:-1}"
# فرعٌ لم يُودَع فيه عملٌ جديدٌ (غيرُ دمجٍ من main) منذ هذه الساعات يُعدّ منسيّاً فلا يدخل التكامل: أشجارٌ قديمةٌ
# على فروعٍ لم تُدمج (وُجد منها فرعُ 09-17 وآخرُ 09-22) تُظهر في المعاينة عملاً مهجوراً كأنّه قيدُ الدمج. 0 = بلا سقف.
MAX_AGE_HOURS="${PREVIEW_INTEGRATE_MAX_AGE_HOURS:-48}"
# ملفّاتُ آلةِ المعاينة نفسِها: تُنفَّذ من شجرة main-preview كلَّ دقيقة، فلا يدخل التكاملَ فرعٌ يعدّلها
# (فرعٌ معطوبٌ يكسر المراقبَ الذي يُفترض أن يستردّ المعاينة). يُعاين بـ`pin`.
MACHINERY=(scripts/preview.sh scripts/session-db.sh docker-compose.preview.yml)

say()  { printf '%s\n' "$*"; }
idle() { [ "${PREVIEW_QUIET_OUTPUT:-0}" = 1 ] || say "$*"; }
warn() { printf '! %s\n' "$*" >&2; }
die()  { printf '✗ %s\n' "$*" >&2; exit 1; }
now()  { date +%s; }
run()  { if [ "$DRY" = 1 ]; then printf '[dry] %s\n' "$*"; else "$@"; fi; }

# ما ستعرضه المعاينةُ: يضبطه resolve_target (وتقرؤه deploy_main وapply_main).
MAIN_SHA=""; TARGET=""; LABEL=""; INTEG_KIND="main"; INTEG_REPORT=""

# ── الحالة: ملفّاتٌ صغيرةٌ داخل .git لهذه الشجرة — لا تُتتبَّع ولا يمسّها reset ──
STATE_DIR=""
state_dir() {
  [ -n "$STATE_DIR" ] || STATE_DIR="$(git -C "$PREVIEW_DIR" rev-parse --absolute-git-dir)/preview-state"
  printf '%s' "$STATE_DIR"
}
sget() { local f; f="$(state_dir)/$1"; if [ -f "$f" ]; then cat "$f"; fi; }
sset() { [ "$DRY" = 1 ] && return 0; mkdir -p "$(state_dir)"; printf '%s' "$2" > "$(state_dir)/$1"; }
sdel() { [ "$DRY" = 1 ] && return 0; rm -f "$(state_dir)/$1"; }

# قفلٌ بسيط: عمليّتان معاً (حلقةُ watch وأمرٌ يدويّ) تُفسدان إعادةَ الإنشاء. قفلٌ قديمٌ (عمليّةٌ
# ماتت) يُكسر بعد 20 دقيقة.
acquire_lock() {
  [ "$DRY" = 1 ] && return 0
  local lock; lock="$(state_dir)/lock"
  mkdir -p "$(state_dir)"
  if ! mkdir "$lock" 2>/dev/null; then
    if [ -n "$(find "$lock" -maxdepth 0 -mmin +20 2>/dev/null)" ]; then
      rmdir "$lock" 2>/dev/null || true
      mkdir "$lock" 2>/dev/null || return 1
    else
      return 1
    fi
  fi
  trap 'rmdir "$(state_dir)/lock" 2>/dev/null || true' EXIT
}

# ── الشجرةُ والقاعدة ────────────────────────────────────────────
# جلبُ ما تتبعه المعاينة: فرعٌ بعيدٌ (origin/…) يُجلب؛ وإيداعٌ بعينه لا يحتاج جلباً.
fetch_ref() {
  case "$REF" in
    origin/*) run git -C "$PREVIEW_DIR" fetch origin "${REF#origin/}" --quiet ;;
  esac
}

ensure_tree() {
  if [ ! -e "$PREVIEW_DIR/.git" ]; then
    say "▸ تُنشأ شجرةُ المعاينة $PREVIEW_DIR على $REF"
    run git -C "$SELF_ROOT" fetch origin main --quiet
    run git -C "$SELF_ROOT" worktree add --detach "$PREVIEW_DIR" "$REF"
  fi
  if [ ! -f "$PREVIEW_DIR/.env" ]; then
    [ -f "$ROOT/.env" ] || die "لا $ROOT/.env لأنسخه — هو مُتجاهَلٌ في غيت ولا يصل الشجرةَ من نفسه"
    run cp "$ROOT/.env" "$PREVIEW_DIR/.env"
  fi
}

# `reset --hard` لا يجري إلّا في شجرةٍ مخصَّصةٍ لهذا وبلا تعديلٍ يدويّ — لا أمسحُ عملَ أحد.
guard_tree() {
  if [ "$(basename "$PREVIEW_DIR")" != "main-preview" ] && [ "${PREVIEW_ALLOW_ANY_DIR:-0}" != 1 ]; then
    die "PREVIEW_DIR ليس main-preview — أرفض reset --hard في شجرةٍ قد تكون لأحد"
  fi
  if [ -n "$(git -C "$PREVIEW_DIR" status --porcelain --untracked-files=no)" ]; then
    die "في شجرة المعاينة تعديلٌ يدويّ على ملفٍّ متتبَّع — لا أمسحه. راجع: git -C $PREVIEW_DIR status"
  fi
}

slug_db() { (cd "$1" && bash "$SELF_ROOT/scripts/session-db.sh" --name); }
ensure_db() {   # ensure_db <شجرة> [اسمٌ صريح]: الاسمُ الصريحُ لأجيال قاعدة المعاينة (انظر preview_db)
  local name="${2:-}"
  [ -n "$name" ] || name="$(slug_db "$1")"
  if [ "$DRY" = 1 ]; then say "[dry] قاعدةُ $name تُنشأ إن لم توجد"; return 0; fi
  (cd "$1" && SESSION_DB_NAME="$name" bash "$SELF_ROOT/scripts/session-db.sh")
}

# ── قاعدةُ المعاينة: لا تحمل هجرةً ليست في الشجرة المعروضة ─────────────────────────
# التكاملُ يطبّق هجراتِ فروعٍ لم تُدمج؛ فإن سُحب فرعٌ (تعارض، أو أعادت جلسةٌ كتابةَ هجرتها) بقيت هجرتُه
# مطبَّقةً في القاعدة والشيفرةُ لا تعرفها: حذفُ عمودٍ مثلاً يُسقط صفحاتٍ بـ«column … does not exist» —
# حادثةُ 2026-09-11 نفسُها. فكلُّ هجرةٍ قد طُبّقت تُسجَّل (db_migrations)، وحين تختفي إحداها من الشجرة
# الجديدة تُنشأ قاعدةٌ جديدةٌ من الأصل المزروع باسمٍ بجيلٍ أعلى؛ والقديمةُ تبقى (عقدُ السكربت ألّا يحذف).
migration_list() {   # migration_list <إيداع> — «تطبيق/رقم_اسم» لكلّ هجرةِ مشروعٍ فيه (من غيت مباشرةً، بلا django)
  git -C "$PREVIEW_DIR" ls-tree -r --name-only "$1" 2>/dev/null \
    | sed -nE 's#^(.*/)?([^/]+)/migrations/([0-9][^/]*)\.py$#\2/\3#p' \
    | LC_ALL=C sort -u
}

preview_db() {   # اسمُ قاعدة المعاينة الحاليّ: ss_main_preview ثمّ ss_main_preview_g1 وg2… بعد كلّ إعادة إنشاء
  local base gen; base="$(slug_db "$PREVIEW_DIR")"; gen="$(sget db_gen)"
  if [ -n "$gen" ] && [ "$gen" != 0 ]; then printf '%s_g%s' "$base" "$gen"; else printf '%s' "$base"; fi
}

prepare_db() {   # prepare_db <إيداع> — قبل كلّ إقلاع: هل في القاعدة هجرةٌ ليست في هذا الإيداع؟
  local target="$1" tree_list applied missing gen
  tree_list="$(migration_list "$target" || true)"
  applied="$(sget db_migrations)"
  # أوّلُ تشغيلٍ بعد هذا الأمر: القاعدةُ على ما خدمته آخرُ نسخة.
  if [ -z "$applied" ] && [ -n "$(sget served_sha)" ]; then
    applied="$(migration_list "$(sget served_sha)" || true)"
  fi
  if [ -n "$applied" ]; then
    missing="$(LC_ALL=C comm -23 <(printf '%s\n' "$applied") <(printf '%s\n' "$tree_list"))"
    if [ -n "$missing" ]; then
      gen="$(sget db_gen)"; gen=$(( ${gen:-0} + 1 ))
      warn "في قاعدة المعاينة هجراتٌ طُبّقت ولم تعد في الشجرة ($(printf '%s\n' "$missing" | head -3 | paste -sd' ' -)) — تُنشأ قاعدةٌ جديدةٌ من الأصل المزروع (الجيل $gen)"
      sset db_gen "$gen"
      sset db_note "$(now) أُعيدت القاعدةُ (الجيل $gen) لأنّ هجرةً مطبَّقةً سابقاً لم تعد في الشجرة المعروضة"
      applied=""
    fi
  fi
  # يُفترض الأسوأ: قد تُطبَّق هجراتُ هذا الإيداع كلُّها قبل أن يسقط الإقلاعُ.
  sset db_migrations "$(printf '%s\n%s\n' "$applied" "$tree_list" | sed '/^$/d' | LC_ALL=C sort -u)"
}

# ── الصورةُ: تُبنى فقط حين تخالف requirements.txt ما فيها ───────────
# الاعتماديّاتُ مثبَّتةٌ (==) في requirements.txt، فتُقارَن بما في الصورة بحاويةٍ عابرةٍ ثانيةً.
deps_drift() {
  local tree="$1" img="$2"
  MSYS_NO_PATHCONV=1 docker run --rm -i --network none --entrypoint python \
    -v "$tree:/probe:ro" "$img" - /probe/requirements.txt <<'PY'
import re
import sys
from importlib import metadata


def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


have = {norm(d.metadata["Name"]): d.version for d in metadata.distributions()}
bad = []
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.split("#", 1)[0].strip()
    m = re.match(r"^([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?==([^\s;]+)", line)
    if m and have.get(norm(m.group(1))) != m.group(2):
        bad.append(f"  {norm(m.group(1))}: في الصورة {have.get(norm(m.group(1)))} ← المطلوب {m.group(2)}")
print("\n".join(bad))
sys.exit(1 if bad else 0)
PY
}

current_image() {
  local img; img="$(sget image)"
  printf '%s' "${SCHOOLOS_IMAGE:-${img:-shschool_mvp-web}}"
}

# طبقةُ فروقٍ لا بناءٌ كامل: `FROM` صورةِ الحزمة الأصليّة (2.4 غيغا) و`pip install -r` — pip يتخطّى
# ما يوافق ويثبّت ما يخالف فقط (ثوانٍ وميغاباياتٌ قليلة، لا دقائقُ وغيغاباياتُ ذاكرة). فالاعتماديّاتُ
# تطابق requirements.txt في main تماماً كما يبنيها Railway، بلا ثمن إعادة البناء.
# ما لا تغطّيه: مكتباتُ النظام في Dockerfile — تغيُّرُها يُحدَّث بـ`docker compose build web` في الجذر.
build_image() {   # build_image <شجرة>
  local base="${PREVIEW_BASE_IMAGE:-shschool_mvp-web}"
  say "▸ تُبنى الصورةُ schoolos-preview: طبقةُ فروقٍ فوق $base (pip يثبّت ما يخالف requirements.txt فقط)"
  run docker build -t schoolos-preview:latest -f - "$1" <<EOF
FROM $base
USER root
COPY requirements.txt /tmp/preview-requirements.txt
RUN pip install --no-cache-dir -r /tmp/preview-requirements.txt
USER appuser
EOF
  sset image "schoolos-preview:latest"
}

ensure_image() {
  local tree="$1" img drift
  img="$(current_image)"
  if [ "$DRY" != 1 ] && ! docker image inspect "$img" >/dev/null 2>&1; then
    warn "الصورة $img غير موجودة"; build_image "$tree"; return 0
  fi
  if ! drift="$(deps_drift "$tree" "$img")"; then
    warn "اعتماديّاتُ الصورة $img تخالف requirements.txt في main:"
    printf '%s\n' "$drift" | head -8 >&2
    build_image "$tree"
  fi
}

# ── البيئةُ التي يقرؤها docker-compose.preview.yml ───────────────
export_env() {   # export_env <prod|dev> <شجرة> <قاعدة>
  local mode="$1" tree="$2" db="$3"
  export PREVIEW_DB="$db" PREVIEW_PORT="$PORT" PREVIEW_ENV_FILE="$PREVIEW_DIR/.env"
  export PREVIEW_SHA; PREVIEW_SHA="$(git -C "$tree" rev-parse --short=7 HEAD)"
  export PREVIEW_MODE="$mode"
  if [ "$mode" = "prod" ]; then
    export PREVIEW_SETTINGS="shschool.settings.preview" PREVIEW_DEBUG="False"
  else
    export PREVIEW_SETTINGS="shschool.settings.development" PREVIEW_DEBUG="True"
  fi
  if [ "$(sget lan)" = "1" ]; then
    export PREVIEW_BIND="0.0.0.0" PREVIEW_ALLOWED_HOSTS="*"
  else
    export PREVIEW_BIND="127.0.0.1"; unset PREVIEW_ALLOWED_HOSTS
  fi
  export SCHOOLOS_IMAGE; SCHOOLOS_IMAGE="$(current_image)"
}

compose() {   # compose <شجرة> <أوامر…>: الشجرةُ المعروضة هي المربوطة `.:/app`
  local tree="$1"; shift
  docker compose -p "$PROJECT" --project-directory "$tree" \
    --env-file "$PREVIEW_DIR/.env" -f "$COMPOSE_FILE" "$@"
}

wait_web() {
  [ "$DRY" = 1 ] && return 0
  local c="${PROJECT}-web-1" state i restarts
  for i in $(seq 1 90); do
    state="$(docker inspect -f '{{.State.Health.Status}}' "$c" 2>/dev/null || echo missing)"
    [ "$state" = "healthy" ] && return 0
    [ "$state" = "unhealthy" ] && break
    # حاويةٌ تُعاد تشغيلُها = الإقلاعُ يسقط (هجرةٌ مثلاً)، فلا ننتظر الأربعَ دقائق كلَّها.
    restarts="$(docker inspect -f '{{.RestartCount}}' "$c" 2>/dev/null || echo 0)"
    [ "$restarts" -ge 2 ] && break
    sleep 3
  done
  warn "الخادمُ لم يصحّ — آخرُ سطورِ سجلّه:"
  docker logs --tail 25 "$c" 2>&1 | sed 's/^/    /' >&2 || true
  return 1
}

served_commit() {
  curl -s -m 5 "http://127.0.0.1:$PORT/health/" | sed -n 's/.*"commit": *"\([0-9a-f]*\)".*/\1/p' || true
}

# ── التكامل: main + ما أودعته الجلساتُ ولم يُدمج ─────────────────────────────
# قراءةٌ وأشياءُ غيت وسيطةٌ فقط (merge-tree وcommit-tree): لا تُفتح شجرةُ جلسةٍ ولا يُبدَّل فرعٌ ولا يُكتب
# غيرُ كائناتٍ في مخزن غيت المشترك. والمرشَّحُ رأسُ كلّ شجرةِ جلسةٍ في فرعها ورأسُ كلّ طلبٍ مفتوح — ما أُودع لا ما لم يُودَع
# (ملفٌّ نصفُ مكتوبٍ يُسقط إقلاعَ الجميع؛ وله `pin`). والإيداعُ المصنوعُ حتميٌّ (هويّةٌ وتاريخٌ ثابتان):
# المدخلاتُ نفسُها تُنتج الإيداعَ نفسَه فلا تُعاد إقامةُ الخادم بلا تغيُّر.
integrate_flag() { local v; v="$(sget integrate)"; printf '%s' "${v:-$INTEGRATE}"; }
integrate_active() { [ "$REF" = "origin/main" ] && [ "$(integrate_flag)" = 1 ]; }

integ_candidates() {   # «الاسم|sha|الفرع» لكلّ شجرةِ جلسةٍ على فرع (بلا main-preview ولا فرعِ main ولا المستثنَين)
  local exclude; exclude=" $(sget integ_exclude) "
  git -C "$PREVIEW_DIR" worktree list --porcelain | awk '
    /^worktree / { p = substr($0, 10); h = ""; b = ""; gone = 0 }
    /^HEAD /     { h = $2 }
    /^branch /   { b = $2 }
    /^prunable/  { gone = 1 }
    /^$/         { if (p != "" && h != "" && b != "" && !gone) print p "|" h "|" b; p = "" }
    END          { if (p != "" && h != "" && b != "" && !gone) print p "|" h "|" b }
  ' | while IFS='|' read -r p h b; do
    n="${p##*/}"
    if [ "$n" = "main-preview" ] || [ "$b" = "refs/heads/main" ]; then continue; fi
    case "$exclude" in *" $n "*) continue ;; esac
    printf '%s|%s|%s\n' "$n" "$h" "${b#refs/heads/}"
  done
}

# رؤوسُ الطلبات المفتوحة غيرِ المسوّدة وغيرِ الآليّة (من GitHub بـgh): طلباتُ جلسةٍ بدّلت فرعَها بينها لا يظهر منها إلّا
# رأسُ شجرتها، وطلباتُ شجرةٍ أُزيلت — فتُضاف مرشَّحةً بعد رؤوس الأشجار. «pr-<رقم>|sha|عنوان». فارغٌ إن غاب gh أو تعذّرت
# الشبكة فيبقى التكاملُ برؤوس الأشجار وحدَها. (لا سقفَ خمولٍ لها: المفتوحُ قيدُ الدمج.)
integ_pr_heads() {
  command -v gh >/dev/null 2>&1 || return 0
  local exclude n h t; exclude=" $(sget integ_exclude) "
  (cd "$PREVIEW_DIR" && gh pr list --state open --limit 100 --json number,headRefOid,isDraft,title,author \
      --jq '.[] | select((.isDraft | not) and (.author.is_bot != true)) | "pr-\(.number)|\(.headRefOid)|\(.title)"' 2>/dev/null) \
    | while IFS='|' read -r n h t; do
        if [ -z "$h" ]; then continue; fi
        case "$exclude" in *" $n "*) continue ;; esac
        printf '%s|%s|%s\n' "$n" "$h" "${t%$'\r'}"   # gh على ويندوز قد ينهي السطرَ بـCR
      done
}

# هجرةٌ جديدةٌ برقمٍ أخذته هجرةٌ في مجلّدها نفسِه = فرعان في مخطّط الهجرات فيسقط migrate. يطبع أوّلَ تصادمٍ
# ويُنجح إن وُجد، وإلّا يُخفق.
integ_migration_clash() {   # integ_migration_clash <شجرةٌ قبل> <شجرةٌ بعد>
  local f dir num
  while IFS= read -r f; do
    dir="${f%/*}"; num="${f##*/}"; num="${num%%_*}"
    if git -C "$PREVIEW_DIR" ls-tree --name-only "$1" "$dir/" 2>/dev/null \
        | awk -v p="$dir/${num}_" 'index($0, p) == 1 { found = 1 } END { exit !found }'; then
      printf '%s' "$f"; return 0
    fi
  done < <(git -C "$PREVIEW_DIR" diff-tree -r --no-renames --diff-filter=A --name-only "$1" "$2" 2>/dev/null \
             | grep -E '(^|/)migrations/[0-9][^/]*\.py$' || true)
  return 1
}

plan_integration() {   # plan_integration <sha-main> — يضبط TARGET وINTEG_KIND وINTEG_REPORT
  local main="$1" trees prs cands key cached cur ctree mtree grp ct n h b disp out t rc files why ahead when fresh clash
  INTEG_REPORT=""; INTEG_KIND="main"; TARGET="$main"

  # رؤوسُ الأشجار أوّلاً (0) ثمّ رؤوسُ الطلبات المفتوحة (1)، والأقدمُ عملاً أوّلاً داخل كلٍّ: له الأولويّةُ إن تعارض اثنان.
  trees="$(integ_candidates || true)"
  prs="$(integ_pr_heads || true)"
  cands="$({
    while IFS='|' read -r n h b; do
      if [ -n "$h" ]; then
        printf '0|%s|%s|%s|%s\n' "$(git -C "$PREVIEW_DIR" log -1 --format=%ct "$h" 2>/dev/null || echo 0)" "$n" "$h" "$b"
      fi
    done <<<"$trees"
    while IFS='|' read -r n h b; do
      if [ -n "$h" ]; then   # رأسٌ دُفع من شجرةٍ أخرى غالباً موجودٌ في المخزن المشترك؛ وإلّا يُجلب من مرجع الطلب
        git -C "$PREVIEW_DIR" cat-file -e "$h^{commit}" 2>/dev/null \
          || git -C "$PREVIEW_DIR" fetch -q origin "refs/pull/${n#pr-}/head" 2>/dev/null || true
        printf '1|%s|%s|%s|%s\n' "$(git -C "$PREVIEW_DIR" log -1 --format=%ct "$h" 2>/dev/null || echo 0)" "$n" "$h" "$b"
      fi
    done <<<"$prs"
  } | LC_ALL=C sort -t'|' -k1,1n -k2,2n -k3,3)"

  # لا أُعيد الحسابَ ما لم يتغيّر main ولا رأسُ أيّ مرشَّحٍ ولا الاستثناءات (وفي كلّ ساعةٍ مرّةً: الخمولُ يتبع الوقتَ).
  key="$(printf '%s\n%s\n%s\n%s\n' "$main" "$cands" "$(sget integ_exclude)" "$(( $(now) / 3600 ))" \
         | git -C "$PREVIEW_DIR" hash-object --stdin)"
  cached="$(sget integ_target)"
  if [ "$key" = "$(sget integ_key)" ] && [ -n "$cached" ] \
      && git -C "$PREVIEW_DIR" cat-file -e "$cached^{commit}" 2>/dev/null; then
    TARGET="$cached"; INTEG_REPORT="$(sget integ_report)"
    if [ "$TARGET" != "$main" ]; then INTEG_KIND=integrated; fi
    return 0
  fi

  cur="$main"
  mtree="$(git -C "$PREVIEW_DIR" rev-parse "$main^{tree}")"; ctree="$mtree"
  while IFS='|' read -r grp ct n h b; do
    if [ -z "$h" ]; then continue; fi
    disp="$n"; if [ "$grp" = 1 ]; then disp="$n «${b}»"; fi   # الطلبُ يُسمّى برقمه وعنوانه (كاملاً: القصُّ بالبايت يكسر الحرفَ العربيّ)
    if ! git -C "$PREVIEW_DIR" cat-file -e "$h^{commit}" 2>/dev/null; then
      INTEG_REPORT+="✗ $disp — تعذّر جلبُ رأسه (الإيداعُ غيرُ موجودٍ في المخزن ولا على GitHub)"$'\n'
      continue
    fi
    if git -C "$PREVIEW_DIR" merge-base --is-ancestor "$h" "$cur" 2>/dev/null; then continue; fi   # مدموجٌ بالنسب
    ahead="$(git -C "$PREVIEW_DIR" rev-list --count "$main..$h" 2>/dev/null || echo '؟')"
    when="$(date -d "@$ct" '+%m-%d %H:%M' 2>/dev/null || echo "$ct")"

    # آخرُ إيداعٍ جديدٍ في الفرع نفسِه (لا دمجٍ من main: هو يُجدّد التاريخَ بلا عملٍ جديد).
    fresh="$(git -C "$PREVIEW_DIR" log --no-merges -1 --format=%ct "$main..$h" 2>/dev/null || true)"
    if [ "$grp" = 0 ] && [ "$MAX_AGE_HOURS" -gt 0 ] && [ -n "$fresh" ] && [ $(( $(now) - fresh )) -gt $(( MAX_AGE_HOURS * 3600 )) ]; then
      INTEG_REPORT+="✗ $disp — خاملٌ: آخرُ إيداعٍ جديدٍ فيه منذ $(( ($(now) - fresh) / 86400 )) يوماً (سقفُ التكامل ${MAX_AGE_HOURS} ساعة)"$'\n'
      continue
    fi

    if out="$(git -C "$PREVIEW_DIR" merge-tree --write-tree --name-only --no-messages "$cur" "$h" 2>/dev/null)"; then
      rc=0
    else
      rc=$?
    fi
    t="${out%%$'\n'*}"
    if [ "$rc" -ne 0 ]; then
      if [ "$rc" -eq 1 ]; then
        files="$(printf '%s\n' "$out" | sed -n '2,4p' | paste -sd' ' -)"
        if git -C "$PREVIEW_DIR" merge-tree --write-tree --no-messages "$main" "$h" >/dev/null 2>&1; then
          why="يتعارض مع فرعٍ ضُمّ قبله"
        else
          why="يتعارض مع main — يحتاج إعادةَ أساس"
        fi
        INTEG_REPORT+="✗ $disp — $why: ${files:-؟}"$'\n'
      else
        INTEG_REPORT+="✗ $disp — خطأ merge-tree ($rc)"$'\n'
      fi
      continue
    fi
    if [ "$t" = "$ctree" ]; then continue; fi   # لا جديدَ بالمحتوى: مدموجٌ بالسحق أو مكرَّر

    if ! git -C "$PREVIEW_DIR" diff-tree --quiet "$mtree" "$t" -- "${MACHINERY[@]}" 2>/dev/null; then
      if [ "$grp" = 0 ]; then
        INTEG_REPORT+="✗ $disp — يعدّل آلةَ المعاينة نفسَها (${MACHINERY[*]}) فلا يدخل التكاملَ — يُعاين بـ: preview.sh pin $n"$'\n'
      else
        INTEG_REPORT+="✗ $disp — يعدّل آلةَ المعاينة نفسَها (${MACHINERY[*]}) فلا يدخل التكاملَ — يُعاين بعد دمجه"$'\n'
      fi
      continue
    fi
    if clash="$(integ_migration_clash "$ctree" "$t")"; then
      INTEG_REPORT+="✗ $disp — هجرةٌ تصادم رقمَ هجرةٍ سابقةٍ في مجلّدها: $clash"$'\n'
      continue
    fi

    cur="$(GIT_AUTHOR_NAME=preview GIT_AUTHOR_EMAIL=preview@localhost GIT_AUTHOR_DATE='1700000000 +0000' \
           GIT_COMMITTER_NAME=preview GIT_COMMITTER_EMAIL=preview@localhost GIT_COMMITTER_DATE='1700000000 +0000' \
           git -c commit.gpgsign=false -C "$PREVIEW_DIR" commit-tree "$t" -p "$cur" -p "$h" -m "preview: $n@${h:0:7}")"
    ctree="$t"
    INTEG_KIND=integrated
    INTEG_REPORT+="+ $disp — $ahead إيداعاً (آخرُها $when)"$'\n'
  done <<<"$cands"
  TARGET="$cur"

  sset integ_key "$key"; sset integ_target "$TARGET"; sset integ_report "$INTEG_REPORT"
}

target_label() {   # LABEL: نصٌّ مقروءٌ لما ستعرضه المعاينة
  if [ "$INTEG_KIND" = integrated ]; then
    LABEL="تكامل@${TARGET:0:7} (main@${MAIN_SHA:0:7} + $(printf '%s' "$INTEG_REPORT" | grep -c '^+' || true) فرعاً)"
  else
    LABEL="main@${TARGET:0:7}"
  fi
}

resolve_target() {   # يضبط MAIN_SHA وTARGET وINTEG_KIND وINTEG_REPORT وLABEL — بعد fetch_ref
  MAIN_SHA="$(git -C "$PREVIEW_DIR" rev-parse "$REF")"
  TARGET="$MAIN_SHA"; INTEG_KIND="main"; INTEG_REPORT=""
  if integrate_active; then plan_integration "$MAIN_SHA"; fi
  target_label
}

# هل الإيداعان بشجرةٍ واحدة؟ تكاملٌ يُعاد بناؤه بإيداعاتٍ مختلفةٍ لمحتوىً واحدٍ لا يستحقّ إعادةَ إنشاء الخادم.
same_content() {
  [ -n "$2" ] || return 1
  if [ "$1" = "$2" ]; then return 0; fi
  [ "$(git -C "$PREVIEW_DIR" rev-parse "$1^{tree}" 2>/dev/null)" = "$(git -C "$PREVIEW_DIR" rev-parse "$2^{tree}" 2>/dev/null)" ]
}

# ── النشرُ المحلّيّ: main/التكامل (إنتاج) أو شجرةُ جلسة (تطوير) ─────────────
deploy_main() {
  local tree="$PREVIEW_DIR" db label
  db="$(preview_db)"
  ensure_db "$tree" "$db"
  ensure_image "$tree"
  export_env prod "$tree" "$db"
  label="${LABEL:-main@$PREVIEW_SHA}"
  say "▸ يُعاد إنشاءُ الخادم والعامل على $label (هجرة ← collectstatic ← daphne) — قاعدة $db"
  run compose "$tree" up -d --force-recreate --remove-orphans || warn "docker compose up أعاد خطأً"
  wait_web || return 1
  sset mode follow
  sset served_sha "$(git -C "$tree" rev-parse HEAD)"
  sset served_label "$label"
  sset served_report "$INTEG_REPORT"
  sset synced_at "$(now)"
  sdel pending_sha; sdel pending_since; sdel wait_since; sdel last_error; sdel pin_tree; sdel pin_until
  say "✔ $label على http://localhost:$PORT — يعلن /health/: commit=$(served_commit)"
}

# يطبّق إيداعاً على شجرة المعاينة؛ وإن سقط عاد إلى آخر نسخةٍ سليمةٍ ولا يكرّر المحاولةَ عليه.
apply_main() {   # apply_main <sha> — بعد resolve_target (LABEL وINTEG_KIND وINTEG_REPORT للهدف)
  local target="$1" good before label="$LABEL" kind="$INTEG_KIND" fails msg
  good="$(sget served_sha)"
  guard_tree
  before="$(git -C "$PREVIEW_DIR" rev-parse HEAD)"
  run git -C "$PREVIEW_DIR" reset --hard "$target" --quiet
  if [ -n "$(git -C "$PREVIEW_DIR" diff --name-only "$before" "$target" -- Dockerfile)" ]; then
    warn "Dockerfile تغيّر في main (مكتباتُ النظام) — الصورةُ الأصل قد تحتاج: docker compose build web (في الجذر)"
  fi
  prepare_db "$target"
  if deploy_main; then sdel failed_sha; sdel integ_failures; return 0; fi
  sset failed_sha "$target"
  msg="$label لم يُقلع"
  if [ "$kind" = integrated ]; then   # إخفاقان متتاليان: فرعٌ معطوبٌ يُسقط كلَّ تحديث — يُطفأ التكاملُ حتى يراجعه المالك
    fails="$(sget integ_failures)"; fails=$(( ${fails:-0} + 1 )); sset integ_failures "$fails"
    if [ "$fails" -ge 2 ]; then
      sset integrate 0
      msg="$msg — وأُطفئ التكاملُ بعد إخفاقين متتاليين (راجع: preview.sh integrate plan ثمّ integrate on)"
      warn "أُطفئ التكاملُ بعد إخفاقين متتاليين — تعود المعاينةُ إلى main وحدَه"
    fi
  fi
  sset last_error "$(now) $msg"
  if [ -n "$good" ] && [ "$good" != "$target" ] && git -C "$PREVIEW_DIR" cat-file -e "$good^{commit}" 2>/dev/null; then
    warn "سقط $label — أعود إلى آخر نسخةٍ سليمة ${good:0:7} كي لا تسقط المعاينة"
    LABEL="$(sget served_label)"; INTEG_REPORT="$(sget served_report)"; LABEL="${LABEL:-main@${good:0:7}}"
    run git -C "$PREVIEW_DIR" reset --hard "$good" --quiet
    prepare_db "$good"
    if deploy_main; then
      sset last_error "$(now) $msg فتُخدَم ${good:0:7}"
    else
      warn "وفشلت العودةُ أيضاً — الخادمُ متوقّف؛ راجع: docker logs ${PROJECT}-web-1"
    fi
  fi
  return 1
}

deploy_pin() {   # deploy_pin <شجرة> <دقائق>
  local tree="$1" mins="$2" db
  db="$(slug_db "$tree")"
  ensure_db "$tree"
  if [ "$DRY" != 1 ] && ! deps_drift "$tree" "$(current_image)" >/dev/null 2>&1; then
    warn "requirements في هذه الشجرة تخالف اعتماديّاتِ الصورة — إن ظهر ImportError فهذا سببُه (لا أبني صورةً لشجرة جلسة)"
  fi
  export_env dev "$tree" "$db"
  say "▸ يُحوَّل الخادمُ إلى $(basename "$tree")@$PREVIEW_SHA (تطوير، قاعدة $db) لمدّة $mins دقيقة"
  run compose "$tree" up -d --force-recreate --remove-orphans || warn "docker compose up أعاد خطأً"
  if ! wait_web; then
    sset last_error "$(now) الإقلاعُ سقط عند تثبيت $(basename "$tree")"
    return 1
  fi
  sset mode pin
  sset pin_tree "$tree"
  sset pin_until "$(( $(now) + mins * 60 ))"
  say "✔ http://localhost:$PORT يعرض شجرةَ $(basename "$tree") — تعديلاتُها الحيّةُ تظهر؛ وتعود المعاينةُ إلى main بعد $mins دقيقة أو بـ: release"
}

release_locked() {
  guard_tree
  fetch_ref
  resolve_target
  apply_main "$TARGET"
}

# ── الأوامر ─────────────────────────────────────────────────────
cmd_up() {
  local lan=0; [ "${1:-}" = "--lan" ] && lan=1
  ensure_tree
  acquire_lock || die "عمليّةٌ أخرى تعمل الآن على المعاينة"
  sset lan "$lan"
  release_locked
  if [ "$lan" = 1 ]; then
    warn "مفتوحٌ لشبكة الجهاز (0.0.0.0) — كلُّ من على الشبكة يصله ببيانات المعاينة. أعِد up بلا --lan لإغلاقه."
  fi
  say "لتتبّع main وما أودعته الجلساتُ تلقائياً: bash scripts/preview.sh watch"
}

cmd_sync() {
  local force=0; [ "${1:-}" = "--now" ] && force=1
  [ -e "$PREVIEW_DIR/.git" ] || die "لا شجرةَ معاينةٍ بعدُ — شغّل: bash scripts/preview.sh up"
  acquire_lock || { idle "عمليّةٌ أخرى تعمل الآن — أتخطّى هذه الدورة"; return 0; }

  if [ "$(sget mode)" = "pin" ]; then
    local until_ts left; until_ts="$(sget pin_until)"; left=$(( ${until_ts:-0} - $(now) ))
    if [ "$force" = 0 ] && [ "$left" -gt 0 ]; then
      idle "مثبَّتةٌ على $(basename "$(sget pin_tree)") — تعود إلى main بعد $(( left / 60 + 1 )) دقيقة"
      return 0
    fi
    say "▸ انتهى التثبيتُ أو طُلب التحديث — عودةٌ إلى main"
    release_locked
    return
  fi

  guard_tree
  fetch_ref
  local new served ts since first age waited
  resolve_target
  new="$TARGET"
  served="$(sget served_sha)"
  ts="$(now)"

  if same_content "$new" "$served"; then
    if [ "$(docker inspect -f '{{.State.Running}}' "${PROJECT}-web-1" 2>/dev/null || echo false)" = "true" ]; then
      idle "على $LABEL — لا جديد"
      return 0
    fi
    say "▸ الخادمُ متوقّف والمعروضُ لم يتغيّر — يُعاد إنشاؤه"
    deploy_main
    return
  fi

  if [ "$force" = 0 ] && [ "$(sget failed_sha)" = "$new" ]; then
    idle "$LABEL سقط تطبيقُه سابقاً — أنتظر تغيّراً (أو: sync --now)"
    return 0
  fi

  # المعروضُ تغيّر (main، أو ما أودعته الجلسات): يُنتظر سكونُه (الدمجُ دفعات)، بسقفٍ كي لا يجوع التحديث.
  if [ "$(sget pending_sha)" != "$new" ]; then
    sset pending_sha "$new"; sset pending_since "$ts"
    [ -n "$(sget wait_since)" ] || sset wait_since "$ts"
  fi
  since="$(sget pending_since)"; first="$(sget wait_since)"
  age=$(( ts - ${since:-$ts} )); waited=$(( ts - ${first:-$ts} ))
  if [ "$force" = 1 ] || [ "$age" -ge "$QUIET" ] || [ "$waited" -ge "$MAX_WAIT" ]; then
    say "▸ $LABEL — يُطبَّق"
    apply_main "$new"
  else
    idle "المعروضُ تغيّر إلى $LABEL — يُنتظر سكونُه ($age/$QUIET ثانية، والسقف $waited/$MAX_WAIT)"
  fi
}

cmd_watch() {
  say "مراقبةُ main وما أودعته الجلساتُ كلّ ${INTERVAL} ثانية — Ctrl+C يوقف المراقبةَ ويبقى الخادمُ"
  while :; do
    PREVIEW_QUIET_OUTPUT=1 bash "${BASH_SOURCE[0]}" sync || warn "دورةٌ فاشلة — تُعاد بعد $INTERVAL ثانية"
    sleep "$INTERVAL"
  done
}

cmd_pin() {
  local target="" mins="$PIN_MINUTES" force=0 arg tree registered
  for arg in "$@"; do
    case "$arg" in
      --force) force=1 ;;
      '' | *[!0-9]*) if [ -z "$target" ]; then target="$arg"; else die "وسيطٌ غيرُ مفهوم: $arg"; fi ;;
      *) mins="$arg" ;;
    esac
  done
  [ -n "$target" ] || die "الاستعمال: preview.sh pin <اسمُ مجلّد الشجرة> [دقائق] [--force] — الأسماءُ في: preview.sh list"
  case "$target" in */* | *\\*) tree="$target" ;; *) tree="$WORKTREES/$target" ;; esac
  [ -f "$tree/manage.py" ] || die "لا شجرةَ عملٍ بهذا الاسم: $target"
  [ "$(basename "$tree")" != "main-preview" ] || die "هذه شجرةُ المعاينة نفسُها — استعمل release"
  registered="$(git -C "$SELF_ROOT" worktree list --porcelain)"
  grep -qxF "worktree $tree" <<<"$registered" || die "$tree ليست شجرةَ عملٍ مسجَّلةً في هذا المستودع"
  [ -e "$PREVIEW_DIR/.git" ] || die "لا شجرةَ معاينةٍ بعدُ — شغّل: bash scripts/preview.sh up"
  acquire_lock || die "عمليّةٌ أخرى تعمل الآن على المعاينة"
  # لا تُنتزَع معاينةُ غيرك: المالكُ قد يكون في منتصف مراجعتها.
  if [ "$force" = 0 ] && [ "$(sget mode)" = "pin" ] && [ "$(sget pin_tree)" != "$tree" ]; then
    local until_ts left; until_ts="$(sget pin_until)"; left=$(( ${until_ts:-0} - $(now) ))
    if [ "$left" -gt 0 ]; then
      die "مثبَّتةٌ الآن على $(basename "$(sget pin_tree)") لمدّة $(( left / 60 + 1 )) دقيقة — لا أنتزعها. انتظر، أو release بإذن المالك، أو أضف --force"
    fi
  fi
  deploy_pin "$tree" "$mins"
}

cmd_release() {
  [ -e "$PREVIEW_DIR/.git" ] || die "لا شجرةَ معاينةٍ بعدُ"
  acquire_lock || die "عمليّةٌ أخرى تعمل الآن على المعاينة"
  release_locked
}

cmd_list() {
  git -C "$SELF_ROOT" worktree list | while read -r path sha branch; do
    [ "$(basename "$path")" = "main-preview" ] && continue
    printf '%-38s %-9s %s\n' "$(basename "$path")" "$sha" "$branch"
  done
}

integrate_text() {
  local ex; ex="$(sget integ_exclude)"
  if [ "$(integrate_flag)" = 1 ]; then printf 'مفعَّل'; else printf 'مُطفأ'; fi
  if [ -n "$ex" ]; then printf ' — مستثنى: %s' "$ex"; fi
}

integ_exclusion() {   # integ_exclusion add|remove <اسمُ مجلّد الشجرة>
  local op="$1" name="$2" new="" n
  [ -n "$name" ] || die "اسمُ مجلّد الشجرة مطلوب — الأسماءُ في: preview.sh list"
  case "$name" in */* | *\\* | *' '*) die "اسمُ مجلّدٍ لا مسارٌ: $name" ;; esac
  for n in $(sget integ_exclude); do
    if [ "$n" != "$name" ]; then new+="$n "; fi
  done
  if [ "$op" = add ]; then new+="$name "; fi
  sset integ_exclude "${new% }"
  say "✔ المستثنَون من التكامل: ${new% }${new:+ (يسري في الدورة القادمة)}"
}

integ_show() {   # ما يدخل التكاملَ الآن — قراءةٌ فقط (لا يطبّق شيئاً)
  git -C "$PREVIEW_DIR" fetch origin main --quiet 2>/dev/null || warn "تعذّر جلبُ main (بلا شبكة؟)"
  MAIN_SHA="$(git -C "$PREVIEW_DIR" rev-parse origin/main)"
  plan_integration "$MAIN_SHA"; target_label
  say "التكامل:      $(integrate_text)"
  say "الخطّة:       $LABEL"
  if [ -n "$INTEG_REPORT" ]; then printf '%s' "$INTEG_REPORT" | sed 's/^/    /'; else say "    (لا فرعَ مودَعاً لم يُدمج)"; fi
}

cmd_integrate() {
  local sub="${1:-plan}"; shift || true
  [ -e "$PREVIEW_DIR/.git" ] || die "لا شجرةَ معاينةٍ بعدُ — شغّل: bash scripts/preview.sh up"
  case "$sub" in
    plan)    integ_show ;;
    on)      sset integrate 1; sdel integ_failures; say "✔ التكاملُ مفعَّل — يُطبَّق في الدورة القادمة (أو: sync --now)" ;;
    off)     sset integrate 0; say "✔ التكاملُ مُطفأ — تعود المعاينةُ إلى main وحدَه في الدورة القادمة (أو: sync --now)" ;;
    exclude) integ_exclusion add "${1:-}" ;;
    include) integ_exclusion remove "${1:-}" ;;
    *)       die "الاستعمال: preview.sh integrate [plan|on|off|exclude <شجرة>|include <شجرة>]" ;;
  esac
}

cmd_status() {
  [ -e "$PREVIEW_DIR/.git" ] || { say "لا معاينةَ بعدُ — شغّل: bash scripts/preview.sh up"; return 0; }
  git -C "$PREVIEW_DIR" fetch origin main --quiet 2>/dev/null || warn "تعذّر جلبُ main (بلا شبكة؟)"
  local mode main prod running serving n pin_note="" label report served plan_report skipped gen
  mode="$(sget mode)"
  main="$(git -C "$PREVIEW_DIR" rev-parse --short=7 origin/main)"
  [ "$REF" = "origin/main" ] || say "تتبع المعاينةُ الآن $REF لا main (PREVIEW_REF) — لتجربة شيفرةٍ لم تُدمج"
  prod="$(curl -s -m 8 "$PROD_URL/health/" | sed -n 's/.*"commit": *"\([0-9a-f]*\)".*/\1/p' || true)"
  running="$(docker inspect -f '{{.State.Status}} ({{.State.Health.Status}})' "${PROJECT}-web-1" 2>/dev/null || echo 'غيرُ موجود')"
  serving="$(served_commit)"
  if [ "$mode" = pin ]; then
    pin_note=" — $(basename "$(sget pin_tree)") (يعود إلى main بعد $(( ($(sget pin_until) - $(now)) / 60 + 1 )) دقيقة)"
  fi

  say "الوضع:        ${mode:-—}$pin_note"
  say "الخادم:       $running — http://localhost:$PORT — يعلن commit=${serving:-?}"
  if [ "$mode" != pin ]; then
    label="$(sget served_label)"; report="$(sget served_report)"
    say "المعروض:      ${label:-main@${main}}"
    printf '%s' "$report" | { grep '^+' || true; } | sed 's/^/    /'   # ما ضُمّ وقتَ التطبيق
    say "التكامل:      $(integrate_text)"
    plan_report="$report"
    if integrate_active; then   # الخطّةُ الآن: ما تغيّر بعد آخر تحديث (المنتظَر) وما يُتخطّى
      served="$(sget served_sha)"
      resolve_target
      plan_report="$INTEG_REPORT"
      if ! same_content "$TARGET" "$served"; then
        say "المنتظَر:      $LABEL — يُطبَّق بعد سكونٍ ${QUIET} ثانية"
        printf '%s' "$INTEG_REPORT" | { grep '^+' || true; } | sed 's/^/    /'
      fi
    fi
    skipped="$(printf '%s' "$plan_report" | { grep '^✗' || true; })"
    if [ -n "$skipped" ]; then say "متخطَّى:"; printf '%s\n' "$skipped" | sed 's/^/    /'; fi
  fi
  say "main:         $main"
  say "الإنتاج:       ${prod:-تعذّرت القراءة}"
  if [ -n "$prod" ] && git -C "$PREVIEW_DIR" cat-file -e "$prod^{commit}" 2>/dev/null; then
    n="$(git -C "$PREVIEW_DIR" rev-list --count "$prod..origin/main")"
    if [ "$n" = 0 ]; then
      say "المقارنة:     main هو الإنتاجُ نفسُه — لا شيءَ معلَّقٌ للنشر"
    else
      say "المقارنة:     main متقدّمٌ على الإنتاج بـ$n إيداعاً (تنتظر الترقية):"
      git -C "$PREVIEW_DIR" log --oneline --no-decorate "$prod..origin/main" | head -30 | sed 's/^/    /'
    fi
  fi
  local err err_ts
  err="$(sget last_error)"
  if [ -n "$err" ]; then
    err_ts="${err%% *}"   # الحالةُ تُخزَّن «<وقت> <نصّ>»؛ يُعرض الوقتُ مقروءاً
    warn "آخرُ خطأ ($(date -d "@$err_ts" '+%Y-%m-%d %H:%M' 2>/dev/null || echo "$err_ts")): ${err#* } — راجع: docker logs ${PROJECT}-web-1"
  fi
  err="$(sget db_note)"
  if [ -n "$err" ]; then
    gen="$(sget db_gen)"; err_ts="${err%% *}"
    say "القاعدة:      الجيل ${gen:-0} — آخرُ إعادة إنشاءٍ ($(date -d "@$err_ts" '+%Y-%m-%d %H:%M' 2>/dev/null || echo "$err_ts")): ${err#* }"
  fi
}

cmd_down() {
  [ -e "$PREVIEW_DIR/.git" ] || die "لا شجرةَ معاينة"
  export PREVIEW_DB=unused PREVIEW_ENV_FILE="$PREVIEW_DIR/.env"
  run compose "$PREVIEW_DIR" down --remove-orphans
  sset mode stopped
  say "أُوقفت المعاينة (الشجرةُ والقاعدةُ باقيتان — up يعيدها)"
}

# يطبع رأسَ الملفّ (بين الشريطين الأخيرين) — الأوامرُ وسببُ التصميم.
usage() { awk '/^# ═/ { n++ } NR >= 3 { print } n == 3 { exit }' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

main() {
  local cmd="${1:-help}"; shift || true
  case "$cmd" in
    up)        cmd_up "$@" ;;
    sync)      cmd_sync "$@" ;;
    watch)     cmd_watch ;;
    pin)       cmd_pin "$@" ;;
    release)   cmd_release ;;
    integrate) cmd_integrate "$@" ;;
    list)      cmd_list ;;
    status)    cmd_status ;;
    down)      cmd_down ;;
    *)         usage ;;
  esac
}

# يُنفَّذ حين يُستدعى الملفُّ لا حين يُستورد بـsource (tests/test_preview_integration.py تستدعي دوالَّه).
if [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; exit $?; fi
