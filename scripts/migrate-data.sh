#!/usr/bin/env bash
# ============================================================================
# SchoolOS Data Migration: Local PostgreSQL -> Railway Production
# Usage: ./migrate-data.sh [DATABASE_PUBLIC_URL]
# ============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()    { printf "${BLUE}[INFO]${NC}  %s\n" "$*"; }
ok()      { printf "${GREEN}[OK]${NC}    %s\n" "$*"; }
warn()    { printf "${YELLOW}[WARN]${NC}  %s\n" "$*"; }
err()     { printf "${RED}[ERROR]${NC} %s\n" "$*"; }
header()  { printf "\n${BOLD}${CYAN}== %s ==${NC}\n" "$*"; }
divider() { printf "${CYAN}──────────────────────────────────────────────${NC}\n"; }

die() {
    err "$@"
    exit 1
}

# ---------------------------------------------------------------------------
# Detect OS / tool paths (Git Bash on Windows vs Linux)
# ---------------------------------------------------------------------------
detect_tools() {
    for cmd in psql pg_dump pg_restore; do
        if ! command -v "$cmd" &>/dev/null; then
            die "'$cmd' not found in PATH. Install PostgreSQL client tools."
        fi
    done
    ok "PostgreSQL client tools found (psql, pg_dump, pg_restore)"
}

# ---------------------------------------------------------------------------
# Load local .env
# ---------------------------------------------------------------------------
load_local_env() {
    header "Loading local .env"

    # Walk up from script dir to find .env
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    ENV_FILE=""
    search="$SCRIPT_DIR"
    while [ "$search" != "/" ] && [ "$search" != "" ]; do
        if [ -f "$search/.env" ]; then
            ENV_FILE="$search/.env"
            break
        fi
        search="$(dirname "$search")"
    done

    # Also check parent of scripts/
    if [ -z "$ENV_FILE" ] && [ -f "$SCRIPT_DIR/../.env" ]; then
        ENV_FILE="$SCRIPT_DIR/../.env"
    fi

    [ -n "$ENV_FILE" ] || die ".env file not found. Create one with DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT."

    info "Using .env from: $ENV_FILE"

    # Source only the DB_ vars (safe extraction)
    LOCAL_DB_NAME="$(grep -E '^DB_NAME=' "$ENV_FILE" | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')"
    LOCAL_DB_USER="$(grep -E '^DB_USER=' "$ENV_FILE" | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')"
    LOCAL_DB_PASSWORD="$(grep -E '^DB_PASSWORD=' "$ENV_FILE" | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')"
    LOCAL_DB_HOST="$(grep -E '^DB_HOST=' "$ENV_FILE" | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')"
    LOCAL_DB_PORT="$(grep -E '^DB_PORT=' "$ENV_FILE" | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')"

    # Defaults
    LOCAL_DB_HOST="${LOCAL_DB_HOST:-localhost}"
    LOCAL_DB_PORT="${LOCAL_DB_PORT:-5432}"

    [ -n "$LOCAL_DB_NAME" ] || die "DB_NAME not set in .env"
    [ -n "$LOCAL_DB_USER" ] || die "DB_USER not set in .env"

    ok "Local DB config: ${LOCAL_DB_USER}@${LOCAL_DB_HOST}:${LOCAL_DB_PORT}/${LOCAL_DB_NAME}"
}

