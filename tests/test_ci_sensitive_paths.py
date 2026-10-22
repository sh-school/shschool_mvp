"""أداةُ المسارات الحسّاسة (`scripts/ci_sensitive_paths.py`) — W-20261002-005.

بلا قاعدةٍ ولا شبكة: دوالُّ السكربت على القائمة الفعليّة وعلى قوائم اصطناعيّة.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "ci_sensitive_paths", ROOT / "scripts" / "ci_sensitive_paths.py"
)
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)

REAL = (ROOT / "security" / "sensitive_paths.json").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rules():
    return sp.load_rules(REAL)


class TestGlob:
    @pytest.mark.parametrize(
        ("pattern", "path", "ok"),
        [
            ("core/permissions*.py", "core/permissions.py", True),
            ("core/permissions*.py", "core/permissions_extra.py", True),
            ("core/permissions*.py", "core/sub/permissions.py", False),
            ("**/rbac*", "rbac.py", True),
            ("**/rbac*", "a/b/rbac_utils.py", True),
            ("breach/**", "breach/models.py", True),
            ("breach/**", "breach/a/b.py", True),
            ("breach/**", "other/breach/x.py", False),
            ("**/migrations/*.py", "operations/migrations/0093_x.py", True),
            ("**/migrations/*.py", "operations/migrations/sub/0093_x.py", False),
            ("**/*upload*", "docs/upload_guide.md", True),
            ("Dockerfile", "Dockerfile", True),
            ("Dockerfile", "docs/Dockerfile.md", False),
        ],
    )
    def test_cases(self, pattern, path, ok):
        assert bool(sp.glob_to_regex(pattern).match(path)) is ok


class TestLoad:
    def test_real_list_is_valid(self, rules):
        assert rules["version"] == 2

    @pytest.mark.parametrize(
        "text", [None, "", "   ", "{فاسد", "[]", "{}", '{"mandatory_review_when_diff_touches": {}}']
    )
    def test_missing_or_corrupt_fails_loudly(self, text):
        with pytest.raises(sp.SensitiveConfigError):
            sp.load_rules(text)

    def test_bad_regex_fails(self):
        bad = {
            "mandatory_review_when_diff_touches": {"a": ["x"]},
            "mandatory_review_when_diff_content_matches": {"r": ["("]},
        }
        with pytest.raises(sp.SensitiveConfigError):
            sp.load_rules(json.dumps(bad))

    def test_empty_category_fails(self):
        with pytest.raises(sp.SensitiveConfigError):
            sp.load_rules(json.dumps({"mandatory_review_when_diff_touches": {"a": []}}))


class TestCategories:
    @pytest.mark.parametrize(
        ("path", "category"),
        [
            ("core/permissions.py", "authorization_identity"),
            ("core/models/crypto.py", "encryption_and_personal_data"),
            ("api/views.py", "external_surface_and_api"),
            ("core/pdf_utils.py", "file_io_and_rendering"),
            ("shschool/settings/prod.py", "production_config_and_deploy"),
            (".github/workflows/quality-gate.yml", "production_config_and_deploy"),
            (".railway/railway.ts", "production_config_and_deploy"),
            ("scripts/ci_sensitive_paths.py", "automation"),
            ("security/sensitive_paths.json", "automation"),
            ("operations/migrations/0093_x.py", "security_tables_migrations"),
        ],
    )
    def test_each_category_matches(self, rules, path, category):
        assert path in sp.match_paths([path], rules).get(category, [])

    def test_no_match_returns_empty(self, rules):
        assert sp.match_paths(["templates/schedule/plain.html", "docs/x.md"], rules) == {}


DIFF_URL = (
    "diff --git a/operations/urls.py b/operations/urls.py\n--- a/operations/urls.py\n+++ b/operations/urls.py\n"
    "@@ -1 +1,2 @@\n+    path('x/', v, name='x'),\n"
)
DIFF_URL_ELSEWHERE = DIFF_URL.replace("operations/urls.py", "operations/helpers.py")
DIFF_REDIRECT = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n+    return redirect(request.GET['u'])\n"
DIFF_REMOVED = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +0,0 @@\n-    redirect(request.GET['u'])\n"


class TestContent:
    def test_new_endpoint_only_in_urls_files(self, rules):
        assert sp.match_content(DIFF_URL, rules) == {
            "new_external_input_endpoints": ["operations/urls.py"]
        }
        assert sp.match_content(DIFF_URL_ELSEWHERE, rules) == {}

    def test_redirect_pattern_any_file(self, rules):
        assert sp.match_content(DIFF_REDIRECT, rules) == {"redirects": ["a.py"]}

    def test_removed_lines_do_not_count(self, rules):
        assert sp.match_content(DIFF_REMOVED, rules) == {}

    def test_added_line_that_looks_like_header_does_not_switch_file(self, rules):
        lines = [
            "diff --git a/x.py b/x.py",
            "--- a/x.py",
            "+++ b/x.py",
            "@@ -1 +1,2 @@",
            "+++ b/operations/urls.py",
            "+path('a/', v)",
        ]
        diff = "\n".join(lines) + "\n"
        assert set(sp.added_lines_by_file(diff)) == {"x.py"}
        assert sp.match_content(diff, rules) == {}

    def test_deleted_file_header_ignored(self, rules):
        diff = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n"
        assert sp.added_lines_by_file(diff) == {}


class TestRender:
    def test_scan_and_render(self, rules):
        res = sp.scan(["core/permissions.py"], DIFF_REDIRECT, rules)
        text = sp.render(res)
        assert sp.MARKER in text
        assert "authorization_identity" in text
        assert "redirects" in text
        assert sp.LABEL in text

    def test_list_covers_own_files(self, rules):
        hits = sp.match_paths([sp.LIST_PATH, "scripts/ci_sensitive_paths.py"], rules)
        assert len(hits["automation"]) == 2
