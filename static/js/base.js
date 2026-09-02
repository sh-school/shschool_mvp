/**
 * base.js — SchoolOS v6
 * الوظائف الأساسية للمنصة: Dropdown · Notifications · PWA · Modal · Toast · Smart Search
 * يُحمَّل عبر <script src> — لا يحتاج nonce (CSP 'self' يسمح بالملفات الخارجية)
 */
'use strict';

/* ══════════════════════════════════════════════════════════════
   البحث الذكي العربي — Smart Arabic Search
   ══════════════════════════════════════════════════════════════
   window.smartNorm(text)   — تطبيع النص (تشكيل + همزات + حالة)
   window.smartMatch(q,text) — هل النص يطابق الاستعلام؟ (كل كلمة AND)
   window.smartFilter(inputId, selector, opts) — ربط بحث فوري بعناصر
   ────────────────────────────────────────────────────────────── */
(function(){
  /* حذف التشكيل العربي (الفتحة، الضمة، الكسرة، السكون، الشدة، التنوين) */
  var TASHKEEL = /[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06E4\u06E7\u06E8\u06EA-\u06ED]/g;

  /* توحيد الهمزات: أ إ آ ؤ ئ ء → ا */
  var HAMZA_MAP = {'\u0623':'ا','\u0625':'ا','\u0622':'ا','\u0624':'و','\u0626':'ي','\u0621':'ا'};
  var HAMZA_RE = /[\u0621-\u0626]/g;

  /* تاء مربوطة → هاء */
  var TAA_RE = /\u0629/g;

  function norm(t) {
    if (!t) return '';
    return t
      .replace(TASHKEEL, '')
      .replace(HAMZA_RE, function(c){ return HAMZA_MAP[c] || c; })
      .replace(TAA_RE, 'ه')
      .toLowerCase()
      .trim();
  }

  /**
   * هل كل كلمات الاستعلام موجودة في النص؟
   * smartMatch("سابع احمد", "الصف السابع أحمد محمد") → true
   */
  function match(query, text) {
    if (!query) return true;
    var nq = norm(query);
    var nt = norm(text);
    var words = nq.split(/\s+/);
    for (var i = 0; i < words.length; i++) {
      if (words[i] && nt.indexOf(words[i]) === -1) return false;
    }
    return true;
  }

  /**
   * ربط بحث فوري بحقل input وعناصر DOM
   * smartFilter('search-id', '[data-filter-row]', {
   *   textAttr: 'data-text',  // اختياري — يأخذ textContent لو غير موجود
   *   countEl: '#count',      // اختياري — عداد النتائج
   *   noResults: '#no-msg',   // اختياري — رسالة لا نتائج
   *   parent: '#container'    // اختياري — حاوية البحث
   * })
   */
  function filter(inputId, selector, opts) {
    var input = document.getElementById(inputId);
    if (!input) return;
    opts = opts || {};
    var countEl = opts.countEl ? document.querySelector(opts.countEl) : null;
    var noEl = opts.noResults ? document.querySelector(opts.noResults) : null;

    /* الصفوفُ تُقرأ عند كلّ تصفيةٍ لا مرّةً واحدة: جدولٌ يُبدّله HTMX يأتي
       بصفوفٍ جديدةٍ كلَّ مرّة، والقائمةُ المحفوظةُ سلفاً تُصفّي عقداً هجرها
       المستندُ فيبدو البحثُ معطَّلاً بعد أوّل فرزٍ أو تنقّل. */
    function apply() {
      var parent = opts.parent ? document.querySelector(opts.parent) : document;
      if (!parent) return;
      var q = input.value;
      var shown = 0;
      parent.querySelectorAll(selector).forEach(function(r){
        var text = opts.textAttr ? r.getAttribute(opts.textAttr) : r.textContent;
        var ok = match(q, text || '');
        r.style.display = ok ? '' : 'none';
        if (ok) shown++;
      });
      if (countEl) countEl.textContent = shown;
      if (noEl) noEl.style.display = (shown === 0 && q) ? '' : 'none';
    }

    input.addEventListener('input', apply);
    /* وبعد كلّ تبديلٍ من HTMX تُعاد التصفيةُ على الصفوف الواردة، فلا يرى
       القارئُ صفوفاً استبعدها بحثُه ما زال مكتوباً في الحقل. */
    document.addEventListener('htmx:afterSwap', function(){ if (input.value) apply(); });
  }

  /* تصدير عام */
  window.smartNorm = norm;
  window.smartMatch = match;
  window.smartFilter = filter;
})();

/* ── Dropdown positioning ────────────────────────────────── */
function sdPos(m, btn) {
  m.classList.add('sd-measure');
  var mw = m.offsetWidth, mh = m.offsetHeight;
  m.classList.remove('sd-measure');
  var r = btn.getBoundingClientRect();
  var top = r.bottom + 4;
  if (top + mh > window.innerHeight - 8) top = r.top - mh - 4;
  if (top < 8) top = 8;
  var left = r.right - mw;
  if (left < 8) left = 8;
  if (left + mw > window.innerWidth - 8) left = window.innerWidth - mw - 8;
  m.style.top  = top + 'px';
  m.style.left = left + 'px';
}

