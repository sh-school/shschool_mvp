"""جردُ التصدير (W-20261021-005): كلُّ دالّةٍ تُخرج ملفّاً تُسجِّل `log_export` أو تُدرج هنا بسببها، وترويسةُ التنزيل واحدة.

* `UNLOGGED_FILE_RESPONSES` سقّاطةٌ تنقص ولا تزيد: دالّةٌ جديدةٌ تُخرج ملفّاً بلا `log_export` تُفشل الحارس.
* لا `Content-Disposition` يُبنى يدويّاً: كلُّه عبر `core.pdf_utils.content_disposition` (تشفيرُ العربيّ واسم ASCII احتياطيّ في موضعٍ واحد).
"""

import re

from tests import export_scan
from tests.export_scan import _py_files

#: دوالُّ تُخرج ملفّاً بلا `log_export` مباشرةً — لكلٍّ سببُها؛ وتنقص بتسجيلها.
UNLOGGED_FILE_RESPONSES = {
    "behavior/views.py::behavior_policy_pdf": "وثيقةُ سياسةٍ ثابتةٌ عامّة لا بياناتَ شخصيّة فيها.",
    "core/views_students.py::_wb_to_response": "مساعدٌ يُسجِّل مستدعيه (student_export_excel وما يشبهه).",
    "docs_viewer/views.py::asset": "أصولُ وثائقَ المنصّة الثابتة (صورٌ) لا بياناتَ شخصيّة.",
    "governance/views_media.py::serve_db_file": "خدمةُ ملفٍّ مخزَّنٍ بتفويض fail-closed؛ ليست تصديراً (تُقدَّم المرفقاتُ لأصحابها).",
    "operations/absence_followup_print.py::build_followup_xlsx": "بنّاءٌ يسجّل مستدعيه followup_xlsx في الـview.",
    "student_affairs/views.py::protected_media": "خدمةُ مرفقٍ محميّ بتفويض الدور والجناح؛ ليست تصديراً.",
    "wings/views_excuse_document.py::excuse_document": "عرضُ مستندِ عذرٍ مرفوعٍ بتفويض الجناح؛ ليس تصديراً.",
}


def test_file_responses_without_log_export_only_shrink():
    found = export_scan.file_responses_without_log_export()

    added = found - set(UNLOGGED_FILE_RESPONSES)
    stale = set(UNLOGGED_FILE_RESPONSES) - found

    assert (
        not added
    ), f"دالّةٌ تُخرج ملفّاً بلا log_export — سجِّل التصدير (core.audit_export): {sorted(added)}"
    assert not stale, f"سُجِّلت أو حُذفت — احذفها من UNLOGGED_FILE_RESPONSES: {sorted(stale)}"


def test_content_disposition_is_built_only_by_the_helper():
    """لا بناءَ يدويّاً لترويسة التنزيل: العربيّ في الاسم يُفسدها بلا تشفير RFC 5987."""
    manual = re.compile(r"""\[["']Content-Disposition["']\]\s*=\s*(?!content_disposition\b)\S""")
    offenders = []
    for path, rel in _py_files():
        if rel == "core/pdf_utils.py":
            continue
        text = path.read_text(encoding="utf-8")
        if manual.search(text):
            offenders.append(rel)
    assert (
        not offenders
    ), f"ترويسةُ Content-Disposition تُبنى يدويّاً — استعمل content_disposition: {offenders}"


def test_absence_followup_pdf_button_goes_through_the_export_centre():
    """زرُّ «تصدير PDF» يمرّ بنقطة الملفّ (تنزيلٌ مسجَّل) لا بصفحة المعاينة، ويحمل data-app-file."""
    from pathlib import Path

    html = (
        Path(__file__).resolve().parent.parent / "templates/operations/absence_followup/base.html"
    ).read_text(encoding="utf-8")
    # الوسمُ الموحَّد يملك الشكل (الاسم و`data-app-file`)؛ والقالبُ يمرّر المسارَ وdownload=1 وحدَهما
    line = next(ln for ln in html.splitlines() if 'export_button "pdf"' in ln)
    assert "absence_followup_pdf" in line and "download=1" in line


def test_excuse_document_exception_still_audits_every_open():
    """استثناءُ excuse_document من log_export سببُه تدقيقٌ بديل: يسقط الاستثناءُ إن زال نداءُ `_log` بـOPENED وDENIED."""
    import ast
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "wings/views_excuse_document.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    func = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "excuse_document"
    )
    events = {
        a.id
        for c in ast.walk(func)
        if isinstance(c, ast.Call) and getattr(c.func, "id", "") == "_log"
        for a in c.args
        if isinstance(a, ast.Name)
    }
    assert {"OPENED", "DENIED"} <= events
