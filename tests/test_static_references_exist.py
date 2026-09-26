"""[DEPLOY] كلُّ `{% static '…' %}` في القوالب يشير إلى ملفٍّ موجود (VI-30أ).

`{% static %}` صارمٌ بـmanifest في الإنتاج (`CompressedManifestStaticFilesStorage`): مرجعٌ إلى ملفٍّ محذوفٍ أو مُعاد تسميتُه يرمي
`Missing staticfiles manifest entry` فتسقط الصفحةُ كلُّها بـ500 — لا في التطوير الذي لا يفحص (`USE_FINDERS`). وقد وقع هذا الخطرُ في التنسيق بين طلبَين:
حذفُ `schedule-export.js` في طلبٍ وبقاءُ سطرِ تحميله في قالبٍ أضافه طلبٌ آخر. فالحارسُ هنا يُمسك المرجعَ اليتيمَ قبل الدمج.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: `{% static 'path' %}` أو `{% static "path" %}` بمسارٍ حرفيٍّ (لا متغيّر).
STATIC_TAG = re.compile(r"""\{%\s*static\s+(['"])([^'"{}]+)\1\s*%\}""")

#: ملفّاتٌ لا تُخدَم من مجلّدات الأصول في المستودع: لوحةُ Django الإداريّة وأدواتُ التطوير تأتي من حزمها.
THIRD_PARTY_PREFIXES = ("admin/", "debug_toolbar/", "rest_framework/", "django_extensions/")


def _static_roots() -> list[pathlib.Path]:
    return [ROOT / "static", *sorted(p for p in ROOT.glob("*/static") if p.is_dir())]


def _templates() -> list[pathlib.Path]:
    roots = [ROOT / "templates", *sorted(p for p in ROOT.glob("*/templates") if p.is_dir())]
    return [path for root in roots for path in sorted(root.rglob("*.html"))]


def _exists(name: str) -> bool:
    return any((root / name).is_file() for root in _static_roots())


def test_every_static_reference_in_a_template_points_to_a_file():
    missing = []
    for template in _templates():
        for _quote, name in STATIC_TAG.findall(template.read_text(encoding="utf-8")):
            if name.startswith(THIRD_PARTY_PREFIXES):
                continue
            if not _exists(name):
                missing.append(f"{template.relative_to(ROOT).as_posix()}: {name}")
    assert not missing, (
        "مراجعُ `{% static %}` إلى ملفّاتٍ غيرِ موجودة — تُسقط الصفحةَ بـ500 في الإنتاج "
        "(Missing staticfiles manifest entry):\n  " + "\n  ".join(missing)
    )


def test_the_detector_sees_a_reference_and_ignores_a_variable():
    text = "{% static 'js/a.js' %} {% static \"css/b.css\" %} {% static path %} {% static 'x/{{ v }}' %}"
    assert [name for _q, name in STATIC_TAG.findall(text)] == ["js/a.js", "css/b.css"]


def test_the_guard_scans_a_meaningful_number_of_references():
    total = sum(len(STATIC_TAG.findall(t.read_text(encoding="utf-8"))) for t in _templates())
    assert total >= 30, f"لم يُقرأ إلّا {total} مرجعاً — المسحُ فارغ"
