#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  اختباراتُ الشجرة بقاعدةٍ مهجَّرةٍ تُعاد استعمالها (W-20261016-014)
# ══════════════════════════════════════════════════════════════
#  داخل حاوية الجلسة:  bash scripts/session-test.sh [مسارات pytest…]
#  من المضيف:          make session-test ARGS="tests/test_x.py"
#  القاعدةُ (TEST_DB_NAME) تُبنى بالهجرات مرّةً وتُعاد ما لم تتغيّر ملفّاتُ الهجرات.
#  وما تعذّر قياسُه يُطبع «غير مقيس» ولا يُعدّ نجاحاً.
set -uo pipefail
export DJANGO_SETTINGS_MODULE=shschool.settings.testing
export TEST_DB_HOST="${TEST_DB_HOST:-${DB_HOST:-localhost}}" TEST_DB_PORT="${TEST_DB_PORT:-${DB_PORT:-5432}}"
export TEST_DB_USER="${TEST_DB_USER:-${DB_USER:-test_user}}" TEST_DB_PASSWORD="${TEST_DB_PASSWORD:-${DB_PASSWORD:-test_pass}}"

start=$(date +%s)
if ! action=$(python scripts/session_test_db.py | tail -1); then
  echo "غير مقيس: تعذّر تجهيزُ قاعدة الاختبار (المحرك لا يعمل) — لا نتيجةَ اختبارٍ تُعتمد."
  exit 3
fi
echo "قاعدة الاختبار: $action ($(( $(date +%s) - start )) ث)"

python -m pytest --reuse-db -q -p no:cacheprovider "$@"
rc=$?
echo "الزمنُ حتى أول نتيجة ($action): $(( $(date +%s) - start )) ث"

if ! python -c "import mypy" 2>/dev/null; then
  echo "غير مقيس: mypy غير مثبّتة في هذه البيئة (pip install -r requirements-mypy.txt)."
fi
exit $rc
