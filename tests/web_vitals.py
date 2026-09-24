"""قياسُ Core Web Vitals وحمولةِ الصفحة في متصفّحٍ حقيقيّ (P3-3).

ما يُقاس:

- **CLS** — انزياحُ التخطيط، بنافذة الجلسة كما تعرّفها Google (فجواتٌ أقلّ من ثانية،
  ونافذةٌ لا تتجاوز خمساً، والأسوأُ منها). حتميٌّ: لا يتذبذب بين تشغيلٍ وآخر.
- **LCP** — أكبرُ عنصرٍ مرسوم. يتذبذب على مُشغِّلات CI، فسقفُه واسع.
- **INP** — أبطأُ تفاعلٍ (النقرُ على مبدّل الوضع الليليّ: يُعيد حسابَ الأنماط لكلّ
  الصفحة، فيقيس كلفةَ CSS فعلاً). `Event Timing` لا يُبلّغ ما دون 16ms فتُقرأ صفراً.
- **الحمولة** — عددُ الطلبات وبايتاتُ CSS وJS والخطوط وما يحجب الرسم. حتميّةٌ،
  وهي التي تُسقط LCP فعلاً: من يزيد ملفَّ CSS بالميغابايت يُرى في العدد قبل
  أن يُرى في الميلّي ثانية.

`live_server` في الاختبارات يخدم `static/` بلا ضغطٍ ولا تصغير (`StaticFilesHandler`)،
فبايتاتُه خامٌّ أكبرُ من الإنتاج (Brotli + مصغَّر). والميزانيةُ سقفٌ على **الخام**
لأنّه الثابتُ بين تشغيلٍ وآخر — كما يفعل `tests/test_css_budget.py` بحجم المصدر.
"""

from __future__ import annotations

from typing import Any

INIT_SCRIPT = """
(() => {
  const v = window.__vitals = {lcp: 0, lcpElement: '', cls: 0, inp: 0, interactions: 0};
  try {
    new PerformanceObserver(list => {
      for (const e of list.getEntries()) {
        v.lcp = e.startTime;
        v.lcpElement = e.element ? e.element.tagName + (e.element.id ? '#' + e.element.id : '') : '';
      }
    }).observe({type: 'largest-contentful-paint', buffered: true});
  } catch (e) {}
  let cur = 0, first = 0, prev = 0, max = 0;
  try {
    new PerformanceObserver(list => {
      for (const e of list.getEntries()) {
        if (e.hadRecentInput) continue;
        if (cur && e.startTime - prev < 1000 && e.startTime - first < 5000) {
          cur += e.value;
        } else {
          cur = e.value; first = e.startTime;
        }
        prev = e.startTime;
        if (cur > max) max = cur;
        v.cls = max;
      }
    }).observe({type: 'layout-shift', buffered: true});
  } catch (e) {}
  const byId = new Map();
  try {
    new PerformanceObserver(list => {
      for (const e of list.getEntries()) {
        if (!e.interactionId) continue;
        byId.set(e.interactionId, Math.max(byId.get(e.interactionId) || 0, e.duration));
        v.inp = Math.max(...byId.values());
        v.interactions = byId.size;
      }
    }).observe({type: 'event', durationThreshold: 16, buffered: true});
  } catch (e) {}
})();
"""

#: أصنافُ الموارد التي تُعدّ في الحمولة.
KINDS = ("stylesheet", "script", "font", "image")


class Load:
    """يجمع ما نزل أثناء تحميل الصفحة — يُنشَأ قبل `goto` ويُقرأ بعده."""

    def __init__(self, page) -> None:
        self.requests = 0
        self.bytes = dict.fromkeys(KINDS, 0)
        self.count = dict.fromkeys(KINDS, 0)
        page.on("response", self._on_response)

    def _on_response(self, response) -> None:
        self.requests += 1
        kind = response.request.resource_type
        if kind not in KINDS:
            return
        try:
            size = len(response.body())
        except Exception:  # noqa: BLE001 — ردٌّ أُلغي قبل اكتمال جسمه (تحويلٌ/إغلاقٌ)
            return
        self.count[kind] += 1
        self.bytes[kind] += size


def install(page) -> Load:
    """يُستدعى قبل أوّل `goto` في الصفحة."""
    page.add_init_script(INIT_SCRIPT)
    return Load(page)


def interact(page, selector: str = "#theme-toggle") -> None:
    """نقرةٌ واحدةٌ حقيقيّةٌ ثمّ إعادتُها — فتُقاس كلفةُ التبديل في الاتّجاهين."""
    page.click(selector)
    page.wait_for_timeout(300)
    page.click(selector)
    page.wait_for_timeout(300)


def read(page, load: Load) -> dict[str, Any]:
    """كلُّ المقاييس بعد اكتمال الصفحة والتفاعل — أرقامٌ عاديّةٌ قابلةٌ للطباعة."""
    vitals = page.evaluate("window.__vitals")
    blocking = page.evaluate(
        "document.querySelectorAll('head link[rel=stylesheet]:not([media=print])').length"
    )
    return {
        "lcp_ms": round(vitals["lcp"]),
        "lcp_element": vitals["lcpElement"],
        "cls": round(vitals["cls"], 4),
        "inp_ms": round(vitals["inp"]),
        "requests": load.requests,
        "blocking_stylesheets": blocking,
        "css_kb": round(load.bytes["stylesheet"] / 1024),
        "js_kb": round(load.bytes["script"] / 1024),
        "font_kb": round(load.bytes["font"] / 1024),
        "image_kb": round(load.bytes["image"] / 1024),
    }


