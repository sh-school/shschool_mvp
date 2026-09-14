/**
 * app-mode.js — المنصّةُ مثبَّتةً تطبيقاً: لا صفحةَ بلا طريقِ رجوع.
 *
 * التطبيقُ المثبَّت (`display-mode: standalone|fullscreen`) بلا شريطِ متصفّح،
 * وآيفون لا يعطي فيه زرَّ رجوعٍ ولا إيماءةً يُعتمد عليها. فكلُّ ما يفترض
 * متصفّحاً يصير فخّاً (2026-09-14، بلاغُ المطوّر بلقطةٍ من آيفون):
 *
 *   ١. ملفٌّ (PDF، Excel، مرفق) يُعرض مكانَ المنصّة بعارض النظام، ولا شيءَ يُضغط
 *      للخروج — حتى ما يُطلب «تنزيلاً» (`as_attachment=True`) يعرضه آيفون مكانه.
 *      فالملفُّ لا يُنتقل إليه على جهاز لمس: يُجلب في الخلفيّة ويُسلَّم لقائمة
 *      المشاركة (معاينةٌ، حفظٌ، طباعةٌ، واتساب) — وتُغلق فتبقى في مكانك. وما يرفضه
 *      النظامُ مشاركةً (أندرويد لا يشارك docx/xlsx) يُنزَّل تنزيلاً.
 *      يُعلَّم الرابطُ بـ`data-app-file`، وحارسٌ في
 *      tests/test_app_mode_no_dead_ends.py يُفشل البوّابةَ على رابطٍ بلا وسم.
 *   ٢. «لسانٌ جديد» (`target="_blank"`) لصفحةٍ من المنصّة يُفتح في النافذة نفسها.
 *      أمّا الملفُّ فلا: حيث لا مشاركة يبقى لسانُه الجديد، ولا يحلّ محلّ التطبيق.
 *   ٣. الأوراقُ المستقلّة (قوالبُ الطباعة بلا إطار المنصّة) تحمل شريطَ
 *      «رجوع إلى المنصّة» — `components/app_back_bar.html` — يظهر هنا وحدَه.
 *
 * وخارج التطبيق لا يتغيّر شيء: المتصفّحُ له أزرارُه.
 */
