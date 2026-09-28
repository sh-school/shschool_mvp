#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  preview_check.sh — ماذا يعرض 8500 الآن فعلاً؟ وهل فيه إيداعٌ أو شجرةٌ بعينها؟
# ══════════════════════════════════════════════════════════════
#  قراءةٌ خالصة: لا git fetch، ولا كتابةٌ في ملفّات الحالة، ولا docker غيرُ inspect، ولا اتّصالٌ
#  إلّا بـ/health/ على الحلقة المحلّيّة. (أمّا `preview.sh status` فيجلب main ويكتب مخبأ التكامل
#  ويسأل الإنتاج — وهذا لا يفعل شيئاً من ذلك.)
#
#  لِمَ؟ سطرُ «المعروض» في `preview.sh status` قد يكون قديماً (رُصد 2026-09-28: الوسم «تكامل@…»
#  والخادمُ يخدم main وحدَه). والحَكَمُ ثلاثة: commit في /health/، ورأسُ شجرة main-preview،
#  وserved_sha في ملفّات الحالة — ومع التثبيت: رأسُ الشجرة المثبَّتة وتعديلاتُها غيرُ المودَعة.
#
#  الاستعمال:
#    bash preview_check.sh                   الحالةُ واتّساقُها
#    bash preview_check.sh --tree <مجلّد|مسار>  هل عملُ هذه الشجرة معروض؟ ولِمَ لا؟
#    bash preview_check.sh --sha <إيداع>       هل هذا الإيداعُ داخلٌ فيما يُعرض؟
#
#  رمزُ الخروج: 0 معروضٌ/متّسق · 1 غيرُ معروض · 2 حالةٌ غيرُ متّسقة أو مجهولة · 3 خطأُ استعمال.
#  متغيّراتٌ للاختبار فقط: PREVIEW_STATE_DIR، PREVIEW_HEALTH_URL، PREVIEW_WEB_CONTAINER، PREVIEW_NOW.
# ══════════════════════════════════════════════════════════════
set -uo pipefail

ROOT="${SCHOOLOS_ROOT:-D:/shschool_mvp}"
WORKTREES="$ROOT/.claude/worktrees"
PREVIEW_DIR="${PREVIEW_DIR:-$WORKTREES/main-preview}"
PORT="${PREVIEW_PORT:-8500}"
HEALTH_URL="${PREVIEW_HEALTH_URL:-http://127.0.0.1:$PORT/health/}"
WEB_CONTAINER="${PREVIEW_WEB_CONTAINER:-schoolos-main-preview-web-1}"
NOW="${PREVIEW_NOW:-$(date +%s)}"

say()  { printf '%s\n' "$*"; }
warn() { printf '! %s\n' "$*"; }
usage() { sed -n '3,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

# ── الوسائط ────────────────────────────────────────────────────
want_sha=""; want_tree=""
while [ $# -gt 0 ]; do
  case "$1" in
    --sha)  want_sha="${2:-}"; shift 2 || { usage; exit 3; } ;;
    --tree) want_tree="${2:-}"; shift 2 || { usage; exit 3; } ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'وسيطٌ غيرُ مفهوم: %s\n' "$1" >&2; usage >&2; exit 3 ;;
  esac
done
if [ -n "$want_sha" ] && [ -n "$want_tree" ]; then
  say "اختر --sha أو --tree لا كليهما" >&2; exit 3
fi

[ -e "$PREVIEW_DIR/.git" ] || { say "لا شجرةَ معاينةٍ في $PREVIEW_DIR — المعاينةُ لم تُقلَع (up للمالك وجلسة النشر)"; exit 2; }

# ملفّاتُ الحالة داخل .git لشجرة المعاينة (كما يكتبها scripts/preview.sh)
STATE="${PREVIEW_STATE_DIR:-$(git -C "$PREVIEW_DIR" rev-parse --absolute-git-dir)/preview-state}"
sget() { if [ -f "$STATE/$1" ]; then cat "$STATE/$1"; fi; }
short() { printf '%s' "${1:0:7}"; }
norm()  { printf '%s' "${1//\\//}"; }   # مساراتُ ويندوز بشرطةٍ مائلةٍ أماميّة كما يطبعها git

