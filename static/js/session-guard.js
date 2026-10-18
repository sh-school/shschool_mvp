/* session-guard.js — لا يضيع ما أدخله المستخدم بانتهاء جلسته (W-20261005-003، س١، قرار المالك 2026-10-05)
 *
 * ثلاثة أعمال:
 *  ١) نبضٌ: كلَّ 5 دقائق يجدّد خمولَ الجلسة (POST /auth/session/touch/) — فقط إن حدث إدخالٌ فعليّ
 *     (input/click/keydown) خلال آخر 20 دقيقة والصفحةُ ظاهرة، ولا يتجاوز المطلقةَ التي يعلنها الخادم.
 *  ٢) تحذير: قبل دقيقتين من الانتهاء نافذةٌ فيها «ابقَ متصلاً» وعدٌّ تنازليّ وإعلانٌ لقارئ الشاشة (WCAG 2.2.1).
 *  ٣) إنقاذ: إن ردّ الخادمُ 401 (أو كان الانتهاءُ معلوماً قبل الإرسال) تُفتح نافذةُ إعادة دخولٍ في الصفحة نفسها
 *     (إطارٌ لصفحة الدخول ذاتِها — لا كلمةَ مرور تمرّ في هذا السكربت)، ثمّ يُحدَّث رمزُ CSRF ويُعاد الطلبُ
 *     بالبيانات نفسها. يشمل: fetch (ومنه التنقّلُ بتبديل المحتوى page-nav.js)، وHTMX، والنماذجَ العاديّة.
 */
