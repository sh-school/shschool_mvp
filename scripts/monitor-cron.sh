#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════
# monitor-cron.sh — SchoolOS Lightweight Health Monitor (cron)
# ════════════════════════════════════════════════════════════════════════
# Designed to run every 5 minutes via cron:
#   */5 * * * * /path/to/scripts/monitor-cron.sh
#
# Checks /health/ endpoint. If 3 consecutive failures, sends alert
# via webhook. Logs all results to /tmp/schoolos-monitor.log.
#
# Environment variables (or edit defaults below):
#   SCHOOLOS_URL        Production URL (default: Railway URL)
#   SCHOOLOS_WEBHOOK    Slack/Discord webhook for alerts
#   SCHOOLOS_LOG        Log file path (default: /tmp/schoolos-monitor.log)
#   SCHOOLOS_THRESHOLD  Consecutive failures before alert (default: 3)
# ════════════════════════════════════════════════════════════════════════

set -uo pipefail

# ── Configuration ───────────────────────────────────────────────────────
BASE_URL="${SCHOOLOS_URL:-https://shschoolmvp-production.up.railway.app}"
WEBHOOK_URL="${SCHOOLOS_WEBHOOK:-}"
LOG_FILE="${SCHOOLOS_LOG:-/tmp/schoolos-monitor.log}"
FAIL_THRESHOLD="${SCHOOLOS_THRESHOLD:-3}"
STATE_FILE="/tmp/schoolos-monitor-failures.count"
TIMEOUT=15

# Strip trailing slash
BASE_URL="${BASE_URL%/}"

HEALTH_URL="${BASE_URL}/health/"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# ── Ensure state file exists ────────────────────────────────────────────
if [ ! -f "$STATE_FILE" ]; then
    echo "0" > "$STATE_FILE"
fi

CONSECUTIVE_FAILURES=$(cat "$STATE_FILE" 2>/dev/null || echo "0")
# Ensure it is a number
if ! [[ "$CONSECUTIVE_FAILURES" =~ ^[0-9]+$ ]]; then
    CONSECUTIVE_FAILURES=0
fi

# ── Health check ────────────────────────────────────────────────────────
HTTP_CODE=$(curl -sS -o /dev/null -w "%{http_code}" \
    --max-time "$TIMEOUT" \
    "$HEALTH_URL" 2>/dev/null) || HTTP_CODE="000"

# ── Evaluate result ─────────────────────────────────────────────────────
if [ "$HTTP_CODE" = "200" ]; then
    # ── SUCCESS ─────────────────────────────────────────────────────
    echo "$TIMESTAMP  OK  $HEALTH_URL -> $HTTP_CODE" >> "$LOG_FILE"

    # If recovering from failures, send recovery notification
    if [ "$CONSECUTIVE_FAILURES" -ge "$FAIL_THRESHOLD" ] && [ -n "$WEBHOOK_URL" ]; then
        RECOVERY_PAYLOAD=$(cat <<ENDJSON
{
    "text": ":large_green_circle: *SchoolOS RECOVERED*\nEndpoint: ${HEALTH_URL}\nStatus: HTTP ${HTTP_CODE}\nTime: ${TIMESTAMP}\nWas down for: ${CONSECUTIVE_FAILURES} consecutive checks",
    "content": ":green_circle: **SchoolOS RECOVERED**\nEndpoint: ${HEALTH_URL}\nStatus: HTTP ${HTTP_CODE}\nTime: ${TIMESTAMP}\nWas down for: ${CONSECUTIVE_FAILURES} consecutive checks"
}
ENDJSON
)
        curl -sS -X POST \
            -H "Content-Type: application/json" \
            -d "$RECOVERY_PAYLOAD" \
            --max-time 10 \
            "$WEBHOOK_URL" >/dev/null 2>&1 || true

        echo "$TIMESTAMP  RECOVERY notification sent (was down for $CONSECUTIVE_FAILURES checks)" >> "$LOG_FILE"
    fi

    # Reset failure counter
    echo "0" > "$STATE_FILE"

