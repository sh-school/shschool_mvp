/* SchoolOS — app.js v5.4 */
'use strict';
(function () {

  /* ── HTML escape — حماية من XSS ──────────────────────────── */
  function esc(str) {
    var d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

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
    palette.classList.remove('cmd-hidden');
    cmdInput.value = '';
    cmdResults.innerHTML = '';
    activeIdx = -1;
    setTimeout(function () { cmdInput.focus(); }, 50);
  }

  window.closePalette = function () {
    if (palette) palette.classList.add('cmd-hidden');
  };

  function renderResults(items) {
    if (!cmdResults) return;
    if (!items.length) {
      cmdResults.innerHTML = '<div class="cmd-empty">\u0644\u0627 \u062a\u0648\u062c\u062f \u0646\u062a\u0627\u0626\u062c</div>';
      return;
    }
    cmdResults.innerHTML = items.map(function (r, i) {
      return '<a class="cmd-item" href="' + esc(r.url) + '" data-idx="' + i + '">'
        + '<span class="cmd-item-icon">' + esc(r.icon) + '</span>'
        + '<div class="cmd-item-text">'
        + '<div class="cmd-item-title">' + esc(r.title) + '</div>'
        + '<div class="cmd-item-sub">' + esc(r.sub) + '</div>'
        + '</div></a>';
    }).join('');
    activeIdx = -1;
  }

  function doSearch(q) {
    if (q.length < 2) { if (cmdResults) cmdResults.innerHTML = ''; return; }
    /* تطبيع البحث: إزالة التشكيل + توحيد الهمزات قبل الإرسال */
    var normQ = (typeof window.smartNorm === 'function') ? window.smartNorm(q) : q;
    fetch('/search/?q=' + encodeURIComponent(q), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      var results = d.results || [];
      /* فلترة ذكية على النتائج — بحث متعدد الكلمات */
      if (typeof window.smartMatch === 'function' && normQ) {
        results = results.filter(function(r) {
          return window.smartMatch(q, (r.title || '') + ' ' + (r.sub || ''));
        });
      }
      renderResults(results);
    })
    .catch(function () {
      if (typeof window.showToast === 'function') {
        window.showToast('\u062e\u0637\u0623 \u0641\u064a \u0627\u0644\u0628\u062d\u062b \u2014 \u062a\u062d\u0642\u0642 \u0645\u0646 \u0627\u0644\u0627\u062a\u0635\u0627\u0644', 'danger');
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
    if (e.key === 'Escape' && palette && !palette.classList.contains('cmd-hidden')) {
      e.preventDefault();
      closePalette();
      return;
    }
    // سهم أعلى/أسفل + Enter داخل palette
    if (palette && !palette.classList.contains('cmd-hidden')) {
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

  /* ── HTMX → Toast (عبر HX-Trigger header) ─────────────── */
  document.addEventListener('htmx:afterRequest', function (e) {
    var trigger = e.detail.xhr && e.detail.xhr.getResponseHeader('HX-Trigger');
    if (trigger) {
      try {
        var parsed = JSON.parse(trigger);
        if (parsed.showToast) {
          window.showToast(parsed.showToast.message || parsed.showToast, parsed.showToast.type || 'success');
        }
      } catch (_) {}
    }
  });

  /* ── HTMX Global Error Handler ────────────────────────────── */
  document.addEventListener('htmx:responseError', function (e) {
    var status = e.detail.xhr ? e.detail.xhr.status : 0;
    var msg = '\u062d\u062f\u062b \u062e\u0637\u0623 \u063a\u064a\u0631 \u0645\u062a\u0648\u0642\u0639';
    if (status === 403) msg = '\u0644\u064a\u0633 \u0644\u062f\u064a\u0643 \u0635\u0644\u0627\u062d\u064a\u0629 \u0644\u0647\u0630\u0627 \u0627\u0644\u0625\u062c\u0631\u0627\u0621';
    else if (status === 404) msg = '\u0627\u0644\u0635\u0641\u062d\u0629 \u0627\u0644\u0645\u0637\u0644\u0648\u0628\u0629 \u063a\u064a\u0631 \u0645\u0648\u062c\u0648\u062f\u0629';
    else if (status >= 500) msg = '\u062e\u0637\u0623 \u0641\u064a \u0627\u0644\u062e\u0627\u062f\u0645 \u2014 \u062d\u0627\u0648\u0644 \u0645\u0631\u0629 \u0623\u062e\u0631\u0649';
    else if (status === 0) msg = '\u062e\u0637\u0623 \u0641\u064a \u0627\u0644\u0627\u062a\u0635\u0627\u0644 \u2014 \u062a\u062d\u0642\u0642 \u0645\u0646 \u0627\u0644\u0634\u0628\u0643\u0629';
    window.showToast(msg, 'danger');
  });

  /* ── Client-side Form Validation ────────────────────────── */
  function showFieldError(input, msg) {
    clearFieldError(input);
    input.classList.add('field-error');
    input.setAttribute('aria-invalid', 'true');
    var el = document.createElement('div');
    el.className = 'field-error-msg';
    el.id = 'err-' + (input.id || input.name || Math.random().toString(36).slice(2));
    el.textContent = msg;
    input.setAttribute('aria-describedby', el.id);
    input.parentNode.appendChild(el);
  }

  function clearFieldError(input) {
    input.classList.remove('field-error');
    input.removeAttribute('aria-invalid');
    input.removeAttribute('aria-describedby');
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
            var msg = input.title || input.validationMessage || '\u0647\u0630\u0627 \u0627\u0644\u062d\u0642\u0644 \u0645\u0637\u0644\u0648\u0628';
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
