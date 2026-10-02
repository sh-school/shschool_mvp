#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════
# ship.sh — شحنٌ بأمرٍ واحد بعد اعتماد المالك على 8500 (W-20260929-015)
# ════════════════════════════════════════════════════════════════════════
# لا يمنح هذا السكربتُ الاعتماد ولا يعرضه على المالك — الاعتمادُ يصلك صراحةً
# في محادثتك أو عبر المايسترو/0501 قبل تشغيله (schoolos-flow، القسم «القواعد»).
# وظيفتُه أن يُنفّذ الخطواتِ الميكانيكيّةَ الثلاث بعد ذلك بأمرٍ واحد، وينتهي عندها:
#   1) تحقّقٌ من نظافة الشجرة وأنّها محدَّثةٌ عن main (لا تحتاج rebase).
#   2) دفعٌ إلى claude/<اسم-المهمّة>.
#   3) فتحُ طلب دمجٍ بوصفٍ يتضمّن سطرَ الاعتماد الحرفيّ، وطباعةُ عقد التسليم
#      إلى «0601 · النشر على الإنتاج والدمج».
#
# **الدمجُ والنشرُ من اختصاص 0601 وحده** (أمرُ المالك، نصُّ الفلو). فهذا
# السكربتُ لا يستدعي auto_merge_gate.py ولا يفعّل auto-merge بنفسه — تلك أداةُ
# 0601 وحدَها: هي من تشغّلها وتقرّر بها بعد استلام الطلب.
#
# الاستعمال:
#   scripts/ship.sh <اسم-المهمّة> <تاريخ-الاعتماد YYYY-MM-DD> [عنوان الطلب]
#
# مثال:
#   scripts/ship.sh w015-ship-script 2026-09-29 "W-015: سكربت شحن بأمر واحد"
# ════════════════════════════════════════════════════════════════════════

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

fail() { echo -e "${RED}[فشل]${NC} $1" >&2; exit 1; }
info() { echo -e "${GREEN}[..]${NC} $1"; }
warn() { echo -e "${YELLOW}[تنبيه]${NC} $1"; }

if [ $# -lt 2 ]; then
    fail "الاستعمال: ship.sh <اسم-المهمّة> <تاريخ-الاعتماد YYYY-MM-DD> [عنوان الطلب]"
fi

TASK_NAME="$1"
APPROVED_DATE="$2"
PR_TITLE="${3:-$TASK_NAME}"

if ! [[ "$APPROVED_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    fail "تاريخُ الاعتماد يجب أن يكون بصيغة YYYY-MM-DD، وصلني: '$APPROVED_DATE'"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

command -v gh >/dev/null 2>&1 || fail "أداة gh غيرُ مثبَّتة"

# ── 1. النظافةُ والتحديث ────────────────────────────────────────────────
info "التحقّقُ من نظافة الشجرة..."
if [ -n "$(git status --porcelain)" ]; then
    fail "الشجرةُ ليست نظيفة — أودِع أو راجع git status قبل الشحن"
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
info "الفرعُ الحاليّ: $BRANCH"

info "جلبُ main..."
git fetch origin main --quiet

if ! git merge-base --is-ancestor origin/main HEAD; then
    fail "الفرعُ ليس محدَّثاً عن origin/main — ادمج/أعِد الأساسَ أوّلاً (لا rebase تلقائيّ هنا: القرارُ يدويّ)"
fi
info "الفرعُ محدَّثٌ عن main."

# ── 2. الدفعُ ────────────────────────────────────────────────────────────
REMOTE_REF="refs/heads/claude/${TASK_NAME}"
info "الدفعُ إلى claude/${TASK_NAME}..."
git push origin "HEAD:${REMOTE_REF}"

# ── 3. فتحُ طلب الدمج بسطر الاعتماد ──────────────────────────────────────
APPROVAL_LINE="اعتُمد من المالك على 8500 — ${APPROVED_DATE}"
BODY_FILE="$(mktemp)"
trap 'rm -f "$BODY_FILE"' EXIT

{
    echo "## الملخّص"
    git log origin/main..HEAD --format='- %s' 2>/dev/null || true
    echo ""
    echo "$APPROVAL_LINE"
    echo ""
    echo "🤖 Generated with [Claude Code](https://claude.com/claude-code)"
} > "$BODY_FILE"

info "فتحُ طلب الدمج..."
PR_URL="$(gh pr create \
    --title "$PR_TITLE" \
    --body-file "$BODY_FILE" \
    --base main \
    --head "claude/${TASK_NAME}")"
echo "$PR_URL"

PR_NUMBER="$(basename "$PR_URL")"
info "الطلبُ #${PR_NUMBER} مفتوح."

# ── 4. عقدُ التسليم إلى 0601 (الدمجُ والنشرُ من اختصاصها وحدَها) ───────────
HEAD_SHA="$(git rev-parse HEAD)"
MIGRATIONS="$(git diff --name-only origin/main..HEAD -- '*/migrations/*' | wc -l | tr -d ' ')"
if [ "$MIGRATIONS" != "0" ]; then
    MIGRATION_NOTE="$(git diff --name-only origin/main..HEAD -- '*/migrations/*')"
else
    MIGRATION_NOTE="لا هجرة"
fi

cat <<EOF

────────────────────────────────────────────────────────────────
عقدُ التسليم إلى «0601 · النشر على الإنتاج والدمج»:
  رقمُ الطلب: #${PR_NUMBER}
  الرأس: ${HEAD_SHA}
  حالةُ الفحوص: راجع CI على الطلب (لم يُقَس محلّيّاً هنا)
  الهجرة: ${MIGRATION_NOTE}
  سطرُ الاعتماد في الوصف: ${APPROVAL_LINE}
  مصدرُ الاعتماد: راجع محادثة الشحن/0501
────────────────────────────────────────────────────────────────
EOF

info "انتهى الشحنُ عند هذه النقطة — لا تفعيلَ لدمجٍ آليٍّ من هنا. حوِّل الطلبَ إلى «0601 · النشر على الإنتاج والدمج» بالعقد أعلاه؛ هي من تشغّل auto_merge_gate.py وتقرّر النشر."
