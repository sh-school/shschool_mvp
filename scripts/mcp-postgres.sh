#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  خادمُ MCP لقاعدة الجلسة — قراءةٌ فقط، ومحلّيٌّ فقط.
#
#  يبني الاتصالَ من .env ومن اسم قاعدة هذه الشجرة (session-db.sh --name)،
#  فلا أسرارَ في .mcp.json المتتبَّع. ثلاثةُ أقفال:
#    ١. رفضُ أيّ مضيفٍ غير محلّيّ (قاعدةُ الإنتاج فيها بياناتُ طلبة — PDPPL).
#    ٢. PGOPTIONS يجعل كلَّ معاملةٍ للقراءة فقط على مستوى الاتصال.
#    ٣. الخادمُ نفسُه يُغلّف كلَّ استعلامٍ بمعاملةٍ للقراءة فقط.
# ══════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=".env"; [ -f "$ENV_FILE" ] || ENV_FILE="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)/.env"
get() { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r"' ; }

DB_USER="$(get DB_USER)"; DB_PASSWORD="$(get DB_PASSWORD)"
HOST="${MCP_PG_HOST:-127.0.0.1}"; PORT="${MCP_PG_PORT:-5433}"
case "$HOST" in 127.0.0.1|localhost) ;; *) echo "مرفوض: المضيفُ $HOST غيرُ محلّيّ" >&2; exit 1 ;; esac

DB="${MCP_PG_DB:-$(bash scripts/session-db.sh --name)}"
export PGOPTIONS="-c default_transaction_read_only=on -c statement_timeout=15000"
exec npx -y @modelcontextprotocol/server-postgres "postgresql://${DB_USER}:${DB_PASSWORD}@${HOST}:${PORT}/${DB}"
