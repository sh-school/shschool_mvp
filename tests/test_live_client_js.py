"""سلوكُ عميل الاستطلاع الحيّ `static/js/director-live.js` المعمَّم (W-20261012-015، D-410م): الفاصلُ من الخادم، التراجعُ حتى 300 ثانية،
التوقّفُ عند الإخفاء وعند 403 وعند `final`، وإطلاقُ حمولة الصفحة على جذرها. يشغّله في `node` بمستندٍ مصطنعٍ وجلبٍ ومؤقّتاتٍ مُحاكاة (يُتخطّى بلا node).
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
JS = ROOT / "static" / "js" / "director-live.js"

HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const src = fs.readFileSync(process.argv[1], "utf8");
const cfg = JSON.parse(process.argv[2]);
const attrs = { "data-live-url": "/x/", "data-phase": cfg.phase || "live" };
if (cfg.noreload) attrs["data-live-noreload"] = "";
const events = [], docEvents = [], timers = [], fetches = [];
const root = {
  getAttribute: (n) => (n in attrs ? attrs[n] : null),
  hasAttribute: (n) => n in attrs,
  querySelectorAll: () => [],
  querySelector: () => null,
  dispatchEvent: (e) => { events.push(e); },
};
let reloads = 0, cleared = 0;
const listeners = {};
const document = {
  hidden: false,
  querySelector: () => root,
  addEventListener: (t, f) => { (listeners[t] = listeners[t] || []).push(f); },
  dispatchEvent: (e) => { docEvents.push(e.type); },
};
class CustomEvent { constructor(type, init) { this.type = type; this.detail = init && init.detail; } }
const queue = cfg.responses.slice();
const window_ = {
  setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
  clearTimeout: () => { cleared++; },
  fetch: (url) => {
    fetches.push(url);
    const r = queue.length > 1 ? queue.shift() : queue[0];
    if (r.reject) return Promise.reject(new Error("net"));
    return Promise.resolve({
      status: r.status, ok: r.status >= 200 && r.status < 300,
      headers: { get: () => (r.json === undefined ? "text/html" : "application/json") },
      json: () => Promise.resolve(r.json),
    });
  },
  location: { reload: () => { reloads++; } },
  Math: Object.create(Math),
};
const ctx = { document, CustomEvent, Math: { ...Math, random: () => 0.5, pow: Math.pow, min: Math.min, max: Math.max }, console };
ctx.window = Object.assign(ctx, window_);
vm.createContext(ctx);
vm.runInContext(src, ctx);
const tick = () => new Promise((r) => setImmediate(r));
(async () => {
  const delays = [];
  for (let i = 0; i < (cfg.cycles || 0); i++) {
    const t = timers.pop();
    if (!t) break;
    delays.push(t.ms);
    t.fn();
    await tick(); await tick(); await tick();
  }
  if (cfg.hide) { document.hidden = true; (listeners.visibilitychange || []).forEach((f) => f()); }
  const before = fetches.length;
  if (cfg.show) { document.hidden = false; (listeners.visibilitychange || []).forEach((f) => f()); await tick(); await tick(); await tick(); }
  console.log(JSON.stringify({
    delays, fetches: fetches.length, fetchesAfterShow: fetches.length - before, reloads, cleared,
    payloadEvents: events.map((e) => e.type), cells: events.length ? events[0].detail.cells : null,
    docEvents, pendingTimers: timers.length,
  }));
})();
"""


def _run(**cfg):
    if not shutil.which("node"):
        pytest.skip("لا node لتشغيل سلوك director-live.js")
    out = subprocess.run(
        ["node", "-e", HARNESS, "--", str(JS), json.dumps(cfg)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout
    return json.loads(out.strip().splitlines()[-1])


def _ok(**extra):
    return {"status": 200, "json": {"schema": 1, "next_in": 60, "phase": "live", **extra}}


def test_the_server_interval_drives_the_next_poll_with_jitter_bounds():
    r = _run(responses=[_ok(cells=[])], cycles=1)
    # أوّلُ جدولةٍ 45 ث (الافتراضيّ) بتشويش ±5 ث.
    assert 40000 <= r["delays"][0] <= 50000
    assert r["pendingTimers"] == 1


def test_a_grid_payload_is_dispatched_on_its_root_and_notifies_the_indicator():
    r = _run(responses=[_ok(cells=[{"c": 1, "s": "u", "h": "h", "st": "absent"}])], cycles=1)
    assert r["payloadEvents"] == ["page-live:payload"]
    assert r["cells"] == [{"c": 1, "s": "u", "h": "h", "st": "absent"}]
    assert "page-live:updated" in r["docEvents"]


def test_failures_back_off_exponentially_and_never_exceed_300_seconds():
    r = _run(responses=[{"status": 500, "json": None}], cycles=7)
    assert 40000 <= r["delays"][0] <= 50000
    assert r["delays"][3] > r["delays"][1] > r["delays"][0]
    assert max(r["delays"]) == 300000


def test_403_stops_polling_for_good():
    r = _run(responses=[{"status": 403, "json": {"error": "forbidden"}}], cycles=1)
    assert r["fetches"] == 1 and r["pendingTimers"] == 0


def test_final_phase_stops_and_a_grid_does_not_reload_while_others_do():
    final = _ok(phase="final", cells=[])
    assert _run(responses=[final], cycles=1, noreload=True)["reloads"] == 0
    assert _run(responses=[final], cycles=1)["reloads"] == 1
    assert _run(responses=[final], cycles=1, noreload=True)["pendingTimers"] == 0


def test_hiding_the_tab_stops_and_showing_it_polls_at_once():
    r = _run(responses=[_ok(cells=[])], cycles=1, hide=True, show=True)
    assert r["cleared"] >= 1
    assert r["fetchesAfterShow"] == 1


def test_a_page_rendered_final_never_polls():
    r = _run(responses=[_ok(cells=[])], cycles=1, phase="final")
    assert r["fetches"] == 0
