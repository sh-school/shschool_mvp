"""عمرُ بيانات الصفحة وتحديثُها (W-20261012-014، D-410م، وW-20261124-008): المؤشّرُ والزرُّ في base.html.

العودةُ إلى تبويبٍ غاب عنه المستخدم أكثرَ من 120 ثانية تُعلِّم المؤشّرَ بالقِدَم فقط ولا تُعيد التحميل أبداً؛ والتحديثُ بضغطة المستخدم.
الشقّ النصّيّ يعمل دائماً؛ وشقُّ السلوك يشغّل `static/js/page-fresh.js` في `node` بمستندٍ مصطنعٍ وساعةٍ مُحاكاة (يُتخطّى بلا node).
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
JS = ROOT / "static" / "js" / "page-fresh.js"
BASE = (ROOT / "templates" / "base" / "base.html").read_text(encoding="utf-8")


def test_indicator_and_button_live_in_the_shared_base_template():
    assert "data-page-fresh" in BASE and "data-fresh-refresh" in BASE and "data-fresh-time" in BASE
    assert 'aria-label="تحديث بيانات الصفحة"' in BASE
    assert "js/page-fresh.js" in BASE


def test_excluded_pages_do_not_show_the_indicator_from_the_server():
    assert "/command-center/" in BASE and "/exports/" in BASE


def test_no_new_css_file_and_rule_lives_in_the_central_components_layer():
    css = (ROOT / "static" / "css" / "custom" / "20-components.css").read_text(encoding="utf-8")
    assert ".page-fresh {" in css
    assert not list((ROOT / "static" / "css").rglob("*fresh*"))


def test_threshold_is_two_minutes_and_listens_to_visibility():
    text = JS.read_text(encoding="utf-8")
    assert "120 * 1000" in text and "visibilitychange" in text
    assert "page-live:updated" in text


def test_visibility_path_never_reloads_it_only_marks_stale():
    text = JS.read_text(encoding="utf-8")
    start = text.index('addEventListener("visibilitychange"')
    end = text.index("if (button)", start)
    segment = text[start:end]
    assert "reload" not in segment
    assert "markStale()" in segment


HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const src = fs.readFileSync(process.argv[1], "utf8");
const cfg = JSON.parse(process.argv[2]);
let nowMs = 1_700_000_000_000;
const RealDate = Date;
class FakeDate extends RealDate {
  constructor(...a) { if (a.length) { super(...a); } else { super(nowMs); } }
  static now() { return nowMs; }
}
const handlers = {};
let reloads = 0, confirms = 0;
const listeners = {};
const attrs = {};
const cls = new Set(["btn-ghost"]);
let tailNode = null;
const lead = { nodeType: 3, nodeValue: "آخر تحديث " };
const box = {
  hidden: false,
  getAttribute: () => String(cfg.serverNow),
  setAttribute: (k, v) => { attrs[k] = v; },
  removeAttribute: (k) => { delete attrs[k]; },
  querySelector: (sel) => sel === "[data-fresh-time]" ? timeNode : (sel === "[data-fresh-refresh]" ? button : (sel === "[data-fresh-gate]" ? gate : null)),
};
// نموذجُ التأكيد المخفيّ: يعترضه base.js ويعرض نافذةَ المنصّة (نحاكيها: confirms++ ثم تأكيدٌ بـ_confirmed وإعادةُ إرسال).
const gate = {
  attrs: {}, subs: [],
  setAttribute(k, v) { this.attrs[k] = v; },
  addEventListener(t, f) { if (t === "submit") { this.subs.push(f); } },
  requestSubmit() {
    const run = () => this.subs.forEach((f) => f({ preventDefault() {} }));
    run();
    if (!this._confirmed) {
      confirms++;
      if (cfg.confirm) { this._confirmed = true; run(); this._confirmed = false; }
    }
  },
};
const timeNode = {
  textContent: "",
  previousSibling: lead,
  nextSibling: null,
  parentNode: { insertBefore: (n) => { tailNode = n; } },
};
const button = {
  addEventListener: (t, f) => { handlers.click = f; },
  classList: { add: (c) => cls.add(c), remove: (c) => cls.delete(c) },
};
const mainEl = {
  contains: () => true,
  querySelector: (sel) => cfg.main.includes(sel) ? {getAttribute: () => "k"} : null,
};
const document = {
  hidden: false,
  querySelector: (sel) => sel === "[data-page-fresh]" ? box : null,
  getElementById: (id) => id === "main-content" ? mainEl : null,
  addEventListener: (t, f) => { (listeners[t] = listeners[t] || []).push(f); },
  createTextNode: (t) => ({ nodeType: 3, nodeValue: t }),
};
const ctx = {
  document, Date: FakeDate, Intl, console,
  location: { pathname: cfg.path, reload: () => { reloads++; } },
  localStorage: { getItem: () => cfg.draft },
  confirm: () => { throw new Error('window.confirm ممنوع'); },
};
ctx.window = { localStorage: ctx.localStorage, location: ctx.location, confirm: ctx.confirm };
vm.createContext(ctx);
vm.runInContext(src, ctx);
const fire = (t, e) => (listeners[t] || []).forEach((f) => f(e || {}));
for (const step of cfg.steps) {
  if (step.type === "hide") { document.hidden = true; fire("visibilitychange"); }
  if (step.type === "show") { document.hidden = false; nowMs += step.after * 1000; fire("visibilitychange"); }
  if (step.type === "input") { fire("input", { target: {} }); }
  if (step.type === "click") { handlers.click(); }
  if (step.type === "nav") { fire("htmx:afterSwap", { detail: { pageNav: true } }); }
}
const label = lead.nodeValue + timeNode.textContent + (tailNode ? tailNode.nodeValue : "");
console.log(JSON.stringify({
  reloads, confirms, time: timeNode.textContent, hidden: box.hidden,
  label, live: attrs["aria-live"] || "", btn: [...cls],
}));
"""

