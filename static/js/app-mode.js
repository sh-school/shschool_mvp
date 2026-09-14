/**
 * app-mode.js — المنصّةُ مثبَّتةً تطبيقاً: لا صفحةَ بلا طريقِ رجوع.
 *
 * التطبيقُ المثبَّت (`display-mode: standalone|fullscreen`) بلا شريطِ متصفّح،
 * وآيفون لا يعطي فيه زرَّ رجوعٍ ولا إيماءةً يُعتمد عليها. فكلُّ ما يفترض
 * متصفّحاً يصير فخّاً (2026-09-14، بلاغُ المطوّر بلقطةٍ من آيفون):
 *
 *   ١. ملفُّ PDF يُعرض مكانَ المنصّة بعارض النظام، ولا شيءَ يُضغط للخروج —
 *      حتى ما يُطلب «تنزيلاً» (`as_attachment=True`) يعرضه آيفون في مكانه.
 *      فالملفُّ لا يُنتقل إليه: يُجلب في الخلفيّة ويُسلَّم لقائمة المشاركة
 *      (معاينةٌ، حفظٌ في الملفّات، طباعةٌ، واتساب) — وتُغلق فتبقى في مكانك.
 *      يُعلَّم الرابطُ بـ`data-app-file`، وحارسٌ في
 *      tests/test_app_mode_no_dead_ends.py يُفشل البوّابةَ على رابطٍ بلا وسم.
 *   ٢. «لسانٌ جديد» (`target="_blank"`) لا لسانَ له في التطبيق: صفحاتُ المنصّة
 *      تُفتح في النافذة نفسها، وتبقى الروابطُ الخارجيّةُ على حالها.
 *   ٣. الأوراقُ المستقلّة (قوالبُ الطباعة بلا إطار المنصّة) تحمل شريطَ
 *      «رجوع إلى المنصّة» — `components/app_back_bar.html` — يظهر هنا وحدَه.
 *
 * وخارج التطبيق لا يتغيّر شيء: المتصفّحُ له أزرارُه.
 */
