"""بياناتٌ خاصّةٌ لا تُودَع في المستودع العامّ: ملفّاتُ JSON خارجه (REP-07b).

أسماءُ الموظّفين الكاملةُ وقواعدُ ربطها بيانٌ شخصيٌّ (PDPPL)، والمستودعُ عامّ. فتُقرأ أدواتُ الاستيراد من ملفٍّ
يحدّده متغيّرُ بيئةٍ أو يقع في `data/` (يتجاهله git). وغيابُ الملفّ أو فسادُه «لا شيء» لا انهيار.
"""

import json
import os
from pathlib import Path

from django.conf import settings


def load_private_json(env_var: str, default_relpath: str):
    """محتوى ملفّ JSON خاصّ، أو None إن غاب أو فسد. المسارُ من متغيّر البيئة وإلّا `BASE_DIR/<default_relpath>`."""
    path = Path(os.environ.get(env_var) or Path(settings.BASE_DIR) / default_relpath)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_private_mapping(env_var: str, default_relpath: str) -> dict[str, str]:
    """جدولٌ نصّيٌّ {مفتاح: قيمة} من ملفّ JSON خاصّ؛ فارغٌ إن غاب أو فسد أو لم يكن قاموساً."""
    data = load_private_json(env_var, default_relpath)
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}
