"""سقّاطةُ الجوال (M-00) — ما يلمسه الإصبعُ ويقرؤه المستخدمُ فعلاً في متصفّحٍ حيّ.

خطّةُ إصلاح الجوال (`docs/mobile_remediation_plan_2026-09.md` §3) تقيس كلَّ بندٍ بمؤشّراتٍ
مسمّاة (K1–K5)، وأساسُها الأوّل (2026-09-20) محاكاةُ `@media` بعرض 390 على 30 صفحةً بحساب
قيادةٍ وحده. وهذا يستبدله: Playwright بسياقِ جوالٍ حقيقيّ (`is_mobile` و`has_touch` و375×812)
على **رحلاتِ خمسة أدوار** (Q-01)، و**بمحرّكَين** Chromium وWebKit (Q-02)، وبسطح مكتبٍ 1440
لمؤشّر K3 الذي يُقاس في الوضعين (D6) ولحدّ الفأرة 24px (K2 على سطح المكتب).

لكلّ صفحةٍ في كلّ مِلفّ:

- `targets` — العناصرُ التفاعليّةُ الظاهرة (رابطٌ، زرّ، حقل، `summary`، ودورُ زرٍّ أو تبويب).
- `small44` / `small24` — ما عرضُه أو ارتفاعُه دون 44px (WCAG 2.5.5 AAA، هدفُ K1) ودون 24px
  (WCAG 2.5.8 AA، K2).
- `tiny_text` — عناصرُ نصُّها المباشرُ دون 12px (K3)، و`min_font` أدنى خطٍّ في الصفحة.
- `h_overflow` — ما يتجاوز عرضَ النافذة أفقيّاً بالبكسل (K4).
- `inputs_under_16` — حقولُ كتابةٍ خطُّها دون 16px فيكبّر iOS الصفحةَ عند لمسها (K5).

السقّاطةُ على نمط `a11y_axe_ratchet`: ما في `GUARDED` زاد لصفحةٍ → سقط البناء؛ ونقص ولم
يُسجَّل → سقط كذلك حتّى يُثبَّت المكسبُ بـ`MOBILE_AUDIT_UPDATE=1`. و`targets` و`min_font`
معلومتان تُسجَّلان ولا تُحرسان — عددُ الأهداف يتغيّر بالميزات لا بالخطأ.
"""

from __future__ import annotations

import json
import pathlib

BASELINE = pathlib.Path("tests/mobile_audit_baseline.json")

#: ما يحرسه الاختبار لكلّ مِلفّ — لا يزيد لصفحة، ونقصُه يُسجَّل صراحةً. سطحُ المكتب يُحرس فيه
#: النصُّ والتجاوزُ وحدَّ الفأرة 24px (WCAG 2.5.8 AA، قرارُ D1: «24px للفأرة»، DBT-44): يسري على
#: كلّ مؤشّر، وكان غيرَ محروسٍ فانجرف خطُّ أساسه بصمت. أمّا 44px وتكبيرُ iOS للحقول فشأنُ الإصبع.
GUARDED = {
    "mobile": ("small44", "small24", "tiny_text", "h_overflow", "inputs_under_16"),
    "desktop": ("small24", "tiny_text", "h_overflow"),
}

#: المِلفّات: جوالٌ حقيقيٌّ بالمحرّكَين، وسطحُ مكتبٍ لمؤشّر K3.
PROFILES = {
    "mobile": {
        "viewport": {"width": 375, "height": 812},
        "is_mobile": True,
        "has_touch": True,
        "device_scale_factor": 2,
    },
    "desktop": {"viewport": {"width": 1440, "height": 900}},
}
ENGINES = {"mobile": ("chromium", "webkit"), "desktop": ("chromium",)}

