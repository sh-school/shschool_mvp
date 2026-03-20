#!/bin/bash
# backup.sh — SchoolOS v5
# يُشغَّل داخل container backup الساعة 2:00 ص يومياً
# المتغيرات تُقرأ من .env عبر docker-compose

BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
KEEP_DAYS=${BACKUP_KEEP_DAYS:-14}
DB_HOST=${DB_HOST:-db}
DB_NAME=${DB_NAME:-shschool_db}
DB_USER=${DB_USER:-shschool_user}

mkdir -p "$BACKUP_DIR"

echo "[$DATE] ═══ بدء النسخ الاحتياطي ==="

# ── قاعدة البيانات ───────────────────────────────
DB_FILE="$BACKUP_DIR/db_${DATE}.sql.gz"
pg_dump -h "$DB_HOST" -U "$DB_USER" "$DB_NAME" | gzip > "$DB_FILE"

if [ $? -eq 0 ]; then
    echo "[$DATE] ✓ DB: $(du -sh $DB_FILE | cut -f1)"
else
    echo "[$DATE] ✗ فشل نسخ DB!"
    exit 1
fi

# ── حذف النسخ القديمة ────────────────────────────
DELETED=$(find "$BACKUP_DIR" -name "db_*.sql.gz" -mtime +${KEEP_DAYS} -delete -print | wc -l)
echo "[$DATE] 🗑  حُذف $DELETED نسخة قديمة"

TOTAL=$(ls "$BACKUP_DIR" | wc -l)
echo "[$DATE] ═══ انتهى — $TOTAL ملف محفوظ ==="
