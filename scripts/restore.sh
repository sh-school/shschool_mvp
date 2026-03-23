#!/bin/bash
# restore.sh — SchoolOS v5.1
# ══════════════════════════════════════════════════════════════
# استعادة قاعدة البيانات من نسخة احتياطية (محلية أو S3)
#
# الاستخدام:
#   ./scripts/restore.sh                          ← آخر نسخة محلية
#   ./scripts/restore.sh db_20260323_020000.sql.gz ← نسخة محددة
#   ./scripts/restore.sh s3                        ← أحدث نسخة من S3
#
# ⚠  تحذير: يُوقف التطبيق أثناء الاستعادة
# ══════════════════════════════════════════════════════════════

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
DB_HOST="${DB_HOST:-db}"
DB_NAME="${DB_NAME:-shschool_db}"
DB_USER="${DB_USER:-shschool_user}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# ── دالة المساعدة ─────────────────────────────────────────────
log()  { echo "[$TIMESTAMP] $1"; }
fail() { echo "[$TIMESTAMP] ✗ $1" >&2; exit 1; }

# ── 1. تحديد ملف النسخة الاحتياطية ───────────────────────────
TARGET="${1:-}"

if [ "$TARGET" = "s3" ]; then
    # جلب أحدث نسخة من S3
    [ -z "${AWS_BACKUP_BUCKET:-}" ] && fail "AWS_BACKUP_BUCKET غير مضبوط"
    log "📥 جلب أحدث نسخة من S3..."
    LATEST=$(aws s3 ls "s3://$AWS_BACKUP_BUCKET/db-backups/" \
        --region "${AWS_S3_REGION_NAME:-me-south-1}" \
        | sort | tail -1 | awk '{print $4}')
    [ -z "$LATEST" ] && fail "لا توجد نسخ في S3"
    mkdir -p "$BACKUP_DIR"
    aws s3 cp "s3://$AWS_BACKUP_BUCKET/db-backups/$LATEST" "$BACKUP_DIR/$LATEST" \
        --region "${AWS_S3_REGION_NAME:-me-south-1}"
    BACKUP_FILE="$BACKUP_DIR/$LATEST"
    log "✓ تم التنزيل: $BACKUP_FILE"

elif [ -n "$TARGET" ]; then
    # ملف محدد
    if [ -f "$TARGET" ]; then
        BACKUP_FILE="$TARGET"
    elif [ -f "$BACKUP_DIR/$TARGET" ]; then
        BACKUP_FILE="$BACKUP_DIR/$TARGET"
    else
        fail "الملف غير موجود: $TARGET"
    fi

else
    # آخر نسخة محلية
    BACKUP_FILE=$(ls -t "$BACKUP_DIR"/db_*.sql.gz 2>/dev/null | head -1)
    [ -z "$BACKUP_FILE" ] && fail "لا توجد نسخ محلية في $BACKUP_DIR"
    log "📂 أحدث نسخة محلية: $BACKUP_FILE"
fi

# ── 2. تأكيد المستخدم ─────────────────────────────────────────
log "══════════════════════════════════════════"
log "⚠  تحذير: سيتم OVERWRITE لقاعدة البيانات:"
log "   DB:   $DB_NAME على $DB_HOST"
log "   ملف:  $BACKUP_FILE"
log "══════════════════════════════════════════"
read -p "هل أنت متأكد؟ اكتب 'نعم' للمتابعة: " CONFIRM
[ "$CONFIRM" != "نعم" ] && { log "تم الإلغاء."; exit 0; }

# ── 3. نسخة احتياطية للحالة الراهنة قبل الاستعادة ────────────
PRE_RESTORE="$BACKUP_DIR/pre_restore_${TIMESTAMP}.sql.gz"
log "💾 نسخة احتياطية للحالة الراهنة → $PRE_RESTORE"
pg_dump -h "$DB_HOST" -U "$DB_USER" "$DB_NAME" | gzip > "$PRE_RESTORE" \
    || log "⚠  تعذّر نسخ الحالة الراهنة — متابعة..."

# ── 4. إيقاف التطبيق (اختياري إذا كان Docker) ───────────────
if command -v docker &>/dev/null; then
    log "⏹  إيقاف خدمة web مؤقتًا..."
    docker compose -f docker-compose.prod.yml stop web 2>/dev/null || true
fi

# ── 5. استعادة قاعدة البيانات ──────────────────────────────
log "🔄 بدء الاستعادة..."
gunzip -c "$BACKUP_FILE" | psql -h "$DB_HOST" -U "$DB_USER" "$DB_NAME" \
    || fail "فشلت الاستعادة — يمكنك الرجوع من: $PRE_RESTORE"

log "✅ تمت الاستعادة بنجاح من: $BACKUP_FILE"

# ── 6. إعادة تشغيل التطبيق ──────────────────────────────────
if command -v docker &>/dev/null; then
    log "▶  إعادة تشغيل خدمة web..."
    docker compose -f docker-compose.prod.yml start web 2>/dev/null || true
fi

log "═══ اكتمل — اختبر التطبيق على /health/ ==="
