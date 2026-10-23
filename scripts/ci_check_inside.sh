#!/usr/bin/env bash
# يعمل داخل حاوية docker-compose.check.yml (لا من المضيف): يثبّت أدوات البوّابة بإصداراتها ثمّ يشغّل فحوصها الخالية من git.
# فحوصٌ تحتاج مستودع git (detect-secrets وحرّاس الهويّة وتصادم الهجرات) لا تعمل داخل شجرة عملٍ مربوطة: تبقى `make prepush` على المضيف.
set -uo pipefail
pip install -q -r requirements-mypy.txt ruff==0.4.4 radon==6.0.1 || { echo "غير مقيس: تعذّر تثبيت أدوات البوّابة"; exit 3; }
rc=0
python -m ruff format --check . || rc=1
python scripts/quality_numbers.py --strict || rc=1
echo "غير مقيس هنا (تعمل بـmake prepush على المضيف): detect-secrets، حرّاس الهويّة، تصادم الهجرات"
exit $rc
