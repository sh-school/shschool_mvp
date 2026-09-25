#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════
# canary-check.sh — كنارُ ما بعد النشر (REP-17 أ)
# ════════════════════════════════════════════════════════════════════════
# يثبت أنّ الـcommit المنشور **صار حيّاً** لا أنّ الخدمة «تتنفّس» فقط، وأنّ صفحةً حقيقيّةً تُرسم بالقوالب والثابت:
#   1) /health/ يُرجع 200 وفيه حقل `commit` يساوي أوّلَ 7 خاناتٍ من SHA المنشور (نسخةٌ قديمةٌ سليمةٌ تُجيب بـ200
#      وبـcommit آخر — وهي بعينها صورةُ النشر الفاشل الذي وُضع هذا الفحصُ لالتقاطه)؛
#   2) /auth/login/ يُرجع 200 (حادثة 2026-09-17: /health/ أخضرُ ساعتين وكلُّ صفحةٍ 500).
# يُعيد المحاولةَ لأنّ Railway يعلن نجاحَ النشر قبل أن يخدم الحاويةَ الجديدةَ بثوانٍ (ويخدم القديمةَ في الأثناء).
#
# الاستعمال:  scripts/canary-check.sh <sha> [base_url]
# الضبط (متغيّراتُ بيئة):  CANARY_ATTEMPTS (18)  CANARY_SLEEP (25 ثانية)  CANARY_TIMEOUT (15 ثانية لكلّ طلب)
# الخروج:  0 = حيّ وسليم؛ 1 = لم يثبت (بعد كلّ المحاولات)؛ 2 = استعمالٌ خاطئ.
#
# يخدم `.github/workflows/post-deploy-canary.yml` (تلقائيّاً عند deployment_status). ومنطقُه هو منطقُ وظيفة
# «Post-Deploy Canary» اليدويّة في deploy-railway.yml نفسُه؛ ولم تُعدَّل تلك (خطُّ نشرٍ يدويٌّ تملكه جلسةُ النشر).
# ════════════════════════════════════════════════════════════════════════

set -uo pipefail

SHA="${1:-}"
BASE_URL="${2:-${PRODUCTION_URL:-https://shschoolmvp-production.up.railway.app}}"
ATTEMPTS="${CANARY_ATTEMPTS:-18}"
SLEEP="${CANARY_SLEEP:-25}"
TIMEOUT="${CANARY_TIMEOUT:-15}"

if [ -z "$SHA" ] || [ "${#SHA}" -lt 7 ]; then
  echo "usage: canary-check.sh <sha (7+ chars)> [base_url]" >&2
  exit 2
fi
BASE_URL="${BASE_URL%/}"
EXPECTED="$(printf '%s' "$SHA" | cut -c1-7)"
PYBIN="$(command -v python3 || command -v python || true)"  # ubuntu: python3؛ ويندوز (Git Bash): python
if [ -z "$PYBIN" ]; then echo "python not found" >&2; exit 2; fi
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

echo "Canary: التحقّق من أنّ commit $EXPECTED حيٌّ على $BASE_URL"

HTTP_CODE="000"
COMMIT=""
LOGIN_CODE=""
for attempt in $(seq 1 "$ATTEMPTS"); do
  HTTP_CODE=$(curl -s -o "$TMP" -w "%{http_code}" --max-time "$TIMEOUT" "$BASE_URL/health/" 2>/dev/null || echo "000")
  COMMIT=""
  if [ "$HTTP_CODE" = "200" ]; then
    COMMIT=$("$PYBIN" -c "import json,sys; print(json.load(open(sys.argv[1])).get('commit',''))" "$TMP" 2>/dev/null || echo "")
  fi
  echo "Attempt $attempt/$ATTEMPTS: HTTP $HTTP_CODE | served=${COMMIT:-?} want=$EXPECTED"

  if [ "$HTTP_CODE" = "200" ]; then
    if [ -z "$COMMIT" ]; then
      echo "  ↳ /health/ بلا حقل commit — لا يُثبت شيئاً، تُعاد المحاولة"
    elif [ "$COMMIT" = "$EXPECTED" ]; then
      LOGIN_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" "$BASE_URL/auth/login/" 2>/dev/null || echo "000")
      if [ "$LOGIN_CODE" = "200" ]; then
        echo "✅ Canary PASSED — commit $COMMIT حيٌّ، وصفحةُ الدخول 200"
        exit 0
      fi
      echo "  ↳ commit $COMMIT حيٌّ لكنّ /auth/login/ أرجعت HTTP $LOGIN_CODE"
    else
      echo "  ↳ النسخةُ القديمة ($COMMIT) ما زالت تخدم — بانتظار $EXPECTED"
    fi
  fi

  if [ "$attempt" -lt "$ATTEMPTS" ]; then sleep "$SLEEP"; fi
done

echo "::error::❌ CANARY FAILED — commit $EXPECTED لا يخدم سليماً (آخر /health/=$HTTP_CODE, served=${COMMIT:-?}, /auth/login/=${LOGIN_CODE:-لم تُطلب})"
exit 1
