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
from docs_viewer.rendering import render_markdown

pytestmark = pytest.mark.django_db


# ── الحمايةُ (developer_only) ────────────────────────────────────────────────


def test_an_anonymous_visitor_is_sent_to_login(client):
    response = client.get(reverse("docs_viewer:index"))
    assert response.status_code == 302
    assert "login" in response["Location"]


def test_a_non_developer_gets_403(client_as, teacher_user):
    assert client_as(teacher_user).get(reverse("docs_viewer:index")).status_code == 403


def test_the_developer_reaches_the_index(client_as, developer_user):
    """`/docs/` يحوِّل إلى README.md (طلبُ المالك: الشجرةُ والمحتوى حاضران من أوّل زيارة)."""
    response = client_as(developer_user).get(reverse("docs_viewer:index"))
    assert response.status_code == 302
    assert response["Location"] == reverse("docs_viewer:detail", kwargs={"doc_path": "README.md"})


def test_the_index_redirect_lands_on_a_full_working_page(client_as, developer_user):
    response = client_as(developer_user).get(reverse("docs_viewer:index"), follow=True)
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "README.md" in body
    assert "CLAUDE.md" in body  # الشجرةُ الجانبيّةُ حاضرةٌ في الصفحة نفسِها


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


# ── عنوانُ العرض (طلبُ المالك: يعبّر عن المحتوى لا اسم الملفّ) ────────────────


def test_extract_title_prefers_a_markdown_heading():
    assert services.extract_title("# عنوانٌ فعليّ\n\nنصّ", fallback="x.md") == "عنوانٌ فعليّ"


def test_extract_title_skips_headings_inside_code_blocks():
    text = "```\n# ليس عنواناً\n```\n\n## هذا هو العنوان"
    assert services.extract_title(text, fallback="x.md") == "هذا هو العنوان"


def test_extract_title_falls_back_to_an_html_h1():
    """`README.md` يكتب عنوانَه `<h1>` HTML لا md (لتوسيط الشعار) — يجب أن يُلتقط أيضاً."""
    text = '<p>مقدّمة</p>\n<h1 align="center">عنوانٌ HTML</h1>'
    assert services.extract_title(text, fallback="x.md") == "عنوانٌ HTML"


def test_extract_title_falls_back_to_the_filename_when_no_heading_exists():
    assert services.extract_title("نصٌّ بلا عنوان", fallback="x.md") == "x.md"


def test_the_tree_shows_a_real_extracted_title_not_the_raw_filename():
    """README.md الفعليّ في المشروع عنوانُه HTML — الشجرةُ تعرضه لا «README.md»."""
    tree = services.build_tree()
    readme_node = next(c for c in tree.children if c.rel_path == "README.md")
    assert readme_node.name != "README.md"
    assert readme_node.filename == "README.md"
    assert "SchoolOS" in readme_node.name


# ── عنوانُ المجلّد (طلبُ المالك: التعريبُ يشمل المجلّدات أيضاً) ─────────────────


def test_a_folder_with_a_readme_shows_its_title_not_its_raw_name():
    """`docs/adr/README.md` الفعليّ عنوانُه «سجلّات القرارات المعماريّة (ADR)»."""
    tree = services.build_tree()
    docs_node = next(c for c in tree.children if c.is_dir and c.rel_path == "docs")
    adr_node = next(c for c in docs_node.children if c.is_dir and c.rel_path == "docs/adr")
    assert adr_node.filename == "adr"
    assert adr_node.name != "adr"
    assert "قرار" in adr_node.name


def test_a_folder_without_a_readme_keeps_its_raw_name():
    tree = services.build_tree()
    claude_node = next(c for c in tree.children if c.is_dir and c.rel_path == ".claude")
    skills_node = next(
        c for c in claude_node.children if c.is_dir and c.rel_path == ".claude/skills"
    )
    # لا README.md مباشرةً في .claude/skills نفسِها — يبقى اسمُها الخام
    assert skills_node.name == "skills"


# ── صورُ md النسبيّة (شعاراتٌ غالباً) — `resolve_asset` و`asset` view ──────────


def test_resolve_asset_serves_a_real_allowed_image():
    resolved = services.resolve_asset("static/brand/emblem.svg")
    assert resolved == (services.DOCS_ROOT / "static/brand/emblem.svg").resolve()


def test_resolve_asset_refuses_a_disallowed_extension():
    """`.py`/`.env` ونحوهما ممنوعةٌ صراحةً — لا يتحوّل مسارُ الصور نافذةَ تسريب."""
    with pytest.raises(Http404):
        services.resolve_asset("manage.py")


@pytest.mark.parametrize(
    "traversal_path",
    [
        "../../../../../../etc/passwd.svg",
        "../../requirements.txt",
        "/etc/passwd.svg",
    ],
)
def test_resolve_asset_refuses_escape_attempts(traversal_path):
    with pytest.raises(Http404):
        services.resolve_asset(traversal_path)


def test_a_non_developer_gets_403_on_asset(client_as, teacher_user):
    url = reverse("docs_viewer:asset", kwargs={"rel_path": "static/brand/emblem.svg"})
    assert client_as(teacher_user).get(url).status_code == 403


def test_the_developer_can_fetch_a_real_logo_asset(client_as, developer_user):
    url = reverse("docs_viewer:asset", kwargs={"rel_path": "static/brand/emblem.svg"})
    response = client_as(developer_user).get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "image/svg+xml"


def test_render_markdown_rewrites_a_relative_image_into_an_asset_link():
    rendered = render_markdown('<img src="static/brand/emblem.svg" alt="شعار">', source_dir="")
    expected = reverse("docs_viewer:asset", kwargs={"rel_path": "static/brand/emblem.svg"})
    assert expected in rendered.content_html


def test_render_markdown_resolves_relative_to_the_source_file_directory():
    """صورةٌ نسبيّةٌ داخل `docs/adr/foo.md` تشير إلى `../assets/x.svg` — النتيجةُ
    `docs/assets/x.svg` لا `docs/adr/assets/x.svg`."""
    rendered = render_markdown('<img src="../assets/x.svg">', source_dir="docs/adr")
    expected = reverse("docs_viewer:asset", kwargs={"rel_path": "docs/assets/x.svg"})
    assert expected in rendered.content_html


def test_render_markdown_leaves_absolute_and_external_images_untouched():
    html = '<img src="https://example.com/a.png"><img src="/static/x.svg">'
    rendered = render_markdown(html, source_dir="")
    assert 'src="https://example.com/a.png"' in rendered.content_html
    assert 'src="/static/x.svg"' in rendered.content_html


def test_the_readme_page_shows_a_working_logo_not_a_broken_one(client_as, developer_user):
    """الشكوى الأصليّة: الشعارُ مكسورٌ في README — الرابطُ المُصيَّر يجب أن يردّ 200 فعلاً."""
    url = reverse("docs_viewer:detail", kwargs={"doc_path": "README.md"})
    response = client_as(developer_user).get(url)
    body = response.content.decode("utf-8")
    asset_url = reverse("docs_viewer:asset", kwargs={"rel_path": "static/brand/emblem.svg"})
    assert asset_url in body
    assert client_as(developer_user).get(asset_url).status_code == 200


def _flatten_files(node: services.DocNode) -> set[str]:
    found: set[str] = set()
    for child in node.children:
        if child.is_dir:
            found |= _flatten_files(child)
        else:
            found.add(child.rel_path)
    return found
