"""[MULTI-TENANT] هوية المدرسة متغيّرة لا ثابتة.

المنصّة متعدّدة المدارس، فاسمُ مدرسةٍ بعينها أو هاتفها أو بريدها مكتوباً في
قالبٍ يعني أن وثائق **كل** مدرسة تحمل بيانات واحدةٍ منها.

وكان ذلك في ٤٨ موضعاً: ستّةٌ نصّاً عارياً — أخطرها ذيل وثائق السلوك بالهاتف
والبريد — و٤٢ بديلاً خلف متغيّر. والبديل ليس بريئاً: إن غاب المتغيّر ظهر اسم
مستأجرٍ بعينه لمستأجرٍ آخر، وهو تسريبُ هويةٍ لا مجرّد نصٍّ خاطئ.

والحالة الأشدّ كانت في `base_qatar_report.html`: القالب يطلب `school_name`
ولا أحد يمرّره، فالبديل المُثبَّت هو المسار **الوحيد** لا الاحتياط.
"""

import pathlib
import re

import pytest

#: بياناتُ مستأجرٍ بعينه — لا يجوز ورودها في أيّ قالب.
TENANT_LITERALS = [
    "مدرسة الشحانية",
    "لمدرسة الشحانية",
    "44994205",
    "ashahanyia",
    "الشحانية، قطر",
]


def _template_roots():
    yield pathlib.Path("templates")
    for app in sorted(pathlib.Path(".").glob("*/templates")):
        if app.is_dir():
            yield app


def _all_templates():
    for root in _template_roots():
        yield from sorted(root.rglob("*.html"))


@pytest.mark.parametrize("literal", TENANT_LITERALS)
def test_no_template_hardcodes_tenant_identity(literal):
    hits = [
        f"{f.as_posix()}:{i}"
        for f in _all_templates()
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1)
        if literal in line
    ]

    assert not hits, f"«{literal}» مُثبَّتة في: {hits}"


def test_the_report_base_reads_the_school_object():
    """`school_name` كان يُطلب ولا يُمرَّر — فالنصّ المُثبَّت هو السلوك لا الاحتياط."""
    src = pathlib.Path("templates/reports/base_qatar_report.html").read_text(encoding="utf-8")

    assert "{{ school.name }}" in src
    assert not re.search(r"{{\s*school_name", src)


def test_the_behavior_document_footer_reads_the_school_object():
    src = pathlib.Path("templates/behavior/pdf/base_form.html").read_text(encoding="utf-8")

    assert "{{ school.name }}" in src
    assert "{{ school.phone }}" in src


@pytest.mark.parametrize(
    "doc",
    [
        "templates/reports/base_qatar_report.html",
        "templates/behavior/pdf/base_form.html",
        "templates/quality/observation_pdf.html",
    ],
)
def test_document_footers_do_not_freeze_the_year(doc):
    """`© 2026` تكذب في يناير."""
    src = pathlib.Path(doc).read_text(encoding="utf-8")

    assert "© 2026" not in src


# ═══════════════════════════════════════════════════════════════════
#  بايثون كذلك — لا القوالب وحدها
# ═══════════════════════════════════════════════════════════════════

_PY_SKIP = ("/.venv/", "/node_modules/", "/worktrees/", "/migrations/", "/tests/")

#: بذورُ بياناتٍ لمدرسةٍ بعينها — بياناتٌ لا شيفرةُ تشغيل، فذكرُ الاسم فيها هو
#: المقصود. وما عداها يُحرَس.
_PY_ALLOWED = (
    "core/management/commands/full_seed.py",
    "core/management/commands/seed.py",
    "scripts/real_seed.py",
    "scripts/seed_data.py",
    "scripts/seed_all.py",
    "operations/management/commands/seed_class_subjects.py",
)


def _python_sources():
    for f in pathlib.Path(".").rglob("*.py"):
        path = "/" + f.as_posix()
        if any(x in path for x in _PY_SKIP) or f.as_posix() in _PY_ALLOWED:
            continue
        yield f, f.read_text(encoding="utf-8", errors="ignore")


@pytest.mark.parametrize("literal", TENANT_LITERALS)
def test_no_python_module_hardcodes_tenant_identity(literal):
    """الحارس الأوّل مسح القوالب وحدها، فمرّت ترويسة لوحة الإدارة:

        admin.site.site_header = "SchoolOS — مدرسة الشحانية"

    وهي تظهر لكل مستأجرٍ يفتح اللوحة. والدرس أن نطاق الفحص جزءٌ من الحارس:
    ما لا يُمسح لا يُحرَس.
    """
    hits = [
        f"{f.as_posix()}:{i}"
        for f, src in _python_sources()
        for i, line in enumerate(src.splitlines(), 1)
        if literal in line and not line.strip().startswith("#")
    ]

    assert not hits, f"«{literal}» مُثبَّتة في: {hits}"
