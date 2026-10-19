"""[CAPABILITIES-SNAPSHOT] `registry()` يطابق لقطتَه المثبَّتة حقلاً حقلاً وبالترتيب نفسه (W-20261019-007).

تقسيمُ `core/capabilities` إلى حزمةٍ بالمجالات لا يغيّر قدرةً ولا حاملاً ولا أساساً ولا ترتيبَ مفتاح.
فمن غيّر سجلَّ القدرات عن قصدٍ حدّث اللقطة بـ `python -m tests.test_capabilities_snapshot --update`
وعرض الفرقَ في المراجعة؛ ومن قسّم الملفَّ لم تتغيّر اللقطة.
"""

import json
from pathlib import Path

SNAPSHOT = Path(__file__).with_name("capabilities_registry_snapshot.json")


def _grant_fingerprint(grant) -> str | None:
    """المنحُ دالّةٌ: اسمُها المؤهَّل بلا الوحدة (فنقلُها بين ملفّات الحزمة لا يغيّر اللقطة)، ومعه مفتاحُ القدرة المفوَّضة إن كانت مغلقاً من `_delegated`."""
    if grant is None:
        return None
    closure = [
        c.cell_contents for c in (grant.__closure__ or ()) if isinstance(c.cell_contents, str)
    ]
    return grant.__qualname__ + (f"[{','.join(closure)}]" if closure else "")


def snapshot() -> list[dict]:
    from core.capabilities import registry

    return [
        {
            "key": cap.key,
            "label": cap.label,
            "roles": sorted(cap.roles),
            "scope": cap.scope,
            "basis": cap.basis,
            "grant": _grant_fingerprint(cap.grant),
            "not_inherited_by": sorted(cap.not_inherited_by),
        }
        for cap in registry().values()
    ]


def test_the_registry_matches_its_pinned_snapshot_field_by_field_and_in_order():
    pinned = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    current = snapshot()
    assert [c["key"] for c in current] == [
        c["key"] for c in pinned
    ], "تغيّر ترتيبُ المفاتيح أو مجموعُها"
    changed = [now["key"] for now, was in zip(current, pinned, strict=True) if now != was]
    assert not changed, f"تغيّرت حقولُ القدرات: {changed} — حدِّث اللقطة عن قصدٍ فقط"


if __name__ == "__main__":
    import os
    import sys

    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shschool.settings.testing")
    django.setup()
    if "--update" in sys.argv:
        SNAPSHOT.write_text(
            json.dumps(snapshot(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print("حُدِّثت اللقطة:", len(snapshot()), "قدرة")
