#!/usr/bin/env bash
# scripts/restore-prod-locally.sh — استعادةُ آخر نسخةٍ من الإنتاج إلى قاعدة التطوير.
#
# لماذا: القاعدةُ المحلّيّة تفترق عن الإنتاج بلا آليّة — كودُ المدرسة مختلف،
# وقراراتُ الازدواج افترقت أسبوعاً دون أن يعلم أحد (2026-09-05). النشرُ ينقل
# الكودَ لا البيانات، فالطريقُ الوحيدُ لمحلّيٍّ يشبه الإنتاجَ هو نسخُه منه.
#
# المصدر: النسخُ اليوميّة المشفَّرة (gpg AES-256) في Cloudflare R2 تحت db-backups/ —
# التي يرفعها .github/workflows/backup.yml. فكُّها بالعبارة نفسِها.
#
# المتطلّبات (Git Bash / WSL): aws cli، gpg، docker. والأسرارُ في البيئة:
#   R2_ENDPOINT، R2_BUCKET، R2_ACCESS_KEY_ID، R2_SECRET_ACCESS_KEY، BACKUP_PASSPHRASE
#
# الاستعمال:
#   ./scripts/restore-prod-locally.sh              # أحدث نسخة
#   ./scripts/restore-prod-locally.sh schoolos-20260905-0200.sql.gz.gpg
#
# ⚠ يمحو قاعدةَ التطوير المحلّيّة (shschool-dev-db) ويستبدلها. لا يمسّ الإنتاج.
set -euo pipefail

for v in R2_ENDPOINT R2_BUCKET R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY BACKUP_PASSPHRASE; do
  [ -n "${!v:-}" ] || { echo "✗ $v غيرُ مضبوط"; exit 1; }
done
for bin in aws gpg docker; do
  command -v "$bin" >/dev/null || { echo "✗ $bin غيرُ مثبَّت"; exit 1; }
done

export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" AWS_DEFAULT_REGION=auto
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

FILE="${1:-}"
if [ -z "$FILE" ]; then
  FILE="$(aws s3 ls "s3://$R2_BUCKET/db-backups/" --endpoint-url "$R2_ENDPOINT" | sort | tail -1 | awk '{print $4}')"
  [ -n "$FILE" ] || { echo "✗ لا نسخَ في R2"; exit 1; }
fi
echo "📥 $FILE"
aws s3 cp "s3://$R2_BUCKET/db-backups/$FILE" "$WORK/$FILE" --endpoint-url "$R2_ENDPOINT" --only-show-errors

# القاعدة المحلّيّة كما يعرفها docker-compose (المضيف يرى 5433، والحاوية تُملأ من env).
DB_USER="$(docker exec shschool-dev-db sh -c 'echo $POSTGRES_USER')"
DB_NAME="$(docker exec shschool-dev-db sh -c 'echo $POSTGRES_DB')"
echo "🗑  إعادةُ إنشاء $DB_NAME على shschool-dev-db (المحلّيّ فقط)"
docker exec shschool-dev-db psql -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 -q \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB_NAME' AND pid<>pg_backend_pid();" \
  -c "DROP DATABASE IF EXISTS \"$DB_NAME\";" -c "CREATE DATABASE \"$DB_NAME\";"

echo "🔓 فكُّ التشفير والاستعادة…"
gpg --batch --quiet --pinentry-mode loopback --passphrase-fd 3 --decrypt "$WORK/$FILE" 3<<<"$BACKUP_PASSPHRASE" \
  | gunzip \
  | docker exec -i shschool-dev-db psql -U "$DB_USER" -d "$DB_NAME" -q -v ON_ERROR_STOP=0 >/dev/null

echo "🔁 الهجراتُ المحلّيّة (إن كان الكودُ أحدثَ من النسخة)"
docker exec shschool-dev-web python manage.py migrate --noinput | tail -2
echo "✅ المحلّيّ الآن صورةٌ من الإنتاج ($FILE). أعِد تشغيل الخادم: docker compose restart web worker"