(function () {
  'use strict';

  var cfg = window.APP_CONFIG || {};
  var embedded = window.top !== window.self;
  // داخل نافذة إعادة الدخول (إطار): نخفي الإطار المحيط ولا نحرس شيئاً.
  if (embedded) { document.documentElement.classList.add('is-embedded'); return; }
  if (!cfg.isAuthenticated || !window.fetch || !window.Promise) return;

  var STATUS_URL = '/auth/session/status/';
  var TOUCH_URL = '/auth/session/touch/';
  var LOGIN_URL = '/auth/login/?next=' + encodeURIComponent('/auth/session/done/') + '&embed=1';
  var LOGOUT_URL = '/auth/logout/';
  var WARN_AT = 120;                 // ثانية — التحذيرُ قبل دقيقتين
  var LAST_CALL_AT = 30;             // ثانية — إعلانٌ ثانٍ لقارئ الشاشة
  var PULSE_EVERY = 5 * 60 * 1000;   // نبضةٌ كل 5 دقائق
  var MIN_RETRY = 60 * 1000;         // لا نعيد محاولة نبضةٍ فشلت قبل دقيقة
  var INPUT_WINDOW = 20 * 60 * 1000; // إدخالٌ فعليّ خلال آخر 20 دقيقة
  var FRESH_FOR = 60 * 1000;         // حالةٌ تحقّقنا منها خلال دقيقة لا تُعاد قبل إرسال نموذج
  var USER_GET_WINDOW = 15 * 1000;   // طلب GET بعد إدخالٍ قريبٍ يُعدّ طلبَ مستخدم لا استطلاعاً خلفيّاً

  var nativeFetch = window.fetch.bind(window);
  var S = {
    known: false, idleEnd: 0, idleLimit: 0, absEnd: 0, lastCheck: 0, lastPulse: 0,
    lastInput: 0, userId: null, csrf: null, expired: false,
    warnShown: false, warnSpoken: false, lastCallSpoken: false, checking: false
  };
  var warnEl, reloginEl, frameEl, reloginStatusEl, relogin = null, opener = null;

  /* ── أدواتٌ صغيرة ─────────────────────────────────────────── */
  function nowMs() { return Date.now(); }
  function sameOrigin(url) {
    try { return new URL(url, location.href).origin === location.origin; } catch (e) { return false; }
  }
  function pathOf(url) {
    try { return new URL(url, location.href).pathname; } catch (e) { return ''; }
  }
  // ما لا يُحرس: المصادقةُ نفسها (وإلّا دُرنا على أنفسنا) والأصول والفحوص.
  function guarded(url) {
    return sameOrigin(url) && !/^\/(auth|static|media|health|ready|api)(\/|$)|^\/(sw\.js|manifest\.json|metrics)/.test(pathOf(url));
  }
  function csrf() {
    var el = document.querySelector('input[name=csrfmiddlewaretoken]');
    return (el && el.value) || S.csrf || '';
  }
  function setCsrf(token) {
    if (!token) return;
    S.csrf = token;
    document.querySelectorAll('input[name=csrfmiddlewaretoken]').forEach(function (el) { el.value = token; });
  }
  function say(text) {
    var live = document.getElementById('sr-live');
    if (!live) return;
    live.textContent = text;
    setTimeout(function () { if (live.textContent === text) live.textContent = ''; }, 6000);
  }
  function fmt(seconds) {
    var s = Math.max(0, Math.ceil(seconds));
    return Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2);
  }
  function remaining() {
    var t = nowMs();
    return Math.min((S.idleEnd - t) / 1000, (S.absEnd - t) / 1000);
  }

  /* ── الخادم: حالةٌ وتجديد ─────────────────────────────────── */
  function applyClock(d) {
    var t = nowMs();
    S.expired = false;
    S.lastCheck = t;
    if (d.user_id) S.userId = S.userId || d.user_id;
    if (d.csrf_token) setCsrf(d.csrf_token);
    if (d.idle_remaining == null || d.absolute_remaining == null) { S.known = false; return; }
    S.known = true;
    S.idleLimit = d.idle_limit * 1000;
    S.idleEnd = t + d.idle_remaining * 1000;
    S.absEnd = t + d.absolute_remaining * 1000;
  }

  // 'ok' | 'expired' | 'unknown' (تعذّر الاتصال: لا نحكم بالانتهاء)
  function check() {
    return nativeFetch(STATUS_URL, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (res) {
        if (res.status === 401) { S.expired = true; S.known = false; return { state: 'expired' }; }
        if (!res.ok) return { state: 'unknown' };
        return res.json().then(function (d) { applyClock(d); return { state: 'ok', data: d }; });
      })
      .catch(function () { return { state: 'unknown' }; });
  }

  function touch() {
    return nativeFetch(TOUCH_URL, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'X-CSRFToken': csrf(), Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
    }).then(function (res) {
      if (res.status === 401) { S.expired = true; S.known = false; return null; }
      if (!res.ok) return null;
      return res.json().then(function (d) { applyClock(d); S.lastPulse = nowMs(); return d; });
    }).catch(function () { return null; });
  }

  /* ── النوافذ ───────────────────────────────────────────────── */
  function focusables(root) {
    return Array.prototype.filter.call(
      root.querySelectorAll('button, iframe, a[href], input, [tabindex]:not([tabindex="-1"])'),
      function (el) { return !el.disabled && !el.hidden && el.offsetParent !== null; }
    );
  }
  function trapTab(e, root) {
    if (e.key !== 'Tab') return;
    var items = focusables(root);
    if (!items.length) return;
    var first = items[0], last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); }
    else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); }
  }
  function remember() { if (!opener) opener = document.activeElement; }
  function restoreFocus() {
    var el = opener; opener = null;
    if (el && el.focus && document.contains(el)) el.focus();
  }

  function showWarning() {
    if (S.warnShown || !warnEl) return;
    S.warnShown = true;
    var absoluteFirst = (S.absEnd - nowMs()) <= (S.idleEnd - nowMs());
    warnEl.setAttribute('data-mode', absoluteFirst ? 'absolute' : 'idle');
    warnEl.querySelector('[data-sg-idle]').hidden = absoluteFirst;
    warnEl.querySelector('[data-sg-absolute]').hidden = !absoluteFirst;
    warnEl.querySelector('[data-sg-stay]').hidden = absoluteFirst;
    warnEl.querySelector('[data-sg-relogin]').hidden = !absoluteFirst;
    remember();
    warnEl.hidden = false;
    tickWarning();
    var primary = warnEl.querySelector(absoluteFirst ? '[data-sg-relogin]' : '[data-sg-stay]');
    if (primary) primary.focus();
    if (!S.warnSpoken) {
      S.warnSpoken = true;
      say(absoluteFirst
        ? 'تنتهي جلستُك نهائياً خلال دقيقتين. احفظ عملك ثم سجّل الدخول من جديد.'
        : 'تنتهي جلستُك خلال دقيقتين. اضغط «ابقَ متصلاً» للمتابعة.');
    }
  }
  function hideWarning() {
    if (!S.warnShown) return;
    S.warnShown = false; S.warnSpoken = false; S.lastCallSpoken = false;
    if (warnEl) warnEl.hidden = true;
    restoreFocus();
  }
  function tickWarning() {
    if (!S.warnShown) return;
    var r = remaining();
    warnEl.querySelectorAll('[data-sg-countdown]').forEach(function (el) { el.textContent = fmt(r); });
    if (r <= LAST_CALL_AT && !S.lastCallSpoken) {
      S.lastCallSpoken = true;
      say('تنتهي جلستُك خلال ' + LAST_CALL_AT + ' ثانية.');
    }
  }

  // الطلبُ المعلّق (إن وُجد) يُعاد بعد النجاح؛ `reason` يغيّر الجملة التمهيديّة فقط.
  function setReloginText(hasPending) {
    reloginEl.querySelector('[data-sg-lead-pending]').hidden = !hasPending;
    reloginEl.querySelector('[data-sg-lead-plain]').hidden = hasPending;
  }
  function reloginMessage(text) { if (reloginStatusEl) reloginStatusEl.textContent = text || ''; }

  function openRelogin(opts, done) {
    opts = opts || {};
    relogin = { done: done, originalUser: S.userId, reloaded: false };
    hideWarning();
    remember();
    setReloginText(!!opts.pending);
    reloginMessage('');
    reloginEl.hidden = false;
    var start = function () {
      frameEl.src = LOGIN_URL;
      var cancel = reloginEl.querySelector('[data-sg-cancel]');
      if (cancel) cancel.focus();
      say('انتهت جلستُك. سجّل الدخول في النافذة لإكمال عملك دون فقدان ما أدخلتَه.');
    };
    if (opts.logoutFirst) {
      nativeFetch(LOGOUT_URL, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf() } })
        .catch(function () {}).then(start);
    } else {
      start();
    }
  }
  function closeRelogin(ok) {
    if (!relogin) return;
    var done = relogin.done;
    relogin = null;
    reloginEl.hidden = true;
    frameEl.removeAttribute('src');
    frameEl.src = 'about:blank';
    restoreFocus();
    done(ok);
  }

  // تحقّقٌ بعد كلّ تحميلٍ في الإطار: صفحةُ الدخول، ثمّ الرمز الثاني، ثمّ تغييرُ كلمة المرور… حتى يكتمل الدخول.
  function onFrameLoaded() {
    if (!relogin || !frameEl.getAttribute('src') || frameEl.getAttribute('src') === 'about:blank') return;
    check().then(function (r) {
      if (!relogin || r.state !== 'ok') return;
      var d = r.data;
      if (d.must_change_password) return;               // يُكمل تغييرَها في الإطار نفسه
      if (relogin.originalUser && d.user_id !== relogin.originalUser) {
        // حسابٌ آخر: ما أُدخل في الصفحة لحساب غيره فلا يُرسَل، وتُعاد الصفحة نظيفة.
        reloginMessage('سجّلتَ الدخول بحسابٍ مختلف عن حساب هذه الصفحة، فلن يُرسَل ما أُدخل بحساب غيرك. ستُعاد تحميل الصفحة…');
        if (!relogin.reloaded) { relogin.reloaded = true; setTimeout(function () { location.reload(); }, 2500); }
        return;
      }
      reloginMessage('تمّ تسجيل الدخول — جارٍ إكمال طلبك…');
      S.userId = d.user_id;
      closeRelogin(true);
      say('تمّ تسجيل الدخول. جارٍ إكمال طلبك.');
    });
  }

  // وعدٌ واحدٌ مشتركٌ: طلباتٌ كثيرةٌ تسقط معاً تفتح نافذةً واحدة وتُعاد كلُّها بعد الدخول.
  // قبل فتحها نسأل الخادمَ: قد تكون الجلسةُ حيّةً (جدّدها تبويبٌ آخر) فلا نافذةَ ولا ضجيج.
  var reloginPromise = null;
  function reauthenticate(opts) {
    if (reloginPromise) return reloginPromise;
    opts = opts || {};
    var verdict = opts.logoutFirst ? Promise.resolve({ state: 'expired' }) : check();
    reloginPromise = verdict.then(function (r) {
      if (r.state === 'ok') return true;
      if (r.state === 'unknown') return false;           // لا اتصال: لا نافذةَ تدخل في فراغ
      return new Promise(function (resolve) { openRelogin(opts, resolve); });
    }).then(function (ok) { reloginPromise = null; return ok; });
    return reloginPromise;
  }

  /* ── fetch: يلتقط 401 (أو الإعادة إلى صفحة الدخول) ويعيد الطلبَ بعد الدخول ───── */
  function isExpiredResponse(res) {
    if (res.status === 401) return res.headers.get('HX-Trigger') === 'session-expired';
    if (res.redirected) return pathOf(res.url).indexOf('/auth/login') === 0;
    return false;
  }
  function headersOf(input, init) {
    return new Headers((init && init.headers) || (input instanceof Request ? input.headers : undefined));
  }
  function reusableBody(body) {
    return body == null || typeof body === 'string' || body instanceof FormData ||
      body instanceof URLSearchParams || body instanceof Blob || body instanceof ArrayBuffer;
  }
  function refreshBody(body, token) {
    if ((body instanceof FormData || body instanceof URLSearchParams) && body.has('csrfmiddlewaretoken')) {
      body.set('csrfmiddlewaretoken', token);
    } else if (typeof body === 'string' && body.indexOf('csrfmiddlewaretoken=') >= 0) {
      return body.replace(/(csrfmiddlewaretoken=)[^&]*/, '$1' + encodeURIComponent(token));
    }
    return body;
  }

  window.fetch = function (input, init) {
    var req = input instanceof Request ? input : null;
    var url = req ? req.url : String(input);
    if (!guarded(url)) return nativeFetch(input, init);

    var method = String((init && init.method) || (req && req.method) || 'GET').toUpperCase();
    var headers = headersOf(input, init);
    var isNav = headers.get('X-Page-Nav') === '1';
    var unsafe = method !== 'GET' && method !== 'HEAD';
    var body = init && init.body;
    var spare = req && !req.bodyUsed ? req.clone() : null;
    var canReplay = reusableBody(body) && (req ? !!spare : true);

    // الانتهاءُ معلومٌ قبل الإرسال: لا نرسل شيئاً يضيع.
    var gate = (S.expired && canReplay && (unsafe || isNav)) ?
      reauthenticate({ pending: true }).then(function (ok) { return ok; }) : Promise.resolve(null);

    return gate.then(function (gated) {
      if (gated === false) return cancelled(null);
      if (gated === true) return resend();
      return nativeFetch(input, init).then(function (res) {
        if (!canReplay || !isExpiredResponse(res)) return res;
        S.expired = true;
        var interactive = unsafe || isNav || (nowMs() - S.lastInput) <= USER_GET_WINDOW;
        if (!interactive) return res;           // استطلاعٌ خلفيّ: لا نافذةَ تفاجئ من ليس أمام الشاشة
        return reauthenticate({ pending: true }).then(function (ok) { return ok ? resend() : cancelled(res); });
      });
    });

    // أُلغيت إعادةُ الدخول: يرى المستدعي ردَّ الخادم الأصليّ (أو يُرسَل الطلبُ ليردّ بـ401 إن لم يُرسَل قطّ).
    // والتنقّلُ بالنموذج يعامل ردَّ JSON غيرَ HTML تنزيلاً؛ فالإلغاءُ عنده فشلُ اتصال (يُنهي التلاشي ويُبقي الصفحة).
    function cancelled(res) {
      if (isNav) return Promise.reject(new TypeError('session-cancelled'));
      return res || nativeFetch(input, init);
    }
    function resend() {
      var token = csrf();
      var h = new Headers(headers);
      if (unsafe) h.set('X-CSRFToken', token);
      var next = {};
      Object.keys(init || {}).forEach(function (k) { next[k] = init[k]; });
      next.headers = h;
      if (body != null) next.body = refreshBody(body, token);
      return nativeFetch(spare ? new Request(spare, { headers: h }) : input, next);
    }
  };

  /* ── HTMX: 401 يُلتقط قبل toast الخطأ العامّ ثمّ يُعاد الطلب بعد الدخول ───── */
  window.addEventListener('htmx:responseError', function (e) {
    var xhr = e.detail && e.detail.xhr;
    if (!xhr || xhr.status !== 401 || xhr.getResponseHeader('HX-Trigger') !== 'session-expired') return;
    e.stopPropagation();      // لا toast «حدث خطأ (401)» فوق نافذتنا
    S.expired = true;
    var conf = e.detail.requestConfig || {};
    var verb = String(conf.verb || 'get').toUpperCase();
    var unsafe = verb !== 'GET';
    if (!unsafe && (nowMs() - S.lastInput) > USER_GET_WINDOW) return;   // استطلاعٌ خلفيّ
    reauthenticate({ pending: true }).then(function (ok) {
      if (!ok || !window.htmx || !conf.path || !document.contains(e.detail.elt)) return;
      window.htmx.ajax(verb, conf.path, { source: e.detail.elt, target: conf.target || e.detail.target });
    });
  }, true);

  /* ── النماذج العاديّة (POST بلا fetch): تحقّقٌ سريعٌ قبل الإرسال إن لم نتحقّق حديثاً ───── */
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (e.defaultPrevented || form._sgPass) { form._sgPass = false; return; }
    if (form._confirmed) return;            // تأكيدٌ جارٍ (base.js): لا نُدخل تحقّقاً ثانياً بينه وبين الإرسال
    if ((form.getAttribute('method') || 'get').toLowerCase() !== 'post') return;
    var action = form.getAttribute('action') || location.href;
    if (!guarded(action)) return;
    var fresh = S.known && !S.expired && (nowMs() - S.lastCheck) < FRESH_FOR && remaining() > 10;
    if (fresh) return;

    e.preventDefault();
    e.stopImmediatePropagation();
    var submitter = e.submitter && e.submitter.form === form ? e.submitter : undefined;
    var resubmit = function () {
      form._sgPass = true;
      if (form.requestSubmit) form.requestSubmit(submitter); else form.submit();
      setTimeout(function () { form._sgPass = false; }, 0);
    };
    (S.expired ? Promise.resolve({ state: 'expired' }) : check()).then(function (r) {
      if (r.state !== 'expired') { resubmit(); return; }
      reauthenticate({ pending: true }).then(function (ok) { if (ok) resubmit(); });
    });
  }, true);

  /* ── التنبّه: إدخالٌ فعليّ، ونبضٌ، وعدٌّ تنازليّ ─────────────────── */
  // آخرُ إدخالٍ فعليّ يبقى عبر تحميلات التبويب (sessionStorage): من يتنقّل بين صفحاتٍ كاملةٍ يظلّ نشطاً،
  // ومن فتح صفحةً وتركها لا يُحسب نشطاً لمجرّد أنّها حُمّلت.
  var inputKey = null, inputSaved = 0;
  function loadInput() {
    try { S.lastInput = Number(sessionStorage.getItem(inputKey)) || 0; } catch (e) { /* تخزينٌ محجوب */ }
  }
  function noteInput() {
    var t = nowMs();
    S.lastInput = t;
    if (inputKey && t - inputSaved > 15000) {
      inputSaved = t;
      try { sessionStorage.setItem(inputKey, String(t)); } catch (e) { /* تخزينٌ محجوب */ }
    }
  }
  ['input', 'click', 'keydown'].forEach(function (type) {
    document.addEventListener(type, noteInput, { capture: true, passive: true });
  });

  function tick() {
    var t = nowMs();
    if (S.warnShown) tickWarning();
    if (!S.known || S.expired || relogin) return;
    var r = remaining();
    if (r <= 0) {                                   // انتهى بحسب ساعتنا: الخادمُ يحكم
      hideWarning();
      if (!S.checking) { S.checking = true; check().then(function () { S.checking = false; }); }
      return;
    }
    // نبضٌ: بإدخالٍ حديث، والصفحةُ ظاهرة، وقبل المطلقة، ومضت 5 دقائق على آخر تجديدٍ يعرفه الخادم.
    var sinceTouch = S.idleLimit - (S.idleEnd - t);
    if (document.visibilityState === 'visible' && (t - S.lastInput) <= INPUT_WINDOW &&
        sinceTouch >= PULSE_EVERY && (t - S.lastPulse) >= MIN_RETRY && (S.absEnd - t) > 0) {
      S.lastPulse = t;
      touch();
    }
    if (r <= WARN_AT && !S.warnShown && !S.checking) {
      // قد جدّد تبويبٌ آخر: نتأكّد من الخادم قبل أن نُقلق المستخدم.
      S.checking = true;
      check().then(function (res) {
        S.checking = false;
        if (res.state === 'ok' && remaining() <= WARN_AT && remaining() > 0) showWarning();
      });
    } else if (r > WARN_AT && S.warnShown) {
      hideWarning();
    }
  }

  function stay() {
    var btn = warnEl.querySelector('[data-sg-stay]');
    if (btn) btn.disabled = true;
    touch().then(function () {
      if (btn) btn.disabled = false;
      if (S.expired) { hideWarning(); reauthenticate({ pending: false }); return; }
      if (remaining() > WARN_AT) { hideWarning(); say('تمّ تمديد جلستك.'); }
      else check().then(function () { if (remaining() > WARN_AT) hideWarning(); });
    });
  }

  function init() {
    warnEl = document.getElementById('session-warning');
    reloginEl = document.getElementById('session-relogin');
    if (!warnEl || !reloginEl) return;
    frameEl = reloginEl.querySelector('[data-sg-frame]');
    reloginStatusEl = reloginEl.querySelector('[data-sg-status]');
    S.userId = reloginEl.getAttribute('data-user') || null;   // مستخدمُ الصفحة كما صُنعت، قبل أيّ قراءة
    inputKey = 'sg:input:' + (S.userId || '');
    loadInput();

    warnEl.querySelector('[data-sg-stay]').addEventListener('click', stay);
    warnEl.querySelector('[data-sg-relogin]').addEventListener('click', function () {
      hideWarning();
      reauthenticate({ pending: false, logoutFirst: true });
    });
    warnEl.querySelector('[data-sg-dismiss]').addEventListener('click', hideWarning);
    warnEl.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') hideWarning(); else trapTab(e, warnEl);
    });
    reloginEl.querySelector('[data-sg-cancel]').addEventListener('click', function () { closeRelogin(false); });
    reloginEl.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeRelogin(false); else trapTab(e, reloginEl);
    });
    frameEl.addEventListener('load', onFrameLoaded);

    // عودةُ الصفحة بعد غياب (نومُ الجهاز، تبويبٌ خلفيّ): نعيد قراءة الحالة فوراً.
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'visible') check();
    });
    window.addEventListener('pageshow', function (e) { if (e.persisted) check(); });

    setInterval(tick, 1000);
    // أوّلُ قراءة بعد استقرار التحميل. جلسةٌ سابقةٌ للختم (بلا مقاييس) تُختم بنبضةٍ واحدة.
    setTimeout(function () {
      check().then(function (r) {
        if (r.state === 'ok' && !S.known) touch();
      });
    }, 1500);
  }

  window.sessionGuard = { check: check, reauthenticate: reauthenticate };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
