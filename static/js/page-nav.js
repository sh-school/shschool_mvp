/**
 * التنقّلُ بين صفحات المنصّة كلِّها بتبديل المحتوى وحدَه (قرارُ المالك 2026-09-20).
 *
 * كان كلُّ رابطٍ أو نموذجٍ يحمّل مستنداً كاملاً: تختفي الصفحةُ كلُّها ثمّ تظهر. فهنا تبقى الترويسةُ والقائمةُ والفوتر
 * ثابتةً، ويتلاشى محتوى الصفحة القديمُ (`.is-leaving`) ثمّ يظهر الجديدُ بحركة `page-in` (كلاهما CSS في 20-components،
 * ومدّتُهما من `--transition-page`)، وتنقّلُ القسم ثابتٌ لا يتلاشى، ويُحدَّث العنوانُ وفتاتُ الخبز والرسائلُ والسجلُّ (`pushState`).
 *
 * يشمل: كلَّ رابطٍ في الصفحة (لا القوائم وحدَها)، والنماذجَ GET (بحثٌ وترشيح) وPOST (حفظٌ ثمّ إعادةُ توجيه).
 * لا يشمل: روابطَ الملفّات (`data-app-file`، pdf/xlsx/csv/export/print/download)، وما فُتح في لسانٍ جديد، وما وسمتَه
 * `data-no-page-nav`، والنماذجَ الحاملةَ لـ`hx-*`. وهذه تعمل كما كانت.
 *
 * سكربتاتُ الصفحة وأنماطُها تُحمَّل وتُشغَّل بعد التبديل بترتيبها. وسكربتٌ شُغِّل من قبلُ في هذا المستند يُشغَّل ثانيةً
 * داخل غلافٍ فلا تصطدم ثوابتُه العامّةُ بالسابقة. وما لا يُؤمَن تبديلُه (ليست من هذا القالب كالدخول، أو ردُّها ليس HTML)
 * يُحمَّل كاملاً كما كان — فالأسوأ حالٌ هو ما كان قبلَه لا صفحةٌ معطوبة.
 *
 * القوائمُ المنسدلةُ تتلاشى من لحظة النقر بمدّة تلاشي الصفحة نفسِها (`.is-fading`، CSS) ثمّ تُغلق — كانت تبقى مفتوحةً حتى يُبدَّل
 * المحتوى ثمّ تختفي فجأة.
 *
 * لوحةُ الإدارة (`data-page-nav="fade"` على وسم السكربت، و`data-page-nav-root` للحاوية): صفحاتُها تحمل سكربتاتٍ تهيّئ أدواتِها عند
 * `load` (SelectFilter وDateTimeShortcuts وactions…) ولا تُعاد هذه بعد تبديل DOM، فلا تُبدَّل. تتلاشى الحاويةُ بالآلية نفسِها
 * ثمّ يُحمَّل المستندُ كاملاً، وتظهر الصفحةُ التالية بحركة `page-in` نفسِها (في admin_theme.css): رمشٌ واحدٌ صار انتقالاً سلساً.
 */
