#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  خادمُ الجلسة بأمرٍ واحد — يجمع خطواتِ CLAUDE.md الثلاث:
#    ١. نسخُ .env من الجذر إن غاب  ٢. قاعدةُ الشجرة (session-db.sh)
#    ٣. تشغيلُ الخادم على أوّل منفذٍ حرٍّ من 8001
#
#      bash scripts/session-up.sh            # تشغيل (أو إظهار المنفذ إن كان يعمل)
#      bash scripts/session-up.sh --port 8005
#      bash scripts/session-up.sh --down     # إيقاف خادم هذه الشجرة
# ══════════════════════════════════════════════════════════════
set -euo pipefail

TREE="$(basename "$PWD")"
PROJECT="schoolos-${TREE}"
ROOT="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)"
COMPOSE_FILE="${COMPOSE_SESSION_FILE:-$ROOT/docker-compose.session.yml}"
compose() { docker compose -p "$PROJECT" --project-directory . -f "$COMPOSE_FILE" "$@"; }

if [ "${1:-}" = "--down" ]; then compose down; exit 0; fi

PORT=""
[ "${1:-}" = "--port" ] && PORT="${2:?--port يحتاج رقماً}"

[ -f .env ] || { cp "$ROOT/.env" .env && echo "نُسخ .env من $ROOT"; }

# يعمل سلفاً؟ اعرض منفذَه ولا تُنشئ ثانياً.
running=$(compose port web 8000 2>/dev/null | sed 's/.*://' || true)
if [ -n "$running" ]; then echo "يعمل سلفاً: http://localhost:$running"; exit 0; fi

bash scripts/session-db.sh

port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
if [ -z "$PORT" ]; then
  PORT=8001
  while port_busy "$PORT"; do PORT=$((PORT + 1)); done
fi

SESSION_DB="$(bash scripts/session-db.sh --name)" WEB_PORT="$PORT" compose up -d

for _ in $(seq 1 60); do
  if curl -fsS -o /dev/null "http://localhost:$PORT/health/" 2>/dev/null; then
    echo "جاهز: http://localhost:$PORT   (إيقاف: bash scripts/session-up.sh --down)"; exit 0
  fi
  sleep 1
done
echo "لم يستجب /health/ خلال 60ث — راجع: docker compose -p $PROJECT logs web" >&2
exit 1
