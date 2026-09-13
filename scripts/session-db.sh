#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  قاعدةُ بياناتٍ لشجرة العمل هذه
# ══════════════════════════════════════════════════════════════
#  كانت الأشجارُ كلُّها تشترك في `shschool_db`. فلمّا حذف فرعٌ عموداً
#  بهجرةٍ يومَ 2026-09-11، سقطت ثمانُ صفحاتٍ في **كلّ** شجرةٍ أخرى ساعاتٍ
#  بـ`column … does not exist` — وشيفرةُ تلك الأشجار سليمةٌ لا علّةَ فيها.
#
#  فلكلّ شجرةٍ قاعدتُها، تُنسخ من المشتركة أوّلَ مرّة (68 ميغابايت، ثوانٍ).
#  والهجرةُ بعدها تخصّ صاحبَها.
#
#  الاستعمال — مرّةً لكلّ شجرة:
#      bash scripts/session-db.sh
#  ثمّ في كلّ تشغيل:
#      SESSION_DB=$(bash scripts/session-db.sh --name) \
#      WEB_PORT=8001 docker compose -p schoolos-$(basename $PWD) \
#        --project-directory . -f D:/shschool_mvp/docker-compose.session.yml up -d
# ══════════════════════════════════════════════════════════════
set -euo pipefail

SOURCE_DB="${SOURCE_DB:-shschool_db}"
DB_CONTAINER="${DB_CONTAINER:-shschool-dev-db}"

# اسمُ القاعدة من اسم الشجرة: الحروفُ والأرقامُ وحدَها، وسقفُ بوستغريس 63 محرفاً.
slug=$(basename "$PWD" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '_' | cut -c1-40)
TARGET_DB="ss_${slug%_}"

if [ "${1:-}" = "--name" ]; then echo "$TARGET_DB"; exit 0; fi

psql_admin() { docker exec -i "$DB_CONTAINER" psql -U "$PGUSER" -d postgres -v ON_ERROR_STOP=1 "$@"; }
PGUSER=$(docker exec "$DB_CONTAINER" printenv POSTGRES_USER)

exists=$(psql_admin -tAc "select 1 from pg_database where datname='$TARGET_DB'" || true)
if [ "$exists" = "1" ]; then
  echo "$TARGET_DB موجودةٌ سلفاً — لا شيءَ يُفعل."
  exit 0
fi

echo "تُنشأ $TARGET_DB نسخةً عن $SOURCE_DB …"
psql_admin -c "CREATE DATABASE \"$TARGET_DB\""
docker exec "$DB_CONTAINER" sh -c \
  "pg_dump -U '$PGUSER' --no-owner --no-privileges '$SOURCE_DB' | psql -U '$PGUSER' -q -d '$TARGET_DB'"
# صلاحياتُ دور التطبيق — الأدوارُ على مستوى العنقود، والمنحُ على مستوى القاعدة.
psql_admin -d "$TARGET_DB" -c "GRANT ALL ON SCHEMA public TO shschool_app" 2>/dev/null || true
psql_admin -d "$TARGET_DB" -c "GRANT ALL ON ALL TABLES IN SCHEMA public TO shschool_app" 2>/dev/null || true
psql_admin -d "$TARGET_DB" -c "GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO shschool_app" 2>/dev/null || true
echo "تمّت: $TARGET_DB"
