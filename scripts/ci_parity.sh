#!/usr/bin/env bash
# فحصٌ محلّيٌّ بالأدوات والإصدارات نفسِها التي تحكم بها البوّابة (W-20261003-008) — أمرٌ واحد من جذر الشجرة:
#   bash scripts/ci_parity.sh            ← prepush الكامل + سطر أرقام الجودة، داخل حاويةٍ بقاعدةٍ تُعاد
# ما تعذّر (لا Docker، لا صورة) يُطبع «غير مقيس» ويخرج 3 — لا نجاحَ صامتاً.
set -uo pipefail
cd "$(dirname "$0")/.."
if ! docker info >/dev/null 2>&1; then
  echo "غير مقيس: Docker لا يعمل — شغّله ثمّ أعد (أو استعمل make prepush للفحوص السريعة بلا حاوية)."
  exit 3
fi
docker compose -f docker-compose.check.yml run --rm --build=false check
rc=$?
docker compose -f docker-compose.check.yml down -v --remove-orphans >/dev/null 2>&1
exit $rc
