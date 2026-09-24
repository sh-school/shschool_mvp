"""[PDPPL] كلُّ مدخلِ رفعٍ يمرّ بتنظيف الصورة أو يُسمّى سببُ إعفائه.

`request.FILES` بابٌ تدخل منه صورةُ جوّالٍ بإحداثيّاتها. قرارُ 2026-09-14: ما يُحفظ من صورٍ (تقريرٌ طبّيٌّ،
إذنُ وليّ أمر) يمرّ بـ`core.photo_privacy.clean_photo` — يحوّلها JPEG مصغّراً ويمحو EXIF وXMP. وكان مدخلُ
`tardiness_record` خارجَه فلم يمنعه أحد.

كلُّ دالّةٍ تقرأ `.FILES` في الشيفرة:
- تستدعي `clean_photo` — أو
- في `NOT_PHOTOS` (مصنّفاتٌ تُستورد: Excel وCSV لا صورَ) — أو
- في `VIA_SERVICE` (تمرّر الملفَّ إلى خدمةٍ تنظّفه، ويتحقّق الحارسُ من ذلك) — أو
- في `DOCUMENTS_ONLY` (نموذجٌ لا يقبل صورةً أصلاً، ويثبت الحارسُ رفضَها) — أو
- في `KNOWN_UNCLEANED`: **دينٌ معلَن** لا يزيد ولا يُنسى؛ فمن نظّف واحداً منها أسقطه الحارسُ حتى يُحذَف من القائمة.
"""

import ast
import importlib
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

ROOT = Path(__file__).resolve().parent.parent
SKIP_PARTS = {".claude", "tests", "migrations", "staticfiles", "node_modules", ".venv", "docs"}

#: مصنّفاتٌ مستوردة — لا صورةَ فيها.
NOT_PHOTOS = {
    "core/views_students.py::student_import_export": "مصنَّفُ Excel لاستيراد الطلبة",
    "staging/views.py::_validate_upload_request": "مصنَّفُ درجاتٍ يُستورد",
}

#: تمرّر الملفَّ إلى خدمةٍ تنظّفه: {الدالّة: (ملفُّ الخدمة، السبب)} — ويتحقّق الحارسُ أنّ ملفَّ الخدمة يستدعي
#: `clean_photo` فعلاً، فلا يبقى الإعفاءُ ادّعاءً.
VIA_SERVICE = {
    "wings/views.py::excuse_grant": ("operations/excuses.py", "grant_excuse"),
    "wings/views_absence_file.py::absence_file_excuse": ("operations/excuses.py", "grant_excuse"),
    "staff_affairs/views_attendance.py::my_permits": (
        "staff_affairs/attendance/exceptions.py",
        "ExceptionService.submit (مرفقُ استثناء الموظّف، DBT-41)",
    ),
}

#: نماذجُ لا تقبل صورةً أصلاً: مدقّقُ الملفّ `document` (PDF وOffice وtxt) يرفض الامتدادات الصوريّة،
#: فلا EXIF يدخل من هذا الباب. {الدالّة: (وحدةُ النموذج، الصنف، الحقل)} — ويثبت الحارسُ الرفضَ فعلاً.
DOCUMENTS_ONLY = {
    "staff_affairs/views.py::leave_request_create": (
        "staff_affairs.forms",
        "LeaveRequestForm",
        "attachment",
    ),
    "student_affairs/views.py::activity_add": (
        "student_affairs.forms",
        "ActivityForm",
        "attachment",
    ),
    "student_affairs/views.py::activity_edit": (
        "student_affairs.forms",
        "ActivityForm",
        "attachment",
    ),
}

#: **دينٌ مسجَّل** — تُراجَع كلٌّ منها (هل تقبل صورةً؟ أهي بياناتٌ شخصيّةٌ أو صحّيّة؟) وتُنظَّف أو تُسمّى بسببها.
KNOWN_UNCLEANED = {
    "quality/views.py::upload_evidence": "دليلُ إجراءٍ: يفحص `document` بالامتداد (لا صور)، ولم يُثبَت ذلك بحارس",
    "quality/views.py::_process_task_update": (
        "دليلُ إجراءٍ من نافذة التحديث: **بلا أيّ فحصِ نوعٍ أو حجم** (يمرّر الملفَّ إلى الخدمة كما هو)"
    ),
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
        if not cleans and key not in {*NOT_PHOTOS, *VIA_SERVICE, *DOCUMENTS_ONLY, *KNOWN_UNCLEANED}
    ]
    assert not unnamed, (
        "مدخلُ رفعٍ جديدٌ بلا `clean_photo` ولا تسمية — نظِّف الصورةَ أو سمِّه في القوائم بسببه:\n  "
        + "\n  ".join(unnamed)
    )


def test_a_known_debt_that_was_cleaned_leaves_the_list():
    found = _functions_reading_files()
    fixed = [key for key in KNOWN_UNCLEANED if found.get(key)]
    assert not fixed, "نُظِّف ولم يُحذف من KNOWN_UNCLEANED — أحسنت، احذفه:\n  " + "\n  ".join(fixed)
    named = (*NOT_PHOTOS, *VIA_SERVICE, *DOCUMENTS_ONLY, *KNOWN_UNCLEANED)
    stale = [key for key in named if key not in found]
    assert not stale, "مسمًّى لا وجودَ له اليوم (نُقل أو حُذف):\n  " + "\n  ".join(stale)


def test_the_tardiness_upload_is_cleaned():
    assert _functions_reading_files()["student_affairs/views.py::tardiness_record"] is True


def test_a_service_named_as_the_cleaner_really_calls_clean_photo():
    for key, (module, _why) in VIA_SERVICE.items():
        text = (ROOT / module).read_text(encoding="utf-8")
        assert "clean_photo(" in text, f"{key}: {module} لا يستدعي clean_photo"


@pytest.mark.parametrize("key", sorted(DOCUMENTS_ONLY))
@pytest.mark.parametrize(
    "name",
    ["scan.jpg", "scan.jpeg", "scan.png", "scan.webp", "scan.heic", "scan.heif"],
)
def test_a_documents_only_form_refuses_every_photo_extension(key, name):
    """لا صورةَ تدخل من هذا الباب — فلا EXIF: مدقّقُ `document` يرفض الامتدادَ."""
    module, cls, field = DOCUMENTS_ONLY[key]
    validators = getattr(importlib.import_module(module), cls).base_fields[field].validators
    upload = SimpleUploadedFile(name, b"\xff\xd8\xff\xe0 not really")
    refused = 0
    for validator in validators:
        try:
            validator(upload)
        except ValidationError:
            refused += 1
    assert refused, f"{cls}.{field} يقبل {name} — نظِّفه بـ clean_photo أو أعِده إلى KNOWN_UNCLEANED"