(function () {
  'use strict';

  var STANDALONE = '(display-mode: standalone), (display-mode: fullscreen)';

  function matches(query) {
    return !!(window.matchMedia && window.matchMedia(query).matches);
  }

  // يُسأل عند كلّ ضغطة لا مرّةً عند التحميل — فيُختبر من الطرفيّة بتبديل matchMedia.
  function inApp() {
    return matches(STANDALONE) || window.navigator.standalone === true;
  }

  // جهازُ لمس — لا «pointer: coarse» وحدَه: آيباد بلوحة مفاتيحٍ ولوحةِ لمسٍ يُعلن
  // مؤشّراً دقيقاً، وهو هو الذي يعرض الملفَّ مكانَ التطبيق.
  function touchDevice() {
    return (navigator.maxTouchPoints || 0) > 0 || matches('(pointer: coarse)');
  }

  function canShareFiles() {
    if (!navigator.share || !navigator.canShare || !window.File) return false;
    try {
      return navigator.canShare({ files: [new File([''], 'x.pdf', { type: 'application/pdf' })] });
    } catch (e) {
      return false;
    }
  }

  function sameOrigin(url) {
    try {
      return new URL(url, window.location.href).origin === window.location.origin;
    } catch (e) {
      return false;
    }
  }

  /* ── ١. الملفّ إلى قائمة المشاركة ─────────────────────────────── */

  // عنصر → {url, file}: ملفٌّ جُلب ولم تُفتح له القائمةُ بعد. والعنوانُ معه: رابطٌ
  // يغيّر سكربتُه عنوانَه (الورق، السنة) لا يُشارَك له ملفُّ العنوان القديم.
  var READY = new WeakMap();

  function filenameFrom(response, url) {
    var cd = response.headers.get('Content-Disposition') || '';
    var star = /filename\*=UTF-8''([^;]+)/i.exec(cd);
    if (star) {
      try { return decodeURIComponent(star[1]); } catch (e) { /* يسقط إلى التالي */ }
    }
    var plain = /filename="?([^";]+)"?/i.exec(cd);
    if (plain) return plain[1];
    var last = new URL(url, window.location.href).pathname.split('/').filter(Boolean).pop();
    return last || 'file';
  }

  function requestFor(el) {
    if (el.tagName === 'A') return { url: el.href, init: {}, method: 'GET' };
    var form = el.form;
    var data = new FormData(form);
    if (el.name) data.append(el.name, el.value);
    var action = el.getAttribute('formaction') || form.getAttribute('action') || window.location.href;
    var method = (el.getAttribute('formmethod') || form.getAttribute('method') || 'get').toUpperCase();
    if (method === 'GET') {
      var url = new URL(action, window.location.href);
      data.forEach(function (value, key) { url.searchParams.append(key, value); });
      return { url: url.href, init: {}, method: method };
    }
    return { url: new URL(action, window.location.href).href, init: { method: method, body: data }, method: method };
  }

  function label(el) {
    return el.querySelector('.app-file-label') || el;
  }

  function setState(el, state) {
    if (!el.hasAttribute('data-app-file-idle')) {
      el.setAttribute('data-app-file-idle', label(el).innerHTML);
    }
    if (state === 'busy') {
      el.setAttribute('data-app-file-state', state);
      el.setAttribute('aria-busy', 'true');
      label(el).textContent = 'جارٍ تجهيز الملف…';
    } else if (state === 'ready') {
      el.setAttribute('data-app-file-state', state);
      el.removeAttribute('aria-busy');
      label(el).textContent = 'الملف جاهز — اضغط للحفظ أو الطباعة';
    } else {
      el.removeAttribute('aria-busy');
      el.removeAttribute('data-app-file-state');
      label(el).innerHTML = el.getAttribute('data-app-file-idle');
    }
  }

  // الأوراقُ المستقلّة لا تحمّل base.js فلا showToast فيها — والرسالةُ لا تُبتلع.
  function tell(msg) {
    if (typeof window.showToast === 'function') window.showToast(msg, 'danger');
    else window.alert(msg);
  }

  // تنزيلٌ بلا انتقال: ما لا تقبله قائمةُ المشاركة يُحفظ ملفّاً والصفحةُ في مكانها.
  function save(file) {
    var href = URL.createObjectURL(file);
    var a = document.createElement('a');
    a.href = href;
    a.download = file.name;
    a.hidden = true;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.setTimeout(function () { URL.revokeObjectURL(href); }, 60000);
  }

  function share(el, url, file, fresh) {
    return navigator.share({ files: [file] }).then(
      function () { READY.delete(el); setState(el, 'idle'); },
      function (err) {
        var name = err && err.name;
        if (name === 'AbortError') {
          // أغلق المستخدمُ القائمة — لا خطأ.
          READY.delete(el);
          setState(el, 'idle');
        } else if (name === 'NotAllowedError' && !fresh) {
          // سفاري يشترط الضغطةَ نفسَها، والملفُّ تأخّر بعدها: ضغطةٌ ثانيةٌ تفتح القائمة.
          READY.set(el, { url: url, file: file });
          setState(el, 'ready');
        } else {
          // رفضٌ والضغطةُ طازجة: ليس انتهاءَ تفعيل بل رفضٌ للملفّ نفسه — فيُنزَّل.
          READY.delete(el);
          setState(el, 'idle');
          save(file);
        }
      }
    );
  }

  function openFile(el) {
    var req = requestFor(el);
    var ready = READY.get(el);
    if (ready && ready.url === req.url) {
      share(el, req.url, ready.file, true);
      return;
    }
    READY.delete(el);
    if (el.getAttribute('data-app-file-state') === 'busy') return;
    setState(el, 'busy');
    fetch(req.url, Object.assign({ credentials: 'same-origin' }, req.init))
      .then(function (response) {
        var type = response.headers.get('Content-Type') || '';
        var html = type.indexOf('text/html') === 0;
        // الجلسةُ انتهت أو لا صلاحية: صفحةُ الدخول أو المنع تُعرض في إطار المنصّة
        // كما كانت تُعرض بالانتقال — لا «حاول مرّةً أخرى» لا تنتهي.
        if ((response.redirected && html) || response.status === 401 || response.status === 403) {
          setState(el, 'idle');
          if (req.method === 'GET') window.location.assign(response.redirected ? response.url : req.url);
          else tell('انتهت الجلسة أو لا صلاحية — أعد المحاولة بعد الدخول.');
          return null;
        }
        if (!response.ok) {
          // render_pdf يشرح سببَ الفشل نصّاً (503) — يُقرأ ولا يُطمس.
          return response.text().then(function (text) {
            setState(el, 'idle');
            tell(type.indexOf('text/plain') === 0 && text ? text.slice(0, 300) : 'تعذّر تجهيز الملف — حاول مرّةً أخرى.');
            return null;
          });
        }
        if (html) {
          // صفحةٌ لا ملفّ: تُفتح كما كانت.
          setState(el, 'idle');
          if (req.method === 'GET') window.location.assign(req.url);
          return null;
        }
        return response.blob().then(function (blob) {
          return new File([blob], filenameFrom(response, req.url), {
            type: blob.type || type || 'application/octet-stream',
          });
        });
      })
      .then(function (file) {
        if (!file) return;
        var shareable = false;
        try { shareable = navigator.canShare({ files: [file] }); } catch (e) { shareable = false; }
        if (!shareable) {
          setState(el, 'idle');
          save(file);
          return;
        }
        return share(el, req.url, file, false);
      })
      .catch(function () {
        setState(el, 'idle');
        tell('تعذّر تجهيز الملف — حاول مرّةً أخرى.');
      });
  }

  /* ── ٢. «لسانٌ جديد» في النافذة نفسها ────────────────────────── */

  document.addEventListener('click', function (event) {
    if (event.defaultPrevented || event.button !== 0 || !inApp()) return;
    var el = event.target.closest && event.target.closest('a[href], button[type="submit"], button:not([type])');
    if (!el) return;

    if (el.hasAttribute('data-app-file')) {
      if (touchDevice() && canShareFiles()) {
        if (el.tagName === 'BUTTON' && el.form && !el.form.reportValidity()) return;
        event.preventDefault();
        openFile(el);
      }
      // وحيث لا مشاركة يُترك الرابطُ لسلوكه — ولسانُه الجديدُ إن كان له.
      return;
    }

    if (el.tagName === 'A' && el.target === '_blank' && sameOrigin(el.href)) {
      event.preventDefault();
      window.location.assign(el.href);
    } else if (el.tagName === 'BUTTON' && el.getAttribute('formtarget') === '_blank') {
      el.removeAttribute('formtarget'); // يُرسَل النموذجُ في النافذة نفسها
    }
  });

  /* ── ٣. شريطُ الرجوع في الأوراق المستقلّة ─────────────────────── */

  var ORIGIN_KEY = 'app-back:' + window.location.pathname;

  // من أين دخلنا الورقة: أوّلُ مرجعٍ من صفحةٍ أخرى. وتغييرُ اختيار الورقة (المعلّم،
  // الورق) يعيد تحميلَها ومرجعُها هي نفسُها — فلا يُكتب فوق الأصل.
  function rememberOrigin() {
    var ref = document.referrer;
    if (!ref || !sameOrigin(ref)) return;
    if (new URL(ref).pathname === window.location.pathname) return;
    try { window.sessionStorage.setItem(ORIGIN_KEY, ref); } catch (e) { /* تخزينٌ محجوب */ }
  }

  function originUrl() {
    try { return window.sessionStorage.getItem(ORIGIN_KEY); } catch (e) { return null; }
  }

  // الورقةُ بلا meta viewport يصغّرها الجوالُ بقدر عرضها على عرض الشاشة — فيُكبَّر
  // الشريطُ بالقدر نفسه. وعرضُ الشاشة بحسب الاتّجاه: screen.width في iOS عرضُ
  // الوضع العموديّ دائماً.
  function scaleBars(bars) {
    var a = window.screen.width || 1;
    var b = window.screen.height || a;
    var screenWidth = matches('(orientation: landscape)') ? Math.max(a, b) : Math.min(a, b);
    var scale = document.documentElement.clientWidth / screenWidth;
    scale = Math.min(Math.max(scale, 1), 4);
    for (var i = 0; i < bars.length; i++) bars[i].style.zoom = String(scale);
  }

  function initBackBars() {
    // داخل إطار المنصّة للورقة إطارٌ حولها — فلا شريطَ هناك.
    if (!inApp() || window.top !== window) return;
    var bars = document.querySelectorAll('[data-app-back-bar]');
    if (!bars.length) return;
    rememberOrigin();
    scaleBars(bars);
    for (var i = 0; i < bars.length; i++) bars[i].hidden = false;
    var rescale = function () { scaleBars(bars); };
    window.addEventListener('resize', rescale);
    window.addEventListener('orientationchange', rescale);
  }

  document.addEventListener('click', function (event) {
    var back = event.target.closest && event.target.closest('[data-app-back]');
    if (!back) return;
    var origin = originUrl();
    if (!origin) return; // الرابطُ نفسُه: الرئيسيّة
    event.preventDefault();
    window.location.assign(origin);
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initBackBars);
  } else {
    initBackBars();
  }
})();
