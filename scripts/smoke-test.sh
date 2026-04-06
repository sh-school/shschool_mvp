#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════
# smoke-test.sh — SchoolOS Post-Deploy Smoke Test
# ════════════════════════════════════════════════════════════════════════
# Run this AFTER every Railway deploy to verify production health.
# Exit 0 = all green, Exit 1 = one or more checks failed.
#
# Usage:
#   ./scripts/smoke-test.sh [URL]
#   ./scripts/smoke-test.sh --webhook https://hooks.slack.com/services/XXX
#   ./scripts/smoke-test.sh https://custom-url.railway.app --webhook URL
# ════════════════════════════════════════════════════════════════════════

set -uo pipefail

# ── Colors ──────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ── Defaults ────────────────────────────────────────────────────────────
DEFAULT_URL="https://shschoolmvp-production.up.railway.app"
BASE_URL=""
WEBHOOK_URL=""
TIMEOUT=10

# ── Parse arguments ─────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --webhook)
            WEBHOOK_URL="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [PRODUCTION_URL] [--webhook WEBHOOK_URL] [--timeout SECONDS]"
            echo ""
            echo "  PRODUCTION_URL   Base URL to test (default: $DEFAULT_URL)"
            echo "  --webhook URL    POST results to Slack/Discord webhook"
            echo "  --timeout N      HTTP timeout in seconds (default: 10)"
            exit 0
            ;;
        -*)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
        *)
            BASE_URL="$1"
            shift
            ;;
    esac
done

BASE_URL="${BASE_URL:-$DEFAULT_URL}"
# Strip trailing slash
BASE_URL="${BASE_URL%/}"

# ── State tracking ──────────────────────────────────────────────────────
PASS_COUNT=0
FAIL_COUNT=0
RESULTS=()
DETAILS=()

pass_check() {
    PASS_COUNT=$((PASS_COUNT + 1))
    RESULTS+=("PASS: $1")
    echo -e "${GREEN}  PASS${NC}  $1"
}

fail_check() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    RESULTS+=("FAIL: $1")
    DETAILS+=("$1")
    echo -e "${RED}  FAIL${NC}  $1"
}

separator() {
    echo -e "${CYAN}────────────────────────────────────────────────────${NC}"
}

# ── HTTP helper ─────────────────────────────────────────────────────────
# http_test URL EXPECTED_CODE [BODY_CHECK]
# BODY_CHECK: optional string or "json" to validate JSON response
http_test() {
    local url="$1"
    local expected_code="$2"
    local body_check="${3:-}"
    local label="$4"

    local tmpfile
    tmpfile=$(mktemp)

    local http_code
    http_code=$(curl -sS -o "$tmpfile" -w "%{http_code}" \
        --max-time "$TIMEOUT" \
        --location \
        "$url" 2>/dev/null) || http_code="000"

    local body
    body=$(cat "$tmpfile" 2>/dev/null || echo "")
    rm -f "$tmpfile"

    # Check for multiple accepted codes (e.g., "200|302")
    local code_match=false
    IFS='|' read -ra CODES <<< "$expected_code"
    for code in "${CODES[@]}"; do
        if [ "$http_code" = "$code" ]; then
            code_match=true
            break
        fi
    done

    if ! $code_match; then
        fail_check "$label -> HTTP $http_code (expected $expected_code)"
        return 1
    fi

    # Body validation
    if [ "$body_check" = "json" ]; then
        if echo "$body" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null ||
           echo "$body" | python -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
            pass_check "$label -> HTTP $http_code + valid JSON"
        else
            fail_check "$label -> HTTP $http_code but invalid JSON body"
            return 1
        fi
    elif [ -n "$body_check" ]; then
        if echo "$body" | grep -qi "$body_check"; then
            pass_check "$label -> HTTP $http_code + body contains '$body_check'"
        else
            fail_check "$label -> HTTP $http_code but body missing '$body_check'"
            return 1
        fi
    else
        pass_check "$label -> HTTP $http_code"
    fi

    return 0
}

# ════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}${CYAN}SchoolOS Post-Deploy Smoke Test${NC}"
echo -e "${CYAN}$(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${CYAN}Target: ${BASE_URL}${NC}"
separator

