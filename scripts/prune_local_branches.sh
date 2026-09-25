#!/bin/bash
# scripts/prune_local_branches.sh — فروعٌ محلّيّةٌ محتواها في main فعلاً، ولو باسمٍ آخر أو بدمجٍ مسحوق.
#
# الحكمُ بالمحتوى لا بالسلفيّة (REP-10، RD5): المنطقُ كلُّه في `scripts/prune_local_branches.py` (وتحرسه
# `tests/test_prune_local_branches.py` في بوّابة الدمج) — هذا الملفُّ مُشغِّلٌ يُبقي الأمرَ المعروف.
#
#   scripts/prune_local_branches.sh                # عرضٌ فقط، لا حذف ولا وسم
#   scripts/prune_local_branches.sh --archive      # يَسِم فروعَ REVIEW بوسمٍ محلّيّ (لا يحذف)
#   scripts/prune_local_branches.sh --apply        # يحذف ما صُنِّف آمناً وحدَه (حتّى 50 فرعاً في المرّة)
#   scripts/prune_local_branches.sh --json         # مخرَجٌ آليّ فيه RK1..RK3 وسقفُ RD5
#
# فرعٌ فيه إيداعاتٌ غيرُ مدموجةٍ (REVIEW) لا يُحذف آليّاً أبداً: يُوسَم أوّلاً بـ--archive ثمّ يُحذف بـ--apply.
set -euo pipefail

PYBIN=""
for candidate in python3 python py; do
  # ويندوز: python3 قد يكون مُشغِّلَ متجرٍ لا يعمل؛ فنجرّب كلَّ اسمٍ لا نكتفي بوجوده في PATH
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys" >/dev/null 2>&1; then
    PYBIN="$candidate"
    break
  fi
done
if [ -z "$PYBIN" ]; then
  echo "python not found" >&2
  exit 2
fi

exec "$PYBIN" "$(dirname "${BASH_SOURCE[0]}")/prune_local_branches.py" "$@"
