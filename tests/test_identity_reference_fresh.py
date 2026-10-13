"""مرجعُ الهويّة المولَّد لا يتقادم عن مصادره (W-20261011-001).

`.claude/rules/identity-reference.md` يُحمَّل في جلسةٍ تلمس الواجهة؛ لو بقي على لونٍ أو أيقونةٍ حُذفت
أو أُضيفت قرأت الجلسةُ مرجعاً كاذباً. التجديد: `python scripts/gen_identity_reference.py`.
"""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "gen_identity_reference", Path("scripts/gen_identity_reference.py")
)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def test_the_generated_identity_reference_matches_its_sources():
    for path, text in gen.build().items():
        assert (
            path.read_text(encoding="utf-8") == text
        ), f"{path.name} متقادم — شغّل: python scripts/gen_identity_reference.py"


def test_the_reference_loads_for_ui_files_only():
    for path in gen.build():
        head = path.read_text(encoding="utf-8").split("---")[1]
        assert '"static/**"' in head and '"templates/**"' in head, path.name


def test_each_identity_file_stays_within_the_constitution_limit():
    """سقّاطةُ حجم الدستور (200 سطر) — كي لا يعود الملفُّ الواحد فيسقط الدمج."""
    for path, text in gen.build().items():
        assert len(text.splitlines()) <= 200, f"{path.name} تجاوز 200 سطر — قسّمه في المولّد"