# ── الهدف: يُتحقَّق منه قبل أيّ طباعة ─────────────────────────────
tree=""; name=""; sha=""; dirty=0
if [ -n "$want_tree" ]; then
  case "$want_tree" in */* | *\\*) tree="$(norm "$want_tree")" ;; *) tree="$WORKTREES/$want_tree" ;; esac
  name="$(basename "$tree")"
  git -C "$ROOT" worktree list --porcelain | grep -qxF "worktree $tree" \
    || { say "$tree ليست شجرةَ عملٍ مسجَّلة — الأسماءُ في: bash scripts/preview.sh list" >&2; exit 3; }
  want_sha="$(git -C "$tree" rev-parse HEAD)"
  dirty="$(git -C "$tree" status --porcelain --untracked-files=no | wc -l | tr -d ' ')"
fi
if [ -n "$want_sha" ]; then
  sha="$(git -C "$PREVIEW_DIR" rev-parse -q --verify "${want_sha}^{commit}" 2>/dev/null || true)"
  [ -n "$sha" ] || { say "الإيداع $want_sha غيرُ موجودٍ في المخزن المحلّيّ" >&2; exit 3; }
fi

# ── ما يُعرض ───────────────────────────────────────────────────
mode="$(sget mode)"; served="$(sget served_sha)"; label="$(sget served_label)"
synced="$(sget synced_at)"; pin_tree="$(norm "$(sget pin_tree)")"; pin_until="$(sget pin_until)"
head="$(git -C "$PREVIEW_DIR" rev-parse HEAD 2>/dev/null || true)"
health="$(curl -s -m 5 "$HEALTH_URL" 2>/dev/null | sed -n 's/.*"commit": *"\([0-9a-f]*\)".*/\1/p' || true)"
web="$(docker inspect -f '{{.State.Status}} ({{.State.Health.Status}})' "$WEB_CONTAINER" 2>/dev/null || echo 'غيرُ موجود/غيرُ مقروء')"

say "الخادم:        $web — /health/ يعلن commit=${health:-تعذّرت القراءة}"
consistent=1
[ -n "$health" ] || consistent=0

if [ "$mode" = "pin" ]; then
  left=$(( ${pin_until:-0} - NOW ))
  if [ "$left" -gt 0 ]; then
    say "الوضع:         pin — $(basename "$pin_tree") (يعود إلى main بعد $(( left / 60 + 1 )) دقيقة) — إعداداتُ التطوير لا الإنتاج"
  else
    say "الوضع:         pin — $(basename "$pin_tree") — انتهت مدّتُه منذ $(( -left / 60 )) دقيقة ولم يُحرَّر"
    warn "العودةُ إلى main يحرّكها sync (watch)؛ تثبيتٌ منتهٍ لم يُحرَّر يعني أنّ watch لا يعمل — release يعيده الآن"
    consistent=0
  fi
  pin_head="$(git -C "$pin_tree" rev-parse HEAD 2>/dev/null || true)"
  if [ -n "$pin_head" ] && [ -n "$health" ] && [ "$(short "$pin_head")" != "$health" ]; then
    warn "رأسُ الشجرة المثبَّتة الآن $(short "$pin_head") و/health/ يعلن $health: أُودع فيها بعد التثبيت (الملفّاتُ الحيّةُ هي المعروضة، والإعلانُ لحظةُ التثبيت)"
  fi
  pin_dirty="$(git -C "$pin_tree" status --porcelain --untracked-files=no 2>/dev/null | wc -l | tr -d ' ')"
  if [ "${pin_dirty:-0}" -gt 0 ]; then
    warn "في الشجرة المثبَّتة ${pin_dirty} ملفّاً معدَّلاً غيرَ مودَع — يراه المالك، وقد يتغيّر بعد اعتماده"
  fi
