"""تسجيلُ زمن تحميل صفحة التفصيل — طلبُ المالك 2026-09-30 لمتابعة أثر التحسينات
بأرقامٍ فعليّة لا انطباعِ بطء. سجلٌّ JSON بسيطٌ في `logs/` (مُستثنًى من غيت،
`.gitignore`) — آخر `PERF_LOG_MAX_ENTRIES` فقط، لا نموّاً بلا حدّ."""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.utils import timezone

PERF_LOG_PATH = Path(settings.BASE_DIR) / "logs" / "docs_viewer_perf.json"
PERF_LOG_MAX_ENTRIES = 200


def record_load(doc_path: str, tree_ms: float, total_ms: float) -> None:
    """يُلحق سطراً بسجلّ الأداء. فشلُ الكتابة (قرصٌ للقراءة فقط، مثلاً) لا يُسقط
    الصفحةَ — القياسُ أداةُ متابعةٍ لا جزءٌ من العرض نفسِه."""
    entry = {
        "at": timezone.now().isoformat(),
        "doc_path": doc_path,
        "tree_ms": round(tree_ms, 1),
        "total_ms": round(total_ms, 1),
    }
    try:
        PERF_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entries = []
        if PERF_LOG_PATH.is_file():
            try:
                entries = json.loads(PERF_LOG_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                entries = []
        entries.append(entry)
        entries = entries[-PERF_LOG_MAX_ENTRIES:]
        PERF_LOG_PATH.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass
