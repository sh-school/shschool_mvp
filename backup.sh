#!/bin/bash
# backup.sh — SchoolOS v5.2
# يُشغَّل داخل container backup الساعة 2:00 ص يومياً
# المتغيرات تُقرأ من .env عبر docker-compose
#
# ✅ v5.2: integrity verification + checksum + alerts

BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
KEEP_DAYS=${BACKUP_KEEP_DAYS:-14}
DB_HOST=${DB_HOST:-db}
DB_NAME=${DB_NAME:-shschool_db}
DB_USER=${DB_USER:-shschool_user}
ALERT_WEBHOOK=${BACKUP_ALERT_WEBHOOK:-""}

mkdir -p "$BACKUP_DIR"

ERRORS=0

echo "[$DATE] ═══ بدء النسخ الاحتياطي ==="

# ── قاعدة البيانات ───────────────────────────────
DB_FILE="$BACKUP_DIR/db_${DATE}.sql.gz"
pg_dump -h "$DB_HOST" -U "$DB_USER" "$DB_NAME" | gzip > "$DB_FILE"

if [ $? -ne 0 ]; then
    echo "[$DATE] ✗ فشل نسخ DB!"
    ERRORS=1
fi

# ── التحقق من سلامة الملف ────────────────────────
if [ -f "$DB_FILE" ]; then
    # فحص حجم الملف (يجب أن يكون > 1KB)
    FILE_SIZE=$(stat -f%z "$DB_FILE" 2>/dev/null || stat -c%s "$DB_FILE" 2>/dev/null || echo "0")
    if [ "$FILE_SIZE" -lt 1024 ]; then
        echo "[$DATE] ✗ الملف صغير جداً ($FILE_SIZE bytes) — قد يكون فارغاً!"
        ERRORS=1
    fi

    # فحص سلامة gzip
    gzip -t "$DB_FILE" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "[$DATE] ✗ ملف النسخة تالف (gzip integrity failed)!"
        ERRORS=1
    else
        echo "[$DATE] ✓ Integrity check passed"
    fi

    # توليد checksum
    md5sum "$DB_FILE" > "$DB_FILE.md5"
    echo "[$DATE] ✓ DB: $(du -sh $DB_FILE | cut -f1) — checksum: $(cat $DB_FILE.md5 | cut -d' ' -f1)"
else
    echo "[$DATE] ✗ ملف النسخة غير موجود!"
    ERRORS=1
fi

# ── رفع إلى S3 (اختياري — يعمل فقط إذا ضُبط AWS_BACKUP_BUCKET) ──
if [ -n "$AWS_BACKUP_BUCKET" ]; then
    S3_KEY="db-backups/$(basename $DB_FILE)"
    aws s3 cp "$DB_FILE" "s3://$AWS_BACKUP_BUCKET/$S3_KEY" \
        --region "${AWS_S3_REGION_NAME:-me-south-1}" \
        --storage-class STANDARD_IA \
        --quiet
    if [ $? -eq 0 ]; then
        echo "[$DATE] ☁  S3 رُفع: s3://$AWS_BACKUP_BUCKET/$S3_KEY"
        # رفع checksum أيضاً
        aws s3 cp "$DB_FILE.md5" "s3://$AWS_BACKUP_BUCKET/$S3_KEY.md5" \
            --region "${AWS_S3_REGION_NAME:-me-south-1}" --quiet 2>/dev/null
    else
        echo "[$DATE] ✗ S3 فشل الرفع!"
        ERRORS=1
    fi
else
    echo "[$DATE] ℹ  AWS_BACKUP_BUCKET غير مضبوط — تخطي رفع S3"
fi

# ── حذف النسخ القديمة (محلياً فقط) ─────────────
DELETED=$(find "$BACKUP_DIR" -name "db_*.sql.gz" -mtime +${KEEP_DAYS} -delete -print | wc -l)
# حذف checksums القديمة أيضاً
find "$BACKUP_DIR" -name "db_*.sql.gz.md5" -mtime +${KEEP_DAYS} -delete 2>/dev/null
echo "[$DATE] 🗑  حُذف $DELETED نسخة قديمة (محلي)"

TOTAL=$(ls "$BACKUP_DIR"/db_*.sql.gz 2>/dev/null | wc -l)
echo "[$DATE] ═══ انتهى — $TOTAL ملف محفوظ محلياً ==="

# ── إشعار عند الفشل (Webhook / Slack) ──────────
if [ "$ERRORS" -ne 0 ] && [ -n "$ALERT_WEBHOOK" ]; then
    curl -sf -X POST "$ALERT_WEBHOOK" \
        -H "Content-Type: application/json" \
        -d "{\"text\": \"⚠️ SchoolOS Backup FAILED at $DATE — check /var/log/backup.log\"}" \
        2>/dev/null || true
    echo "[$DATE] 📢 تم إرسال تنبيه الفشل"
fi

exit $ERRORS
