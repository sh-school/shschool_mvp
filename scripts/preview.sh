#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  المعاينةُ المركزيّة — خادمٌ واحدٌ يعرض main بوضع الإنتاج ويتبعه وحدَه
# ══════════════════════════════════════════════════════════════
#  كان لكلّ جلسةٍ خادمُها لِيراها صاحبُ القرار، فاجتمعت خوادمُ مقيمةٌ أكثرُها خاملٌ على
#  جهازٍ ذاكرتُه 16 غيغا. فهنا خادمٌ واحد (`docker-compose.preview.yml`، منفذ 8500):
#
#    • الافتراضيّ (follow): شجرةُ `main-preview` المثبَّتة على رأس main، بإعدادات الإنتاج
#      (shschool.settings.preview) — يتبع main تلقائيّاً بعد أن يسكن بضعَ دقائق.
#    • التثبيتُ المؤقّت (pin): شجرةُ جلسةٍ بإعدادات التطوير لمعاينة عملٍ لم يصر طلبَ دمجٍ
#      بعدُ، ثمّ يعود إلى main وحدَه بعد مدّةٍ (120 دقيقةً افتراضاً) أو بـ`release`.
#
#  الأوامر (bash scripts/preview.sh <أمر>):
#    up [--lan]            أوّلَ مرّة: الشجرةُ والقاعدةُ ثمّ الإقلاع (متساوي الأثر). `--lan` يفتحه لشبكة
#                          الجهاز (لمعاينة الجوال)، وبلا `--lan` يعود إلى الحلقة المحلّيّة فقط.
#    sync [--now]          دورةٌ واحدة: إن تقدّم main وسكن طُبّق. `--now` بلا انتظار السكون.
#    watch                 حلقةٌ تستدعي sync كلّ دقيقة (تبقى في تبويب طرفيّةٍ أو مهمّةٍ مجدولة).
#    pin <شجرة> [دقائق]    حوّل الخادمَ إلى شجرة جلسة (اسمُ مجلّدها، انظر list). لا يُنتزع تثبيتُ غيرك
#                          ما دامت مدّتُه قائمة إلّا بـ`--force` (بإذن المالك).
#    release               ارجع إلى main الآن.
#    list                  الأشجارُ التي يمكن تثبيتُها.
#    status                ما يخدمه الخادمُ، ومقارنتُه بـmain وبالإنتاج (commit من /health/).
#    down                  أوقف الخادمَ والعامل (لا يحذف شيئاً).
#
#  قبل أن تصل هذه الشيفرةُ إلى main (إعداداتُ preview.py ليست فيه فلا يُقلع عليه) تُجرَّب على إيداعها:
#      PREVIEW_REF=<sha> bash scripts/preview.sh up        (أو PREVIEW_REF=origin/<فرع>)
#  وبعد دمجها: `up` بلا PREVIEW_REF من شجرة main-preview نفسِها.
#
#  لِمَ فحصٌ دوريّ لا خطّاف؟ طابورُ الدمج يدمج على GitHub بلا حدثٍ محلّيّ، والفحصُ يلتقط أيضاً
#  دمجاً يدويّاً وأيَّ تراجعٍ للإنتاج. ولِمَ السكون (3 دقائق)؟ الدمجُ يأتي دفعات (81 إيداعاً في
#  يومٍ)، فتحديثٌ لكلّ إيداعٍ هدرٌ؛ وله سقفُ انتظارٍ (15 دقيقة) كي لا يجوع التحديثُ. وإن سقط
#  تطبيقُ إيداعٍ (هجرةٌ مثلاً) عاد إلى آخر نسخةٍ سليمةٍ كي لا تسقط المعاينة، ولا يعيد المحاولةَ
#  على الإيداع نفسِه — وسقوطُه على بياناتٍ مزروعةٍ إنذارٌ مبكّرٌ بأنّ هجرةَ الإنتاج ستسقط.
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

