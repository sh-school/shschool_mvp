/**
 * export-center.js — مركزُ التصدير: كلُّ رابطٍ أو زرٍّ يحمل `data-app-file` يُنفَّذ من هنا (VI-30أ، قرارُ المالك 2026-09-26).
 *
 * كان للتصدير ثلاثُ آليّاتٍ: رابطٌ يُنقَل إليه بلا أيّ إشعار (يتجمّد المتصفّحُ على صفحةٍ بيضاء تسعَ عشرةَ ثانيةً لصفحات المعلّمين PDF)،
 * و`schedule-export.js` للجدول وحدَه (مهمّةٌ خلفيّةٌ بإشعارٍ عائم)، وشقُّ `data-app-file` في `app-mode.js` لقائمة المشاركة على الجوال المثبَّت.
 * فصارت واحدةً: يُطلب الملفُّ في الخلفيّة (`X-Requested-With: XMLHttpRequest`) والصفحةُ في مكانها، ويُميَّز الجوابُ بـ**Content-Type**:
 *
 *   غيرُ JSON            الملفُّ نفسُه (`200` + `Content-Disposition`) ← يُحفَظ، أو يُسلَّم لقائمة المشاركة على جهاز لمسٍ في التطبيق المثبَّت.
 *   202 + JSON           مهمّةٌ خلفيّة: `{status_url, poll_ms?}` ← إشعارُ «جارٍ التحضير» ثمّ استطلاعُ `status_url` (300←600←1200←2000ms) إلى الجاهزيّة.
 *                        ويُقبل الشكلُ القديم (200 + JSON فيه `status_url`، واستطلاعُه بـ`?format=json`) إلى أن يُنقل الجدولُ إلى العقد الجديد.
 *   429 / 403 + JSON     إشعارٌ أحمرُ بنصّ `error.message` وحدَه — عربيّةٌ ثابتةٌ من الخادم، ولا نصَّ استثناءٍ أبداً.
 *   HTML                 صفحةٌ لا ملفّ (انتهت الجلسةُ، لا صلاحيّة، أو رابطٌ يعرض صفحةً): **لا يُنزَّل HTML على أنّه ملفّ** — تُفتح الصفحةُ كما كانت.
 *
 * وإشعارُ «جارٍ التحضير» بمكوّن التوست القائم (`showToast`، role=status) **بعد 600ms فقط** فلا يومض لأغلب الملفّات (Excel بين 60 و200ms)،
 * ويُغلَق عند الجاهزيّة أو الفشل. والفشلُ لا يمرّ صامتاً أبداً: إشعارٌ أحمر، وللاستطلاع سقفٌ أعلى.
 *
 * وبلا إشعارٍ عائم (`showToast` غائب: ورقةٌ مستقلّةٌ بلا base.js) يُترك الرابطُ لسلوكه إلّا في قائمة المشاركة على الجوال المثبَّت.
 * ولا يُلمس ما يحمل مفتاحَ تعديل (Ctrl/Cmd/Shift) أو زرّاً غيرَ الأيسر، ولا رابطاً من أصلٍ آخر، **ولا رابطاً `target=_blank`** (عرضُ PDF في لسانٍ جديد):
 * يبقى للمتصفّح بعارضه الأصليّ — فتحُه من blob بعد الجلب يرثُ سياسةَ CSP للصفحة (`object-src 'none'`) فيُحجب عارضُ PDF، وتنزيلُه بدل عرضه يغيّر
 * ما اعتاده المستخدم. وما كان مهمّةً ثقيلةً منها يحوّله الخادمُ (بلا ترويسة XHR) إلى صفحة المتابعة كما اليوم.
 *
 * وحارسُ الوسم: tests/test_app_mode_no_dead_ends.py (رابطُ ملفٍّ بلا `data-app-file` يُفشل البوّابة) واختبارُ التدفّق الحيّ tests/e2e/test_export_center_live.py.
 */
