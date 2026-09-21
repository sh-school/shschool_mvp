#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  بدءُ الجلسة من شيفرة الإنتاج (2026-09-21)
# ══════════════════════════════════════════════════════════════
#  الغرض: كلُّ جلسةٍ جديدةٍ تبدأ من الإيداع المنشور فعلاً على الإنتاج
#  (`/health/` يعرضه)، لا من رأس `main` الذي قد يسبقه بطلباتٍ لم تُنشر
#  (النشرُ يدويٌّ بعد الدوام).
#
#  يُشغَّل من خطّاف SessionStart في `.claude/settings.json`. آمنٌ بالتصميم:
#    - لا يفعل شيئاً إن كانت الشجرةُ متّسخة، أو في الفرع إيداعاتٌ ليست في
#      origin/main (عملٌ حقيقيّ)، أو تعذّر قراءةُ الإنتاج.
#    - لا يبدّل فرعاً ولا يخبّئ ولا يدفع؛ يحرّك رأسَ الفرع الحاليّ وحدَه.
#    - يخرج دائماً بـ0 كي لا يُعطّل بدءَ الجلسة.
# ══════════════════════════════════════════════════════════════
set -uo pipefail

PROD_URL="${PRODUCTION_URL:-https://shschoolmvp-production.up.railway.app}"

say() { echo "[session-start-prod] $*"; }

git rev-parse --git-dir >/dev/null 2>&1 || exit 0

branch=$(git symbolic-ref --short -q HEAD || true)
[ -n "$branch" ] || { say "HEAD منفصل — تُرك كما هو"; exit 0; }
case "$branch" in main) say "فرعُ main — تُرك كما هو"; exit 0 ;; esac

if [ -n "$(git status --porcelain)" ]; then
  say "الشجرةُ متّسخة — تُرك كما هو"; exit 0
fi

prod=$(curl -fsS -m 10 "$PROD_URL/health/" 2>/dev/null \
  | sed -n 's/.*"commit": *"\([0-9a-f]\{7,40\}\)".*/\1/p')
[ -n "$prod" ] || { say "تعذّرت قراءةُ إيداع الإنتاج — تُرك كما هو"; exit 0; }

git fetch origin main --quiet 2>/dev/null || true
full=$(git rev-parse --verify -q "${prod}^{commit}" 2>/dev/null) \
  || { say "إيداع الإنتاج $prod غير موجودٍ محلّياً — تُرك كما هو"; exit 0; }

if [ "$(git rev-parse HEAD)" = "$full" ]; then
  say "الجلسةُ على إيداع الإنتاج $prod أصلاً"; exit 0
fi

# لا عملَ فريداً في الفرع: رأسُه سلفٌ لـorigin/main
if ! git merge-base --is-ancestor HEAD origin/main 2>/dev/null; then
  say "في الفرع إيداعاتٌ ليست في main — تُرك كما هو"; exit 0
fi

# وإيداعُ الإنتاج نفسُه يجب أن يكون في تاريخ main
if ! git merge-base --is-ancestor "$full" origin/main 2>/dev/null; then
  say "إيداع الإنتاج ليس في تاريخ main — تُرك كما هو"; exit 0
fi

git reset --hard "$full" --quiet \
  && say "الجلسةُ الآن على إيداع الإنتاج $prod — $(git log -1 --format=%s)"
exit 0