window.sd = function(id, btn) {
  var m = document.getElementById(id);
  if (!m) return;
  var isOpen = m.classList.contains('open');
  document.querySelectorAll('.sd-menu.open').forEach(function(x) { x.classList.remove('open'); });
  document.querySelectorAll('.nb.on').forEach(function(x) { x.classList.remove('on'); x.setAttribute('aria-expanded', 'false'); });
  if (!isOpen) { sdPos(m, btn); m.classList.add('open'); btn.classList.add('on'); btn.setAttribute('aria-expanded', 'true'); }
};

/* ── Event delegation: all interactive buttons ── */
document.addEventListener('click', function(e) {
  var sdBtn = e.target.closest('[data-sd]');
  if (sdBtn) { sd(sdBtn.getAttribute('data-sd'), sdBtn); return; }
  var mobBtn = e.target.closest('#mob-menu-btn');
  if (mobBtn) { toggleMobMenu(); return; }
  var printBtn = e.target.closest('.js-print-btn');
  if (printBtn) { window.print(); return; }
  var dismissBtn = e.target.closest('[data-dismiss="msg-bar"]');
  if (dismissBtn) { var bar = dismissBtn.closest('.msg-bar'); if (bar) bar.remove(); return; }
  var backdropEl = e.target.closest('[data-dismiss-on-backdrop]');
  if (backdropEl && e.target === backdropEl && typeof closePalette === 'function') { closePalette(); return; }
  var pwaInstall = e.target.closest('[data-action="install-pwa"]');
  if (pwaInstall && typeof installPWA === 'function') { installPWA(); return; }
  var pwaDismiss = e.target.closest('[data-action="dismiss-pwa"]');
  if (pwaDismiss && typeof dismissBanner === 'function') { dismissBanner(); return; }
  if (!e.target.closest('.sd-menu') && !e.target.closest('[data-sd]')) {
    document.querySelectorAll('.sd-menu.open').forEach(function(x) { x.classList.remove('open'); });
    document.querySelectorAll('.nb.on').forEach(function(x) { x.classList.remove('on'); x.setAttribute('aria-expanded', 'false'); });
  }
});

window.addEventListener('resize', function() {
  document.querySelectorAll('.sd-menu.open').forEach(function(m) {
    var btn = document.getElementById('btn-' + m.id.replace('m-', ''));
    if (btn) sdPos(m, btn);
  });
});


/* ── Notification bell ────────────────────────────────────── */
(function() {
  var badge = document.getElementById('notif-badge');
  if (!badge) return;

  function setBadge(count) {
    count = parseInt(count, 10) || 0;
    badge.textContent = count > 99 ? '99+' : count;
    badge.style.display = count > 0 ? 'flex' : 'none';
  }

  function startPolling() {
    function poll() {
      fetch('/notifications/api/unread-count/', {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      })
      .then(function(r) { return r.ok ? r.json() : null; })
      .then(function(d) { if (d) setBadge(d.count); })
      .catch(function() {});
    }
    poll();
    return setInterval(poll, 30000);
  }

  var wsProto = location.protocol === 'https:' ? 'wss' : 'ws';
  var ws;
  var pollTimer = null;

  function showEmergencyBanner(msg) {
    var banner = document.getElementById('emergency-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'emergency-banner';
      banner.className = 'emergency-banner';
      document.body.prepend(banner);
    }
    banner.textContent = '🚨 ' + msg;
    banner.style.display = 'block';
  }

  function connectWS() {
    try {
      ws = new WebSocket(wsProto + '://' + location.host + '/ws/notifications/');
    } catch(e) {
      pollTimer = startPolling();
      return;
    }

    ws.onmessage = function(e) {
      var d;
      try { d = JSON.parse(e.data); } catch(_) { return; }
      if (d.type === 'unread_count' || d.type === 'new_notification') {
        setBadge(d.count);
      }
      if (d.type === 'new_notification' && typeof window.showToast === 'function') {
        var toastType = (d.priority === 'urgent' || d.priority === 'high') ? 'danger' : 'info';
        window.showToast(d.title, toastType);
      }
      if (d.type === 'emergency') {
        showEmergencyBanner(d.message);
      }
    };
    ws.onclose = function() { if (!pollTimer) { pollTimer = startPolling(); } };
    ws.onerror = function() { if (!pollTimer) { pollTimer = startPolling(); } };
  }

  // فقط إذا كان المستخدم مسجّلاً — يُضبط من القالب عبر APP_CONFIG
  if (window.APP_CONFIG && window.APP_CONFIG.isAuthenticated) {
    connectWS();
  }
})();


/* ── Hamburger mobile menu ────────────────────────────────── */
window.toggleMobMenu = function() {
  var bar = document.querySelector('.nb-bar');
  var btn = document.getElementById('mob-menu-btn');
  if (!bar || !btn) return;
  var isOpen = bar.classList.toggle('open');
  btn.setAttribute('aria-expanded', String(isOpen));
  btn.textContent = isOpen ? '✕' : '☰';
};