say()  { printf '%s\n' "$*"; }
idle() { [ "${PREVIEW_QUIET_OUTPUT:-0}" = 1 ] || say "$*"; }
warn() { printf '! %s\n' "$*" >&2; }
die()  { printf '✗ %s\n' "$*" >&2; exit 1; }
now()  { date +%s; }
run()  { if [ "$DRY" = 1 ]; then printf '[dry] %s\n' "$*"; else "$@"; fi; }

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
ensure_db() {
  if [ "$DRY" = 1 ]; then say "[dry] قاعدةُ $(slug_db "$1") تُنشأ إن لم توجد"; return 0; fi
  (cd "$1" && bash "$SELF_ROOT/scripts/session-db.sh")
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

# ── النشرُ المحلّيّ: main (إنتاج) أو شجرةُ جلسة (تطوير) ─────────────
deploy_main() {
  local tree="$PREVIEW_DIR" db
  db="$(slug_db "$tree")"
  ensure_db "$tree"
  ensure_image "$tree"
  export_env prod "$tree" "$db"
  say "▸ يُعاد إنشاءُ الخادم والعامل على main@$PREVIEW_SHA (هجرة ← collectstatic ← daphne) — قاعدة $db"
  run compose "$tree" up -d --force-recreate --remove-orphans || warn "docker compose up أعاد خطأً"
  wait_web || return 1
  sset mode follow
  sset served_sha "$(git -C "$tree" rev-parse HEAD)"
  sset synced_at "$(now)"
  sdel pending_sha; sdel pending_since; sdel wait_since; sdel last_error; sdel pin_tree; sdel pin_until
  say "✔ main@$PREVIEW_SHA على http://localhost:$PORT — يعلن /health/: commit=$(served_commit)"
}

# يطبّق إيداعاً على شجرة المعاينة؛ وإن سقط عاد إلى آخر نسخةٍ سليمةٍ ولا يكرّر المحاولةَ عليه.
apply_main() {   # apply_main <sha>
  local target="$1" good before; good="$(sget served_sha)"
  guard_tree
  before="$(git -C "$PREVIEW_DIR" rev-parse HEAD)"
  run git -C "$PREVIEW_DIR" reset --hard "$target" --quiet
  if [ -n "$(git -C "$PREVIEW_DIR" diff --name-only "$before" "$target" -- Dockerfile)" ]; then
    warn "Dockerfile تغيّر في main (مكتباتُ النظام) — الصورةُ الأصل قد تحتاج: docker compose build web (في الجذر)"
  fi
  if deploy_main; then sdel failed_sha; return 0; fi
  sset failed_sha "$target"
  sset last_error "$(now) main@${target:0:7} لم يُقلع"
  if [ -n "$good" ] && [ "$good" != "$target" ]; then
    warn "سقط main@${target:0:7} — أعود إلى آخر نسخةٍ سليمة ${good:0:7} كي لا تسقط المعاينة"
    run git -C "$PREVIEW_DIR" reset --hard "$good" --quiet
    if deploy_main; then
      sset last_error "$(now) main@${target:0:7} لم يُقلع فتُخدَم ${good:0:7}"
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
  apply_main "$(git -C "$PREVIEW_DIR" rev-parse "$REF")"
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
  say "لتتبّع main تلقائياً: bash scripts/preview.sh watch"
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
  new="$(git -C "$PREVIEW_DIR" rev-parse "$REF")"
  served="$(sget served_sha)"
  ts="$(now)"

  if [ "$new" = "$served" ]; then
    if [ "$(docker inspect -f '{{.State.Running}}' "${PROJECT}-web-1" 2>/dev/null || echo false)" = "true" ]; then
      idle "على main@${new:0:7} — لا جديد"
      return 0
    fi
    say "▸ الخادمُ متوقّف وmain لم يتغيّر — يُعاد إنشاؤه"
    deploy_main
    return
  fi

  if [ "$force" = 0 ] && [ "$(sget failed_sha)" = "$new" ]; then
    idle "main@${new:0:7} سقط تطبيقُه سابقاً — أنتظر إيداعاً جديداً (أو: sync --now)"
    return 0
  fi

  # main تقدّم: يُنتظر سكونُه (الدمجُ دفعات)، بسقفٍ كي لا يجوع التحديث.
  if [ "$(sget pending_sha)" != "$new" ]; then
    sset pending_sha "$new"; sset pending_since "$ts"
    [ -n "$(sget wait_since)" ] || sset wait_since "$ts"
  fi
  since="$(sget pending_since)"; first="$(sget wait_since)"
  age=$(( ts - ${since:-$ts} )); waited=$(( ts - ${first:-$ts} ))
  if [ "$force" = 1 ] || [ "$age" -ge "$QUIET" ] || [ "$waited" -ge "$MAX_WAIT" ]; then
    say "▸ main@${new:0:7} — يُطبَّق"
    apply_main "$new"
  else
    idle "main تقدّم إلى ${new:0:7} — يُنتظر سكونُه ($age/$QUIET ثانية، والسقف $waited/$MAX_WAIT)"
  fi
}

cmd_watch() {
  say "مراقبةُ main كلّ ${INTERVAL} ثانية — Ctrl+C يوقف المراقبةَ ويبقى الخادمُ"
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

cmd_status() {
  [ -e "$PREVIEW_DIR/.git" ] || { say "لا معاينةَ بعدُ — شغّل: bash scripts/preview.sh up"; return 0; }
  git -C "$PREVIEW_DIR" fetch origin main --quiet 2>/dev/null || warn "تعذّر جلبُ main (بلا شبكة؟)"
  local mode main prod running serving n pin_note=""
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
  if [ -n "$(sget last_error)" ]; then warn "آخرُ خطأ: $(sget last_error) — راجع: docker logs ${PROJECT}-web-1"; fi
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
    up)      cmd_up "$@" ;;
    sync)    cmd_sync "$@" ;;
    watch)   cmd_watch ;;
    pin)     cmd_pin "$@" ;;
    release) cmd_release ;;
    list)    cmd_list ;;
    status)  cmd_status ;;
    down)    cmd_down ;;
    *)       usage ;;
  esac
}

main "$@"; exit $?
