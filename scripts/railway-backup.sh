#!/bin/bash
# نسخةٌ احتياطيّةٌ يوميّةٌ مشفّرةٌ داخل Railway (W-20261023-018) — خدمةُ cron تخرج بعد الإنجاز.
# pg_dump عبر الشبكة الخاصّة (لا egress على سحب القاعدة) → gzip → gpg AES256 → Railway Bucket.
# تحقّقٌ فوريّ (فكّ تشفير + gunzip + خاتمة pg_dump + مطابقة الحجم في الحاوية) وأيُّ خللٍ = خروجٌ ≠ 0.
# مواصفةُ التشفير مطابقةٌ لـ .github/workflows/backup.yml فيعمل backup-restore-test.yml وrestore-prod-locally.sh كما هما.
set -euo pipefail

fail() {
    echo "::error:: $1" >&2
    exit 1
}

: "${DATABASE_URL:?DATABASE_URL (الداخليّ) مطلوب}"
: "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE مطلوب}"
: "${BACKUP_S3_ENDPOINT:?BACKUP_S3_ENDPOINT مطلوب}"
: "${BACKUP_S3_BUCKET:?BACKUP_S3_BUCKET مطلوب}"
: "${BACKUP_S3_ACCESS_KEY_ID:?BACKUP_S3_ACCESS_KEY_ID مطلوب}"
: "${BACKUP_S3_SECRET_ACCESS_KEY:?BACKUP_S3_SECRET_ACCESS_KEY مطلوب}"

# المستودعُ عامّ: التشفيرُ هو الحصنُ الوحيد. دون 32 حرفاً = رفض.
[ "${#BACKUP_PASSPHRASE}" -ge 32 ] || fail "BACKUP_PASSPHRASE أقصر من 32 حرفاً"

# حارسُ الرسوم: ممنوعٌ السحبُ عبر الوكيل العام (egress). الشبكةُ الخاصّة فقط.
case "$DATABASE_URL" in
    *rlwy.net*) fail "DATABASE_URL يشير إلى الوكيل العام — استعمل رابطَ الشبكة الخاصّة (*.railway.internal)" ;;
esac
case "$DATABASE_URL" in
    *.railway.internal*) ;;
    *) fail "DATABASE_URL ليس من الشبكة الخاصّة (*.railway.internal)" ;;
esac

KEEP_DAILY_DAYS="${BACKUP_KEEP_DAILY_DAYS:-14}"
KEEP_MONTHLY_MONTHS="${BACKUP_KEEP_MONTHLY_MONTHS:-12}"
MIN_BYTES="${BACKUP_MIN_BYTES:-1024}"
PREFIX="db-backups/"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
FILE="schoolos-${STAMP}.sql.gz.gpg"
WORK="$(mktemp -d /tmp/backup.XXXXXX)"
trap 'rm -r -f "$WORK"' EXIT
OUT="$WORK/$FILE"

export AWS_ACCESS_KEY_ID="$BACKUP_S3_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$BACKUP_S3_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION="${BACKUP_S3_REGION:-auto}"
export AWS_CONFIG_FILE="$WORK/aws-config"
# وثائقُ Railway: عناوينُ virtual-hosted افتراضاً، وحاوياتٌ أقدم قد تحتاج path (تبويب Credentials).
printf '[default]\ns3 =\n    addressing_style = %s\n' "${BACKUP_S3_ADDRESSING_STYLE:-virtual}" > "$AWS_CONFIG_FILE"
s3() { aws --endpoint-url "$BACKUP_S3_ENDPOINT" "$@"; }

echo "pg_dump (شبكة خاصّة) -> gzip -> gpg AES256 ..."
pg_dump --no-owner --no-privileges "$DATABASE_URL" \
    | gzip -9 \
    | gpg --batch --yes --symmetric --cipher-algo AES256 \
          --s2k-mode 3 --s2k-count 65011712 --s2k-digest-algo SHA512 \
          --pinentry-mode loopback --passphrase-fd 3 -o "$OUT" 3<<<"$BACKUP_PASSPHRASE"

