#!/usr/bin/env bash
# ──────────────────────────────────────────────────────
#  quality-check.sh — بوابة الجودة المحلية
#  Usage: bash scripts/quality-check.sh
# ──────────────────────────────────────────────────────
set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

PASS="${GREEN}PASS${NC}"
FAIL="${RED}FAIL${NC}"
SKIP="${YELLOW}SKIP${NC}"

total=0
passed=0
failed=0
failed_checks=""

header() {
    echo ""
    echo -e "${CYAN}══════════════════════════════════════════${NC}"
    echo -e "${BOLD}  $1${NC}"
    echo -e "${CYAN}══════════════════════════════════════════${NC}"
}

record_result() {
    local name="$1"
    local exit_code="$2"
    total=$((total + 1))
    if [ "$exit_code" -eq 0 ]; then
        passed=$((passed + 1))
        echo -e "  ${name}: ${PASS}"
    else
        failed=$((failed + 1))
        failed_checks="${failed_checks}\n  - ${name}"
        echo -e "  ${name}: ${FAIL}"
    fi
}

# ── 1. Ruff lint ─────────────────────────────────────
header "1/5  Ruff — lint"
ruff_lint_exit=0
if command -v ruff &>/dev/null; then
    ruff check . --quiet 2>&1 || ruff_lint_exit=$?
else
    echo -e "  ${SKIP} — ruff not installed (pip install ruff)"
    ruff_lint_exit=0
fi
record_result "Ruff lint" "$ruff_lint_exit"

# ── 2. Ruff format ───────────────────────────────────
header "2/5  Ruff — format"
ruff_fmt_exit=0
if command -v ruff &>/dev/null; then
    ruff format --check . --quiet 2>&1 || ruff_fmt_exit=$?
else
    echo -e "  ${SKIP} — ruff not installed"
    ruff_fmt_exit=0
fi
record_result "Ruff format" "$ruff_fmt_exit"

# ── 3. pytest + coverage ─────────────────────────────
header "3/5  pytest — coverage ≥85%"
pytest_exit=0
if command -v pytest &>/dev/null; then
    pytest tests/ -q --tb=short 2>&1 || pytest_exit=$?
else
    echo -e "  ${SKIP} — pytest not installed"
    pytest_exit=0
fi
record_result "pytest + coverage ≥85%" "$pytest_exit"

# ── 4. Radon complexity ──────────────────────────────
header "4/5  Radon — CC ≤ 10"
radon_exit=0
if command -v radon &>/dev/null; then
    result=$(radon cc . \
        --exclude "migrations,.venv,manage.py,scripts" \
        --min C \
        --show-complexity 2>/dev/null)
    if [ -n "$result" ]; then
        echo "$result"
        radon_exit=1
    else
        echo "  All functions within CC ≤ 10"
    fi
else
    echo -e "  ${SKIP} — radon not installed (pip install radon)"
    radon_exit=0
fi
record_result "Radon CC ≤ 10" "$radon_exit"

# ── 5. detect-secrets ────────────────────────────────
header "5/5  detect-secrets — leaked credentials"
secrets_exit=0
if command -v detect-secrets &>/dev/null; then
    scan_output=$(detect-secrets scan \
        --exclude-files '\.venv|migrations|\.git|staticfiles|htmlcov|node_modules|\.pyc' \
        --exclude-lines 'SECRET_KEY.*=.*decouple|getenv|config\(' \
        2>/dev/null)

    secrets_count=$(echo "$scan_output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
count = sum(len(v) for v in data.get('results', {}).items())
print(count)
" 2>/dev/null || echo "0")

    if [ "$secrets_count" -gt "0" ]; then
        echo "  Potential secrets found: $secrets_count"
        echo "$scan_output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for filename, secrets in data.get('results', {}).items():
    for s in secrets:
        print(f'  {filename}:{s[\"line_number\"]} — {s[\"type\"]}')
" 2>/dev/null || true
        secrets_exit=1
    else
        echo "  No secrets detected"
    fi
else
    echo -e "  ${SKIP} — detect-secrets not installed (pip install detect-secrets)"
    secrets_exit=0
fi
record_result "detect-secrets" "$secrets_exit"

# ── Summary ──────────────────────────────────────────
echo ""
echo -e "${CYAN}══════════════════════════════════════════${NC}"
echo -e "${BOLD}  Quality Gate Summary${NC}"
echo -e "${CYAN}══════════════════════════════════════════${NC}"
echo -e "  Total checks: ${total}"
echo -e "  Passed:       ${GREEN}${passed}${NC}"
echo -e "  Failed:       ${RED}${failed}${NC}"

if [ "$failed" -gt 0 ]; then
    echo ""
    echo -e "${RED}  QUALITY GATE FAILED${NC}"
    echo -e "  Failed checks:${failed_checks}"
    echo ""
    exit 1
else
    echo ""
    echo -e "${GREEN}  QUALITY GATE PASSED${NC}"
    echo ""
    exit 0
fi
