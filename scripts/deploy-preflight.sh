#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════
# deploy-preflight.sh — SchoolOS Pre-Deployment Validation
# ════════════════════════════════════════════════════════════════════════
# Run this BEFORE every Railway deploy to catch issues locally.
# Exit 0 = all green, Exit 1 = one or more checks failed.
# ════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ── Project root (script lives in scripts/) ─────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# ── Detect Python in venv ───────────────────────────────────────────────
if [ -f ".venv/Scripts/python.exe" ]; then
    PYTHON=".venv/Scripts/python.exe"
elif [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
else
    echo -e "${RED}ERROR: No virtualenv found at .venv/${NC}"
    echo "Create one with: python -m venv .venv && pip install -r requirements.txt"
    exit 1
fi

export DJANGO_SETTINGS_MODULE="shschool.settings"

# ── State tracking ──────────────────────────────────────────────────────
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0
RESULTS=()

pass_check() {
    PASS_COUNT=$((PASS_COUNT + 1))
    RESULTS+=("${GREEN}  PASS${NC}  $1")
    echo -e "${GREEN}  PASS${NC}  $1"
}

fail_check() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    RESULTS+=("${RED}  FAIL${NC}  $1")
    echo -e "${RED}  FAIL${NC}  $1"
}

warn_check() {
    WARN_COUNT=$((WARN_COUNT + 1))
    RESULTS+=("${YELLOW}  WARN${NC}  $1")
    echo -e "${YELLOW}  WARN${NC}  $1"
}

separator() {
    echo -e "${CYAN}────────────────────────────────────────────────────${NC}"
}

# ════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}${CYAN}SchoolOS Deploy Preflight${NC}"
echo -e "${CYAN}$(date '+%Y-%m-%d %H:%M:%S')${NC}"
separator

# ── 1. Dependencies check ──────────────────────────────────────────────
echo -e "\n${BOLD}[1/10] Dependencies check${NC}"
if [ ! -f "requirements.txt" ]; then
    fail_check "requirements.txt not found"
else
    MISSING_PKGS=""
    while IFS= read -r line; do
        # Skip comments, blank lines, -r references, git URLs
        line="$(echo "$line" | sed 's/#.*//' | xargs)"
        [[ -z "$line" ]] && continue
        [[ "$line" == -* ]] && continue
        [[ "$line" == http* ]] && continue
        [[ "$line" == git+* ]] && continue

        # Extract package name (before ==, >=, <=, ~=, !=, [)
        pkg_name="$(echo "$line" | sed 's/[=<>!~\[].*//' | xargs)"
        # Normalize: dashes to underscores for import check
        import_name="$(echo "$pkg_name" | tr '-' '_')"

        # Some packages have different import names — common mappings
        # Lowercase for matching
        import_lower="$(echo "$import_name" | tr '[:upper:]' '[:lower:]')"

        case "$import_lower" in
            pillow)                  import_name="PIL" ;;
            python_dateutil)         import_name="dateutil" ;;
            pyyaml)                  import_name="yaml" ;;
            python_dotenv)           import_name="dotenv" ;;
            dj_database_url)         import_name="dj_database_url" ;;
            django_redis)            import_name="django_redis" ;;
            psycopg2_binary|psycopg2) import_name="psycopg2" ;;
            djangorestframework)     import_name="rest_framework" ;;
            djangorestframework_simplejwt) import_name="rest_framework_simplejwt" ;;
            django_filter)           import_name="django_filters" ;;
            django_cors_headers)     import_name="corsheaders" ;;
            django_celery_beat)      import_name="django_celery_beat" ;;
            django_celery_results)   import_name="django_celery_results" ;;
            django_environ)          import_name="environ" ;;
            django_crispy_forms)     import_name="crispy_forms" ;;
            django_storages)         import_name="storages" ;;
            django_htmx)             import_name="django_htmx" ;;
            django_import_export)    import_name="import_export" ;;
            django_debug_toolbar)    import_name="debug_toolbar" ;;
            django_csp)              import_name="csp" ;;
            django_timezone_field)   import_name="timezone_field" ;;
            django_axes)             import_name="axes" ;;
            django)                  import_name="django" ;;
            beautifulsoup4)          import_name="bs4" ;;
            scikit_learn)            import_name="sklearn" ;;
            python_bidi)             import_name="bidi" ;;
            python_crontab)          import_name="crontab" ;;
            python_decouple)         import_name="decouple" ;;
            python_docx)             import_name="docx" ;;
            pycairo)                 import_name="cairo" ;;
            pyhanko)                 import_name="pyhanko" ;;
            pyjwt)                   import_name="jwt" ;;
            pyopenssl)               import_name="OpenSSL" ;;
            pdfminer.six|pdfminer_six) import_name="pdfminer" ;;
            py_ubjson)               import_name="ubjson" ;;
            rpds_py)                 import_name="rpds" ;;
            twisted)                 import_name="twisted" ;;
            automat)                 import_name="automat" ;;
            incremental)             import_name="incremental" ;;
            celery_types)            import_name="celery" ;; # type stubs, check celery
            fonttools)               import_name="fontTools" ;;
            freetype_py)             import_name="freetype" ;;
            flower)                  import_name="flower" ;;
            locust)                  import_name="locust" ;;
            mutmut)                  import_name="mutmut" ;;
        esac

        # Dev/test-only packages — skip (not needed in production)
        case "$import_lower" in
            locust|mutmut|pytest*|coverage|ruff|bandit|black|isort|flake8|mypy|pre_commit)
                continue ;;
        esac

        if ! $PYTHON -c "import $import_name" 2>/dev/null; then
            MISSING_PKGS="$MISSING_PKGS $pkg_name"
        fi
    done < requirements.txt

    if [ -z "$MISSING_PKGS" ]; then
        pass_check "All requirements.txt packages importable"
    else
        fail_check "Missing packages:$MISSING_PKGS"
    fi
