"""مجموعاتُ الأدوار في `core/permissions.py` — لا في ملفّات الواجهات.

كانت ستَّ عشرةَ مجموعةً معرَّفةً في ملفّات واجهاتها: `_REPORT_ROLES` بنصّه في
الجدول والحضور، و`_QUALITY_ALL` بنصّه في الجودة وتقاريرها، واثنتان لا يستعملهما
أحد. ومجموعةٌ في ملفّ الواجهة لا يراها من يقرأ المركز، فتتغيّر الصلاحيّةُ ولا
يُعرف أين — ولا تبلغها دراسةُ الصلاحيّات حين تُحصي من يفتح ماذا.

فهذا الملفّ حارسان:

- **النقلُ لم يغيّر عضواً.** أعضاءُ كلّ مجموعةٍ منقولةٍ مثبَّتون هنا بما كانوا
  عليه قبل النقل. فمن غيّر أحدَها عمداً غيّر السطرَ هنا معه، وكان التغييرُ قراراً
  مرئيّاً في المراجعة لا أثراً جانبيّاً لإعادة ترتيب.
- **لا مجموعةَ جديدةً في ملفّ واجهات.** مجموعةٌ من أسماء أدوارٍ حرفيّةٍ على مستوى
  الوحدة في `views*.py` تُسقط الاختبار — إلّا ما استُثني باسمه وسببه.
"""

import ast
from pathlib import Path

import pytest

from core import permissions
from core.models.access import Role

ROOT = Path(__file__).resolve().parent.parent

#: الأعضاءُ كما كانوا في ملفّات الواجهات قبل النقل.
MOVED = {
    "OPERATIONS_REPORTS": {
        "principal",
        "vice_academic",
        "vice_admin",
        "coordinator",
        "admin_supervisor",
        "admin",
    },
    "SCHEDULE_ADMIN": {"principal", "vice_academic", "admin"},
    "SCHEDULE_SETTINGS": {"principal", "vice_academic", "platform_developer"},
    "SCHEDULE_BROWSE": {
        "principal",
        "vice_academic",
        "vice_admin",
        "coordinator",
        "e_projects_coordinator",
        "admin_supervisor",
        "admin",
    },
    "EXAM_CONTROL_ACCESS": {
        "principal",
        "vice_academic",
        "vice_admin",
        "coordinator",
        "admin_supervisor",
        "admin",
    },
    "STAFF_AFFAIRS_MANAGE": {"principal", "vice_admin", "vice_academic", "platform_developer"},
    "PARENT_PORTAL": {"parent", "principal", "vice_admin", "vice_academic", "admin"},
    "PARENT_PORTAL_ADMIN": {"principal", "admin"},
    "QUALITY_ACCESS": set(permissions.QUALITY_MANAGE)
    | set(permissions.QUALITY_VIEW)
    | {"ese_teacher"},
    "BEHAVIOR_STATS_TEACHING": {"teacher", "coordinator", "ese_teacher"},
    "WING_DAY_RECORD": {
        "admin_supervisor",
        "vice_admin",
        "vice_academic",
        "principal",
        "platform_developer",
    },
}

#: ما يبقى محلّيّاً عمداً — باسمه وسببه.
LOCAL_BY_DESIGN = {
    # سياسةُ أمانٍ للدخول لا صلاحيّةُ وصول: من يُلزَم بالتحقّق الثنائيّ.
    ("core/views_auth.py", "ROLES_REQUIRING_2FA"),
    # تختار اللوحةُ بها أيَّ تخطيطٍ تعرض، ولا تفتح شيئاً ولا تمنعه.
    ("core/views_dashboard.py", "_DIRECTOR_ROLES"),
    ("core/views_dashboard.py", "_TEACHER_ROLES"),
    ("core/views_dashboard.py", "_SPECIALIST_SOCIAL_ROLES"),
    ("core/views_dashboard.py", "_THERAPIST_ROLES"),
    ("core/views_dashboard.py", "_ADMIN_OPS_ROLES"),
    ("core/views_dashboard.py", "_SERVICE_ROLES"),
    ("core/views_dashboard.py", "_TRANSPORT_ROLES"),
}

_ROLE_NAMES = {name for name, _ in Role.ROLES}
_SKIP_DIRS = {
    "tests",
    "node_modules",
    ".venv",
    "venv",
    "static",
    "staticfiles",
    "templates",
    "AAdocs",
    "docs",
}


@pytest.mark.parametrize("name", sorted(MOVED))
def test_moved_group_kept_its_members(name):
    assert set(getattr(permissions, name)) == MOVED[name]


@pytest.mark.parametrize("name", sorted(MOVED))
def test_moved_group_is_immutable(name):
    """مجموعةٌ مشتركةٌ بين ملفّات يُضاف إليها في أحدها فتتّسع في كلّها."""
    assert isinstance(getattr(permissions, name), frozenset)


def _literal_role_groups(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)):
            continue
        value = node.value
        if isinstance(value, ast.Call) and getattr(value.func, "id", "") == "frozenset":
            value = value.args[0] if value.args else None
        if not isinstance(value, (ast.Set, ast.Tuple, ast.List)) or not value.elts:
            continue
        if all(isinstance(e, ast.Constant) and e.value in _ROLE_NAMES for e in value.elts):
            yield node.targets[0].id, node.lineno


def _view_files():
    for app in sorted(ROOT.iterdir()):
        if not app.is_dir() or app.name in _SKIP_DIRS or app.name.startswith("."):
            continue
        for path in app.rglob("*.py"):
            rel = path.relative_to(ROOT)
            if "migrations" in rel.parts:
                continue
            if path.name.startswith("views") or "views" in rel.parts[:-1]:
                yield path


def test_no_role_group_is_defined_in_a_views_file():
    found = []
    for path in _view_files():
        rel = path.relative_to(ROOT).as_posix()
        for name, line in _literal_role_groups(path):
            if (rel, name) not in LOCAL_BY_DESIGN:
                found.append(f"{rel}:{line} {name}")
    assert not found, (
        "مجموعةُ أدوارٍ في ملفّ واجهات — انقلها إلى core/permissions.py باسمٍ يقول معناها:\n  "
        + "\n  ".join(sorted(found))
    )


def test_every_exception_still_exists():
    """استثناءٌ زال صاحبُه يُحذف — وإلّا صار بابَ مرورٍ لمجموعةٍ جديدة بالاسم نفسه."""
    present = set()
    for path in _view_files():
        rel = path.relative_to(ROOT).as_posix()
        present |= {(rel, name) for name, _ in _literal_role_groups(path)}
    assert LOCAL_BY_DESIGN <= present, sorted(LOCAL_BY_DESIGN - present)