document.addEventListener('click', function(e) {
  if (!e.target.closest('.nb-bar') && !e.target.closest('#mob-menu-btn')) {
    var bar = document.querySelector('.nb-bar');
    var btn = document.getElementById('mob-menu-btn');
    if (bar) bar.classList.remove('open');
    if (btn) { btn.textContent = '☰'; btn.setAttribute('aria-expanded', 'false'); }
  }
});


/* ── PWA Install Banner ───────────────────────────────────── */
var _pwaPrompt = null;
window.addEventListener('beforeinstallprompt', function(e) {
  e.preventDefault();
  _pwaPrompt = e;
  if (!localStorage.getItem('pwaDismissed')) {
    setTimeout(function() {
      var b = document.getElementById('pwa-banner');
      if (b) b.classList.add('visible');
    }, 5000);
  }
});

window.installPWA = function() {
  if (_pwaPrompt) { _pwaPrompt.prompt(); _pwaPrompt = null; }
  var b = document.getElementById('pwa-banner');
  if (b) b.classList.remove('visible');
};

window.dismissBanner = function() {
  var b = document.getElementById('pwa-banner');
  if (b) b.classList.remove('visible');
  localStorage.setItem('pwaDismissed', '1');
};


/* ── Service Worker ───────────────────────────────────────── */
if ('serviceWorker' in navigator && !location.pathname.startsWith('/parents/')) {
  window.addEventListener('load', function() {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function() {});
  });
}


/* ── WCAG 2.2: menu role propagation ──────────────────────── */
document.querySelectorAll('[role="menu"] a').forEach(function(a) { a.setAttribute('role', 'menuitem'); });
document.querySelectorAll('[role="menu"] .sd-label').forEach(function(l) { l.setAttribute('role', 'none'); });

/* ── Auto-dismiss flash messages after 7s ─────────────────── */
setTimeout(function() {
  document.querySelectorAll('.msg-bar').forEach(function(el) {
    el.style.opacity = '0';
    setTimeout(function() { if (el.parentNode) el.parentNode.removeChild(el); }, 420);
  });
}, 7000);


/* ── Toast System (canonical — app.js لا يعيد تعريفه) ─────── */
window.showToast = function(msg, type, duration) {
  type = type || 'success';
  duration = duration || 4000;
  var icons = { success: '\u2713', danger: '\u2717', info: '\u2139', warning: '\u26A0' };
  var container = document.getElementById('toast-container');
  if (!container) return;
  var toast = document.createElement('div');
  toast.className = 'toast toast-' + type;
  toast.setAttribute('role', 'alert');

  var icon = document.createElement('span');
  icon.className = 'toast-icon';
  icon.setAttribute('aria-hidden', 'true');
  icon.textContent = icons[type] || '\u2022';

  var text = document.createElement('span');
  text.className = 'toast-msg';
  text.textContent = msg;

  var btn = document.createElement('button');
  btn.className = 'toast-close';
  btn.setAttribute('aria-label', '\u0625\u063a\u0644\u0627\u0642');
  btn.textContent = '\u00d7';
  btn.onclick = function() { _removeToast(toast); };

  toast.appendChild(icon);
  toast.appendChild(text);
  toast.appendChild(btn);
  container.appendChild(toast);
  setTimeout(function() { _removeToast(toast); }, duration);
};

function _removeToast(el) {
  el.classList.add('toast-leaving');
  setTimeout(function() { if (el.parentNode) el.parentNode.removeChild(el); }, 260);
}

window.removeToast = function(btn) {
  var toast = btn.closest ? btn.closest('.toast') : btn.parentElement;
  if (toast) _removeToast(toast);
};

/* ── HTMX → showToast via HX-Trigger header ──────────────── */
document.body.addEventListener('showToast', function(e) {
  if (e.detail) window.showToast(e.detail.msg, e.detail.type);
});

/* ── HTMX CSRF Token — يُرسَل تلقائياً مع كل طلب ──────────
   [P2-A] المصدر الوحيد هو الحقل المخفي في DOM. كان هنا رجوع إلى
   document.cookie، وهو ما يمنع CSRF_COOKIE_HTTPONLY=True.
   base/base.html يضع {% csrf_token %} داخل نموذج الخروج تحت
   {% if user.is_authenticated %} بلا شرط دور، فالحقل حاضر على كل صفحة
   مُعتمَدة — والجزئيات المحقونة بـHTMX تقرأه من المستند الحاضن. */
document.addEventListener('htmx:configRequest', function(e) {
  var csrf = document.querySelector('[name=csrfmiddlewaretoken]');
  if (csrf) e.detail.headers['X-CSRFToken'] = csrf.value;
});

/* ── HTMX Global Loading Bar ─────────────────────────────── */
(function() {
  var bar = document.getElementById('htmx-loading-bar');
  if (!bar) return;
  document.addEventListener('htmx:beforeRequest', function() { bar.classList.add('active'); });
  document.addEventListener('htmx:afterRequest',  function() { bar.classList.remove('active'); });
})();

