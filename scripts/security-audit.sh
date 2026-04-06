#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
# SchoolOS — Local Security Audit Script
# Works on Linux, macOS, and Windows (Git Bash / MSYS2)
# Usage: bash scripts/security-audit.sh
# ══════════════════════════════════════════════════════════════

set -euo pipefail

# ── Colors (safe for Git Bash) ────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

PASS=0
FAIL=0
WARN=0

# Find project root (where manage.py lives)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${CYAN}══════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  SchoolOS Security Audit — $(date '+%Y-%m-%d %H:%M')${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════${NC}"
echo ""

# ── 1. Bandit SAST Scan ──────────────────────────────────────
echo -e "${CYAN}[1/6] Bandit — Python SAST scan...${NC}"
if command -v bandit &>/dev/null; then
    if bandit -r . \
        -x .venv,migrations,tests,manage.py,scripts \
        --severity-level high \
        --confidence-level high \
        -f screen 2>&1; then
        echo -e "${GREEN}  PASS: No HIGH severity issues${NC}"
        ((PASS++))
    else
        echo -e "${RED}  FAIL: HIGH severity issues found${NC}"
        ((FAIL++))
    fi
else
    echo -e "${YELLOW}  SKIP: bandit not installed (pip install bandit)${NC}"
    ((WARN++))
fi
echo ""

# ── 2. pip-audit — CVE Scan ──────────────────────────────────
echo -e "${CYAN}[2/6] pip-audit — Known CVEs in dependencies...${NC}"
if command -v pip-audit &>/dev/null; then
    if pip-audit -r requirements.txt --desc --progress-spinner off 2>&1; then
        echo -e "${GREEN}  PASS: No known CVEs${NC}"
        ((PASS++))
    else
        echo -e "${RED}  FAIL: Known CVEs found in dependencies${NC}"
        ((FAIL++))
    fi
else
    echo -e "${YELLOW}  SKIP: pip-audit not installed (pip install pip-audit)${NC}"
    ((WARN++))
fi
echo ""

# ── 3. Django Deployment Check ────────────────────────────────
echo -e "${CYAN}[3/6] Django — manage.py check --deploy...${NC}"
if [ -f "manage.py" ]; then
    # Use production settings if available, otherwise testing
    SETTINGS="${DJANGO_SETTINGS_MODULE:-shschool.settings.testing}"
    if python manage.py check --deploy --settings="$SETTINGS" 2>&1; then
        echo -e "${GREEN}  PASS: Django deployment checks passed${NC}"
        ((PASS++))
    else
        echo -e "${YELLOW}  WARN: Django deployment check reported issues (review above)${NC}"
        ((WARN++))
    fi
else
    echo -e "${RED}  FAIL: manage.py not found — run from project root${NC}"
    ((FAIL++))
fi
echo ""

# ── 4. Hardcoded Secrets Check ────────────────────────────────
echo -e "${CYAN}[4/6] Checking for hardcoded secrets...${NC}"
SECRET_PATTERNS=(
    'password\s*=\s*["\x27][^"\x27]{4,}'
    'secret_key\s*=\s*["\x27][^"\x27]{4,}'
    'api_key\s*=\s*["\x27][^"\x27]{4,}'
    'token\s*=\s*["\x27][a-zA-Z0-9_\-]{20,}'
    'AWS_SECRET_ACCESS_KEY\s*=\s*["\x27][^"\x27]{4,}'
    'FERNET_KEY\s*=\s*["\x27][^"\x27]{10,}'
)
SECRET_FOUND=0
for pattern in "${SECRET_PATTERNS[@]}"; do
    # Search Python files, excluding safe locations
    MATCHES=$(grep -rniE "$pattern" \
        --include="*.py" \
        --exclude-dir=.venv \
        --exclude-dir=migrations \
        --exclude-dir=tests \
        --exclude-dir=node_modules \
        --exclude="settings/base.py" \
        --exclude="settings/testing.py" \
        --exclude="conftest.py" \
        . 2>/dev/null || true)
    # Filter out lines that use config() / os.environ / decouple (safe patterns)
    UNSAFE=$(echo "$MATCHES" | grep -vE '(config\(|os\.environ|decouple|default=|""|\x27\x27|#|example|placeholder|test|dummy|ci-test|dev-only)' || true)
    if [ -n "$UNSAFE" ]; then
        echo -e "${RED}  Potential hardcoded secret:${NC}"
        echo "$UNSAFE" | head -5
        SECRET_FOUND=1
    fi
done
if [ "$SECRET_FOUND" -eq 0 ]; then
    echo -e "${GREEN}  PASS: No hardcoded secrets detected${NC}"
    ((PASS++))
else
    echo -e "${RED}  FAIL: Potential hardcoded secrets found (review above)${NC}"
    ((FAIL++))
fi
echo ""

# ── 5. DEBUG=False in Production ──────────────────────────────
echo -e "${CYAN}[5/6] Checking DEBUG=False in production settings...${NC}"
PROD_SETTINGS="shschool/settings/production.py"
if [ -f "$PROD_SETTINGS" ]; then
    if grep -qE '^\s*DEBUG\s*=\s*False' "$PROD_SETTINGS"; then
        echo -e "${GREEN}  PASS: DEBUG=False in production.py${NC}"
        ((PASS++))
    else
        echo -e "${RED}  FAIL: DEBUG is not explicitly False in production.py${NC}"
        ((FAIL++))
    fi
else
    echo -e "${RED}  FAIL: production.py not found${NC}"
    ((FAIL++))
fi
echo ""

# ── 6. ALLOWED_HOSTS not * ────────────────────────────────────
echo -e "${CYAN}[6/6] Checking ALLOWED_HOSTS is not wildcard...${NC}"
if [ -f "$PROD_SETTINGS" ]; then
    if grep -qE "ALLOWED_HOSTS\s*=\s*\['\*'\]" "$PROD_SETTINGS" || \
       grep -qE 'ALLOWED_HOSTS\s*=\s*\["\*"\]' "$PROD_SETTINGS" || \
       grep -qE "default=['\"]?\*['\"]?" "$PROD_SETTINGS"; then
        echo -e "${RED}  FAIL: ALLOWED_HOSTS contains wildcard * in production${NC}"
        ((FAIL++))
    else
        echo -e "${GREEN}  PASS: ALLOWED_HOSTS is not wildcard${NC}"
        ((PASS++))
    fi
else
    echo -e "${RED}  FAIL: production.py not found${NC}"
    ((FAIL++))
fi
echo ""

# ── Summary ───────────────────────────────────────────────────
echo -e "${CYAN}══════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Security Audit Summary${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}PASS: $PASS${NC}"
echo -e "  ${RED}FAIL: $FAIL${NC}"
echo -e "  ${YELLOW}WARN: $WARN${NC}"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}  RESULT: FAILED — $FAIL issue(s) require attention${NC}"
    exit 1
else
    echo -e "${GREEN}  RESULT: PASSED — all critical checks passed${NC}"
    exit 0
fi