fi

# ── 2. Gunicorn config check ──────────────────────────────────────────
echo -e "\n${BOLD}[2/10] Gunicorn config check${NC}"
if [ ! -f "gunicorn.conf.py" ]; then
    fail_check "gunicorn.conf.py not found"
else
    # Check worker_class — if uvicorn is set, verify it is installed
    WORKER_CLASS=$($PYTHON -c "
import os, runpy
os.environ.setdefault('PORT', '8000')
conf = runpy.run_path('gunicorn.conf.py')
print(conf.get('worker_class', 'sync'))
" 2>/dev/null || echo "UNKNOWN")

    if [[ "$WORKER_CLASS" == *uvicorn* ]]; then
        if $PYTHON -c "import uvicorn" 2>/dev/null; then
            pass_check "worker_class=$WORKER_CLASS (uvicorn installed)"
        else
            fail_check "worker_class=$WORKER_CLASS but uvicorn is NOT installed"
        fi
    elif [[ "$WORKER_CLASS" == "sync" || "$WORKER_CLASS" == "gthread" ]]; then
        pass_check "worker_class=$WORKER_CLASS (standard WSGI)"
    else
        warn_check "worker_class=$WORKER_CLASS (unexpected value)"
    fi

    # Check bind uses $PORT
    BIND_VALUE=$($PYTHON -c "
import os, runpy
os.environ.setdefault('PORT', '8000')
conf = runpy.run_path('gunicorn.conf.py')
print(conf.get('bind', ''))
" 2>/dev/null || echo "")

    if [[ "$BIND_VALUE" == *"0.0.0.0"* ]]; then
        pass_check "bind=$BIND_VALUE (respects \$PORT)"
    else
        fail_check "bind=$BIND_VALUE (should use 0.0.0.0:\$PORT)"
    fi
fi

# ── 3. Local gunicorn test ─────────────────────────────────────────────
echo -e "\n${BOLD}[3/10] Local gunicorn boot test${NC}"
# gunicorn uses fcntl which is Linux-only — skip boot test on Windows
IS_WINDOWS=false
if [[ "$(uname -s)" == MINGW* ]] || [[ "$(uname -s)" == MSYS* ]] || [[ "$(uname -s)" == CYGWIN* ]] || [[ "${OS:-}" == "Windows_NT" ]]; then
    IS_WINDOWS=true
fi

if $IS_WINDOWS; then
    warn_check "gunicorn boot test skipped on Windows (fcntl unavailable — test runs in CI/Docker)"
    echo -e "\n${BOLD}[4/10] Health endpoint check${NC}"
    warn_check "health check skipped on Windows (depends on gunicorn)"
elif ! $PYTHON -c "import gunicorn" 2>/dev/null; then
    fail_check "gunicorn not installed"
else
    export PORT=19876
    # Start gunicorn in background, capture PID
    $PYTHON -m gunicorn shschool.wsgi:application \
        --bind "0.0.0.0:$PORT" \
        --workers 1 \
        --timeout 10 \
        --log-level error \
        --error-logfile - \
        --access-logfile /dev/null \
        --pid /tmp/preflight_gunicorn.pid \
        &>/tmp/preflight_gunicorn.log &
    GUNICORN_PID=$!

    # Wait up to 5 seconds for it to boot
    BOOTED=false
    for i in 1 2 3 4 5; do
        sleep 1
        if kill -0 "$GUNICORN_PID" 2>/dev/null; then
            BOOTED=true
        else
            break
        fi
    done

    if $BOOTED; then
        pass_check "gunicorn booted successfully on port $PORT"
    else
        BOOT_LOG=$(cat /tmp/preflight_gunicorn.log 2>/dev/null | tail -5)
        fail_check "gunicorn failed to boot: $BOOT_LOG"
    fi

    # ── 4. Health endpoint check ────────────────────────────────────────
    echo -e "\n${BOLD}[4/10] Health endpoint check${NC}"
    if $BOOTED; then
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/health/" 2>/dev/null || echo "000")
        if [ "$HTTP_CODE" = "200" ]; then
            pass_check "/health/ returned HTTP 200"
        else
            fail_check "/health/ returned HTTP $HTTP_CODE (expected 200)"
        fi
    else
        fail_check "/health/ skipped (gunicorn not running)"
    fi

    # Kill gunicorn
    kill "$GUNICORN_PID" 2>/dev/null || true
    wait "$GUNICORN_PID" 2>/dev/null || true
    rm -f /tmp/preflight_gunicorn.pid /tmp/preflight_gunicorn.log
    unset PORT
fi

# ── 5. Superuser exists ───────────────────────────────────────────────
echo -e "\n${BOLD}[5/10] Superuser exists${NC}"
SU_COUNT=$($PYTHON manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
print(User.objects.filter(is_superuser=True).count())
" 2>/dev/null || echo "0")

if [ "$SU_COUNT" -gt 0 ] 2>/dev/null; then
    pass_check "Found $SU_COUNT superuser(s) in local DB"
else
    warn_check "No superusers in local DB (may be fine if using production DB)"
fi

# ── 6. DATABASE_URL format check ──────────────────────────────────────
echo -e "\n${BOLD}[6/10] DATABASE_URL check${NC}"
if [ -n "${DATABASE_URL:-}" ]; then
    if [[ "$DATABASE_URL" == postgres://* ]] || [[ "$DATABASE_URL" == postgresql://* ]]; then
        pass_check "DATABASE_URL is set (postgres)"
    else
        warn_check "DATABASE_URL is set but not postgres: ${DATABASE_URL:0:20}..."
    fi
else
    warn_check "DATABASE_URL not set locally (ensure it is set on Railway)"
fi

# ── 7. Static files (collectstatic --dry-run) ─────────────────────────
echo -e "\n${BOLD}[7/10] Static files check${NC}"
STATIC_OUTPUT=$($PYTHON manage.py collectstatic --dry-run --noinput 2>&1) || true
if echo "$STATIC_OUTPUT" | grep -qi "error\|traceback"; then
    fail_check "collectstatic --dry-run has errors"
    echo "    $(echo "$STATIC_OUTPUT" | grep -i 'error\|traceback' | head -3)"
else
    pass_check "collectstatic --dry-run OK"
fi

# ── 8. Migrations check ──────────────────────────────────────────────
echo -e "\n${BOLD}[8/10] Migrations check${NC}"
UNAPPLIED=$(timeout 30 $PYTHON manage.py showmigrations --plan 2>/dev/null | grep '\[ \]' | head -20 || true)
if [ -z "$UNAPPLIED" ]; then
    pass_check "All migrations applied"
else
    UNAPPLIED_COUNT=$(echo "$UNAPPLIED" | wc -l | xargs)
    fail_check "$UNAPPLIED_COUNT unapplied migration(s):"
    echo "$UNAPPLIED" | head -5 | while read -r line; do echo "    $line"; done
fi

# ── 9. Security settings check ───────────────────────────────────────
echo -e "\n${BOLD}[9/10] Security settings check${NC}"
PROD_SETTINGS="shschool/settings/production.py"
if [ ! -f "$PROD_SETTINGS" ]; then
    fail_check "$PROD_SETTINGS not found"
else
    if grep -q "SECURE_PROXY_SSL_HEADER" "$PROD_SETTINGS"; then
        pass_check "SECURE_PROXY_SSL_HEADER found in production.py"
    else
        fail_check "SECURE_PROXY_SSL_HEADER missing in production.py"
    fi
fi

# ── 10. Railway config check ─────────────────────────────────────────
echo -e "\n${BOLD}[10/10] Railway config check${NC}"
if [ ! -f "railway.json" ]; then
    fail_check "railway.json not found"
else
    if $PYTHON -c "
import json, sys
with open('railway.json') as f:
    cfg = json.load(f)
hp = cfg.get('deploy', {}).get('healthcheckPath', '')
if not hp:
    sys.exit(1)
print(hp)
" 2>/dev/null; then
        pass_check "railway.json has healthcheckPath"
    else
        fail_check "railway.json missing deploy.healthcheckPath"
    fi
fi

# ════════════════════════════════════════════════════════════════════════
# Summary
# ════════════════════════════════════════════════════════════════════════
echo ""
separator
echo -e "${BOLD}PREFLIGHT SUMMARY${NC}"
separator
echo -e "  ${GREEN}Passed : $PASS_COUNT${NC}"
echo -e "  ${YELLOW}Warned : $WARN_COUNT${NC}"
echo -e "  ${RED}Failed : $FAIL_COUNT${NC}"
separator

if [ "$FAIL_COUNT" -gt 0 ]; then
    echo ""
    echo -e "  ${RED}${BOLD}RED — $FAIL_COUNT check(s) failed. Do NOT deploy.${NC}"
    echo ""
    exit 1
else
    echo ""
    echo -e "  ${GREEN}${BOLD}GREEN — All checks passed. Safe to deploy.${NC}"
    echo ""
    exit 0
fi
