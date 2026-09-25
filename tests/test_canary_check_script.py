"""[CI] كنارُ ما بعد النشر (`scripts/canary-check.sh`، REP-17 أ): يثبت أنّ الـcommit المنشور حيٌّ وأنّ صفحةً حقيقيّةً تُرسم.

الفحصُ الذي يقول «سليم» لخدمةٍ تخدم النسخةَ القديمة هو بعينه ما وُضع الكنارُ لالتقاطه؛ فالاختباراتُ تجرّبه على خادمٍ محلّيٍّ
بحالاتٍ يجب أن تسقط (نسخةٌ قديمة، /health/ بلا commit، صفحةُ دخولٍ 500، صحّةٌ 500) وحالةٍ يجب أن تمرّ.
تُتخطّى حيث لا `bash` أو `curl` (حاويةُ الجلسة المحلّيّة بلا curl؛ وCI على ubuntu بهما).
"""

import http.server
import json
import os
import pathlib
import shutil
import subprocess
import threading

import pytest

SCRIPT = pathlib.Path("scripts/canary-check.sh")
SHA = "abc1234def5678900000000000000000000000ff"  # الأربعون؛ الفحصُ يقارن أوّلَ سبعٍ منها


def _bash() -> str | None:
    """bash الحقيقيّ: على ويندوز يسبق `bash.exe` الخاصُّ بـWSL (System32) Git Bash في PATH فلا يرى مساراتِ المشروع."""
    if os.environ.get("CANARY_TEST_BASH"):
        return os.environ["CANARY_TEST_BASH"]
    if os.name == "nt":
        for candidate in (
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
        ):
            if os.path.exists(candidate):
                return candidate
    return shutil.which("bash")


BASH = _bash()
pytestmark = pytest.mark.skipif(not (BASH and shutil.which("curl")), reason="يحتاج bash وcurl")


class _Server:
    """خادمٌ محلّيّ بمسارات: المسارُ ← (حالة، جسم)."""

    def __init__(self):
        self.routes: dict[str, tuple[int, str]] = {}
        routes = self.routes

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 — اسمٌ يفرضه BaseHTTPRequestHandler
                status, body = routes.get(self.path, (404, "لا شيء"))
                payload = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    srv = _Server()
    yield srv
    srv.close()


def _canary(url, sha=SHA):
    env = {**os.environ, "CANARY_ATTEMPTS": "2", "CANARY_SLEEP": "0", "CANARY_TIMEOUT": "5"}
    return subprocess.run(
        [BASH, SCRIPT.as_posix(), sha, url],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=60,
    )


def _healthy(server, commit="abc1234"):
    server.routes["/health/"] = (
        200,
        json.dumps({"status": "ok", "commit": commit, "version": "9.9"}),
    )
    server.routes["/auth/login/"] = (200, "<html>login</html>")


def test_a_live_commit_with_a_rendering_login_page_passes(server):
    _healthy(server)

    result = _canary(server.url)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Canary PASSED" in result.stdout


def test_the_first_seven_characters_of_the_sha_are_what_is_compared(server):
    _healthy(server, commit="abc1234")

    assert _canary(server.url, sha="abc1234").returncode == 0
    other_sha = "abc1235def"  # pragma: allowlist secret — تجزئةٌ وهميّة لا سرّ
    assert _canary(server.url, sha=other_sha).returncode == 1


def test_an_old_healthy_version_still_serving_is_a_failure_not_a_pass(server):
    """خدمةٌ سليمةٌ تخدم النسخةَ السابقة: هذه صورةُ النشر الفاشل — تُجيب 200 وبـcommit آخر."""
    _healthy(server, commit="0ld0000")

    result = _canary(server.url)

    assert result.returncode == 1
    assert "النسخةُ القديمة" in result.stdout


def test_a_health_answer_without_a_commit_proves_nothing(server):
    server.routes["/health/"] = (200, json.dumps({"status": "ok"}))
    server.routes["/auth/login/"] = (200, "ok")

    result = _canary(server.url)

    assert result.returncode == 1
    assert "بلا حقل commit" in result.stdout


def test_a_login_page_that_does_not_render_fails_even_when_health_is_green(server):
    """حادثة 2026-09-17: /health/ لا يرسم قالباً — أخضرُ ساعتين وكلُّ صفحةٍ 500."""
    _healthy(server)
    server.routes["/auth/login/"] = (500, "Server Error")

    result = _canary(server.url)

    assert result.returncode == 1
    assert "HTTP 500" in result.stdout


def test_a_failing_health_endpoint_is_a_failure(server):
    server.routes["/health/"] = (500, "down")

    assert _canary(server.url).returncode == 1


def test_a_missing_sha_is_a_usage_error_not_a_pass():
    result = subprocess.run(
        [BASH, SCRIPT.as_posix()], capture_output=True, text=True, encoding="utf-8", timeout=30
    )

    assert result.returncode == 2