SIZE="$(stat -c%s "$OUT")"
echo "تمّ: $FILE ($SIZE بايت)"
[ "$SIZE" -gt "$MIN_BYTES" ] || fail "النسخة صغيرة جداً ($SIZE) — فشل محتمل"

# تحقّقٌ فوريّ بلا كتابة البيانات على القرص: فكّ التشفير + سلامة gzip + خاتمة pg_dump (اكتمال الإخراج).
gpg --batch --quiet --pinentry-mode loopback --passphrase-fd 3 --decrypt "$OUT" 3<<<"$BACKUP_PASSPHRASE" \
    | gunzip \
    | tail -n 20 | grep -q "PostgreSQL database dump complete" \
    || fail "فشل التحقّق: فكّ التشفير/gunzip/خاتمة pg_dump"
echo "النسخةُ قابلةٌ لفكّ التشفير وخاتمتُها سليمة."

s3 s3 cp "$OUT" "s3://${BACKUP_S3_BUCKET}/${PREFIX}${FILE}" --only-show-errors
REMOTE_SIZE="$(s3 s3api head-object --bucket "$BACKUP_S3_BUCKET" --key "${PREFIX}${FILE}" --query ContentLength --output text)"
[ "$REMOTE_SIZE" = "$SIZE" ] || fail "حجمُ الملف في الحاوية ($REMOTE_SIZE) يخالف المحلّي ($SIZE)"
echo "رُفِع وتطابق الحجم: ${PREFIX}${FILE}"

# الاحتفاظ: Railway لا يدعم lifecycle للحاويات بعد — نقلّم هنا، وبعد نجاح الرفع والتحقّق فقط.
# نُبقي: كلَّ نسخ آخر N يوماً + أولَ نسخةٍ في كلّ شهرٍ لآخر M شهراً. لا حذفَ لما لا يطابق النمط.
DAILY_CUTOFF="$(date -u -d "-${KEEP_DAILY_DAYS} days" +%Y%m%d)"
MONTHLY_CUTOFF="$(date -u -d "-${KEEP_MONTHLY_MONTHS} months" +%Y%m)"
KEYS="$(s3 s3api list-objects-v2 --bucket "$BACKUP_S3_BUCKET" --prefix "$PREFIX" --query 'Contents[].Key' --output text | tr '\t' '\n' | sort)"
PATTERN='^schoolos-([0-9]{6})([0-9]{2})-[0-9]{6}\.sql\.gz\.gpg$'
declare -A first_of_month=()
for key in $KEYS; do
    name="${key#"$PREFIX"}"
    [[ "$name" =~ $PATTERN ]] || continue
    [ -n "${first_of_month[${BASH_REMATCH[1]}]:-}" ] || first_of_month[${BASH_REMATCH[1]}]="$key"
done
deleted=0
for key in $KEYS; do
    name="${key#"$PREFIX"}"
    [[ "$name" =~ $PATTERN ]] || continue
    ym="${BASH_REMATCH[1]}"
    day="${ym}${BASH_REMATCH[2]}"
    if [ "$day" -ge "$DAILY_CUTOFF" ]; then continue; fi
    if [ "$ym" -ge "$MONTHLY_CUTOFF" ] && [ "${first_of_month[$ym]}" = "$key" ]; then continue; fi
    s3 s3 rm "s3://${BACKUP_S3_BUCKET}/${key}" --only-show-errors
    deleted=$((deleted + 1))
done
echo "تقليم الاحتفاظ: حُذف $deleted نسخة (يومي ${KEEP_DAILY_DAYS} يوماً + شهري ${KEEP_MONTHLY_MONTHS} شهراً)."
echo "اكتملت النسخة الاحتياطية بنجاح."
