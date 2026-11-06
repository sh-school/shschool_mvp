"""حارسُ روابط المسارات الجديدة (`scripts/route_link_guard.py`) — W-20261106-025.

دوالُّ نقيّةٌ على نصوص diff: بلا قاعدةٍ ولا Django ولا git.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "route_link_guard", ROOT / "scripts" / "route_link_guard.py"
)
guard = importlib.util.module_from_spec(_spec)
sys.modules["route_link_guard"] = guard  # يحتاجه @dataclass مع تحميلٍ بلا استيراد
_spec.loader.exec_module(guard)


def _new_file(path: str, lines: list[str]) -> str:
    body = "\n".join("+" + line for line in lines)
    return f"diff --git a/{path} b/{path}\n--- /dev/null\n+++ b/{path}\n@@ -0,0 +1 @@\n{body}\n"


def _modified(path: str, added: list[str], context: list[str] | None = None) -> str:
    ctx = "".join(f" {c}\n" for c in context or [])
    body = "\n".join("+" + line for line in added)
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n{ctx}{body}\n"


URLS_MULTILINE = _modified(
    "students/urls.py",
    [
        "    path(",
        '        "movements/",',
        "        views.movements,",
        '        name="movements",',
        "    ),",
    ],
    context=['app_name = "students"'],
)
SELF_LINK_TEMPLATE = _new_file(
    "templates/students/movements.html", ["<a href=\"{% url 'students:movements' %}\">هنا</a>"]
)


def test_multiline_path_with_only_self_link_in_new_template_fails():
    # انحدار #1367: الرابط الذاتيّ في قالب الشاشة الجديدة لا يُحتسب
    violations = guard.find_violations(URLS_MULTILINE + SELF_LINK_TEMPLATE)
    assert [v.full_name for v in violations] == ["students:movements"]


def test_link_in_existing_base_template_passes():
    base = _modified(
        "templates/base/base.html", ["<a href=\"{% url 'students:movements' %}\">الحركات</a>"]
    )
    assert guard.find_violations(URLS_MULTILINE + SELF_LINK_TEMPLATE + base) == []


def test_href_with_route_in_existing_file_passes():
    nav = _modified("templates/base/nav.html", ['<a href="/students/movements/">x</a>'])
    assert guard.find_violations(URLS_MULTILINE + nav) == []


def test_reverse_and_redirect_in_existing_python_file_pass():
    view = _modified("students/views.py", ['    return redirect("students:movements")'])
    assert guard.find_violations(URLS_MULTILINE + view) == []


def test_link_in_a_test_file_does_not_count():
    test = _modified("tests/test_x.py", ['    reverse("students:movements")'])
    assert guard.find_violations(URLS_MULTILINE + test)


def test_api_and_parameterised_routes_are_not_checked():
    urls = _modified(
        "analytics/urls.py",
        [
            '    path("api/x/", views.x, name="x"),',
            '    path("analytics/api/x/", views.x, name="x2"),',
            '    path("item/<int:pk>/", views.item, name="item"),',
            '    path("report/pdf/", views.r, name="r"),',
        ],
        context=['app_name = "analytics"'],
    )
    assert guard.find_violations(urls) == []


def test_diff_without_urls_does_not_fail():
    assert guard.find_violations(_modified("students/views.py", ["x = 1"])) == []
    assert guard.find_violations("") == []


def test_unnamed_path_and_include_are_skipped():
    urls = _modified("core/urls.py", ['    path("a/", include("a.urls")),'])
    assert guard.find_violations(urls) == []


def test_app_name_falls_back_to_file_reader():
    urls = _modified("students/urls.py", ['    path("x/", views.x, name="x"),'])
    found = guard.extract_new_routes(
        guard.parse_diff(urls), read_file=lambda _p: "app_name = 'students'\n"
    )
    assert found[0].full_name == "students:x"


def test_main_exit_code_from_diff_file(tmp_path, capsys):
    f = tmp_path / "d.diff"
    f.write_text(URLS_MULTILINE + SELF_LINK_TEMPLATE, encoding="utf-8")
    assert guard.main(["--diff-file", str(f)]) == 1
    assert "students:movements" in capsys.readouterr().out
    f.write_text("", encoding="utf-8")
    assert guard.main(["--diff-file", str(f)]) == 0