(function () {
  'use strict';

  var STANDALONE = '(display-mode: standalone), (display-mode: fullscreen)';
  // المشاركةُ للّمس وحدَه: على الحاسوب المثبَّت نافذةٌ جديدةٌ للملفّ خيرٌ من قائمة مشاركة.
  var TOUCH = '(hover: none) and (pointer: coarse)';

  function matches(query) {
    return !!(window.matchMedia && window.matchMedia(query).matches);
  }

  // يُسأل عند كلّ ضغطة لا مرّةً عند التحميل — فيُختبر من الطرفيّة بتبديل matchMedia.
  function inApp() {
    return matches(STANDALONE) || window.navigator.standalone === true;
  }

  function canShareFiles() {
    if (!navigator.canShare || !window.File) return false;
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

  var READY = new WeakMap(); // عنصر → File جُلب ولم تُفتح له القائمةُ بعد

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
    if (el.tagName === 'A') return { url: el.href, init: {} };
    var form = el.form;
    var data = new FormData(form);
    if (el.name) data.append(el.name, el.value);
    var action = el.getAttribute('formaction') || form.getAttribute('action') || window.location.href;
    var method = (el.getAttribute('formmethod') || form.getAttribute('method') || 'get').toUpperCase();
    if (method === 'GET') {
      var url = new URL(action, window.location.href);
      data.forEach(function (value, key) { url.searchParams.append(key, value); });
      return { url: url.href, init: {} };
    }
    return { url: new URL(action, window.location.href).href, init: { method: method, body: data } };
  }

  function label(el) {
    return el.querySelector('.app-file-label') || el;
  }

  function setState(el, state) {
    if (!el.hasAttribute('data-app-file-idle')) {
      el.setAttribute('data-app-file-idle', label(el).innerHTML);
    }
    el.setAttribute('data-app-file-state', state);
    if (state === 'busy') {
      el.setAttribute('aria-busy', 'true');
      label(el).textContent = 'جارٍ تجهيز الملف…';
    } else if (state === 'ready') {
      el.removeAttribute('aria-busy');
      label(el).textContent = 'الملف جاهز — اضغط للحفظ أو الطباعة';
    } else {
      el.removeAttribute('aria-busy');
      el.removeAttribute('data-app-file-state');
      label(el).innerHTML = el.getAttribute('data-app-file-idle');
    }
  }

  function toast(msg) {
    if (typeof window.showToast === 'function') window.showToast(msg, 'danger');
  }

  function share(el, file) {
    return navigator.share({ files: [file] }).then(
      function () { READY.delete(el); setState(el, 'idle'); },
      function (err) {
        if (err && err.name === 'NotAllowedError') {
          // سفاري يشترط الضغطةَ نفسَها، والملفُّ تأخّر بعدها: ضغطةٌ ثانيةٌ تفتح القائمة.
          READY.set(el, file);
          setState(el, 'ready');
        } else {
          // AbortError: أغلق المستخدمُ القائمة — لا خطأ.
          READY.delete(el);
          setState(el, 'idle');
        }
      }
    );
  }

  function openFile(el) {
    var ready = READY.get(el);
    if (ready) {
      share(el, ready);
      return;
    }
    if (el.getAttribute('data-app-file-state') === 'busy') return;
    var req = requestFor(el);
    setState(el, 'busy');
    fetch(req.url, Object.assign({ credentials: 'same-origin' }, req.init))
      .then(function (response) {
        var type = response.headers.get('Content-Type') || '';
        if (!response.ok || type.indexOf('text/html') === 0) {
          throw new Error('not-a-file');
        }
        return response.blob().then(function (blob) {
          return new File([blob], filenameFrom(response, req.url), {
            type: blob.type || type || 'application/octet-stream',
          });
        });
      })
      .then(function (file) { return share(el, file); })
      .catch(function () {
        setState(el, 'idle');
        toast('تعذّر تجهيز الملف — حاول مرّةً أخرى.');
      });
  }

  /* ── ٢. «لسانٌ جديد» في النافذة نفسها ────────────────────────── */

  document.addEventListener('click', function (event) {
    if (event.defaultPrevented || event.button !== 0 || !inApp()) return;
    var el = event.target.closest && event.target.closest('a[href], button[type="submit"], button:not([type])');
    if (!el) return;

    if (el.hasAttribute('data-app-file') && matches(TOUCH) && canShareFiles()) {
      if (el.tagName === 'BUTTON' && el.form && !el.form.reportValidity()) return;
      event.preventDefault();
      openFile(el);
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

  function initBackBars() {
    // داخل إطار المنصّة للورقة إطارٌ حولها — فلا شريطَ هناك.
    if (!inApp() || window.top !== window) return;
    // الورقةُ بلا meta viewport يصغّرها الجوالُ بقدر عرضها على عرض الشاشة — فيُكبَّر الشريطُ بالقدر نفسه.
    var scale = document.documentElement.clientWidth / (window.screen.width || 1);
    scale = Math.min(Math.max(scale, 1), 4);
    var bars = document.querySelectorAll('[data-app-back-bar]');
    for (var i = 0; i < bars.length; i++) {
      bars[i].style.zoom = String(scale);
      bars[i].hidden = false;
    }
  }

  document.addEventListener('click', function (event) {
    var back = event.target.closest && event.target.closest('[data-app-back]');
    if (!back) return;
    // رجوعٌ إلى الصفحة التي فُتحت منها إن كانت من المنصّة، وإلّا فالرئيسيّة (href).
    if (window.history.length > 1 && document.referrer && sameOrigin(document.referrer)) {
      event.preventDefault();
      window.history.back();
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initBackBars);
  } else {
    initBackBars();
  }
})();
