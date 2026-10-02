# HTMX وJS في الواجهة

متى تقرأ هذا الملف: حين تكتب سلوكاً تفاعليّاً — HTMX، نقرةٌ تفتح أو تخفي، تأكيدٌ، تصديرٌ من زرّ، سكربتُ صفحة — أو حين «لا يعمل الزرّ في الإنتاج».

المصادر: `core/htmx_utils.py`، `static/js/app.js`، `static/js/actions.js`، `static/js/page-nav.js`، `static/js/export-center.js`، `shschool/settings/base.py` و`production.py` (CSP)، `tests/test_htmx_patterns.py`، `tests/test_page_nav_*.py`.

## HTMX
- المكتبة محلّيّة: `static/js/htmx.min.js` الإصدار 1.9.12 (`defer` في `templates/base/base.html`) — لا CDN. و`django-htmx` مثبّت (`request.htmx`).
- **الـview تختار القالب**، لا القالب:
```python
from core.htmx_utils import htmx_or_full, htmx_toast, htmx_redirect, is_htmx
return htmx_or_full(request, "library/partials/book_rows.html", "library/book_list.html", ctx)
```
  `{% extends %}` يجب أن يكون أوّلَ وسمٍ في القالب، فـ`{% if request.htmx %}{% extends … %}` خطأُ قالبٍ لا نمط.
- الإشعار: `htmx_toast(...)` يضع `HX-Trigger: {"showToast": …}`، ويلتقطه `app.js` فينادي `window.showToast(message, type)`؛ وإعادةُ التوجيه `htmx_redirect`، والتحديثُ `htmx_refresh`.
- أخطاءُ الشبكة يلتقطها مستمعٌ واحدٌ في `app.js` (`htmx:responseError`: 403 صلاحيّة، 404، ≥500، 0 اتّصال) — لا تكتب معالجاً آخر.
- مؤشّرُ التحميل `#htmx-loading-bar`، والإعلانُ لقارئ الشاشة في `#sr-live` (`aria-live="polite"`)، والإشعاراتُ في `#toast-container`.
- البحثُ الحيّ عبر `field`: `hx_get=url hx_trigger="input changed delay:400ms"` (المثالُ في رأس `ui.py`)؛ والروابطُ بـ`{% url %}` لا مساراتٍ مكتوبة.
- بعد تبديل المحتوى بـ`page-nav.js` يُعاد ربطُ HTMX (`tests/test_page_nav_htmx_process.py`).

## سياسةُ أمن المحتوى (CSP)
- `script-src` يحمل `nonce` ⇒ المتصفّحُ يتجاهل `'unsafe-inline'` للسكربتات: **كلُّ `<script>` داخليٍّ يلزمه `nonce="{{ request.csp_nonce }}"`**، وسماتُ `onclick`/`onchange` تُحجب ولا ينفعها nonce.
- الإنتاجُ **يفرض** السياسة (`CSP_ENFORCE` افتراضُه `True` في `shschool/settings/production.py`) بعد نقل المعالجات الستّة والثمانين إلى `data-*`؛ والقوالبُ اليومَ بلا `onclick=`/`onchange=`. فالمعالجُ المضمَّنُ الجديدُ يعمل في التطوير (report-only) **ويموت في الإنتاج** صامتاً. والحارس: `tests/test_csp_policy.py`.
- `script-src` في الإنتاج: الذاتُ والـnonce و`cdn.jsdelivr.net` و`unpkg.com` وحدَها — مكتبةٌ من مصدرٍ آخر تُحجب.
- `style-src` يُبقي `'unsafe-inline'` لسمات `style=` القديمة — ولا يبيح سمةً جديدة (سقّاطةُ الهويّة على صفر).

## مفرداتُ `data-*` (`static/js/actions.js`)
| السمة | الحدث | الفعل |
|---|---|---|
| `data-autosubmit` | change | يرسل النموذجَ الحاضن |
| `data-confirm="نصّ"` | submit | تأكيدٌ بنافذةٍ مخصّصة (`base.js`) |
| `data-loading` | submit | دوّارةٌ على الزرّ المرسِل |
| `data-toggle="#sel"` / `data-toggle-class="#sel|صنف"` / `data-hide` / `data-show` / `data-remove` / `data-click` | click | إظهارٌ وإخفاءٌ وحذفٌ ونقرٌ بالنيابة |
| `data-copy="نصّ"` | click | نسخٌ إلى الحافظة |
| `data-call="اسم"` + `data-arg` | click | دالّةٌ من القائمة البيضاء `CALLABLE` |
| `data-mirror="#sel"` | input | يعكس القيمة |
| `data-bulk*` | — | اختيارٌ جماعيٌّ بعدّاد وتأكيد |
| `data-action="reload|back|stop"` | click | (و`print` للقوالب الورقيّة المسمّاة وحدَها) |
- دالّةٌ جديدةٌ لـ`data-call`: تُسنَد إلى `window` في سكربتٍ **وتُضاف إلى `CALLABLE`** — لا تُعلَن مجرّدةً (`tests/test_page_nav_callables.py`).

## سكربتُ الصفحة
- داخل IIFE: `page-nav.js` يعيد تشغيله في المستند نفسِه، والثوابتُ العامّة تنفجر في الزيارة الثانية (فيُحمَّل كاملاً).
- لا رقمَ مدّةٍ في JS لحركةٍ مركزيّة — يُقرأ من CSS (`--transition-page`).
- ألوانُ الرسوم من `window.chartColor('chart-1')`/`chartPalette(n)`/`chartAlpha(n, a)` (في رأس `base.html`) — لا سداسيّ.
- لا `data-no-page-nav` إلّا لعلّة.

## التصدير من الواجهة
- رابطُ ملفٍّ أو زرُّه بسمة `data-app-file` يمرّ من `static/js/export-center.js`: ملفٌّ مباشرٌ يُحفظ بلا وميض، ومهمّةٌ خلفيّةٌ (202 + JSON) بإشعار «جارٍ التحضير» ثمّ التنزيل (`tests/test_app_mode_no_dead_ends.py`). بناءُ الملفّ نفسِه في مهارة `schoolos-report-ar`.
- لا `window.print()` في صفحةٍ تفاعليّة (`tests/test_no_web_page_print_button.py`).

## أنماطٌ مضادّة
- `<button onclick="…">` أو `<script>` بلا `nonce`، أو `eval`/`new Function`.
- `fetch` يدويٌّ يكرّر ما يفعله HTMX أو `export-center.js`.
- معالجُ `htmx:responseError` ثانٍ، أو `alert()` بدل `showToast`.
- مسارٌ مكتوبٌ `hx-get="/grades/edit/1/"` بدل `{% url %}`.
- سكربتُ صفحةٍ يعلن `const X = …` في النطاق العامّ.