else
    # ── FAILURE ─────────────────────────────────────────────────────
    CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))
    echo "$CONSECUTIVE_FAILURES" > "$STATE_FILE"

    echo "$TIMESTAMP  FAIL  $HEALTH_URL -> $HTTP_CODE  (consecutive: $CONSECUTIVE_FAILURES)" >> "$LOG_FILE"

    # Send alert only when hitting the threshold (not every time after)
    if [ "$CONSECUTIVE_FAILURES" -eq "$FAIL_THRESHOLD" ] && [ -n "$WEBHOOK_URL" ]; then
        ALERT_PAYLOAD=$(cat <<ENDJSON
{
    "text": ":red_circle: *SchoolOS DOWN*\nEndpoint: ${HEALTH_URL}\nStatus: HTTP ${HTTP_CODE}\nConsecutive failures: ${CONSECUTIVE_FAILURES}\nTime: ${TIMESTAMP}\nAction required: Check Railway dashboard and logs immediately.",
    "content": ":red_circle: **SchoolOS DOWN**\nEndpoint: ${HEALTH_URL}\nStatus: HTTP ${HTTP_CODE}\nConsecutive failures: ${CONSECUTIVE_FAILURES}\nTime: ${TIMESTAMP}\nAction required: Check Railway dashboard and logs immediately."
}
ENDJSON
)
        WEBHOOK_RESULT=$(curl -sS -o /dev/null -w "%{http_code}" \
            -X POST \
            -H "Content-Type: application/json" \
            -d "$ALERT_PAYLOAD" \
            --max-time 10 \
            "$WEBHOOK_URL" 2>/dev/null) || WEBHOOK_RESULT="000"

        echo "$TIMESTAMP  ALERT sent via webhook (HTTP $WEBHOOK_RESULT)" >> "$LOG_FILE"
    fi

    # Send escalation alert at 2x threshold (e.g., 6 failures = 30 min down)
    if [ "$CONSECUTIVE_FAILURES" -eq $((FAIL_THRESHOLD * 2)) ] && [ -n "$WEBHOOK_URL" ]; then
        ESCALATION_PAYLOAD=$(cat <<ENDJSON
{
    "text": ":rotating_light: *SchoolOS STILL DOWN — ESCALATION*\nEndpoint: ${HEALTH_URL}\nStatus: HTTP ${HTTP_CODE}\nConsecutive failures: ${CONSECUTIVE_FAILURES} (~$((CONSECUTIVE_FAILURES * 5)) minutes)\nTime: ${TIMESTAMP}\nThis is an escalation. The service has been down for an extended period.",
    "content": ":rotating_light: **SchoolOS STILL DOWN -- ESCALATION**\nEndpoint: ${HEALTH_URL}\nStatus: HTTP ${HTTP_CODE}\nConsecutive failures: ${CONSECUTIVE_FAILURES} (~$((CONSECUTIVE_FAILURES * 5)) minutes)\nTime: ${TIMESTAMP}\nThis is an escalation. The service has been down for an extended period."
}
ENDJSON
)
        curl -sS -X POST \
            -H "Content-Type: application/json" \
            -d "$ESCALATION_PAYLOAD" \
            --max-time 10 \
            "$WEBHOOK_URL" >/dev/null 2>&1 || true

        echo "$TIMESTAMP  ESCALATION alert sent ($CONSECUTIVE_FAILURES consecutive failures)" >> "$LOG_FILE"
    fi
fi

# ── Log rotation (keep last 2000 lines) ────────────────────────────────
if [ -f "$LOG_FILE" ]; then
    LINE_COUNT=$(wc -l < "$LOG_FILE")
    if [ "$LINE_COUNT" -gt 2000 ]; then
        tail -1000 "$LOG_FILE" > "${LOG_FILE}.tmp"
        mv "${LOG_FILE}.tmp" "$LOG_FILE"
    fi
fi
