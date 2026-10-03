"""[LEGAL] علَمُ محو سجلّ الرصد مفتاحٌ لا إذن — لا يظهر اسمُه إلّا في موضعه (W-20261002-020، حكمُ 0105 N3).

مشغّلُ القاعدة على جدولَي السجلّ يسمح بالحذف وحدَه حين تضبط المعاملةُ `app.attendance_erasure = 'on'`. وأيُّ كودٍ في
التطبيق يستطيع ضبطَه، فلا يحمي منه إلّا أن يُرى. هذا الحارسُ يمسح الشيفرة ويُسقط أيَّ ظهورٍ لاسم العلَم
أو لثابته `ERASURE_FLAG` أو لدالّة المحو خارج المواضع المسمّاة. والمستدعي الوحيدُ لدالّة المحو `ErasureService`.
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP_PARTS = {"tests", "migrations", "node_modules", ".venv", "venv", ".claude", "staticfiles"}

#: الموضعُ → سببُه.
FLAG_NAME_ALLOWED = {
    "operations/models/attendance_ledger.py": "تعريفُ الثابت ERASURE_FLAG",
}
FLAG_CONSTANT_ALLOWED = {
    "operations/models/attendance_ledger.py": "تعريفُ الثابت",
    "operations/attendance_entries.py": "erase_attendance_ledger: الضبطُ المحلّيّ في معاملة المحو",
}
ERASE_CALLERS_ALLOWED = {
    "operations/attendance_entries.py": "تعريفُ الدالّة",
    "operations/models/attendance_ledger.py": "إشارةٌ في الوثيقة (docstring) لا استدعاء",
    "governance/erasure_service.py": "ErasureService — المسارُ الوحيد المشروع",
}


def _sources():
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if (
            set(rel.parts) & SKIP_PARTS
            or path.name.startswith("test_")
            or path.name == "conftest.py"
        ):
            continue
        yield rel.as_posix(), path.read_text(encoding="utf-8")


def _offenders(needle: str, allowed: dict[str, str]) -> list[str]:
    return sorted(rel for rel, text in _sources() if needle in text and rel not in allowed)


def test_the_erasure_flag_name_appears_only_where_it_is_defined():
    assert _offenders("app.attendance_erasure", FLAG_NAME_ALLOWED) == []


def test_the_erasure_flag_constant_is_used_only_by_the_erasure_function():
    assert _offenders("ERASURE_FLAG", FLAG_CONSTANT_ALLOWED) == []


def test_only_the_erasure_service_calls_the_ledger_eraser():
    assert _offenders("erase_attendance_ledger", ERASE_CALLERS_ALLOWED) == []


def test_the_raw_eraser_is_only_called_inside_the_erasure_function():
    """`_erase()` على استعلام السجلّ — حذفٌ خامٌّ بلا حارس — لا يُستدعى إلّا من دالّة المحو."""
    offenders = sorted(
        rel
        for rel, text in _sources()
        if "._erase()" in text and rel != "operations/attendance_entries.py"
    )
    assert offenders == []