# ── 1. Health endpoint ─────────────────────────────────────────────────
echo -e "\n${BOLD}[1/5] Health endpoint${NC}"
http_test "${BASE_URL}/health/" "200" "" "/health/"

# ── 2. Readiness endpoint ──────────────────────────────────────────────
echo -e "\n${BOLD}[2/5] Readiness endpoint${NC}"
http_test "${BASE_URL}/ready/" "200" "" "/ready/"

# ── 3. Status endpoint (JSON) ──────────────────────────────────────────
echo -e "\n${BOLD}[3/5] Status endpoint (JSON)${NC}"
http_test "${BASE_URL}/status/" "200" "json" "/status/"

# ── 4. Homepage / Login form ───────────────────────────────────────────
echo -e "\n${BOLD}[4/5] Homepage (login form)${NC}"
http_test "${BASE_URL}/" "200" "login" "/ (login form)"

# ── 5. Admin interface ─────────────────────────────────────────────────
echo -e "\n${BOLD}[5/5] Admin interface${NC}"
http_test "${BASE_URL}/admin/" "200|302" "" "/admin/"

# ════════════════════════════════════════════════════════════════════════
# Summary
# ════════════════════════════════════════════════════════════════════════
echo ""
separator
echo -e "${BOLD}SMOKE TEST SUMMARY${NC}"
separator
echo -e "  ${GREEN}Passed : $PASS_COUNT${NC}"
echo -e "  ${RED}Failed : $FAIL_COUNT${NC}"
separator

TOTAL=$((PASS_COUNT + FAIL_COUNT))

if [ "$FAIL_COUNT" -gt 0 ]; then
    STATUS_EMOJI=":red_circle:"
    STATUS_TEXT="RED -- $FAIL_COUNT/$TOTAL checks failed"
    echo ""
    echo -e "  ${RED}${BOLD}RED — $FAIL_COUNT check(s) failed. Investigate immediately.${NC}"
    echo ""
    echo -e "  ${RED}Failed checks:${NC}"
    for detail in "${DETAILS[@]}"; do
        echo -e "    ${RED}- $detail${NC}"
    done
    echo ""
else
    STATUS_EMOJI=":large_green_circle:"
    STATUS_TEXT="GREEN -- All $TOTAL checks passed"
    echo ""
    echo -e "  ${GREEN}${BOLD}GREEN — All checks passed. Deploy verified.${NC}"
    echo ""
fi

# ── Webhook notification ────────────────────────────────────────────────
if [ -n "$WEBHOOK_URL" ]; then
    echo -e "${CYAN}Sending results to webhook...${NC}"

    RESULTS_TEXT=""
    for r in "${RESULTS[@]}"; do
        RESULTS_TEXT="${RESULTS_TEXT}\n${r}"
    done

    # Build payload compatible with both Slack and Discord
    PAYLOAD=$(cat <<ENDJSON
{
    "text": "${STATUS_EMOJI} *SchoolOS Smoke Test* - ${STATUS_TEXT}\nTarget: ${BASE_URL}\nTime: $(date -u '+%Y-%m-%d %H:%M:%S UTC')\n\n${RESULTS_TEXT}",
    "content": "${STATUS_EMOJI} **SchoolOS Smoke Test** - ${STATUS_TEXT}\nTarget: ${BASE_URL}\nTime: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
}
ENDJSON
)

    WEBHOOK_RESPONSE=$(curl -sS -o /dev/null -w "%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD" \
        --max-time 10 \
        "$WEBHOOK_URL" 2>/dev/null) || WEBHOOK_RESPONSE="000"

    if [ "$WEBHOOK_RESPONSE" = "200" ] || [ "$WEBHOOK_RESPONSE" = "204" ]; then
        echo -e "${GREEN}  Webhook delivered (HTTP $WEBHOOK_RESPONSE)${NC}"
    else
        echo -e "${YELLOW}  Webhook failed (HTTP $WEBHOOK_RESPONSE)${NC}"
    fi
fi

# ── Exit code ───────────────────────────────────────────────────────────
if [ "$FAIL_COUNT" -gt 0 ]; then
    exit 1
else
    exit 0
fi