#: يقيس الصفحةَ المفتوحة. ما لا يُرى لا يُحسب: `display:none` والمقصوصُ لقارئ الشاشة (1×1)
#: والمخفيُّ بـ`visibility`. والنصُّ يُحسب لعنصره الذي يحمله مباشرةً، لا لكلّ آبائه؛ ولا يُحسب
#: ما لا حرفَ فيه ولا رقم (سهمُ `.chv` 8px وفاصلُ الفتات `/`) ولا ما أُخفي عن قارئ الشاشة —
#: زخرفةٌ لا نصٌّ يُقرأ (القائمةُ المسموحةُ في H-03).
MEASURE_JS = r"""() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width <= 1 || r.height <= 1) return null;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity === 0) return null;
    return r;
  };
  const SEL = 'a[href], button, input:not([type="hidden"]), select, textarea, summary, '
            + '[role="button"], [role="tab"], [role="menuitem"], [role="link"]';
  let targets = 0, small44 = 0, small24 = 0;
  for (const el of document.querySelectorAll(SEL)) {
    const r = visible(el); if (!r) continue;
    targets++;
    if (r.width < 44 || r.height < 44) small44++;
    if (r.width < 24 || r.height < 24) small24++;
  }
  const READABLE = /[\p{L}\p{N}]/u;
  let tiny = 0, minFont = 999;
  for (const el of document.body.querySelectorAll('*')) {
    let own = false;
    for (const n of el.childNodes) if (n.nodeType === 3 && READABLE.test(n.textContent)) { own = true; break; }
    if (!own || el.closest('[aria-hidden="true"]') || !visible(el)) continue;
    const size = parseFloat(getComputedStyle(el).fontSize);
    if (size < minFont) minFont = size;
    if (size < 12) tiny++;
  }
  const TYPING = 'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"])'
               + ':not([type="submit"]):not([type="button"]):not([type="range"]), select, textarea';
  let smallInputs = 0;
  for (const el of document.querySelectorAll(TYPING)) {
    if (visible(el) && parseFloat(getComputedStyle(el).fontSize) < 16) smallInputs++;
  }
  const root = document.documentElement;
  return {
    targets, small44, small24, tiny_text: tiny,
    min_font: minFont === 999 ? 0 : Math.round(minFont * 10) / 10,
    h_overflow: Math.max(0, root.scrollWidth - root.clientWidth),
    inputs_under_16: smallInputs,
  };
}"""


def measure_page(page) -> dict[str, float]:
    return page.evaluate(MEASURE_JS)


def compare(baseline: dict, current: dict) -> tuple[list[str], list[str]]:
    """(ما زاد، ما نقص ولم يُسجَّل) للمؤشّرات المحروسة وحدها — كلٌّ سطرٌ: الصفحة، المؤشّر، قبل → بعد."""
    worse, stale = [], []
    for key in sorted(set(baseline) | set(current)):
        before, now = baseline.get(key, {}), current.get(key, {})
        profile = key.split("/")[1] if key.count("/") >= 2 else "mobile"
        for metric in GUARDED[profile]:
            was, is_ = before.get(metric, 0), now.get(metric, 0)
            if is_ > was:
                worse.append(f"{key}: {metric} {was} → {is_}")
            elif is_ < was:
                stale.append(f"{key}: {metric} {was} → {is_}")
    return worse, stale


def summary(data: dict) -> dict[str, dict[str, float]]:
    """مؤشّراتُ الخطّة لكلّ مِلفّ ومحرّك: K1 وK2 نسبتان، وK3 وK4 وK5 عددُ صفحات."""
    out: dict[str, dict[str, float]] = {}
    for key, m in data.items():
        run = key.rsplit("/", 1)[0]
        s = out.setdefault(
            run, {"pages": 0, "targets": 0, "small44": 0, "small24": 0, "k3": 0, "k4": 0, "k5": 0}
        )
        s["pages"] += 1
        s["targets"] += m["targets"]
        s["small44"] += m["small44"]
        s["small24"] += m["small24"]
        s["k3"] += 1 if 0 < m["min_font"] <= 10 else 0
        s["k4"] += 1 if m["h_overflow"] else 0
        s["k5"] += 1 if m["inputs_under_16"] else 0
    for s in out.values():
        s["k1_pct"] = round(100 * s["small44"] / s["targets"], 1) if s["targets"] else 0
        s["k2_pct"] = round(100 * s["small24"] / s["targets"], 1) if s["targets"] else 0
    return out


def read_baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def write_baseline(data: dict) -> None:
    BASELINE.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
