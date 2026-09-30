"""[DOCS-VIEWER] عارضُ md المركزيّ — لمطوّر المنصّة وحدَه (W-20260930-002).

يثبت: الحمايةَ (مجهولٌ يُحوَّل، غيرُ المطوّر 403)، وأنّ الفهرسَ يبني شجرةً من ملفّات
md حقيقيّة، وأنّ التصييرَ يعمل على ملفٍّ حقيقيّ من المشروع — وعمودُ الفقار: **حارسُ
الخروج عن الجذر (path traversal)** بأشكالٍ متعدّدة، لأنّ المسارَ مُدخَلٌ من المستخدم.
"""

from __future__ import annotations

import pytest
from django.http import Http404
from django.urls import resolve, reverse

from docs_viewer import services

pytestmark = pytest.mark.django_db


# ── الحمايةُ (developer_only) ────────────────────────────────────────────────


def test_an_anonymous_visitor_is_sent_to_login(client):
    response = client.get(reverse("docs_viewer:index"))
    assert response.status_code == 302
    assert "login" in response["Location"]


def test_a_non_developer_gets_403(client_as, teacher_user):
    assert client_as(teacher_user).get(reverse("docs_viewer:index")).status_code == 403


def test_the_developer_reaches_the_index(client_as, developer_user):
    response = client_as(developer_user).get(reverse("docs_viewer:index"))
    assert response.status_code == 200
    assert "CLAUDE.md" in response.content.decode("utf-8")


def test_a_non_developer_gets_403_on_detail(client_as, teacher_user):
    url = reverse("docs_viewer:detail", kwargs={"doc_path": "README.md"})
    assert client_as(teacher_user).get(url).status_code == 403


# ── التصييرُ على ملفٍّ حقيقيّ ─────────────────────────────────────────────────


def test_the_developer_can_view_a_real_project_file(client_as, developer_user):
    url = reverse("docs_viewer:detail", kwargs={"doc_path": "README.md"})
    response = client_as(developer_user).get(url)
    assert response.status_code == 200
    assert response.context["doc_path"] == "README.md"


def test_a_missing_file_is_404(client_as, developer_user):
    url = reverse("docs_viewer:detail", kwargs={"doc_path": "this-file-does-not-exist.md"})
    assert client_as(developer_user).get(url).status_code == 404


def test_a_non_markdown_file_is_404(client_as, developer_user):
    """`manage.py` موجودٌ فعلاً — لكنّه ليس md، فلا يطابق مسارَ العرض أصلاً (رابطٌ خامٌ لا `reverse`، الوسمُ يقبل .md وحدَها)."""
    assert client_as(developer_user).get("/docs/manage.py/").status_code == 404


def test_safe_resolve_itself_refuses_a_non_markdown_file():
    with pytest.raises(Http404):
        services.safe_resolve("manage.py")


# ── حارسُ الخروج عن الجذر (path traversal) — الإلزاميّ ─────────────────────────


@pytest.mark.parametrize(
    "traversal_path",
    [
        "../../../../../../etc/passwd.md",
        "../../requirements.txt",
        "docs/../../../../etc/passwd.md",
        "/etc/passwd.md",
        "....//....//etc/passwd.md",
    ],
)
def test_safe_resolve_refuses_every_escape_attempt(traversal_path):
    with pytest.raises(Http404):
        services.safe_resolve(traversal_path)


def test_safe_resolve_refuses_an_absolute_windows_style_path():
    with pytest.raises(Http404):
        services.safe_resolve("C:/Windows/win.ini")


def test_safe_resolve_refuses_a_symlink_escaping_the_root(tmp_path):
    """رابطٌ رمزيٌّ داخل الجذر يشير خارجَه — `resolve()` يتبعه فيرفضه `is_relative_to`."""
    outside_file = tmp_path / "secret.md"
    outside_file.write_text("سرّ", encoding="utf-8")
    link = services.DOCS_ROOT / "docs_viewer_test_symlink.md"
    try:
        link.symlink_to(outside_file)
    except OSError:
        pytest.skip("لا صلاحيّةَ لإنشاء رابطٍ رمزيّ في هذه البيئة")
    try:
        with pytest.raises(Http404):
            services.safe_resolve("docs_viewer_test_symlink.md")
    finally:
        link.unlink(missing_ok=True)


def test_the_view_itself_returns_404_for_a_traversal_attempt(client_as, developer_user):
    url = reverse("docs_viewer:detail", kwargs={"doc_path": "../../../../../../etc/passwd.md"})
    assert client_as(developer_user).get(url).status_code == 404


def test_the_view_returns_404_for_a_url_encoded_traversal_attempt(client_as, developer_user):
    """`%2e%2e%2f` يفكّه Django قبل المطابقة إلى `../` حرفيّاً — والحارسُ يرفضه رغم ذلك."""
    response = client_as(developer_user).get("/docs/%2e%2e/%2e%2e/CLAUDE.md/")
    assert response.status_code == 404


def test_safe_resolve_accepts_a_real_file():
    resolved = services.safe_resolve("README.md")
    assert resolved == (services.DOCS_ROOT / "README.md").resolve()


# ── الفهرسُ وurlconf ─────────────────────────────────────────────────────────


def test_urlconf_resolves_both_routes():
    assert resolve("/docs/").view_name == "docs_viewer:index"
    assert resolve("/docs/README.md/").view_name == "docs_viewer:detail"


def test_build_tree_finds_readme_and_claude_md():
    tree = services.build_tree()
    all_files = _flatten_files(tree)
    assert "README.md" in all_files
    assert "CLAUDE.md" in all_files


def test_build_tree_includes_files_inside_dot_claude():
    """طلبُ المالك صراحةً: `.claude/` تظهر في الشجرة رغم أنّها تبدأ بنقطة (خلافاً لمجلّداتٍ أخرى بنقطة)."""
    all_files = _flatten_files(services.build_tree())
    assert any(path.startswith(".claude/") for path in all_files), all_files
    assert ".claude/skills/drf-endpoint-scaffold/CHANGES.md" in all_files


def _flatten_files(node: services.DocNode) -> set[str]:
    found: set[str] = set()
    for child in node.children:
        if child.is_dir:
            found |= _flatten_files(child)
        else:
            found.add(child.rel_path)
    return found