(function () {
  'use strict';
  var cfg = document.currentScript;
  var FADE_ONLY = !!cfg && cfg.getAttribute('data-page-nav') === 'fade';
  if (!document.body) return;
  if (FADE_ONLY) {
    if (document.body.classList.contains('popup')) return;   // نافذةُ إضافةٍ/بحثٍ منبثقة: لا انتقالَ فيها
  } else if (!document.body.hasAttribute('data-page-nav') || !window.fetch || !window.DOMParser || !window.FormData) return;

  var ROOT = (cfg && cfg.getAttribute('data-page-nav-root')) || '#main-content';
  var SKIP_PATH = FADE_ONLY ? /^\/(static|media|api)\b|\/logout\/?$/ : /^\/(admin|logout|static|media|api)\b/;
  var FILE_LIKE = /(\.(pdf|xlsx?|csv|zip|docx?|png|jpe?g|svg|json)$|\/(pdf|xlsx|csv|export|download|print)(\/|$|\?))/i;
  // ما يحمل حالةَ الفتح: قائمةُ المنصّة `.open`، وقسمُ قائمة الإدارة `.is-open` (والتلاشي `.is-fading` يوضع على الحامل نفسِه).
  var MENUS = '.sd-menu.open, .sd-menu.is-open, .adm-nav__item.is-open';
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  // ما يدعم المزجَ الأصليَّ بين صفحتين (`@view-transition`): الإدارةُ تتركه له بدل تلاشي JS.
  var NATIVE_VT = !!(window.CSS && CSS.supports && CSS.supports('at-rule(@view-transition)'));
  var token = 0;
  var nonce = (function () { var s = document.querySelector('script[nonce]'); return s ? (s.nonce || s.getAttribute('nonce') || '') : ''; })();
  var executed = new Set();   // سكربتاتُ الصفحات التي شُغِّلت بعد التحميل الأوّل

  // مدّةُ التلاشي تُقرأ من CSS (`--transition-base` في الهويّة)، فلا رقمَ ثانياً هنا يتباعد عنها.
  function fadeMs() {
    var d = (getComputedStyle(document.documentElement).getPropertyValue('--transition-page') || '').trim().split(/\s+/)[0];
    var n = parseFloat(d);
    return isNaN(n) ? 0 : (d.slice(-2) === 'ms' ? n : n * 1000);
  }

  function eligibleLink(a, e) {
    if (!a || !a.href || a.origin !== location.origin) return false;
    if (e && (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey)) return false;
    if (a.target || a.hasAttribute('download') || a.hasAttribute('data-app-file') || a.hasAttribute('data-action')) return false;
    if (a.hasAttribute('hx-get') || a.hasAttribute('data-no-page-nav') || a.closest('[data-no-page-nav]')) return false;
    if (a.getAttribute('href') === '#' || /^javascript:/i.test(a.getAttribute('href') || '')) return false;
    if (SKIP_PATH.test(a.pathname) || FILE_LIKE.test(a.pathname)) return false;
    // رابطٌ إلى موضعٍ في الصفحة نفسِها (#…) يبقى للمتصفّح. أمّا الرابطُ إلى الصفحة الحاليّة بعينها (الرئيسيّة وأنت فيها)
    // فيُمنع من إعادة التحميل (يعالجه معالِجُ النقر أدناه) — كان المتصفّحُ يعيد تحميلها كاملةً فترمش الأيقونات وصورتا الفوتر.
    if (a.pathname === location.pathname && a.search === location.search && a.hash) return false;
    return true;
  }

  function eligibleForm(form, submitter) {
    if (!form || form.target || form.hasAttribute('data-app-file') || form.hasAttribute('data-no-page-nav') || form.closest('[data-no-page-nav]')) return false;
    if (submitter && (submitter.hasAttribute('data-app-file') || submitter.hasAttribute('formtarget') || submitter.hasAttribute('formaction'))) return false;
    for (var i = 0; i < form.attributes.length; i++) { if (/^hx-/.test(form.attributes[i].name)) return false; }
    var action = new URL(form.getAttribute('action') || location.href, location.href);
    if (action.origin !== location.origin || SKIP_PATH.test(action.pathname) || FILE_LIKE.test(action.pathname)) return false;
    var method = (form.getAttribute('method') || 'get').toLowerCase();
    return method === 'get' || method === 'post';
  }

  function have() {
    var f = { src: new Set(), inline: new Set(), css: new Set() };
    document.querySelectorAll('script').forEach(function (s) {
      if (s.src) f.src.add(new URL(s.src, location.href).pathname);
      else f.inline.add(s.textContent.trim());
    });
    document.querySelectorAll('link[rel="stylesheet"]').forEach(function (l) { f.css.add(new URL(l.href, location.href).pathname); });
    document.querySelectorAll('style').forEach(function (s) { f.css.add(s.textContent.trim()); });
    return f;
  }

  // ما تحمله الصفحةُ الواردة ولم تحمله الحاليّة: سكربتاتٌ وأنماط. `again` = شُغِّل من قبلُ فيُشغَّل داخل غلاف.
  function extras(doc) {
    var f = have(), out = { scripts: [], links: [], styles: [] };
    doc.querySelectorAll('script').forEach(function (s) {
      if (s.type === 'speculationrules' || s.type === 'application/json' || s.type === 'application/ld+json') return;
      var key = s.src ? 'src:' + new URL(s.src, location.href).pathname : 'inline:' + s.textContent.trim();
      var loaded = s.src ? f.src.has(key.slice(4)) : f.inline.has(key.slice(7));
      var seenBefore = executed.has(key);
      // مكتبةٌ محمَّلةٌ في الصفحة الأولى (Chart.js…) لا تُعاد؛ وسكربتُ صفحةٍ سبق تشغيلُه يُعاد داخل غلاف.
      if (loaded && !seenBefore) return;
      out.scripts.push({ el: s, key: key, again: seenBefore });
    });
    doc.querySelectorAll('link[rel="stylesheet"]').forEach(function (l) {
      if (!f.css.has(new URL(l.href, location.href).pathname)) out.links.push(l);
    });
    doc.querySelectorAll('style').forEach(function (s) { if (!f.css.has(s.textContent.trim())) out.styles.push(s); });
    return out;
  }

  // أثناء تشغيل سكربتٍ بعد التحميل: `DOMContentLoaded` و`load` وقعا، فيُنفَّذ مستمعُهما فوراً بدل أن يُسجَّل.
  function withShim(work) {
    var d = document.addEventListener, w = window.addEventListener;
    function wrap(orig, target) {
      return function (type, cb, opts) {
        if (type === 'DOMContentLoaded' || (target === window && type === 'load')) {
          setTimeout(function () { try { cb.call(target, new Event(type)); } catch (err) { console.error(err); } }, 0);
          return;
        }
        return orig.call(target, type, cb, opts);
      };
    }
    document.addEventListener = wrap(d, document);
    window.addEventListener = wrap(w, window);
    return work(function restore() { document.addEventListener = d; window.addEventListener = w; });
  }

  function inject(code, restore, resolve) {
    var n = document.createElement('script');
    if (nonce) n.nonce = nonce;
    n.textContent = code;
    try { document.body.appendChild(n); } catch (err) { console.error(err); }
    setTimeout(function () { restore(); resolve(); }, 0);
  }

  function runScript(item) {
    return new Promise(function (resolve) {
      var old = item.el;
      executed.add(item.key);
      withShim(function (restore) {
        if (old.src && !item.again) {
          var n = document.createElement('script');
          Array.prototype.forEach.call(old.attributes, function (a) { if (a.name !== 'nonce' && a.name !== 'defer') n.setAttribute(a.name, a.value); });
          n.async = false;
          n.onload = n.onerror = function () { setTimeout(function () { restore(); resolve(); }, 0); };
          document.body.appendChild(n);
        } else if (old.src) {
          // سكربتٌ خارجيٌّ سبق تشغيلُه: يُجلب نصُّه ويُشغَّل داخل غلافٍ لئلّا تُعاد إعلاناتُه العامّة.
          fetch(old.src, { credentials: 'same-origin' }).then(function (r) { return r.text(); })
            .then(function (code) { inject('(function(){\n' + code + '\n})();', restore, resolve); })
            .catch(function () { restore(); resolve(); });
        } else {
          // دائماً داخل غلاف: صفحتان تعلنان `const OPTS` نفسَه في مستندٍ واحدٍ تصطدمان (وقع بين لوحة التحكّم والعيادة).
          inject('(function(){\n' + old.textContent + '\n})();', restore, resolve);
        }
      });
    });
  }

  function addStyles(list) {
    var waits = [];
    list.links.forEach(function (l) {
      var n = document.createElement('link');
      n.rel = 'stylesheet'; n.href = l.href;
      waits.push(new Promise(function (r) { n.onload = n.onerror = r; setTimeout(r, 2500); }));
      document.head.appendChild(n);
    });
    list.styles.forEach(function (s) {
      var n = document.createElement('style'); if (nonce) n.nonce = nonce;
      n.textContent = s.textContent; document.head.appendChild(n);
    });
    return Promise.all(waits);
  }

  function syncChrome(doc) {
    ['.site-nav a', '.mobile-bottom-nav a'].forEach(function (sel) {
      var now = document.querySelectorAll(sel), next = doc.querySelectorAll(sel);
      if (now.length !== next.length) return;
      now.forEach(function (el, i) {
        var n = next[i];
        if (el.tagName !== n.tagName || el.getAttribute('href') !== n.getAttribute('href')) return;
        el.className = n.className;
        if (n.hasAttribute('aria-current')) el.setAttribute('aria-current', n.getAttribute('aria-current'));
        else el.removeAttribute('aria-current');
      });
    });
  }

  // إغلاقٌ فوريٌّ (بعد أن انقضى التلاشي، أو لمن يُفضّل تقليلَ الحركة).
  function closeMenus() {
    document.querySelectorAll('.is-fading').forEach(function (el) { el.classList.remove('is-fading'); });
    document.querySelectorAll(MENUS).forEach(function (el) { el.classList.remove('open', 'is-open'); });
    document.querySelectorAll('[data-sd][aria-expanded="true"], .adm-nav__btn[aria-expanded="true"]').forEach(function (el) { el.setAttribute('aria-expanded', 'false'); });
    if (window.sdCloseAll) window.sdCloseAll();   // زرُّ القائمة الرئيسيّة `.nb.on` ولوحةُ الجوّال — وحدَه base.js يعرفهما
    if (window.closeMobMenu) window.closeMobMenu();   // ولوحةُ الجوّال نفسُها لا قوائمُها الفرعيّةُ وحدَها
  }

  // النقرُ على رابطٍ: تتلاشى القائمةُ المفتوحةُ من هذه اللحظة بمدّة تلاشي الصفحة، لا بعد التبديل.
  function fadeMenus() {
    // لوحةُ الجوّال تُغلق فوراً عند النقر على وجهةٍ فيها — لا تنتظر التلاشي، وقد لا تكون ثمّة قائمةٌ منسدلةٌ مفتوحةٌ أصلاً.
    if (window.closeMobMenu) window.closeMobMenu();
    var open = document.querySelectorAll(MENUS);
    if (!open.length) return;
    if (reduced) { closeMenus(); return; }
    open.forEach(function (el) { el.classList.add('is-fading'); });
    setTimeout(closeMenus, fadeMs());
  }

  // انتقالٌ لن يُبدَّل فيه المحتوى: إن لم يقع (تنزيلٌ أو إلغاءٌ) عاد المحتوى الشفّافُ ظاهراً بدل أن تبقى الصفحةُ فارغة.
  function restoreLater() {
    var t = setTimeout(function () {
      var root = document.querySelector(ROOT);
      if (root) root.classList.remove('is-leaving');
      closeMenus();
    }, fadeMs() + 4000);
    window.addEventListener('pagehide', function () { clearTimeout(t); }, { once: true });
  }

  function full(url) { restoreLater(); window.location.href = url; }

  // نمطُ `fade` (الإدارة): تلاشٍ بالآلية نفسِها ثمّ تحميلٌ كامل.
  function leave(url) {
    var root = document.querySelector(ROOT);
    if (!root || reduced) { window.location.href = url; return; }
    root.classList.add('is-leaving');
    fadeMenus();
    restoreLater();
    setTimeout(function () { window.location.href = url; }, fadeMs());
  }

  // الرجوعُ من ذاكرة الصفحة (bfcache) يعيدها كما تُركت: `is-leaving` قائمٌ فيبقى المحتوى شفّافاً.
  window.addEventListener('pageshow', function (e) {
    if (!e.persisted) return;
    var root = document.querySelector(ROOT);
    if (root) root.classList.remove('is-leaving');
    closeMenus();
  });

  function download(res, name) {
    return res.blob().then(function (blob) {
      var m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(res.headers.get('content-disposition') || '');
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = m ? decodeURIComponent(m[1]) : (name || 'file');
      document.body.appendChild(a); a.click(); a.remove();
    });
  }

  // `init`: طلبُ fetch للنموذج (POST) أو undefined لرابط. الـPOST لا يُعاد بعد الإرسال، فالرجوعُ عند غير HTML تنزيلٌ لا تحميلٌ ثانٍ.
  function go(url, push, init) {
    var mine = ++token;
    var main = document.getElementById('main-content');
    var post = init && init.method === 'POST';
    if (!main) { if (post) return; full(url); return; }
    if (!reduced) main.classList.add('is-leaving');
    fadeMenus();
    var fade = new Promise(function (r) { setTimeout(r, reduced ? 0 : fadeMs()); });
    var options = { credentials: 'same-origin', headers: { 'X-Page-Nav': '1', Accept: 'text/html' } };
    if (init) { options.method = init.method; options.body = init.body; }
    Promise.all([fetch(url, options), fade]).then(function (pair) {
      var res = pair[0];
      if (mine !== token) return null;
      var type = res.headers.get('content-type') || '';
      if (type.indexOf('text/html') < 0) {
        if (post) { main.classList.remove('is-leaving'); return download(res).then(function () { return null; }); }
        full(url); return null;
      }
      if (!res.ok && !post) { full(url); return null; }
      return res.text().then(function (html) { return { html: html, final: res.url, ok: res.ok }; });
    }).then(function (got) {
      if (!got || mine !== token) return null;
      var doc = new DOMParser().parseFromString(got.html, 'text/html');
      var incoming = doc.getElementById('main-content');
      if (!doc.body || !doc.body.hasAttribute('data-page-nav') || !incoming || !doc.getElementById('crumbs')) {
        if (post) { document.open(); document.write(got.html); document.close(); } else full(got.final || url);
        return null;
      }
      var more = extras(doc);
      return addStyles(more).then(function () {
        if (mine !== token) return;
        var fresh = document.adoptNode(incoming);
        main.replaceWith(fresh);   // ظهورُ الجديد حركةُ `page-in` في CSS تبدأ بإدراجه
        // التبديلُ هنا يدويٌّ لا عبر آلية HTMX الخاصّة بالتبديل، وهذه النسخةُ من htmx.min.js
        // بلا MutationObserver يكتشف عناصر جديدة من نفسه — فـ`hx-get`/`hx-trigger` داخل
        // المحتوى الوارد تبقى خرساء (لا تُستجاب أبداً، ولو بتفاعل المستخدم) حتى يُستدعى
        // `htmx.process` عليها صراحةً، كما توصي وثائقُ htmx لكلّ تبديلٍ يدويٍّ للـDOM.
        if (window.htmx) htmx.process(fresh);
        document.getElementById('crumbs').innerHTML = doc.getElementById('crumbs').innerHTML;
        var msgs = document.getElementById('page-msgs');
        if (msgs && doc.getElementById('page-msgs')) msgs.innerHTML = doc.getElementById('page-msgs').innerHTML;
        document.title = doc.title;
        syncChrome(doc);
        closeMenus();
        if (push) history.pushState({ pageNav: 1 }, '', got.final || url);
        window.scrollTo(0, 0);
        // ما يهيّئه base.js وapp.js للمحتوى المُبدَّل (فرزُ الجداول، التحقّق…) يستمع لهذا الحدث.
        fresh.dispatchEvent(new CustomEvent('htmx:afterSwap', { bubbles: true, detail: { pageNav: true } }));
        return more.scripts.reduce(function (p, item) { return p.then(function () { return runScript(item); }); }, Promise.resolve());
      });
    }).catch(function () { if (!post) full(url); else main.classList.remove('is-leaving'); });
  }

  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href]');
    if (!eligibleLink(a, e) || e.defaultPrevented) return;
    var same = a.pathname === location.pathname && a.search === location.search;
    // المتصفّحُ يمازج الصفحتين بنفسه (`@view-transition` في admin_theme.css): لا نعترض الرابطَ، ونُخفت القائمةَ وحدَها من لحظة النقر.
    if (FADE_ONLY && NATIVE_VT && !same) { fadeMenus(); return; }
    e.preventDefault();
    // رابطٌ إلى الصفحة الحاليّة بعينها (النقرةُ الثانية على مفتاحٍ في القائمة الرئيسيّة أو فرعيّتها): لا شيءَ يُعاد — لا تحميلَ
    // ولا تلاشي ولا طلب. تُغلق القائمةُ المنسدلة فقط (بتلاشيها).
    if (same) { fadeMenus(); return; }
    if (FADE_ONLY) leave(a.href); else go(a.href, true);
  });

  if (FADE_ONLY) return;   // لا نماذجَ ولا سجلَّ في نمط `fade`: الحفظُ بإرسالٍ عاديٍّ والرجوعُ بالمتصفّح

  // بعد معالِج التأكيد (`data-confirm` في actions.js): إن مُنع الإرسالُ فلا نُكمل.
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (e.defaultPrevented || !eligibleForm(form, e.submitter)) return;
    var data = new FormData(form);
    if (e.submitter && e.submitter.name) data.append(e.submitter.name, e.submitter.value);
    var action = new URL(form.getAttribute('action') || location.href, location.href);
    e.preventDefault();
    if ((form.getAttribute('method') || 'get').toLowerCase() === 'get') {
      new URLSearchParams(data).forEach(function (v, k) { if (typeof v === 'string') action.searchParams.append(k, v); });
      go(action.pathname + action.search, true);
    } else {
      go(action.href, true, { method: 'POST', body: data });
    }
  });

  history.replaceState({ pageNav: 1 }, '', location.href);
  window.addEventListener('popstate', function () { go(location.href, false); });
})();