/* ── HTMX Global Error Handling ──────────────────────────── */
document.addEventListener('htmx:responseError', function(e) {
  var status = e.detail.xhr ? e.detail.xhr.status : 0;
  var msgs = {
    400: '\u0628\u064a\u0627\u0646\u0627\u062a \u063a\u064a\u0631 \u0635\u062d\u064a\u062d\u0629',
    403: '\u063a\u064a\u0631 \u0645\u0635\u0631\u062d \u0644\u0643 \u0628\u0647\u0630\u0627 \u0627\u0644\u0625\u062c\u0631\u0627\u0621',
    404: '\u0627\u0644\u0645\u0648\u0631\u062f \u063a\u064a\u0631 \u0645\u0648\u062c\u0648\u062f',
    429: '\u0637\u0644\u0628\u0627\u062a \u0643\u062b\u064a\u0631\u0629 \u2014 \u0627\u0646\u062a\u0638\u0631 \u0644\u062d\u0638\u0629',
    500: '\u062e\u0637\u0623 \u0641\u064a \u0627\u0644\u062e\u0627\u062f\u0645 \u2014 \u062a\u0648\u0627\u0635\u0644 \u0645\u0639 \u0627\u0644\u062f\u0639\u0645',
    503: '\u0627\u0644\u062e\u062f\u0645\u0629 \u063a\u064a\u0631 \u0645\u062a\u0627\u062d\u0629 \u0645\u0624\u0642\u062a\u0627\u064b'
  };
  if (window.showToast) window.showToast(msgs[status] || '\u062d\u062f\u062b \u062e\u0637\u0623 (' + status + ')', 'danger');
});

document.addEventListener('htmx:timeout', function() {
  if (window.showToast) window.showToast('\u0627\u0646\u062a\u0647\u062a \u0645\u0647\u0644\u0629 \u0627\u0644\u0627\u062a\u0635\u0627\u0644. \u062a\u062d\u0642\u0642 \u0645\u0646 \u0627\u0644\u0634\u0628\u0643\u0629.', 'warning');
});

document.addEventListener('htmx:sendError', function() {
  if (window.showToast) window.showToast('\u062a\u0639\u0630\u0651\u0631 \u0627\u0644\u0627\u062a\u0635\u0627\u0644 \u0628\u0627\u0644\u062e\u0627\u062f\u0645', 'danger');
});

/* ── HTMX Screen Reader Announcements ────────────────────── */
document.addEventListener('htmx:afterSwap', function() {
  var sr = document.getElementById('sr-live');
  if (sr) {
    sr.textContent = '\u062a\u0645 \u062a\u062d\u062f\u064a\u062b \u0627\u0644\u0645\u062d\u062a\u0648\u0649';
    setTimeout(function() { sr.textContent = ''; }, 1500);
  }
});


/* ── Modal Manager (with Focus Trap — WCAG 2.4.3) ────────── */
window.modalManager = {
  _stack: [],
  _trapHandler: null,

  open: function(id) {
    var overlay = document.getElementById('modal-' + id);
    if (!overlay) return;
    this._stack.push({ id: id, trigger: document.activeElement });
    overlay.style.display = 'flex';
    overlay.removeAttribute('hidden');
    document.body.style.overflow = 'hidden';

    // Focus first focusable element
    var focusable = overlay.querySelectorAll(
      'button, [href], input:not([type="hidden"]), select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (focusable.length) setTimeout(function() { focusable[0].focus(); }, 50);

    // Focus Trap — Tab stays inside modal
    var self = this;
    this._trapHandler = function(e) {
      if (e.key !== 'Tab' || !self._stack.length) return;
      var current = self._stack[self._stack.length - 1];
      var el = document.getElementById('modal-' + current.id);
      if (!el) return;
      var nodes = el.querySelectorAll(
        'button:not([disabled]), [href], input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (!nodes.length) return;
      var first = nodes[0], last = nodes[nodes.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus();
      }
    };
    document.addEventListener('keydown', this._trapHandler);
  },

  close: function(id) {
    var overlay = document.getElementById('modal-' + id);
    if (!overlay) return;
    overlay.style.display = 'none';
    overlay.setAttribute('hidden', '');
    if (this._trapHandler) {
      document.removeEventListener('keydown', this._trapHandler);
      this._trapHandler = null;
    }
    var prev = this._stack.pop();
    if (!this._stack.length) document.body.style.overflow = '';
    if (prev && prev.trigger) prev.trigger.focus();
  },

  closeTop: function() {
    if (this._stack.length) this.close(this._stack[this._stack.length - 1].id);
  }
};

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') window.modalManager.closeTop();
});


/* ── Custom Confirm Dialog (replaces browser confirm()) ────
   المالكُ الوحيد لـ`data-confirm` في المنصّة. وكان في `actions.js` مستمعٌ
   ثانٍ بـ`window.confirm` يسبقه في طور الالتقاط، فيُسأل المستخدمُ مرّتين،
   ويُرسَل ما ألغاه: أُزيل هناك وبقي هنا.

   والسمةُ تُقرأ من النموذج ومن الزرّ المُرسِل كليهما — كما كانت تُقرأ في
   `actions.js` — كي لا يسقط سلوكٌ موثَّقٌ بإزالة المستمع. */