#: سقفُ كلِّ مقياس. كلُّ رقمٍ له سببٌ، ولا رقمَ «ما تحمّله الأجهزة».
#:
#: - `lcp_ms` 2500 و`cls` 0.1: عتبتا «جيّد» عند Google. المقيسُ محلّياً 184–888ms
#:   و0–0.007، فالهامشُ يستوعب مُشغِّلَ CI أبطأَ بمرّتين أو ثلاث بلا تذبذب.
#: - `inp_ms` 300: المقيسُ 24–64ms (نقرةُ مبدّل الوضع الليليّ). أوسعُ من «جيّد» (200)
#:   لأنّ CI أبطأ؛ وأضيقُ من «ضعيف» (500) ليُمسك تراجعاً حقيقيّاً في كلفة الأنماط.
#: - الحمولةُ **خامٌّ من خادم الاختبار** (بلا ضغطٍ ولا تصغير)، سقفُها ≈ المقيس + 15%:
#:   `css_kb` 404 → 460 → 462 (2026-09-22: تجميعُ معلّمي الزيارة الصفّية حسب
#:   القسم — نقطةُ لونٍ + نظيرُها الليليّ لكلّ الخمسةَ عشرَ قسماً، لا مساحةَ
#:   لحذف أحدهما فتُكسر مركزيّةُ الهويّة/CSS بين النهاريّ والليليّ) → 466 (اليومُ
#:   نفسُه: دمجُ main بعد اندماج #475/#477 أضاف ~2.5KB مستقلّةً عن هذا الفرع —
#:   السقفُ هنا مشتركٌ بين كلّ طلبات الدمج المفتوحة، فطلبٌ يقيسه مقابل main
#:   قديمةٍ يصطدم به بعد كلّ دمجٍ آخر يسبقه؛ هامشٌ أوسعُ قليلاً يمتصّ نموّاً
#:   عضويّاً كهذا لا ميزةً واحدةً بعينها) → 468 (2026-09-23: قوائمُ الشريط
#:   الطويلة بأعمدة — `.sd-menu--cols-{2,3,4}` نظيرُ القائمة الأفقيّة في لوحة
#:   الإدارة، مركزيٌّ لتسع قوائم لا ميزةً واحدة، فلا مساحةَ لحذفه) → 470
#:   (2026-09-24، قرارُ المالك: M-01 أهدافُ اللمس 44px على `pointer: coarse` — +1.6KB
#:   تُنزل K1 من 49.4% إلى 0.5% في رحلات الأدوار الخمسة؛ الحجمُ الخامّ صار 468.1KB
#:   بلا هامشٍ تحت 468، وكتلةٌ واحدةٌ مجمَّعةٌ كما توصي خطّةُ الجوال)، `js_kb`
#:   333 → 400 (لوحة التحكم تحمّل Chart.js)، الخطوطُ 61 → 120، الصورُ 134 → 220.
#:   و`blocking_stylesheets` 8 → 10: كلُّ ملفٍّ فوقها طلبٌ يحجب الرسمَ (ADR-0003
#:   قسّم الملفَّ ثمانيةً؛ فليكن التالي قراراً لا انزلاقاً).
BUDGET = {
    "cls": 0.1,
    "lcp_ms": 2500,
    "inp_ms": 300,
    "requests": 40,
    "blocking_stylesheets": 10,
    "css_kb": 470,
    "js_kb": 400,
    "font_kb": 120,
    "image_kb": 220,
}

#: مقاييسُ لا تُقاس على كلّ صفحة: الصفرُ فيها يعني «لم يُبلَّغ» لا «فوريّ».
#: صفحةُ الدخول كانت لا تُبلِّغ FCP ولا LCP في Chromium أصلاً: بطاقتُها تدخل بأنيميشن
#: `loginCardIn` من `opacity: 0` (لا شيءَ في 1.4 ثانية؛ وبلا `opacity` 408–420ms).
#: أُصلح بإزالة التلاشي وبقاء الانزلاق، والاختبارُ يشترط الآن LCP لها. وما بقي هنا
#: للـINP: لا مبدّلَ في صفحة الدخول يُنقر عليه.
NOT_REPORTED_IS_OK = ("lcp_ms", "inp_ms")


def violations(name: str, metrics: dict[str, Any], budget: dict[str, float] = BUDGET) -> list[str]:
    """أسطرٌ «الصفحة: المقياس قيمته > سقفه» — فارغةٌ إن لم يُتجاوَز شيء."""
    found = []
    for key, ceiling in budget.items():
        value = metrics.get(key)
        if value is None or (value == 0 and key in NOT_REPORTED_IS_OK):
            continue
        if value > ceiling:
            found.append(f"{name}: {key} {value} > {ceiling}")
    return found


def median_of(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """وسيطُ كلِّ مقياسٍ رقميّ عبر التشغيلات — يخفّف تذبذبَ LCP وINP على مُشغِّلات CI."""
    out: dict[str, Any] = dict(runs[0])
    for key, first in runs[0].items():
        if isinstance(first, (int, float)) and not isinstance(first, bool):
            values = sorted(run[key] for run in runs)
            out[key] = values[len(values) // 2]
    return out
