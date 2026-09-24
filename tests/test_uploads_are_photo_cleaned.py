"""[PDPPL] كلُّ مدخلِ رفعٍ يمرّ بتنظيف الصورة أو يُسمّى سببُ إعفائه.

`request.FILES` بابٌ تدخل منه صورةُ جوّالٍ بإحداثيّاتها. قرارُ 2026-09-14: ما يُحفظ من صورٍ (تقريرٌ طبّيٌّ،
إذنُ وليّ أمر) يمرّ بـ`core.photo_privacy.clean_photo` — يحوّلها JPEG مصغّراً ويمحو EXIF وXMP. وكان مدخلُ
`tardiness_record` خارجَه فلم يمنعه أحد.

كلُّ دالّةٍ تقرأ `.FILES` في الشيفرة:
- تستدعي `clean_photo` — أو
- في `NOT_PHOTOS` (مصنّفاتٌ تُستورد: Excel وCSV لا صورَ) — أو
- في `VIA_SERVICE` (تمرّر الملفَّ إلى خدمةٍ تنظّفه) — أو
- في `KNOWN_UNCLEANED`: **دينٌ معلَن** لا يزيد ولا يُنسى؛ فمن نظّف واحداً منها أسقطه الحارسُ حتى يُحذَف من القائمة.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_PARTS = {".claude", "tests", "migrations", "staticfiles", "node_modules", ".venv", "docs"}

#: مصنّفاتٌ مستوردة — لا صورةَ فيها.
NOT_PHOTOS = {
    "core/views_students.py::student_import_export": "مصنَّفُ Excel لاستيراد الطلبة",
    "staging/views.py::_validate_upload_request": "مصنَّفُ درجاتٍ يُستورد",
}

#: تمرّر الملفَّ إلى خدمةٍ تنظّفه (`operations.excuses.record_excuse` ← `clean_photo`).
VIA_SERVICE = {
    "wings/views.py::excuse_grant": "operations.excuses.grant_excuse",
    "wings/views_absence_file.py::absence_file_excuse": "operations.excuses.grant_excuse",
}

#: **دينٌ مسجَّل** — تُراجَع كلٌّ منها (هل تقبل صورةً؟ هل فيها بياناتٌ شخصيّةٌ أو صحّيّة؟) وتُنظَّف أو تُسمّى بسببها.
KNOWN_UNCLEANED = {
    "staff_affairs/views.py::leave_request_create": "مرفقُ طلب إجازةِ موظّف (قد يكون تقريراً طبّيّاً)",
    "staff_affairs/views_attendance.py::my_permits": "مرفقُ استثناءِ حضورِ موظّف",
    "student_affairs/views.py::activity_add": "مرفقُ نشاطٍ طلّابيّ (صورٌ فيها طلّاب)",
    "student_affairs/views.py::activity_edit": "مرفقُ نشاطٍ طلّابيّ (صورٌ فيها طلّاب)",
    "quality/views.py::upload_evidence": "دليلُ إجراءٍ في الجودة",
    "quality/views.py::_process_task_update": "دليلُ إجراءٍ في الجودة",
}


def _call_name(node):
    func = node.func
    return getattr(func, "id", getattr(func, "attr", ""))


def _functions_reading_files():
    """(مفتاح `path::function`، هل يمرّ بـ`clean_photo`) لكلّ دالّةٍ تقرأ `.FILES`.

    يمرّ بها إن استدعاها مباشرةً، أو استدعى دالّةً من الوحدة نفسها تستدعيها (مساعدُ فحصٍ واحد) —
    فاستخراجُ الفحص من عرضٍ طويلٍ (سقّاطةُ الطبقات) لا يُسقط الحارس.
    """
    found = {}
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT)
        if SKIP_PARTS & set(rel.parts) or path.name.startswith("test"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        functions = [
            fn for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef)
        ]
        calls = {
            fn.name: {_call_name(n) for n in ast.walk(fn) if isinstance(n, ast.Call)}
            for fn in functions
        }
        cleaners = {name for name, called in calls.items() if "clean_photo" in called}
        for fn in functions:
            if any(isinstance(n, ast.Attribute) and n.attr == "FILES" for n in ast.walk(fn)):
                found[f"{rel.as_posix()}::{fn.name}"] = bool(
                    calls[fn.name] & ({"clean_photo"} | cleaners)
                )
    return found


def test_every_upload_entry_point_cleans_the_photo_or_is_named():
    unnamed = [
        key
        for key, cleans in _functions_reading_files().items()
        if not cleans and key not in {*NOT_PHOTOS, *VIA_SERVICE, *KNOWN_UNCLEANED}
    ]
    assert not unnamed, (
        "مدخلُ رفعٍ جديدٌ بلا `clean_photo` ولا تسمية — نظِّف الصورةَ أو سمِّه في القوائم بسببه:\n  "
        + "\n  ".join(unnamed)
    )


def test_a_known_debt_that_was_cleaned_leaves_the_list():
    found = _functions_reading_files()
    fixed = [key for key in KNOWN_UNCLEANED if found.get(key)]
    assert not fixed, "نُظِّف ولم يُحذف من KNOWN_UNCLEANED — أحسنت، احذفه:\n  " + "\n  ".join(fixed)
    stale = [key for key in (*NOT_PHOTOS, *VIA_SERVICE, *KNOWN_UNCLEANED) if key not in found]
    assert not stale, "مسمًّى لا وجودَ له اليوم (نُقل أو حُذف):\n  " + "\n  ".join(stale)


def test_the_tardiness_upload_is_cleaned():
    assert _functions_reading_files()["student_affairs/views.py::tardiness_record"] is True
