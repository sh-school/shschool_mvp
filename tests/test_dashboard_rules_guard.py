"""حارسٌ نصّيٌّ لقاعدتَي اللوحات (`.claude/rules/dashboards.md`، D-171م، W-20261003-036).

سقّاطةٌ: الاستثناءاتُ المسمّاةُ دَينٌ معلنٌ بسببه وبطاقته، ويفشل الحارسُ إن أُصلح أحدُها وبقي مسمّى.
"""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_ROLES = ROOT / "templates" / "dashboard" / "roles"
SELECTORS = ROOT / "core" / "dashboard_selectors.py"

# ١) قوالبُ رأسٍ لا يظهر فيها اسمُ طالب (المدير يرى العددَ والرابط).
NO_STUDENT_NAMES = ("director.html",)
NAME_USES = re.compile(r"\.student\.full_name|student\.full_name|\.student\.name")
NAMES_DEBT = {"director.html": "تنبيهاتُ الغياب تعرض أسماء الطلبة للمدير — تنتظر بطاقة تنفيذ D-171م"}

# ٢) دوالُّ سياقٍ مشتركةٌ بين أدوار (تأخذ role) تحمل فحصَ قدرةٍ أو نطاقاً.
# `student_scope` يقيّد قوائمَ الطلبة لا العدّادات (وُجد في get_admin_ops_ctx وعدّاداتُه بلا قدرة)، فلا يكفي وحدَه.
GUARD_CALLS = {"has_capability"}
COUNTER_DEBT = {
    "get_admin_ops_ctx": "عدّاداتٌ بمستوى المدرسة بلا فحص قدرة — W-20261003-030 عند 0105",
    "get_teacher_ctx": "فرعُ المنسّق يُحصر بقيمة role لا بقدرة — يراجعه 0105 مع W-030",
    "get_service_ctx": "فروعُ الممرّض والمكتبي والفنّي تُحصر بقيمة role لا بقدرة — يراجعه 0105 مع W-030",
}


def _calls(node):
    names = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            fn = sub.func
            names.add(fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", ""))
    return names


def _shared_ctx_functions():
    tree = ast.parse(SELECTORS.read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.FunctionDef)
            and node.name.startswith("get_")
            and node.name.endswith("_ctx")
        ):
            if "role" in [a.arg for a in node.args.args]:
                yield node


def test_the_guard_sees_its_files():
    assert (DASHBOARD_ROLES / "director.html").exists()
    assert list(_shared_ctx_functions()), "لا دالّةَ سياقٍ مشتركة — تغيّرت البنية فحدِّث الحارس"


def test_director_head_shows_no_student_names_except_named_debt():
    offenders = {
        name
        for name in NO_STUDENT_NAMES
        if NAME_USES.search((DASHBOARD_ROLES / name).read_text(encoding="utf-8"))
    }
    assert offenders <= set(
        NAMES_DEBT
    ), f"اسمُ طالبٍ في رأس لوحةٍ ممنوع (D-171م): {sorted(offenders - set(NAMES_DEBT))}"
    stale = set(NAMES_DEBT) - offenders
    assert not stale, f"أُصلح ولم يُحذف من NAMES_DEBT: {sorted(stale)}"


def test_shared_context_counters_check_capability_or_scope():
    unguarded = {fn.name for fn in _shared_ctx_functions() if not (_calls(fn) & GUARD_CALLS)}
    assert unguarded <= set(
        COUNTER_DEBT
    ), f"عدّادٌ مشتركٌ بلا فحص قدرةٍ ولا نطاق (قاعدة 0105): {sorted(unguarded - set(COUNTER_DEBT))}"
    stale = set(COUNTER_DEBT) - unguarded
    assert not stale, f"أُصلح ولم يُحذف من COUNTER_DEBT: {sorted(stale)}"
