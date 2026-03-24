/**
 * base.js — SchoolOS v6
 * الوظائف الأساسية للمنصة: Dropdown · Notifications · PWA · Modal · Toast
 * يُحمَّل عبر <script src> — لا يحتاج nonce (CSP 'self' يسمح بالملفات الخارجية)
 */
'use strict';

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
  document.querySelectorAll('.nb.on').forEach(function(x) { x.classList.remove('on'); });
  if (!isOpen) { sdPos(m, btn); m.classList.add('open'); btn.classList.add('on'); }
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
    document.querySelectorAll('.nb.on').forEach(function(x) { x.classList.remove('on'); });
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


/* ── Modal Manager ────────────────────────────────────────── */
window.modalManager = {
  _stack: [],
  open: function(id) {
    var overlay = document.getElementById('modal-' + id);
    if (!overlay) return;
    this._stack.push({ id: id, trigger: document.activeElement });
    overlay.style.display = 'flex';
    overlay.removeAttribute('hidden');
    var focusable = overlay.querySelector(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (focusable) setTimeout(function() { focusable.focus(); }, 50);
  },
  close: function(id) {
    var overlay = document.getElementById('modal-' + id);
    if (!overlay) return;
    overlay.style.display = 'none';
    overlay.setAttribute('hidden', '');
    var prev = this._stack.pop();
    if (prev && prev.trigger) prev.trigger.focus();
  },
  closeTop: function() {
    if (this._stack.length) this.close(this._stack[this._stack.length - 1].id);
  }
};

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') window.modalManager.closeTop();
});


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
  if (!btn) return;

  function isDark() { return document.documentElement.classList.contains('dark'); }

  function updateIcon() {
    var dark = isDark();
    if (icon) icon.textContent = dark ? '☀️' : '🌙';
    if (meta) meta.content = dark ? '#1a0a12' : '#8A1538';
    var menuIcon = document.getElementById('theme-menu-icon');
    var menuText = document.getElementById('theme-menu-text');
    if (menuIcon) menuIcon.textContent = dark ? '☀️' : '🌙';
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
