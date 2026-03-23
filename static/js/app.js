/* SchoolOS — app.js v5.3 */
'use strict';
(function () {

  /* ── Swipe يساراً على إشعار → تحديد كمقروء ──────────────── */
  function initSwipe(el) {
    var sx = 0;
    el.addEventListener('touchstart', function (e) {
      sx = e.touches[0].clientX;
    }, { passive: true });
    el.addEventListener('touchend', function (e) {
      var dx = e.changedTouches[0].clientX - sx;
      if (dx < -60) {
        var btn = el.querySelector('button[hx-post]');
        if (btn) btn.click();
      }
    }, { passive: true });
  }

  function initAllSwipes() {
    document.querySelectorAll('.notif-item').forEach(initSwipe);
  }

  /* ── Command Palette (Ctrl+K) ────────────────────────────── */
  var palette = null;
  var cmdInput = null;
  var cmdResults = null;
  var searchTimer = null;
  var activeIdx = -1;

  function openPalette() {
    palette = document.getElementById('cmd-palette');
    cmdInput = document.getElementById('cmd-input');
    cmdResults = document.getElementById('cmd-results');
    if (!palette) return;
    palette.style.display = 'flex';
    cmdInput.value = '';
    cmdResults.innerHTML = '';
    activeIdx = -1;
    setTimeout(function () { cmdInput.focus(); }, 50);
  }

  window.closePalette = function () {
    if (palette) palette.style.display = 'none';
  };

  function renderResults(items) {
    if (!cmdResults) return;
    if (!items.length) {
      cmdResults.innerHTML = '<div style="text-align:center;padding:24px;color:#9ca3af;font-size:13px;">لا توجد نتائج</div>';
      return;
    }
    cmdResults.innerHTML = items.map(function (r, i) {
      return '<a class="cmd-item" href="' + r.url + '" data-idx="' + i + '">'
        + '<span class="cmd-item-icon">' + r.icon + '</span>'
        + '<div class="cmd-item-text">'
        + '<div class="cmd-item-title">' + r.title + '</div>'
        + '<div class="cmd-item-sub">' + r.sub + '</div>'
        + '</div></a>';
    }).join('');
    activeIdx = -1;
  }

  function doSearch(q) {
    if (q.length < 2) { if (cmdResults) cmdResults.innerHTML = ''; return; }
    fetch('/search/?q=' + encodeURIComponent(q), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
    .then(function (r) { return r.json(); })
    .then(function (d) { renderResults(d.results || []); })
    .catch(function () {
      if (typeof window.showToast === 'function') {
        window.showToast('خطأ في البحث — تحقق من الاتصال', 'danger');
      }
    });
  }

  function highlightItem(idx) {
    if (!cmdResults) return;
    var items = cmdResults.querySelectorAll('.cmd-item');
    items.forEach(function (el) { el.classList.remove('active'); });
    if (idx >= 0 && idx < items.length) {
      items[idx].classList.add('active');
      items[idx].scrollIntoView({ block: 'nearest' });
    }
    activeIdx = idx;
  }

  document.addEventListener('keydown', function (e) {
    // Ctrl+K أو Cmd+K
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      openPalette();
      return;
    }
    // Escape
    if (e.key === 'Escape' && palette && palette.style.display !== 'none') {
      e.preventDefault();
      closePalette();
      return;
    }
    // سهم أعلى/أسفل + Enter داخل palette
    if (palette && palette.style.display !== 'none') {
      var items = cmdResults ? cmdResults.querySelectorAll('.cmd-item') : [];
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        highlightItem(Math.min(activeIdx + 1, items.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        highlightItem(Math.max(activeIdx - 1, 0));
      } else if (e.key === 'Enter' && activeIdx >= 0 && items[activeIdx]) {
        e.preventDefault();
        window.location.href = items[activeIdx].href;
      }
    }
  });

  /* ── Toast Helper (من HTMX أو JS) ───────────────────────── */
  window.showToast = function (msg, type) {
    type = type || 'success';
    var container = document.getElementById('toast-container');
    if (!container) return;
    var icons = { success: '✅', danger: '❌', warning: '⚠️', info: 'ℹ️' };
    var toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = '<span class="toast-icon">' + (icons[type] || '✅') + '</span>'
      + '<span style="flex:1;">' + msg + '</span>'
      + '<button class="toast-close" onclick="removeToast(this)" aria-label="إغلاق">✕</button>';
    container.appendChild(toast);
    setTimeout(function () { removeToast(toast.querySelector('.toast-close')); }, 4500);
  };

  window.removeToast = function (btn) {
    var toast = btn.closest ? btn.closest('.toast') : btn.parentElement;
    if (!toast) return;
    toast.classList.add('toast-leaving');
    setTimeout(function () { toast.remove(); }, 250);
  };

  /* ── HTMX → Toast (عبر HX-Trigger header) ─────────────── */
  document.addEventListener('htmx:afterRequest', function (e) {
    var trigger = e.detail.xhr && e.detail.xhr.getResponseHeader('HX-Trigger');
    if (trigger) {
      try {
        var parsed = JSON.parse(trigger);
        if (parsed.showToast) {
          showToast(parsed.showToast.message || parsed.showToast, parsed.showToast.type || 'success');
        }
      } catch (_) {}
    }
  });

  /* ── HTMX Global Error Handler ────────────────────────────── */
  document.addEventListener('htmx:responseError', function (e) {
    var status = e.detail.xhr ? e.detail.xhr.status : 0;
    var msg = 'حدث خطأ غير متوقع';
    if (status === 403) msg = 'ليس لديك صلاحية لهذا الإجراء';
    else if (status === 404) msg = 'الصفحة المطلوبة غير موجودة';
    else if (status >= 500) msg = 'خطأ في الخادم — حاول مرة أخرى';
    else if (status === 0) msg = 'خطأ في الاتصال — تحقق من الشبكة';
    showToast(msg, 'danger');
  });

  /* ── Client-side Form Validation ────────────────────────── */
  function showFieldError(input, msg) {
    clearFieldError(input);
    input.classList.add('field-error');
    var el = document.createElement('div');
    el.className = 'field-error-msg';
    el.textContent = msg;
    input.parentNode.appendChild(el);
  }

  function clearFieldError(input) {
    input.classList.remove('field-error');
    var err = input.parentNode.querySelector('.field-error-msg');
    if (err) err.remove();
  }

  function initFormValidation() {
    document.querySelectorAll('form[data-validate]').forEach(function (form) {
      form.addEventListener('submit', function (e) {
        var valid = true;
        form.querySelectorAll('[required], [pattern]').forEach(function (input) {
          clearFieldError(input);
          if (!input.validity.valid) {
            var msg = input.title || input.validationMessage || 'هذا الحقل مطلوب';
            showFieldError(input, msg);
            valid = false;
          }
        });
        if (!valid) {
          e.preventDefault();
          var firstErr = form.querySelector('.field-error');
          if (firstErr) firstErr.focus();
        }
      });

      form.querySelectorAll('[required], [pattern]').forEach(function (input) {
        input.addEventListener('input', function () { clearFieldError(input); });
      });
    });
  }

  /* ── Init ──────────────────────────────────────────────────── */
  function initAll() {
    initAllSwipes();
    initFormValidation();
    // ربط حقل البحث
    var input = document.getElementById('cmd-input');
    if (input && !input._bound) {
      input._bound = true;
      input.addEventListener('input', function () {
        clearTimeout(searchTimer);
        var val = input.value.trim();
        searchTimer = setTimeout(function () { doSearch(val); }, 250);
      });
    }
  }

  document.addEventListener('DOMContentLoaded', initAll);
  document.addEventListener('htmx:afterSwap', function () {
    initAllSwipes();
    initFormValidation();
  });

})();