FRESH_LABEL = "آخر تحديث 01:13"
STALE_LABEL = "بيانات منذ 01:13 — حدّث"


def _run(steps, *, path="/dashboard/", main="", draft=None, confirm=True):
    if not shutil.which("node"):
        pytest.skip("لا node لتشغيل سلوك page-fresh.js")
    cfg = {
        "serverNow": 1_700_000_000,
        "path": path,
        "main": main,
        "draft": draft,
        "confirm": confirm,
        "steps": steps,
    }
    out = subprocess.run(
        ["node", "-e", HARNESS, "--", str(JS), json.dumps(cfg)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout
    return json.loads(out.strip().splitlines()[-1])


AWAY_600 = [{"type": "hide"}, {"type": "show", "after": 600}]


def test_returning_after_more_than_two_minutes_marks_stale_without_reload():
    r = _run([{"type": "hide"}, {"type": "show", "after": 121}])
    assert r["reloads"] == 0
    assert r["label"] == STALE_LABEL
    assert r["live"] == "polite"
    assert r["btn"] == ["btn-warning"]


def test_returning_within_two_minutes_does_not_mark_stale():
    r = _run([{"type": "hide"}, {"type": "show", "after": 119}])
    assert r["reloads"] == 0
    assert r["label"] == FRESH_LABEL
    assert r["live"] == ""
    assert r["btn"] == ["btn-ghost"]


def test_repeated_returns_keep_one_stale_mark_and_do_not_reannounce():
    r = _run(AWAY_600 + AWAY_600)
    assert r["reloads"] == 0
    assert r["label"] == STALE_LABEL
    assert r["live"] == "polite"


def test_dirty_page_is_only_marked_stale_and_input_is_kept():
    r = _run([{"type": "input"}, {"type": "hide"}, {"type": "show", "after": 600}])
    assert r["reloads"] == 0
    assert r["label"] == STALE_LABEL


def test_saved_draft_page_is_marked_stale_not_reloaded():
    r = _run(AWAY_600, main="[data-draft-key]", draft='{"1":"p"}')
    assert r["reloads"] == 0
    assert r["label"] == STALE_LABEL


@pytest.mark.parametrize(
    "main",
    [
        "[data-live-url], [data-director-live]",
        "[data-quiet-poll]",
        '[hx-trigger*="every"]',
    ],
)
def test_live_pages_are_never_marked_stale(main):
    r = _run(AWAY_600, main=main)
    assert r["reloads"] == 0
    assert r["label"] == FRESH_LABEL
    assert r["live"] == ""
    assert r["btn"] == ["btn-ghost"]


def test_hx_trigger_without_every_is_not_a_live_page():
    r = _run(AWAY_600, main='[hx-trigger="click"]')
    assert r["label"] == STALE_LABEL


def test_excluded_pages_are_hidden_and_never_marked_or_refreshed():
    for path in ("/admin/x/", "/command-center/", "/exports/1/"):
        r = _run(AWAY_600, path=path)
        assert r["reloads"] == 0 and r["hidden"] is True, path
        assert r["live"] == "" and r["btn"] == ["btn-ghost"], path


def test_page_nav_clears_the_stale_mark():
    r = _run(AWAY_600 + [{"type": "nav"}])
    assert r["reloads"] == 0
    assert r["label"] == "آخر تحديث 01:23"
    assert r["live"] == ""
    assert r["btn"] == ["btn-ghost"]


def test_manual_button_on_stale_clean_page_reloads_without_asking():
    r = _run(AWAY_600 + [{"type": "click"}])
    assert r["confirms"] == 0 and r["reloads"] == 1


def test_manual_button_asks_first_when_dirty_and_respects_refusal():
    asked = _run([{"type": "input"}, {"type": "click"}], confirm=False)
    assert asked["confirms"] == 1 and asked["reloads"] == 0
    accepted = _run([{"type": "input"}, {"type": "click"}], confirm=True)
    assert accepted["confirms"] == 1 and accepted["reloads"] == 1


def test_manual_button_still_asks_on_a_stale_dirty_page():
    r = _run(
        [{"type": "input"}, {"type": "hide"}, {"type": "show", "after": 600}, {"type": "click"}],
        confirm=False,
    )
    assert r["confirms"] == 1 and r["reloads"] == 0
    assert r["label"] == STALE_LABEL


def test_manual_button_on_clean_page_reloads_without_asking():
    r = _run([{"type": "click"}])
    assert r["confirms"] == 0 and r["reloads"] == 1


def test_time_uses_server_clock_in_doha():
    # 1_700_000_000 = 2023-11-14 22:13:20 UTC = 01:13 (+03:00) من اليوم التالي
    assert _run([])["time"] == "01:13"
