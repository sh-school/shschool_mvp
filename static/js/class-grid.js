/**
 * جدولُ الشعبة العموديّ لرصد الغياب — الضغطةُ بحالةٍ صريحة، والحفظُ بالعمود، وردُّ التعارض، ومسوّدةٌ محلّيّةٌ بلا أسماء.
 * (W-20261006-005، قرارا المالك D-239م وD-240م)
 *
 * - الضغطةُ: لم تُرصد ← غائب ← حاضر ← غائب… والواجهةُ **ترسل الحالةَ الصريحة** مع `head` (رأسُ الخليّة الذي رأته) لا «تبديلاً».
 * - مفاتيحُ أسفل كلّ عمود: «الكلّ ✓/✗» تعدّل خلايا العمود في الواجهة فقط (بلا تأكيد ولا حفظ، D-247م) و«حفظ» يحفظ ذلك العمودَ وحدَه.
 * - الحفظُ لعمودٍ واحد: خلايا العمود المتغيّرةُ فقط، وتنبيهٌ بعدد الفارغات (تُكتب «حاضراً افتراضيّاً» لعمودٍ بدأت حصّتُه) يطلب تأكيداً.
 * - تعارضٌ (207): تُبرَز الخليّةُ بقيمتها الحاليّة ومن كتبها ومتى، ويحسم المستخدمُ كلَّ واحدةٍ على حدة.
 * - المسوّدةُ في `localStorage`: **رموزُ الحالة ومعرّفاتُ الطلبة فقط** (بلا أسماء)، وتُمسح عند الحفظ الناجح؛ ولا كتابةَ تلقائيّةَ للخادم.
 * - لا CSP inline: كلُّ شيءٍ بسمات `data-*`؛ والملفُّ مغلَّفٌ فلا يعلن شيئاً عامّاً (page-nav يعيد تشغيله).
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-class-grid]');
  if (!root) return;
  var saveUrl = root.getAttribute('data-save-url');
  var lateUrl = root.getAttribute('data-late-url');
  var exitUrl = root.getAttribute('data-exit-url');
  var draftKey = root.getAttribute('data-draft-key');
  var statusLine = root.querySelector('[data-grid-status]');
  var tokenInput = document.querySelector('input[name=csrfmiddlewaretoken]');
  var SYMBOL = { '': '·', present: '✓', absent: 'غ', late: 'ت' };
  var CYCLE = { '': 'absent', absent: 'present', present: 'absent', late: 'present' };

  function csrf() { return tokenInput ? tokenInput.value : ''; }
  function say(text) { if (statusLine) statusLine.textContent = text || ''; }
  // رسالةٌ ظاهرةٌ (toast المنصّة المركزيّ) مع سطر الحالة: سطرُ الحالة أسفلَ الجدول يغيب عن النظر في بطاقةٍ تتمرّر.
  function notify(text, type) {
    say(text);
    if (typeof window.showToast === 'function') window.showToast(text, type || 'info');
  }

  // ── المسوّدة: { col: { studentId: status } } ──
  function readDraft() {
    try { return JSON.parse(window.localStorage.getItem(draftKey) || '{}') || {}; } catch (e) { return {}; }
  }
  function writeDraft(draft) {
    try { window.localStorage.setItem(draftKey, JSON.stringify(draft)); } catch (e) { /* لا تخزين */ }
  }
  var draft = readDraft();

  function cells(col) { return root.querySelectorAll('[data-cell][data-col="' + col + '"]'); }

  function paint(cell, status) {
    cell.classList.remove('is-none', 'is-present', 'is-absent', 'is-late', 'is-default', 'is-conflict');
    cell.classList.add('is-' + (status || 'none'));
    cell.setAttribute('data-status', status || '');
    cell.textContent = SYMBOL[status || ''];
  }

  function remember(cell) {
    var col = cell.getAttribute('data-col');
    draft[col] = draft[col] || {};
    draft[col][cell.getAttribute('data-student')] = cell.getAttribute('data-status');
    writeDraft(draft);
  }

  // استعادةُ المسوّدة فوق خلايا لم يتغيّر رأسُها (لا نكتب فوق ما رأيناه جديداً)؛ `scope` يحصرها في صفٍّ بُدّل من الخادم.
  function restoreDraft(scope) {
    Object.keys(draft).forEach(function (col) {
      Object.keys(draft[col]).forEach(function (student) {
        var cell = scope.querySelector('[data-cell][data-col="' + col + '"][data-student="' + student + '"]');
        if (cell && cell.getAttribute('data-writable') === '1' && !cell.getAttribute('data-head')) {
          paint(cell, draft[col][student]);
          cell.classList.add('is-dirty');
        }
      });
    });
  }
  restoreDraft(root);

  root.addEventListener('click', function (event) {
    var cell = event.target.closest('[data-cell]');
    if (cell && cell.getAttribute('data-writable') === '1') {
      var next = CYCLE[cell.getAttribute('data-status') || ''] || 'absent';
      paint(cell, next);
      cell.classList.add('is-dirty');
      remember(cell);
      return;
    }
    var bulk = event.target.closest('[data-bulk]');
    if (bulk) return bulkFill(bulk);
    var saveBtn = event.target.closest('[data-save-col]');
    if (saveBtn) return save(saveBtn.getAttribute('data-save-col'));
    var opener = event.target.closest('[data-acts-open]');
    if (opener) return openSheet(opener.getAttribute('data-acts-open'));
    if (event.target.closest('[data-sheet-close]')) return closeSheets();
    // نقرةٌ على حجب الحوار نفسِه (لا على محتواه) تغلق الورقة.
    if (event.target.matches && event.target.matches('dialog[data-acts-sheet]')) return closeSheets();
    var late = event.target.closest('[data-late]');
    if (late) { closeSheets(); return markLate(late); }
    var exitBtn = event.target.closest('[data-exit]');
    if (exitBtn) { closeSheets(); return exitAction(exitBtn.getAttribute('data-exit'), 'leave'); }
    var backBtn = event.target.closest('[data-exit-return]');
    if (backBtn) { closeSheets(); return exitAction(backBtn.getAttribute('data-exit-return'), 'return'); }
    var hist = event.target.closest('[data-history-open]');
    if (hist) return openHistory(hist.getAttribute('data-student'), currentCol());
    var tab = event.target.closest('[data-tab]');
    if (tab) return showTab(tab.getAttribute('data-tab'));
  });

  // دائرةُ الخروج: المعلوماتُ (الوجهة والساعة والمدّة) تطفو عند مرور المؤشّر فقط؛ لا نقرَ ولا بقاء، وعلى اللمس يبقى الرقمُ وحدَه.
  var pop = null;
  function exitPop() {
    if (!pop) {
      pop = document.createElement('div');
      pop.className = 'cg-exitpop';
      pop.setAttribute('role', 'tooltip');
      pop.hidden = true;
      document.body.appendChild(pop);
    }
    return pop;
  }
  root.addEventListener('mouseover', function (event) {
    var dot = event.target.closest('[data-exit-tip]');
    if (!dot) return;
    var box = exitPop();
    box.textContent = dot.getAttribute('data-exit-tip');
    box.hidden = false;
    var r = dot.getBoundingClientRect();
    var w = box.offsetWidth, h = box.offsetHeight;
    var left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), window.innerWidth - w - 8);
    var top = r.top - h - 6 < 8 ? r.bottom + 6 : r.top - h - 6;
    box.style.left = left + 'px';
    box.style.top = top + 'px';
  });
  root.addEventListener('mouseout', function (event) {
    if (event.target.closest('[data-exit-tip]') && pop) pop.hidden = true;
  });

  root.addEventListener('dblclick', function (event) {
    var cell = event.target.closest('[data-cell]');
    if (cell) openHistory(cell.getAttribute('data-student'), cell.getAttribute('data-col'));
  });

  function currentCol() {
    var current = root.querySelector('th.cg-col--current');
    if (current) return current.getAttribute('data-col');
    var next = root.querySelector('th.cg-col--next');
    if (next) return next.getAttribute('data-col');
    var started = root.querySelectorAll('th.cg-col--past');
    return started.length ? started[started.length - 1].getAttribute('data-col') : '1';
  }

  // نافذةُ التأكيد = نافذةُ المنصّة المركزيّة (`base.js`، مالكةُ `data-confirm`): نموذجٌ مخفيٌّ بنصّ التأكيد يُرسَل برمجيّاً، فتظهر النافذةُ
  // المصمَّمةُ بهويّة المنصّة (لا `window.confirm` الأصليّ)، وعند «تأكيد» يعود الإرسالُ إلى هنا فننفّذ المؤجَّل.
  var gate = root.querySelector('[data-grid-confirm]');
  var pending = null;
  if (gate) {
    gate.addEventListener('submit', function (event) {
      if (!gate._confirmed) return;           // الإرسالُ الأوّل: تعترضه نافذةُ المنصّة
      event.preventDefault();                 // الإرسالُ المؤكَّد: ننفّذ ما أُجِّل ولا نُرسل النموذج
      var next = pending; pending = null;
      // بعد أن يُسقط base.js علَمَ التأكيد (setTimeout 0): تنفيذٌ فوريٌّ يجعل تأكيداً ثانياً متداخلاً يمرّ بلا نافذة.
      if (next) window.setTimeout(next, 30);
    });
  }
  function confirmThen(message, next) {
    if (!gate) { next(); return; }
    pending = next;
    gate.setAttribute('data-confirm', message);
    gate.requestSubmit();
  }

  // «الكلّ ✓/✗» لعمود الزرّ نفسِه: تغييرٌ في الواجهة فقط (خلايا مكتوبةٌ لا تُحفظ) — لا تأكيدَ هنا؛ التأكيدُ والحفظُ عند «حفظ».
  function bulkFill(button) {
    var col = button.getAttribute('data-col');
    var status = button.getAttribute('data-bulk') === 'all_absent' ? 'absent' : 'present';
    Array.prototype.forEach.call(cells(col), function (c) {
      if (c.getAttribute('data-writable') !== '1') return;
      paint(c, status);
      c.classList.add('is-dirty');
      remember(c);
    });
    root.setAttribute('data-bulk-' + col, button.getAttribute('data-bulk'));
  }

  function save(col) {
    var all = cells(col);
    var dirty = Array.prototype.filter.call(all, function (c) { return c.classList.contains('is-dirty'); });
    var empties = Array.prototype.filter.call(all, function (c) {
      return c.getAttribute('data-writable') === '1' && !c.getAttribute('data-status');
    });
    if (!dirty.length && !empties.length) { notify('لا تغييرَ لحفظه في ح' + col, 'info'); return; }
    var reasonInput = document.querySelector('[data-grid-reason]');
    var reason = reasonInput ? reasonInput.value.trim() : '';
    if (empties.length) {
      confirmThen('يوجد ' + empties.length + ' خليّةٍ فارغةٍ في ح' + col + ' ستُكتب «حاضراً افتراضيّاً». حفظُ العمود؟', function () {
        send(col, dirty, true, reason);
      });
      return;
    }
    send(col, dirty, false, reason);
  }

  function send(col, dirty, fill, reason) {
    var payload = {
      period: parseInt(col, 10),
      date: root.getAttribute('data-date') || '',
      cells: dirty.map(function (c) {
        return { student: c.getAttribute('data-student'), status: c.getAttribute('data-status'), head: c.getAttribute('data-head') || '' };
      }),
      fill_empty: fill,
      bulk: root.getAttribute('data-bulk-' + col) || '',
      reason: reason || ''
    };
    say('جارٍ الحفظ…');
    fetch(saveUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
      body: JSON.stringify(payload)
    }).then(function (response) {
      return response.json().then(function (data) { return { status: response.status, data: data }; });
    }).then(function (result) {
      if (result.status === 403 && result.data && result.data.message) { notify(result.data.message, 'danger'); return; }
      if (result.status >= 400) { notify('تعذّر الحفظ — لم يُحفظ شيء (' + result.status + ').', 'danger'); return; }
      applyResult(col, result.data);
    }).catch(function () { notify('تعذّر الحفظ — المسوّدةُ محفوظةٌ في جهازك، أعِد المحاولة.', 'danger'); });
  }

  function cellOf(col, student) {
    return root.querySelector('[data-cell][data-col="' + col + '"][data-student="' + student + '"]');
  }

  function applyResult(col, data) {
    (data.saved || []).forEach(function (item) {
      var cell = cellOf(col, item.student);
      if (!cell) return;
      paint(cell, item.status);
      cell.classList.remove('is-dirty');
      cell.setAttribute('data-head', item.head || '');
      if (item.default_present) cell.classList.add('is-default');
    });
    (data.conflicts || []).forEach(function (item) {
      var cell = cellOf(col, item.student);
      if (!cell) return;
      paint(cell, item.status);
      cell.classList.add('is-conflict');
      cell.setAttribute('data-head', item.head || '');
      cell.setAttribute('title', 'غيّره ' + (item.by || 'آخر') + (item.at ? ' الساعة ' + item.at : '') + ' — أعِد الاختيار');
    });
    if (draft[col]) {
      (data.saved || []).forEach(function (item) { delete draft[col][item.student]; });
      if (!Object.keys(draft[col]).length) delete draft[col];
      writeDraft(draft);
    }
    var conflicts = (data.conflicts || []).length;
    var saved = (data.saved || []).length;
    if (conflicts) {
      notify('حُفظ ' + saved + ' وتعارض ' + conflicts + ' — راجع الخلايا المعلَّمة بالأحمر وأعِد الاختيار.', 'warning');
    } else if ((data.errors || []).length) {
      notify('حُفظ ' + saved + ' وتعذّر ' + data.errors.length + ' — أعِد المحاولة.', 'warning');
    } else {
      notify('تمّ الحفظ ✓ — ح' + col + ': ' + saved + ' خليّة' + (data.defaults ? ' (منها ' + data.defaults + ' حاضرٌ افتراضيّ)' : '') + '.', 'success');
    }
  }

  // يبدّل صفَّ الطالب وحدَه من الخادم بلا إعادة تحميل الصفحة (لا رمشَ ولا ضياعَ لمسوّدة بقيّة الصفوف).
  function refreshRow(student) {
    fetch(window.location.href, { credentials: 'same-origin' })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, 'text/html');
        var fresh = doc.querySelector('tr[data-student="' + student + '"]');
        var old = root.querySelector('tr[data-student="' + student + '"]');
        if (fresh && old) {
          var node = document.importNode(fresh, true);
          old.replaceWith(node);
          restoreDraft(node);
          tick();
          showTab(activeCol);
        } else window.location.reload();
      }).catch(function () { window.location.reload(); });
  }

  // عدّادُ الخروج: دقائقُ وثوانٍ من لحظة الضغط حتى «عاد» (الزمنُ من الخادم لا ساعةِ الجهاز وحدَها).
  var skew = Number(root.getAttribute('data-now')) - Date.now() / 1000;
  function elapsed(sinceSec) {
    var secs = Math.max(0, Math.floor(Date.now() / 1000 + skew - sinceSec));
    var m = Math.floor(secs / 60), r = secs % 60;
    return (m < 10 ? '0' : '') + m + ':' + (r < 10 ? '0' : '') + r;
  }
  function tick() {
    root.querySelectorAll('[data-out-since]').forEach(function (t) {
      t.textContent = elapsed(Number(t.getAttribute('data-out-since')));
    });
  }
  tick();
  window.setInterval(tick, 1000);

  // يبدّل جسمَ الجدول (الصفوفَ والتذييل) من الخادم بلا إعادة تحميل الصفحة.
  function refreshTable() {
    fetch(window.location.href, { credentials: 'same-origin' })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, 'text/html');
        var fresh = doc.querySelector('.cg-wrap');
        var old = root.querySelector('.cg-wrap');
        if (fresh && old) {
          var wrap = document.importNode(fresh, true);
          old.replaceWith(wrap);
          restoreDraft(wrap);
          tick();
          showTab(activeCol);
        } else window.location.reload();
      }).catch(function () { window.location.reload(); });
  }

  function markLate(button) {
    var body = new URLSearchParams();
    body.append('student', button.getAttribute('data-late'));
    body.append('csrfmiddlewaretoken', csrf());
    fetch(lateUrl, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf() }, body: body })
      .then(function (response) { return response.json().then(function (d) { return { status: response.status, data: d }; }); })
      .then(function (result) {
        if (result.status === 403) { notify((result.data && result.data.message) || 'تعذّر تسجيلُ التأخّر', 'danger'); return; }
        notify('سُجّل التأخّر ✓', 'success');
        refreshRow(button.getAttribute('data-late'));
      }).catch(function () { notify('تعذّر تسجيلُ التأخّر.', 'danger'); });
  }

  // «خرج من الفصل» (بوجهةٍ من القائمة) و«عاد» — تُنسب إلى الحصّة الجارية وقتَ الضغط، والخادمُ هو الحَكَم.
  function exitAction(student, action) {
    var body = new URLSearchParams();
    body.append('student', student);
    body.append('action', action);
    var select = root.querySelector('[data-exit-dest="' + student + '"]');
    if (select) body.append('destination', select.value);
    body.append('csrfmiddlewaretoken', csrf());
    fetch(exitUrl, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf() }, body: body })
      .then(function (response) { return response.json().then(function (d) { return { status: response.status, data: d }; }); })
      .then(function (result) {
        if (result.status === 403) { notify((result.data && result.data.message) || 'تعذّر تسجيلُ الخروج', 'danger'); return; }
        var timer = root.querySelector('tr[data-student="' + student + '"] [data-out-since]');
        var took = timer ? ' — غاب ' + timer.textContent : '';
        notify(action === 'return' ? 'سُجّلت العودة ✓' + took : 'سُجّل الخروج ✓', 'success');
        refreshRow(student);
      }).catch(function () { notify('تعذّر تسجيلُ الخروج.', 'danger'); });
  }

  function openHistory(student, col) {
    var dialog = root.querySelector('[data-history-dialog]');
    var holder = root.querySelector('[data-history-body]');
    if (!dialog || !holder) return;
    var url = saveUrl.replace(/save\/$/, 'history/') + student + '/' + col + '/';
    fetch(url, { credentials: 'same-origin' }).then(function (r) { return r.text(); }).then(function (html) {
      holder.innerHTML = html;
      if (typeof dialog.showModal === 'function') dialog.showModal();
    });
  }

  // وضعُ الهاتف: عمودٌ واحدٌ بتبويب ح1–ح7 وإجراءاتُ الصفّ في ورقةٍ سفليّة وشريطُ مفاتيح. **عتبتُه في CSS وحدَها**
  // (`--cg-narrow` على الجذر داخل استعلام الوسائط الوحيد في 33-modules-4.css) فلا يختلف العرضُ عن السلوك؛ ويُعاد التقييمُ عند تدوير الشاشة.
  function isNarrow() {
    return window.getComputedStyle(root).getPropertyValue('--cg-narrow').trim() === '1';
  }

  // الورقةُ السفليّة: حوارٌ أصليٌّ (`showModal`) يحبس التركيزَ ويغلقه Esc؛ وعلى الحاسوب يُرسم مضمَّناً فلا يُفتح قطّ.
  function openSheet(student) {
    var sheet = root.querySelector('dialog[data-acts-sheet="' + student + '"]');
    if (!sheet || !isNarrow() || typeof sheet.showModal !== 'function' || sheet.open) return;
    sheet.setAttribute('role', 'dialog');
    sheet.showModal();
  }
  function closeSheets() {
    root.querySelectorAll('dialog[data-acts-sheet][open]').forEach(function (sheet) { sheet.close(); });
  }
  // الحدثُ `close` لا يفور: نلتقطه في طور الالتقاط ليعود الدورُ «مجموعةً» على الحاسوب عند الإغلاق بأيّ طريق (Esc أو زرّ).
  root.addEventListener('close', function (event) {
    if (event.target.matches && event.target.matches('dialog[data-acts-sheet]')) event.target.setAttribute('role', 'group');
  }, true);

  var activeCol = '';
  function showTab(col) {
    activeCol = col;
    var narrow = isNarrow();
    root.querySelectorAll('[data-tab]').forEach(function (tab) {
      var on = tab.getAttribute('data-tab') === col;
      tab.classList.toggle('btn-primary', on);
      tab.classList.toggle('btn-secondary', !on);
      tab.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    var tabs = root.querySelector('[data-tabs]');
    if (tabs) tabs.hidden = !narrow;
    root.querySelectorAll('th[data-col], td[data-col]').forEach(function (cell) {
      cell.hidden = narrow && cell.getAttribute('data-col') !== col;
    });
    if (!narrow) closeSheets();
    syncKeybar(col);
  }

  // شريطُ المفاتيح يحمل أزرارَ العمود المعروض: يأخذ حالةَ التعطيل وسببَه من مفاتيح التذييل لذلك العمود (مصدرٌ واحدٌ للقاعدة).
  function syncKeybar(col) {
    var bar = root.querySelector('[data-keybar]');
    if (!bar) return;
    var label = bar.querySelector('[data-keybar-col]');
    if (label) label.textContent = col;
    bar.querySelectorAll('[data-bulk], [data-save-col]').forEach(function (button) {
      var isSave = button.hasAttribute('data-save-col');
      var source = root.querySelector(isSave
        ? 'tfoot [data-save-col="' + col + '"]'
        : 'tfoot [data-bulk="' + button.getAttribute('data-bulk') + '"][data-col="' + col + '"]');
      if (isSave) button.setAttribute('data-save-col', col); else button.setAttribute('data-col', col);
      button.disabled = !source || source.disabled;
      if (source && source.getAttribute('title')) button.setAttribute('title', source.getAttribute('title'));
      else button.removeAttribute('title');
    });
  }

  var resizeTimer = 0;
  function onResize() {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(function () { showTab(activeCol); }, 120);
  }
  window.addEventListener('resize', onResize);
  window.addEventListener('orientationchange', onResize);
  showTab(currentCol());
})();
