"""[CALENDAR] استعلامات الشُّعب مقيَّدةٌ بعامها — عطبٌ نائمٌ يستيقظ عند الترفيع.

`ClassGroup` يحمل `academic_year`، ولا شيء يُعطّل شُعب العام المنقضي: الصفّ
يُنشأ لعامه ويبقى `is_active=True`. وسبعةَ عشر استعلاماً كانت تُرشّح بالنشاط
وحده — تعمل اليوم لسببٍ واحد فقط: **لم تُنشأ شُعبٌ لعام 2026-2027 بعد**.

وفي اللحظة التي تُدخل فيها المدرسة شُعب العام الجديد تستيقظ كلّها معاً:

    القوائم المنسدلة    تعرض شُعب عامين
    استيراد الطلاب      `.first()` تُعيد شعبةً عشوائية — فيُسجَّل الطالب في
                        شعبة العام الماضي
    استيراد الجدول      خريطة الشُّعب تخلط العامين
    تقرير الاختبارات    يقارن شعبةَ عامٍ بشعبة آخر

وثلاثة عشر استعلاماً كانت مقيَّدةً بالعام أصلاً — فالتقييد هو القصد، لا اجتهاد.

والاستعلام بالمعرّف (`id=` أو `id__in=`) لا يُقيَّد: المعرّف يحمل عامه معه.
"""

import ast
import pathlib

SKIP = (
    "/.venv/",
    "/node_modules/",
    "/.claude/",
    "/.mypy_cache/",
    "/migrations/",
    "/tests/",
    "/_archive/",
    "/scripts/",
)

#: مفاتيح تُغني عن التقييد — المعرّف يحمل عام شعبته.
BY_IDENTITY = {"id", "id__in", "pk", "pk__in"}


def _classgroup_filters():
    for f in sorted(pathlib.Path(".").rglob("*.py")):
        if any(x in "/" + f.as_posix() for x in SKIP):
            continue
        src = f.read_text(encoding="utf-8", errors="ignore")
        if "ClassGroup" not in src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            fn = n.func
            if not (isinstance(fn, ast.Attribute) and fn.attr in ("filter", "exclude")):
                continue
            if "ClassGroup" not in ast.unparse(n):
                continue
            yield f"{f.as_posix()}:{n.lineno}", {k.arg or "" for k in n.keywords}


def test_the_sweep_finds_the_queries():
    """حارسٌ يمسح لا شيء يمرّ دائماً."""
    found = list(_classgroup_filters())

    assert len(found) >= 25, len(found)


def test_every_class_group_query_is_scoped_to_a_year_or_an_identity():
    """شعبةٌ بلا عامٍ ولا معرّف تعبر الأعوام."""
    unscoped = [
        where
        for where, keys in _classgroup_filters()
        if not any(k.startswith("academic_year") for k in keys) and not (keys & BY_IDENTITY)
    ]

    assert not unscoped, "استعلام شُعبٍ بلا عام:\n" + "\n".join(unscoped)


def test_the_student_import_names_the_year_when_it_finds_no_section():
    """رسالةٌ لا تذكر العام تُقرأ «الشعبة غير موجودة» وهي موجودةٌ في عامٍ آخر."""
    src = pathlib.Path("core/views_students.py").read_text(encoding="utf-8")

    assert "غير موجود في {year}" in src