(function() {
  var open = false;   // نافذةٌ واحدةٌ في المرّة: إرسالان متسابقان لا يفتحان اثنتين

  document.addEventListener('submit', function(e) {
    var form = e.target;
    if (form._confirmed) { form._confirmed = false; return; } // already confirmed

    var holder = form.hasAttribute('data-confirm') ? form : null;
    if (!holder && e.submitter && e.submitter.closest) {
      holder = e.submitter.closest('[data-confirm]');
    }
    if (!holder) return; // no data-confirm → normal submit
    var msg = holder.getAttribute('data-confirm');
    if (!msg) return;

    e.preventDefault();
    if (open) return;
    open = true;

    var submitter = e.submitter || null;
    var opener = document.activeElement;

    // Build confirm overlay
    var overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.setAttribute('role', 'alertdialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-labelledby', 'confirm-dlg-title');
    overlay.style.display = 'flex';
    overlay.innerHTML =
      '<div class="modal-box modal-sm" role="document">' +
      '  <div class="modal-header"><span id="confirm-dlg-title" style="color:#dc2626">' +
      '    <svg class="icon" aria-hidden="true" focusable="false"><use href="#icon-alert-triangle"/></svg> ' +
      '    \u062a\u0623\u0643\u064a\u062f \u0627\u0644\u0625\u062c\u0631\u0627\u0621</span>' +
      '    <button type="button" class="modal-close-btn" data-action="cancel" aria-label="\u0625\u063a\u0644\u0627\u0642">\u00d7</button>' +
      '  </div>' +
      '  <div class="modal-body"><p data-confirm-message style="color:var(--text-secondary);line-height:1.7"></p></div>' +
      '  <div class="modal-footer">' +
      '    <button type="button" class="btn-secondary" data-action="cancel">\u0625\u0644\u063a\u0627\u0621</button>' +
      '    <button type="button" class="btn-danger" data-action="confirm">\u062a\u0623\u0643\u064a\u062f</button>' +
      '  </div>' +
      '</div>';

    overlay.querySelector('[data-confirm-message]').textContent = msg;

    document.body.appendChild(overlay);
    overlay.querySelector('[data-action="confirm"]').focus();

    function dismiss() {
      overlay.remove();
      open = false;
      if (opener && opener.focus) opener.focus();
    }

    overlay.addEventListener('click', function(ev) {
      // click target may be the icon inside the button \u2014 ask the nearest [data-action] host
      var btn = ev.target.closest ? ev.target.closest('[data-action]') : null;
      var action = btn ? btn.getAttribute('data-action') : null;
      if (action === 'confirm') {
        overlay.remove();
        open = false;
        form._confirmed = true;
        // requestSubmit keeps native validation + the submitter's name/value;
        // submit() drops both, so a two-button form loses which one was pressed.
        if (form.requestSubmit) form.requestSubmit(submitter || undefined);
        else form.submit();
        // guard: if no submit actually happened, do not leave the flag raised
        // (the next submit would then skip its confirmation).
        setTimeout(function() { form._confirmed = false; }, 0);
      } else if (action === 'cancel' || ev.target === overlay) {
        dismiss();
      }
    });
    overlay.addEventListener('keydown', function(ev) {
      if (ev.key === 'Escape') dismiss();
    });
  });
})();

/* ── Active nav link (aria-current) ──────────────────────── */
(function() {
  var path = location.pathname;
  document.querySelectorAll('.nb-bar a.nb').forEach(function(a) {
    var href = a.getAttribute('href');
    if (href && path.startsWith(href) && href !== '/dashboard/') {
      a.setAttribute('aria-current', 'page');
    } else if (href === '/dashboard/' && path === '/dashboard/') {
      a.setAttribute('aria-current', 'page');
    }
  });
})();

document.addEventListener('click', function(e) {
  var t = e.target;
  if (t.dataset.modalOpen) window.modalManager.open(t.dataset.modalOpen);
  if (t.dataset.modalClose) window.modalManager.close(t.dataset.modalClose);
});

