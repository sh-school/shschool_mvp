"""يطبّق تعديلاتِ الربط الأربعة لتطبيق local_ai على SchoolOS — آمنٌ للتكرار (لا يضيف ما هو موجود).

يُشغَّل من جذر المشروع:  .\\.venv\\Scripts\\python.exe scripts\\apply_local_ai_patches.py

1. `shschool/settings/base.py`  → إضافة التطبيق إلى INSTALLED_APPS + إعدادات LOCAL_AI_*
2. `shschool/urls.py`           → مسار `/ai/`
3. `shschool/celery.py`         → جدولُ Beat (مسحٌ كلَّ ساعة + إعادةُ المحاولة ليلاً)
4. `.env.example`               → توثيقُ المتغيّرات
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PATCHES: list[tuple[str, str, str, str]] = [
    (
        "shschool/settings/base.py",
        '    "docs_viewer.apps.DocsViewerConfig",\n',
        '    "docs_viewer.apps.DocsViewerConfig",\n'
        "    # الذكاءُ المحلّيّ (LM Studio على جهاز المدرسة): مساعدٌ وRAG وأتمتةٌ — لا يغادر البيانُ الجهاز\n"
        '    "local_ai.apps.LocalAiConfig",\n',
        '"local_ai.apps.LocalAiConfig"',
    ),
    (
        "shschool/settings/base.py",
        'PREF_MAX_GAP_ACTIVE = config("PREF_MAX_GAP_ACTIVE", default=False, cast=bool)\n',
        'PREF_MAX_GAP_ACTIVE = config("PREF_MAX_GAP_ACTIVE", default=False, cast=bool)\n'
        "\n"
        "# ── الذكاءُ المحلّيّ (local_ai) — خادمُ LM Studio على جهاز المدرسة ───────────\n"
        "# معطَّلٌ افتراضاً؛ فعّله في .env حيث يعمل LM Studio. لا مزوِّدَ خارجيّاً ولا مفتاحَ API.\n"
        'LOCAL_AI_ENABLED = config("LOCAL_AI_ENABLED", default=False, cast=bool)\n'
        'LOCAL_AI_BASE_URL = config("LOCAL_AI_BASE_URL", default="http://127.0.0.1:1234/v1")\n'
        'LOCAL_AI_CHAT_MODEL = config("LOCAL_AI_CHAT_MODEL", default="qwen/qwen3-8b")\n'
        'LOCAL_AI_EMBED_MODEL = config("LOCAL_AI_EMBED_MODEL", default="text-embedding-bge-m3")\n'
        'LOCAL_AI_TIMEOUT = config("LOCAL_AI_TIMEOUT", default=120, cast=int)\n'
        'LOCAL_AI_MAX_UPLOAD_MB = config("LOCAL_AI_MAX_UPLOAD_MB", default=20, cast=int)\n',
        "LOCAL_AI_ENABLED",
    ),
    (
        "shschool/urls.py",
        '    path("docs/", include("docs_viewer.urls")),\n',
        '    path("docs/", include("docs_viewer.urls")),\n'
        "    # الذكاءُ المحلّيّ: المساعدُ لكلّ موظّف، ووثائقُ المعرفة للقيادة (local_ai)\n"
        '    path("ai/", include("local_ai.urls", namespace="local_ai")),\n',
        '"local_ai.urls"',
    ),
    (
        ".env.example",
        "",
        "\n# ── الذكاءُ المحلّيّ (LM Studio على جهاز المدرسة) ──────────────────────────\n"
        "LOCAL_AI_ENABLED=false\n"
        "LOCAL_AI_BASE_URL=http://127.0.0.1:1234/v1\n"
        "LOCAL_AI_CHAT_MODEL=qwen/qwen3-8b\n"
        "LOCAL_AI_EMBED_MODEL=text-embedding-bge-m3\n"
        "LOCAL_AI_TIMEOUT=120\n",
        "LOCAL_AI_ENABLED",
    ),
]

CELERY_TAIL = (
    "\n# الذكاءُ المحلّيّ: مسحُ الفهرسة كلَّ ساعة وإعادةُ المحاولة ليلاً (local_ai/tasks.py)\n"
    "from local_ai.tasks import local_ai_beat  # noqa: E402\n"
    "\n"
    "app.conf.beat_schedule.update(local_ai_beat())\n"
)


def apply(rel: str, anchor: str, replacement: str, marker: str) -> str:
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return f"= {rel}: موجودٌ مسبقاً"
    if anchor:
        if anchor not in text:
            return f"✗ {rel}: لم أجد المرساة — أضف يدويّاً:\n{replacement}"
        text = text.replace(anchor, replacement, 1)
    else:
        text = text.rstrip("\n") + "\n" + replacement
    path.write_text(text, encoding="utf-8")
    return f"✓ {rel}: أُضيف"


def main() -> int:
    results = [apply(*patch) for patch in PATCHES]
    celery_path = ROOT / "shschool/celery.py"
    celery_text = celery_path.read_text(encoding="utf-8")
    if "local_ai_beat" in celery_text:
        results.append("= shschool/celery.py: موجودٌ مسبقاً")
    else:
        celery_path.write_text(celery_text.rstrip("\n") + "\n" + CELERY_TAIL, encoding="utf-8")
        results.append("✓ shschool/celery.py: أُضيف جدولُ Beat")
    print("\n".join(results))
    return 1 if any(r.startswith("✗") for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