# ---------------------------------------------------------------------------
# Resolve remote DATABASE_PUBLIC_URL
# ---------------------------------------------------------------------------
resolve_remote_url() {
    header "Resolving remote DATABASE_PUBLIC_URL"

    if [ -n "${1:-}" ]; then
        REMOTE_URL="$1"
        info "Using URL from command-line argument"
    elif [ -n "${DATABASE_PUBLIC_URL:-}" ]; then
        REMOTE_URL="$DATABASE_PUBLIC_URL"
        info "Using URL from DATABASE_PUBLIC_URL env var"
    elif [ -n "${DATABASE_URL:-}" ]; then
        REMOTE_URL="$DATABASE_URL"
        warn "DATABASE_PUBLIC_URL not set, falling back to DATABASE_URL"
    else
        die "No remote DB URL provided. Pass as argument or set DATABASE_PUBLIC_URL."
    fi

    # Basic validation
    if [[ "$REMOTE_URL" != postgres://* ]] && [[ "$REMOTE_URL" != postgresql://* ]]; then
        die "URL must start with postgres:// or postgresql://"
    fi

    ok "Remote URL resolved (host hidden for security)"
}

# ---------------------------------------------------------------------------
# Step 1: Validate local DB connection
# ---------------------------------------------------------------------------
validate_local() {
    header "Step 1/7: Validating local DB connection"

    export PGPASSWORD="$LOCAL_DB_PASSWORD"
    if psql -h "$LOCAL_DB_HOST" -p "$LOCAL_DB_PORT" -U "$LOCAL_DB_USER" -d "$LOCAL_DB_NAME" -c "SELECT 1;" &>/dev/null; then
        ok "Local DB connection successful"
    else
        die "Cannot connect to local DB. Check credentials in .env"
    fi

    # Show some stats
    local count
    count=$(psql -h "$LOCAL_DB_HOST" -p "$LOCAL_DB_PORT" -U "$LOCAL_DB_USER" -d "$LOCAL_DB_NAME" -tAc \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")
    info "Local DB has $count tables in public schema"
    unset PGPASSWORD
}

# ---------------------------------------------------------------------------
# Step 2: Validate remote DB connection
# ---------------------------------------------------------------------------
validate_remote() {
    header "Step 2/7: Validating remote DB connection"

    if psql "$REMOTE_URL" -c "SELECT 1;" &>/dev/null; then
        ok "Remote DB connection successful"
    else
        die "Cannot connect to remote DB. Check DATABASE_PUBLIC_URL."
    fi

    local count
    count=$(psql "$REMOTE_URL" -tAc \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null || echo "0")
    info "Remote DB currently has $count tables in public schema"
}

# ---------------------------------------------------------------------------
# Step 3: Confirmation
# ---------------------------------------------------------------------------
confirm_migration() {
    header "Step 3/7: Confirmation"

    divider
    printf "${BOLD}Source:${NC}      %s@%s:%s/%s (LOCAL)\n" "$LOCAL_DB_USER" "$LOCAL_DB_HOST" "$LOCAL_DB_PORT" "$LOCAL_DB_NAME"
    printf "${BOLD}Destination:${NC} Railway production (REMOTE)\n"
    divider

    warn "This will DESTROY all data in the remote database and replace it."
    printf "\n"

    read -rp "$(printf "${YELLOW}Type 'yes' to proceed: ${NC}")" answer
    if [ "$answer" != "yes" ]; then
        info "Migration cancelled."
        exit 0
    fi
    printf "\n"
}

# ---------------------------------------------------------------------------
# Step 4: pg_dump local
# ---------------------------------------------------------------------------
dump_local() {
    header "Step 4/7: Dumping local database"

    TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
    BACKUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/backups"
    mkdir -p "$BACKUP_DIR"
    DUMP_FILE="$BACKUP_DIR/${LOCAL_DB_NAME}_${TIMESTAMP}.dump"

    info "Backup file: $DUMP_FILE"

    export PGPASSWORD="$LOCAL_DB_PASSWORD"
    if pg_dump \
        -h "$LOCAL_DB_HOST" \
        -p "$LOCAL_DB_PORT" \
        -U "$LOCAL_DB_USER" \
        -d "$LOCAL_DB_NAME" \
        --no-owner \
        --no-privileges \
        -F c \
        -f "$DUMP_FILE"; then
        ok "Dump completed successfully"
        local size
        size=$(du -h "$DUMP_FILE" | cut -f1)
        info "Dump size: $size"
    else
        die "pg_dump failed"
    fi
    unset PGPASSWORD
}

# ---------------------------------------------------------------------------
# Step 5: Drop + recreate public schema on remote
# ---------------------------------------------------------------------------
reset_remote_schema() {
    header "Step 5/7: Resetting remote public schema"

    warn "Dropping all objects in remote public schema..."

    if psql "$REMOTE_URL" <<-'SQL'
        DROP SCHEMA public CASCADE;
        CREATE SCHEMA public;
        GRANT ALL ON SCHEMA public TO PUBLIC;
SQL
    then
        ok "Remote schema reset complete"
    else
        die "Failed to reset remote schema. Check permissions."
    fi
}

# ---------------------------------------------------------------------------
# Step 6: pg_restore to remote
# ---------------------------------------------------------------------------
restore_remote() {
    header "Step 6/7: Restoring data to remote"

    info "This may take a few minutes depending on data size..."

    # pg_restore returns non-zero on warnings, so we capture exit code
    local exit_code=0
    pg_restore \
        --no-owner \
        --no-privileges \
        --no-acl \
        -d "$REMOTE_URL" \
        "$DUMP_FILE" 2>&1 | while IFS= read -r line; do
            # Filter out noise, show real errors
            if echo "$line" | grep -qiE "error|fatal"; then
                err "$line"
            fi
        done || exit_code=$?

    # pg_restore exit code 1 = warnings (usually OK), 2+ = real errors
    if [ "${exit_code:-0}" -le 1 ]; then
        ok "Restore completed (exit code: ${exit_code:-0})"
    else
        die "pg_restore failed with exit code $exit_code"
    fi
}

# ---------------------------------------------------------------------------
# Step 7: Verify
# ---------------------------------------------------------------------------
verify_remote() {
    header "Step 7/7: Verifying remote database"

    local tables users schools migrations

    tables=$(psql "$REMOTE_URL" -tAc \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null || echo "?")

    # Try common Django/SchoolOS table names
    users=$(psql "$REMOTE_URL" -tAc \
        "SELECT count(*) FROM auth_user;" 2>/dev/null || \
        psql "$REMOTE_URL" -tAc \
        "SELECT count(*) FROM users_customuser;" 2>/dev/null || \
        echo "N/A")

    schools=$(psql "$REMOTE_URL" -tAc \
        "SELECT count(*) FROM schools_school;" 2>/dev/null || \
        psql "$REMOTE_URL" -tAc \
        "SELECT count(*) FROM school;" 2>/dev/null || \
        echo "N/A")

    migrations=$(psql "$REMOTE_URL" -tAc \
        "SELECT count(*) FROM django_migrations;" 2>/dev/null || echo "N/A")

    divider
    printf "  ${BOLD}Tables:${NC}      %s\n" "$tables"
    printf "  ${BOLD}Users:${NC}       %s\n" "$users"
    printf "  ${BOLD}Schools:${NC}     %s\n" "$schools"
    printf "  ${BOLD}Migrations:${NC}  %s\n" "$migrations"
    divider
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
show_summary() {
    printf "\n"
    printf "${GREEN}${BOLD}============================================${NC}\n"
    printf "${GREEN}${BOLD}  MIGRATION COMPLETED SUCCESSFULLY${NC}\n"
    printf "${GREEN}${BOLD}============================================${NC}\n"
    printf "\n"
    info "Backup saved at: $DUMP_FILE"
    info "Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
    printf "\n"
    warn "Next steps:"
    printf "  1. Test the production site thoroughly\n"
    printf "  2. Run: python manage.py check --deploy\n"
    printf "  3. Keep the backup file until you verify everything works\n"
    printf "\n"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    printf "\n"
    printf "${BOLD}${CYAN}SchoolOS Data Migration Tool${NC}\n"
    printf "${CYAN}Local PostgreSQL -> Railway Production${NC}\n"
    divider

    detect_tools
    load_local_env
    resolve_remote_url "${1:-}"
    validate_local
    validate_remote
    confirm_migration
    dump_local
    reset_remote_schema
    restore_remote
    verify_remote
    show_summary
}

main "$@"
