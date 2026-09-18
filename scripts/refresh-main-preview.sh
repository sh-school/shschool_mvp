#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  تحديثُ معاينة main المحليّة (2026-09-18)
# ══════════════════════════════════════════════════════════════
#  شجرةُ `.claude/worktrees/main-preview` مثبَّتةٌ دائماً على رأس `main` —
#  لا فرعَ عملٍ فيها أبداً، ولا تُعدَّل يدويّاً. هذا السكربتُ يسحب أحدثَ
#  دمجٍ ويطبّق هجراته، فيراها صاحبُ القرار على http://localhost:8500
#  **قبل** أن يُنشَر أيُّ شيءٍ على الإنتاج (النشرُ التلقائيُّ مقطوعٌ منذ
#  2026-09-18 — railway service redeploy --from-source هو البابُ الوحيد
#  للإنتاج الآن).
#
#  يُشغَّل بعد كلّ دمجٍ إلى main:
#      bash scripts/refresh-main-preview.sh
# ══════════════════════════════════════════════════════════════
set -euo pipefail

PREVIEW_DIR="D:/shschool_mvp/.claude/worktrees/main-preview"
cd "$PREVIEW_DIR"
git fetch origin main --quiet
git reset --hard origin/main --quiet
echo "main-preview الآن على $(git rev-parse --short HEAD) — $(git log -1 --format=%s)"

docker compose -p schoolos-main-preview --project-directory . \
  -f D:/shschool_mvp/docker-compose.session.yml exec -T web \
  python manage.py migrate --noinput

echo "جاهزةٌ على http://localhost:8500"
