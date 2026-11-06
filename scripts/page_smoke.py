"""scripts/page_smoke.py — فاحصُ صفحاتٍ حتميٌّ بلا نموذج (استشاري) — W-20261106-025.

يفتح مساراتٍ بحساب دورٍ في Playwright ويطبع JSON. يفشل عند: حالة 500، أو خطأ وحدة تحكّم،
أو طلب شبكةٍ فاشل، أو تجاوزٍ أفقيٍّ على عرض 375، أو حقل `required` داخل حاويةٍ مخفيّة
(يمنع المتصفّحُ الإرسالَ صامتاً لأنّه لا يستطيع التركيزَ عليه)، أو رسمٍ بلا كائن Chart أو بياناته.
الفحوصُ دوالُّ نقيّةٌ على نصوص HTML وقياساتٍ؛ و Playwright لا يُستورد إلا داخل دالّة تشغيله.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from html.parser import HTMLParser

MOBILE_WIDTH = 375
_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)
_HIDDEN_STYLE_RE = re.compile(r"display\s*:\s*none", re.IGNORECASE)
_HIDDEN_CLASSES = frozenset({"d-none", "hidden"})


class _RequiredInHiddenParser(HTMLParser):
    """يتتبّع مكدّس الوسوم ويسجّل كلَّ حقل required تحت وسمٍ مخفيّ."""

    def __init__(self) -> None:
        super().__init__()
        self._stack: list[bool] = []
        self.found: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        hidden = (
            "hidden" in a
            or bool(_HIDDEN_STYLE_RE.search(a.get("style") or ""))
            or bool(_HIDDEN_CLASSES & set((a.get("class") or "").split()))
        )
        inside_hidden = any(self._stack)
        if (
            "required" in a
            and tag in {"input", "select", "textarea"}
            and (a.get("type") or "").lower() != "hidden"
            and (inside_hidden or hidden)
        ):
            self.found.append(a.get("name") or a.get("id") or tag)
        if tag not in _VOID_TAGS:
            self._stack.append(hidden)

    def handle_endtag(self, tag: str) -> None:
        if tag not in _VOID_TAGS and self._stack:
            self._stack.pop()


def required_in_hidden(html: str) -> list[str]:
    """أسماءُ الحقول required الواقعة داخل حاويةٍ مخفيّة."""
    parser = _RequiredInHiddenParser()
    parser.feed(html)
    return parser.found


def judge_page(path: str, result: dict) -> list[str]:
    """مخالفاتُ صفحةٍ واحدةٍ من قياساتها: status وconsole_errors وfailed_requests وscroll_width وhtml وcharts."""
    problems: list[str] = []
    status = result.get("status", 0)
    if status >= 500:
        problems.append(f"{path}: حالة {status}")
    problems += [f"{path}: خطأ وحدة تحكّم: {m}" for m in result.get("console_errors", [])]
    problems += [f"{path}: طلبٌ فاشل: {m}" for m in result.get("failed_requests", [])]
    if result.get("scroll_width", 0) > result.get("viewport_width", MOBILE_WIDTH):
        problems.append(
            f"{path}: تجاوزٌ أفقيٌّ {result['scroll_width']}px على {result.get('viewport_width', MOBILE_WIDTH)}px"
        )
    problems += [
        f"{path}: required داخل حاويةٍ مخفيّة: {n}"
        for n in required_in_hidden(result.get("html", ""))
    ]
    charts = result.get("charts")
    if charts and charts.get("canvases", 0) > 0:
        if not charts.get("chart_defined"):
            problems.append(f"{path}: رسمٌ بلا كائن Chart")
        elif charts.get("with_data", 0) < charts["canvases"]:
            problems.append(
                f"{path}: رسمٌ بلا بيانات ({charts.get('with_data', 0)}/{charts['canvases']})"
            )
    return problems


_CHARTS_JS = """() => {
  const canvases = Array.from(document.querySelectorAll('canvas'));
  const defined = typeof window.Chart !== 'undefined';
  const withData = defined ? canvases.filter(c => {
    const ch = window.Chart.getChart ? window.Chart.getChart(c) : null;
    return ch && ch.data.datasets.some(d => d.data && d.data.length > 0);
  }).length : 0;
  return {canvases: canvases.length, chart_defined: defined, with_data: withData};
}"""


def run(base_url: str, username: str, password: str, login_path: str, paths: list[str]) -> dict:
    """يشغّل المتصفّح؛ الاستيرادُ هنا لا في رأس الملفّ فتبقى الاختباراتُ بلا متصفّح."""
    from playwright.sync_api import sync_playwright

    report: dict = {"pages": {}, "problems": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": MOBILE_WIDTH, "height": 800})
        page.goto(base_url + login_path)
        page.fill("input[name=username]", username)
        page.fill("input[name=password]", password)
        page.click("button[type=submit]")
        page.wait_for_load_state("networkidle")
        for path in paths:
            console_errors: list[str] = []
            failed: list[str] = []

            def on_console(msg, acc=console_errors):
                if msg.type == "error":
                    acc.append(msg.text)

            def on_failed(req, acc=failed):
                acc.append(req.url)

            page.on("console", on_console)
            page.on("requestfailed", on_failed)
            response = page.goto(base_url + path)
            page.wait_for_load_state("networkidle")
            result = {
                "status": response.status if response else 0,
                "console_errors": console_errors,
                "failed_requests": failed,
                "scroll_width": page.evaluate("document.documentElement.scrollWidth"),
                "viewport_width": MOBILE_WIDTH,
                "html": page.content(),
                "charts": page.evaluate(_CHARTS_JS),
            }
            page.remove_listener("console", on_console)
            page.remove_listener("requestfailed", on_failed)
            problems = judge_page(path, result)
            report["pages"][path] = {k: v for k, v in result.items() if k != "html"}
            report["problems"] += problems
        browser.close()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--login-path", default="/accounts/login/")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)
    report = run(
        args.base_url,
        os.environ["SMOKE_USERNAME"],
        os.environ["SMOKE_PASSWORD"],
        args.login_path,
        args.paths,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
