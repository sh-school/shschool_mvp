"""[LEGAL] مفتاحُ تجميد الأهل يُقرأ من دالّةٍ واحدة — لا قراءةَ مباشرةَ لـ`PARENTS_FROZEN` (W-20261008-013، D-268م).

موضعُ قراءةٍ واحدٌ يعني فكّاً واحداً وتدقيقاً واحداً. فمن قرأ `settings.PARENTS_FROZEN` في كودٍ آخر تجاوز الافتراضَ الآمن
(مجمَّدٌ عند غياب الإعداد) وفرّق المفتاحَ. هذا الحارسُ يمسح الشيفرة ويُسقط أيَّ ظهورٍ للاسم خارج المواضع المسمّاة.
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP_PARTS = {"tests", "migrations", "node_modules", ".venv", "venv", ".claude", "staticfiles"}

#: الموضعُ → سببُه.
ALLOWED = {
    "core/parents_freeze.py": "الدالّةُ الوحيدةُ التي تقرأ الإعداد",
    "shschool/settings/base.py": "تعريفُ المفتاح من البيئة",
    "shschool/settings/testing.py": "إطفاؤه في الاختبارات",
}


def test_nothing_reads_the_parents_frozen_setting_outside_the_one_function():
    offenders = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if (
            set(rel.parts) & SKIP_PARTS
            or path.name.startswith("test_")
            or path.name == "conftest.py"
        ):
            continue
        if rel.as_posix() in ALLOWED:
            continue
        if "PARENTS_FROZEN" in path.read_text(encoding="utf-8"):
            offenders.append(rel.as_posix())
    assert sorted(offenders) == []
