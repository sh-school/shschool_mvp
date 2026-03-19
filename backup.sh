#!/bin/bash
# /home/schoolos/backup.sh
# نسخ احتياطي يومي تلقائي لـ SchoolOS

BACKUP_DIR="/home/schoolos/schoolos/backups"
DATE=$(date +%Y%m%d_%H%M%S)
COMPOSE_FILE="/home/schoolos/schoolos/docker-compose.prod.yml"
KEEP_DAYS=14

mkdir -p "$BACKUP_DIR"

echo "[$DATE] ═══ بدء النسخ الاحتياطي ==="

# ── قاعدة البيانات ──────────────────────────────
DB_FILE="$BACKUP_DIR/db_${DATE}.sql.gz"
docker compose -f "$COMPOSE_FILE" exec -T db \
    pg_dump -U shschool_user shschool_db \
    | gzip > "$DB_FILE"

if [ $? -eq 0 ]; then
    echo "[$DATE] ✓ قاعدة البيانات: $(du -sh $DB_FILE | cut -f1)"
else
    echo "[$DATE] ✗ فشل نسخ قاعدة البيانات!"
fi

# ── الملفات المرفوعة ─────────────────────────────
MEDIA_FILE="$BACKUP_DIR/media_${DATE}.tar.gz"
tar -czf "$MEDIA_FILE" -C /home/schoolos/schoolos media/ 2>/dev/null

if [ $? -eq 0 ]; then
    echo "[$DATE] ✓ الملفات: $(du -sh $MEDIA_FILE | cut -f1)"
fi

# ── حذف النسخ القديمة ────────────────────────────
DELETED=$(find "$BACKUP_DIR" -name "*.gz" -mtime +${KEEP_DAYS} -delete -print | wc -l)
echo "[$DATE] 🗑  حُذف $DELETED ملف قديم"

# ── ملخص ─────────────────────────────────────────
TOTAL=$(ls "$BACKUP_DIR" | wc -l)
echo "[$DATE] ═══ انتهى — $TOTAL ملف محفوظ ==="