/* ── Dark Mode Toggle ────────────────────────────────────── */
(function() {
  var btn = document.getElementById('theme-toggle');
  var icon = document.getElementById('theme-icon');
  var meta = document.getElementById('meta-theme-color');
  var metaCS = document.getElementById('meta-color-scheme');
  if (!btn) return;

  function isDark() { return document.documentElement.classList.contains('dark'); }

  function updateIcon() {
    var dark = isDark();
    if (icon) icon.innerHTML = dark ? '<svg class="icon" aria-hidden="true" focusable="false"><use href="#icon-sun"/></svg>' : '<svg class="icon" aria-hidden="true" focusable="false"><use href="#icon-moon"/></svg>';
    if (meta) meta.content = dark ? '#1a0a12' : '#8A1538';
    if (metaCS) metaCS.content = dark ? 'dark' : 'light';
    var menuIcon = document.getElementById('theme-menu-icon');
    var menuText = document.getElementById('theme-menu-text');
    if (menuIcon) menuIcon.innerHTML = dark ? '<svg class="icon" aria-hidden="true" focusable="false"><use href="#icon-sun"/></svg>' : '<svg class="icon" aria-hidden="true" focusable="false"><use href="#icon-moon"/></svg>';
    if (menuText) menuText.textContent = dark ? 'الوضع النهاري' : 'الوضع الليلي';
  }

  updateIcon();

  btn.addEventListener('click', function() {
    document.documentElement.classList.toggle('dark');
    var theme = isDark() ? 'dark' : 'light';
    localStorage.setItem('theme', theme);
    updateIcon();
  });

  // Listen for system preference changes
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
    if (!localStorage.getItem('theme')) {
      document.documentElement.classList.toggle('dark', e.matches);
      updateIcon();
    }
  });
})();

/* ══════════════════════════════════════════════════════════════
   الفرزُ الجدوليّ — Sortable table columns
   ══════════════════════════════════════════════════════════════
   جداولُ المنصّة تُفرَز من غير أن يُكتب في قالبها شيء: المحرّكُ يقرأ
   الترويسةَ والخلايا فيستنتج نوعَ كلّ عمود، ويُهيّئ نفسَه عند تحميل
   الصفحة وبعد كلّ تبديلٍ من HTMX.

   والاستثناءُ صريحٌ لا ضمنيّ:
     <table data-no-sort>            الجدولُ كلُّه لا يُفرَز
     <th data-sort="none">           عمودٌ بعينه لا يُفرَز
     <th data-sort="text|num">       نوعٌ مفروضٌ بدل المستنتَج
     <th data-sort-first="asc|desc"> اتّجاهُ النقرة الأولى بدل الطبيعيّ
     <td data-sort-value="…">        قيمةُ الفرز حين يخالف النصُّ المعنى
     <tr data-sort-pin>              صفٌّ يبقى في الذيل (الإجماليّات)

   والدورةُ: تصاعديٌّ ← تنازليٌّ ← الترتيبُ الأصليّ. والأعمدةُ الرقميّةُ
   تبدأ تنازليّاً لأنّ الأكبرَ هو المقصودُ أوّلاً في أعمدة الأعداد.
   ────────────────────────────────────────────────────────────── */