else
  say "الوضع:         ${mode:-—} — المعروض: $(short "$served") (رأسُ main-preview $(short "$head"))"
  if [ -n "$served" ] && [ "$(short "$served")" != "$health" ]; then
    warn "served_sha $(short "$served") لا يطابق /health/ ${health:-؟} — الخادمُ يُعاد إنشاؤه أو متوقّف"; consistent=0
  fi
  if [ -n "$served" ] && [ "$head" != "$served" ]; then
    warn "رأسُ main-preview لا يطابق served_sha — تطبيقٌ جارٍ أو سقط"; consistent=0
  fi
  lsha="$(printf '%s' "$label" | sed -n 's/^[^@]*@\([0-9a-f]\{7\}\).*/\1/p' | head -1)"
  # الوسمُ «تكامل@<مصنوع> (main@<رأس> …)» أو «main@<رأس>»: أوّلُ @ هو المعروض
  if [ -n "$lsha" ] && [ -n "$served" ] && [ "$lsha" != "$(short "$served")" ]; then
    warn "وسمُ «المعروض» في status قديم («$label») والمعروضُ فعلاً $(short "$served") — لا تنقل الوسمَ للمالك"
  fi
  if git -C "$PREVIEW_DIR" rev-parse -q --verify origin/main >/dev/null && [ -n "$served" ]; then
    behind="$(git -C "$PREVIEW_DIR" rev-list --count "$served..origin/main" 2>/dev/null || echo 0)"
    age=$(( (NOW - ${synced:-$NOW}) / 60 ))
    if [ "$behind" -gt 0 ]; then
      say "main (آخرُ جلبٍ محلّيّ) متقدّمٌ على المعروض بـ$behind إيداعاً؛ آخرُ تطبيقٍ قبل $age دقيقة"
      [ "$age" -le 20 ] || warn "أكثرُ من 20 دقيقةً بلا تطبيق وmain متقدّم: watch قد لا يعمل — أبلغ جلسةَ النشر (لا تشغّله بنفسك)"
    fi
  fi
fi

# ── الهدف: شجرةٌ أو إيداع ────────────────────────────────────────
[ -n "$sha" ] || { [ "$consistent" = 1 ] && exit 0 || exit 2; }
say "الهدف:         ${name:+$name @ }$(short "$sha")"

if [ "$mode" = "pin" ]; then
  if [ -n "$tree" ] && [ "$tree" = "$pin_tree" ]; then
    say "النتيجة:       معروض — الشجرةُ نفسُها مثبَّتة (ملفّاتُها الحيّةُ بإعدادات التطوير)"; exit 0
  fi
  if [ -z "$tree" ] && git -C "$pin_tree" merge-base --is-ancestor "$sha" HEAD 2>/dev/null; then
    say "النتيجة:       معروض — داخلٌ في رأس الشجرة المثبَّتة $(basename "$pin_tree")"; exit 0
  fi
  say "النتيجة:       غيرُ معروض — الخادمُ مثبَّتٌ على $(basename "$pin_tree")"; exit 1
fi

if [ -n "$served" ] && git -C "$PREVIEW_DIR" merge-base --is-ancestor "$sha" "$served" 2>/dev/null; then
  if git -C "$PREVIEW_DIR" merge-base --is-ancestor "$sha" origin/main 2>/dev/null; then
    say "النتيجة:       معروض — وهو في main أصلاً (لا جديدَ فيه للمعاينة)"
  else
    say "النتيجة:       معروض — مضمومٌ في التكامل"
  fi
  [ "${dirty:-0}" = 0 ] || warn "وفي الشجرة ${dirty} ملفّاً معدَّلاً غيرَ مودَع لا يراه التكامل"
  exit 0
fi
say "النتيجة:       غيرُ معروض"
if [ -n "$name" ]; then
  line="$(sget integ_report | grep -F -- " $name " | head -1)"
  case "$line" in
    "+"*) say "خطّةُ التكامل: داخلٌ في التطبيق القادم (بعد سكون 3 دقائق ودورة watch) — $line" ;;
    "✗"*) say "خطّةُ التكامل: يُتخطّى — $line" ;;
    *)    say "خطّةُ التكامل: لا ذكرَ له في آخر خطّةٍ مخزَّنة (أُودع بعدها؟ أو التكاملُ مُطفأ؟) — bash scripts/preview.sh integrate" ;;
  esac
  [ "${dirty:-0}" = 0 ] || warn "في الشجرة ${dirty} ملفّاً معدَّلاً غيرَ مودَع: التكاملُ لا يرى ما لم يُودَع"
fi
exit 1