(function () {
  'use strict';

  var NOTICE_AFTER_MS = 600;
  var POLL_STEPS = [300, 600, 1200];
  var POLL_MS = 2000;
  // أطولُ من مهلة الخادم بكثير: الخادمُ يُفشل العالقَ برسالةٍ فتصل، فهذا سقفٌ أخيرٌ لا مهلةٌ صامتة.
  var GIVE_UP_MS = 300000;
  var GENERIC_FAIL = 'تعذّر تجهيز الملف — حاول مرّةً أخرى.';
  var STANDALONE = '(display-mode: standalone), (display-mode: fullscreen)';

  /* ── الجهاز والإشعار ─────────────────────────────────────────── */

  function matches(query) {
    return !!(window.matchMedia && window.matchMedia(query).matches);
  }

  // يُسأل عند كلّ ضغطة لا مرّةً عند التحميل — فيُختبر من الطرفيّة بتبديل matchMedia.
  function inApp() {
    return matches(STANDALONE) || window.navigator.standalone === true;
  }

  // جهازُ لمس — لا «pointer: coarse» وحدَه: آيباد بلوحة مفاتيحٍ ولوحةِ لمسٍ يُعلن مؤشّراً دقيقاً، وهو الذي يعرض الملفَّ مكانَ التطبيق.
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

  // الإشعارُ من الصفحة أو من إطارها الأمّ (ورقةٌ في إطارٍ تُصدِّر بإشعار المنصّة).
  function toaster(name) {
    if (typeof window[name] === 'function') return window[name];
    try {
      if (window.parent && window.parent !== window && typeof window.parent[name] === 'function') {
        return window.parent[name];
      }
    } catch (e) { /* إطارٌ من أصلٍ آخر */ }
    return null;
  }

  function toast(msg, type, duration) {
    var fn = toaster('showToast');
    if (fn) return fn(msg, type, duration);
    if (type === 'danger') window.alert(msg); // الرسالةُ لا تُبتلع
    return null;
  }

  function dismiss(el) {
    var fn = toaster('dismissToast');
    if (el && fn) fn(el);
  }

  /* ── الطلب ────────────────────────────────────────────────────── */

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

  // رابطٌ: GET بعنوانه. زرُّ نموذجٍ: ما كان سيرسله النموذجُ (GET بوسطاءَ في العنوان، أو POST بجسم) — بزرّه وقيمته.
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

  function request(req) {
    var init = Object.assign({ credentials: 'same-origin' }, req.init);
    init.headers = { 'X-Requested-With': 'XMLHttpRequest' }; // ما يُميّز XHR عند الخادم؛ `fetch` لا تضيفه وحدَها
    return fetch(req.url, init);
  }

  /* ── التسليم ─────────────────────────────────────────────────── */

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

  // عنصر → {file}: ملفٌّ جُلب في التطبيق المثبَّت ولم تُفتح له قائمةُ المشاركة بعد (سفاري يشترط الضغطةَ نفسَها).
  var READY = new WeakMap();

  function share(job, file, fresh) {
    return navigator.share({ files: [file] }).then(
      function () { READY.delete(job.el); },
      function (err) {
        var name = err && err.name;
        if (name === 'AbortError') {
          READY.delete(job.el); // أغلق المستخدمُ القائمة — لا خطأ.
        } else if (name === 'NotAllowedError' && !fresh) {
          // الملفُّ تأخّر بعد الضغطة فانتهى تفعيلُها: ضغطةٌ ثانيةٌ تفتح القائمة.
          READY.set(job.el, { file: file, url: job.req.url });
          toast('الملفّ جاهز — اضغط الزرّ مرّةً أخرى للحفظ أو الطباعة.', 'info');
        } else {
          READY.delete(job.el); // رفضٌ لا لتفعيلٍ منتهٍ بل للملفّ نفسِه — فيُنزَّل.
          save(file);
        }
      }
    );
  }

  function deliver(job, file) {
    var sharing = inApp() && touchDevice() && canShareFiles();
    var shareable = false;
    if (sharing) {
      try { shareable = navigator.canShare({ files: [file] }); } catch (e) { shareable = false; }
    }
    if (shareable) return share(job, file, !job.slow);
    // ما لا تقبله قائمةُ المشاركة (أندرويد لا يشارك xlsx) يُنزَّل — والصفحةُ في مكانها.
    save(file);
    if (job.slow) toast('الملفّ جاهز — بدأ التنزيل.', 'success'); // ما لم يطل التحضيرُ فالتنزيلُ صامتٌ كما كان
    return null;
  }

  /* ── دورةُ الطلب ─────────────────────────────────────────────── */

  function finish(job) {
    window.clearTimeout(job.timer);
    dismiss(job.notice);
    job.notice = null;
    job.el.removeAttribute('aria-busy');
  }

  function fail(job, message) {
    finish(job);
    toast(message || GENERIC_FAIL, 'danger');
  }

  // انتهت الجلسةُ أو لا صلاحية: صفحةُ الدخول أو المنع تُعرض في إطار المنصّة كما كانت تُعرض بالانتقال — لا «حاول مرّةً أخرى» لا تنتهي.
  function leave(job, url) {
    finish(job);
    if (job.req.method === 'GET') window.location.assign(url);
    else toast('انتهت الجلسة أو لا صلاحية — أعد المحاولة بعد الدخول.', 'danger');
  }

  function fetchFile(job, url) {
    return fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } }).then(function (response) {
      if (!response.ok) throw new Error('download');
      var type = (response.headers.get('Content-Type') || '').toLowerCase();
      if (type.indexOf('text/html') === 0 || (type.indexOf('application/json') === 0 && !/attachment/i.test(response.headers.get('Content-Disposition') || ''))) {
        throw new Error('not-a-file'); // لا يُنزَّل HTML ولا JSON على أنّه ملف
      }
      return response.blob().then(function (blob) {
        return new File([blob], filenameFrom(response, url), {
          type: blob.type || type || 'application/octet-stream',
        });
      });
    });
  }

  function errorMessage(data) {
    var error = data && data.error;
    if (typeof error === 'string') return error; // الشكلُ القديم: {status:'failed', error:'…'}
    return (error && error.message) || '';
  }

  function follow(job, first) {
    var statusUrl = first.status_url;
    var started = Date.now();
    var step = 0;

    function again() {
      var wait = step < POLL_STEPS.length ? POLL_STEPS[step] : (first.poll_ms || POLL_MS);
      step += 1;
      window.setTimeout(tick, wait);
    }

    function tick() {
      // `format=json`: الشكلُ القديم يردّ الصفحةَ بلا الوسيط؛ والجديدُ يردّ JSON دائماً ويتجاهله.
      var joiner = statusUrl.indexOf('?') === -1 ? '?' : '&';
      fetch(statusUrl + joiner + 'format=json', { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function (response) {
          if (!response.ok) throw new Error('status');
          return response.json();
        })
        .then(function (data) {
          if (data.status === 'done') {
            return fetchFile(job, data.download_url || statusUrl).then(function (file) {
              job.slow = true; // مهمّةٌ خلفيّةٌ: التحضيرُ طالَ بتعريفه فيستحقّ «الملفّ جاهز»
              deliver(job, file);
              finish(job);
            });
          }
          if (data.status === 'failed') {
            fail(job, errorMessage(data));
            return null;
          }
          if (Date.now() - started > GIVE_UP_MS) {
            fail(job, 'تأخّر تحضير الملفّ — أعِد المحاولة بعد قليل.');
            return null;
          }
          again();
          return null;
        })
        .catch(function () { fail(job, GENERIC_FAIL); });
    }

    tick();
  }

  function handleJson(job, response, data) {
    if (data && data.status_url) {
      follow(job, data); // مهمّةٌ: 202 (العقدُ الجديد) أو 200 (الشكلُ القديم للجدول)
      return null;
    }
    fail(job, response.ok ? GENERIC_FAIL : errorMessage(data));
    return null;
  }

  function handle(job, response) {
    var type = (response.headers.get('Content-Type') || '').toLowerCase();
    var json = type.indexOf('application/json') === 0;
    var html = type.indexOf('text/html') === 0;
    var attachment = /attachment/i.test(response.headers.get('Content-Disposition') || '');

    if ((response.redirected && html) || response.status === 401 || (response.status === 403 && !json)) {
      leave(job, response.redirected ? response.url : job.req.url);
      return null;
    }
    if (json && !attachment) {
      return response.json().then(function (data) { return handleJson(job, response, data); },
        function () { fail(job, GENERIC_FAIL); });
    }
    if (!response.ok) {
      // render_pdf يشرح سببَ الفشل نصّاً (503) — يُقرأ ولا يُطمس.
      return response.text().then(function (text) {
        fail(job, type.indexOf('text/plain') === 0 && text ? text.slice(0, 300) : GENERIC_FAIL);
        return null;
      });
    }
    if (html) {
      // صفحةٌ لا ملفّ: تُفتح كما كانت — ولا يُنزَّل HTML على أنّه ملفّ.
      finish(job);
      if (job.req.method === 'GET') window.location.assign(job.req.url);
      return null;
    }
    return response.blob().then(function (blob) {
      var file = new File([blob], filenameFrom(response, job.req.url), {
        type: blob.type || type || 'application/octet-stream',
      });
      deliver(job, file);
      finish(job);
      return null;
    });
  }

  function run(el) {
    var req = requestFor(el);
    var ready = READY.get(el);
    if (ready && ready.url === req.url) {
      share({ el: el, req: req }, ready.file, true);
      return;
    }
    READY.delete(el);
    if (el.getAttribute('aria-busy') === 'true') return;
    el.setAttribute('aria-busy', 'true');
    var job = { el: el, req: req, notice: null, slow: false, timer: null };
    job.timer = window.setTimeout(function () {
      job.slow = true;
      job.notice = toast('جارٍ تحضير الملفّ… سيُسلَّم إليك عند الجاهزية.', 'info', 0); // 0 = يبقى حتى `dismiss`
    }, NOTICE_AFTER_MS);
    request(req)
      .then(function (response) { return handle(job, response); })
      .catch(function () { fail(job, GENERIC_FAIL); });
  }

  // طورُ الالتقاط: قبل أيّ معالجٍ آخر (page-nav.js يستثني `data-app-file` أصلاً).
  document.addEventListener('click', function (event) {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey) return;
    var el = event.target.closest && event.target.closest('a[data-app-file][href], button[data-app-file]');
    if (!el) return;
    if (el.tagName === 'A' && !sameOrigin(el.href)) return; // من أصلٍ آخر: يبقى لسلوكه
    var sharing = inApp() && touchDevice() && canShareFiles();
    if (!sharing && !toaster('showToast')) return; // بلا إشعارٍ عائمٍ ولا قائمةِ مشاركةٍ يُترك الرابطُ لسلوكه
    if (!sharing && el.tagName === 'A' && el.target === '_blank') return; // عرضُ PDF في لسانٍ جديد: للمتصفّح (انظر الترويسة)
    if (el.tagName === 'BUTTON' && !(el.form && el.form.reportValidity())) return; // نموذجٌ ناقص: يعرض المتصفّحُ ما ينقصه
    event.preventDefault();
    run(el);
  }, true);

  // تصديرٌ طلبته الورقةُ المستقلّة (`?export=pdf|excel`) — السكربتُ `defer` فالصفحةُ مرسومة.
  var params = new URLSearchParams(window.location.search);
  var kind = params.get('export');
  if (kind) {
    params.delete('export');
    var rest = params.toString();
    window.history.replaceState(null, '', window.location.pathname + (rest ? '?' + rest : ''));
    var requested = document.querySelector('a[data-export-job="' + (kind === 'excel' ? 'excel' : 'pdf') + '"]');
    if (requested && toaster('showToast')) run(requested);
  }
})();