(function () {
  var COLLATOR = (typeof Intl !== 'undefined' && Intl.Collator)
    ? new Intl.Collator('ar', { numeric: true, sensitivity: 'base' })
    : null;

  var MIN_ROWS = 3;          /* أقلُّ من ثلاثةِ صفوفٍ لا يُفرَز: لا فائدةَ تُرتجى. */
  var NUM_SHARE = 0.7;       /* عمودٌ جُلُّ خلاياه أعدادٌ عمودٌ رقميّ. */
  var PIN_RE = /(^|[\s_-])(total|totals|summary|sum-row|footer-row)([\s_-]|$)/i;
  var TOTAL_TEXT_RE = /^\s*(الإجمالي|الاجمالي|المجموع|الكلي|الكلّي)/;
  var LETTERS_RE = /[A-Za-zء-ي]{3,}/;

  /* أرقامٌ عربيّة-هنديّة → لاتينيّة، ثمّ أوّلُ عددٍ في النصّ. */
  function toNumber(text) {
    var t = (text || '').replace(/[٠-٩]/g, function (d) {
      return String.fromCharCode(d.charCodeAt(0) - 0x0660 + 48);
    }).replace(/[٫٬,]/g, '').replace(/[−–—]/g, '-');
    var m = t.match(/-?\d+(?:\.\d+)?/);
    return m ? parseFloat(m[0]) : null;
  }

  /* نصُّ الخليّة كما يقرؤه الإنسان: القيمةُ المصرَّحة، ثمّ حقلُ الإدخال، ثمّ النصّ. */
  function cellText(cell) {
    if (!cell) return '';
    if (cell.hasAttribute('data-sort-value')) return cell.getAttribute('data-sort-value');
    var field = cell.querySelector('input, select, textarea');
    if (field) {
      if (field.type === 'checkbox' || field.type === 'radio') return field.checked ? '1' : '0';
      if (field.tagName === 'SELECT' && field.selectedIndex >= 0) return field.options[field.selectedIndex].text;
      return field.value || '';
    }
    return cell.textContent || '';
  }

  function cellValue(row, index, kind) {
    var raw = cellText(row.children[index]);
    if (kind === 'num') return toNumber(raw);
    return (window.smartNorm ? window.smartNorm(raw) : (raw || '').trim().toLowerCase());
  }

  function isBlank(v, kind) {
    return kind === 'num' ? (v === null) : !v;
  }

  function compare(a, b, kind) {
    if (kind === 'num') return a - b;
    return COLLATOR ? COLLATOR.compare(a, b) : (a < b ? -1 : a > b ? 1 : 0);
  }

  /* ── استنتاجُ بنية الجدول ──────────────────────────────────── */

  /* صفُّ تفصيلٍ: خليّةٌ واحدةٌ ممدودةٌ على الجدول، تتبع صفَّها فتُنقل معه. */
  function isDetailRow(row, ncols) {
    if (row.cells.length !== 1) return false;
    var span = parseInt(row.cells[0].getAttribute('colspan') || '1', 10);
    return span >= Math.min(ncols, 2);
  }

  /* صفُّ إجماليٍّ يبقى في الذيل مهما فُرز الجدول. */
  function isPinned(row) {
    if (row.hasAttribute('data-sort-pin')) return true;
    if (PIN_RE.test(row.className)) return true;
    var first = row.cells[0];
    return !!first && TOTAL_TEXT_RE.test((first.textContent || '').trim());
  }

  /* نوعُ العمود: مفروضٌ من القالب، أو مستنتَجٌ من خلاياه — وإلّا فلا يُفرَز. */
  function columnKind(th, rows, index) {
    var forced = th.getAttribute('data-sort');
    if (forced === 'none') return null;
    if (forced === 'num' || forced === 'text') return forced;

    var srOnly = th.querySelector('.sr-only');
    var label = (th.textContent || '').replace(/\s+/g, ' ').trim();
    if (srOnly) label = label.replace((srOnly.textContent || '').replace(/\s+/g, ' ').trim(), '').trim();
    if (!label || label === '#') return null;
    if (th.querySelector('input, button')) return null;

    var nums = 0, filled = 0, controls = 0;
    for (var i = 0; i < rows.length; i++) {
      var cell = rows[i].children[index];
      if (!cell) continue;
      if (!cell.hasAttribute('data-sort-value') &&
          cell.querySelector('button, .btn, input[type="checkbox"]')) controls++;
      var raw = cellText(cell).replace(/\s+/g, ' ').trim();
      if (!raw || raw === '—' || raw === '-') continue;
      filled++;
      if (toNumber(raw) !== null && !LETTERS_RE.test(raw)) nums++;
    }
    if (controls > rows.length / 2) return null;   /* عمودُ إجراءاتٍ لا بيانات */
    if (!filled) return null;
    return (nums / filled >= NUM_SHARE) ? 'num' : 'text';
  }

  /* ── المحرّك ───────────────────────────────────────────────── */

  function sortable(table, opts) {
    table = (typeof table === 'string') ? document.querySelector(table) : table;
    if (!table || table.__sortBound) return false;
    opts = opts || {};

    var tbody = table.tBodies[0];
    var head = (table.tHead && table.tHead.rows.length === 1) ? table.tHead.rows[0] : null;
    if (!tbody || !head || !head.cells.length) return false;
    if (table.hasAttribute('data-no-sort')) return false;
    if (table.closest && table.closest('[data-no-sort]')) return false;

    var ncols = 0;
    Array.prototype.forEach.call(head.cells, function (th) {
      ncols += parseInt(th.getAttribute('colspan') || '1', 10);
    });
    if (ncols !== head.cells.length) return false;   /* ترويسةٌ مدموجةٌ لا يقابلها عمود */

    /* الصفوفُ الصالحة: خلاياها بعدد الترويسة؛ وما دونها إمّا تفصيلٌ يتبع أو مانعٌ للفرز. */
    var all = Array.prototype.slice.call(tbody.rows);
    var groups = [], pinned = [], i, row;
    for (i = 0; i < all.length; i++) {
      row = all[i];
      if (isDetailRow(row, ncols)) {
        if (!groups.length) return false;            /* تفصيلٌ بلا صفٍّ قبله: بنيةٌ لا تُفهم */
        groups[groups.length - 1].nodes.push(row);
        continue;
      }
      if (row.querySelector('[rowspan]') || row.cells.length !== ncols) return false;
      if (isPinned(row)) { pinned.push(row); continue; }
      groups.push({ row: row, nodes: [row], order: groups.length });
    }
    if (groups.length < MIN_ROWS) return false;

    var plain = groups.map(function (g) { return g.row; });
    var kinds = [], sortableCount = 0;
    Array.prototype.forEach.call(head.cells, function (th, index) {
      var kind = columnKind(th, plain, index);
      kinds.push(kind);
      if (kind) sortableCount++;
    });
    if (sortableCount < 2) return false;

    /* عمودُ الترقيم: أوّلُ عمودٍ عنوانُه «#» أو «م» تُعاد أرقامُه فيصير رتبةً. */
    var firstLabel = (head.cells[0].textContent || '').trim();
    var renumber = (firstLabel === '#' || firstLabel === 'م');

    var state = { index: -1, dir: 0 };

    /* الفرزُ يُغيّر الترتيبَ لا المعروض؛ فيُطوى التفصيلُ المفتوحُ حتى لا يُقرأ في غير موضعه. */
    function collapseDetails() {
      groups.forEach(function (g) {
        for (var n = 1; n < g.nodes.length; n++) {
          var d = g.nodes[n];
          if (d.hidden) continue;
          d.hidden = true;
          var btn = d.id ? table.querySelector('[aria-controls="' + d.id + '"]') : null;
          if (btn) {
            btn.setAttribute('aria-expanded', 'false');
            var owner = btn.closest('tr');
            if (owner) owner.classList.remove('is-open');
          }
        }
      });
    }

    function apply() {
      var list = groups.slice();
      if (state.dir !== 0) {
        var kind = kinds[state.index];
        var keyed = list.map(function (g) {
          return { g: g, key: cellValue(g.row, state.index, kind) };
        });
        keyed.sort(function (x, y) {
          /* الخليّةُ الخاليةُ لا قيمةَ لها يُفرَز بها: تُدفَع إلى الذيل في الاتّجاهين
             كليهما — قبل الاتّجاه لا بعده، وإلّا تصدّرَ الفراغُ الفرزَ التنازليّ. */
          var ax = isBlank(x.key, kind), ay = isBlank(y.key, kind);
          if (ax || ay) {
            if (ax && ay) return x.g.order - y.g.order;
            return ax ? 1 : -1;
          }
          var c = compare(x.key, y.key, kind);
          if (c !== 0) return state.dir === 1 ? c : -c;
          return x.g.order - y.g.order; /* ثباتُ الترتيب عند التساوي */
        });
        list = keyed.map(function (k) { return k.g; });
      }

      var frag = document.createDocumentFragment();
      list.forEach(function (g) {
        g.nodes.forEach(function (n) { frag.appendChild(n); });
      });
      pinned.forEach(function (n) { frag.appendChild(n); });
      tbody.appendChild(frag);
      collapseDetails();

      if (renumber) {
        list.forEach(function (g, n) {
          var cell = g.row.children[0];
          if (cell && !cell.querySelector('*')) cell.textContent = n + 1;
        });
      }
      if (opts.onSort) opts.onSort(state);
    }

    Array.prototype.forEach.call(head.cells, function (th, index) {
      var kind = kinds[index];
      if (!kind) return;
      var label = (th.textContent || '').replace(/\s+/g, ' ').trim();
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'th-sort';
      btn.innerHTML = '<span class="th-sort-label"></span><span class="th-sort-arrow" aria-hidden="true"></span>';
      btn.querySelector('.th-sort-label').textContent = label;
      btn.setAttribute('aria-label', 'رتّب حسب ' + label);
      /* محاذاةُ الزرّ تتبع محاذاةَ الترويسة، فلا ينزاح عنوانُ عمودٍ عن موضعه. */
      var align = window.getComputedStyle ? window.getComputedStyle(th).textAlign : '';
      if (align === 'center') btn.style.justifyContent = 'center';
      else if (align === 'left' || align === 'end') btn.style.justifyContent = 'flex-end';
      th.textContent = '';
      th.appendChild(btn);
      th.setAttribute('aria-sort', 'none');
      th.classList.add('is-sortable');

      /* الاتّجاهُ الأوّل: تنازليٌّ في الأعداد لأنّ الأكبرَ هو المقصودُ أوّلاً،
         ما لم يُصرّح القالبُ بغيره — كعمود الشعبة الذي يُقرأ من 7/1 صعوداً. */
      var firstDir = th.getAttribute('data-sort-first');
      var startDesc = firstDir ? (firstDir === 'desc') : (kind === 'num');

      btn.addEventListener('click', function () {
        if (state.index !== index) {
          state.index = index;
          state.dir = startDesc ? -1 : 1;
        } else if (startDesc) {
          state.dir = state.dir === -1 ? 1 : (state.dir === 1 ? 0 : -1);
        } else {
          state.dir = state.dir === 1 ? -1 : (state.dir === -1 ? 0 : 1);
        }
        if (state.dir === 0) state.index = -1;

        Array.prototype.forEach.call(head.cells, function (other) {
          if (other.classList.contains('is-sortable')) other.setAttribute('aria-sort', 'none');
        });
        th.setAttribute('aria-sort', state.dir === 1 ? 'ascending' : state.dir === -1 ? 'descending' : 'none');
        apply();
      });
    });

    table.__sortBound = true;
    table.classList.add('is-sortable-table');
    return true;
  }

  /* ── التهيئةُ التلقائيّة ───────────────────────────────────── */

  function initAll(root) {
    var scope = (root && root.querySelectorAll) ? root : document;
    var tables = Array.prototype.slice.call(scope.querySelectorAll('table'));
    if (scope.tagName === 'TABLE') tables.push(scope);
    tables.forEach(function (t) {
      /* جدولٌ داخل جدولٍ تابعٌ لأمّه: يُفرَز الأصلُ لا الفرع. */
      if (t.parentElement && t.parentElement.closest('table')) return;
      sortable(t);
    });
  }

  window.sortableTable = sortable;
  window.initSortableTables = initAll;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { initAll(document); });
  } else {
    initAll(document);
  }
  /* HTMX يستبدل أجزاءً من الصفحة، والجدولُ الجديدُ يحتاج ترويسةً جديدة. */
  document.addEventListener('htmx:afterSwap', function (e) { initAll(e.target); });
})();
