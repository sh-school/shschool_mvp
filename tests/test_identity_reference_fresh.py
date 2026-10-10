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
    assert (
        gen.OUT.read_text(encoding="utf-8") == gen.build()
    ), "مرجع الهويّة متقادم — شغّل: python scripts/gen_identity_reference.py"


def test_the_reference_loads_for_ui_files_only():
    head = gen.OUT.read_text(encoding="utf-8").split("---")[1]
    assert '"static/**"' in head and '"templates/**"' in head
