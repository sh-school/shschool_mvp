/**
 * كشفُ الحصص — «الكلُّ حاضر» و«غيابُ الكلّ»، والحفظُ الفوريُّ في الهاتف.
 *
 * كلُّ ضغطةٍ تُحفظ في `localStorage` بمفتاح الشعبة واليوم والحصّة، فانقطاعُ
 * الشبكة في الممرّ أو رنينُ الهاتف لا يمحو ما رُصد. وتُمسح المسوّدةُ عند
 * الإرسال. والتخزينُ قد يُمنع (نافذةٌ خاصّة) — فكلُّ قراءةٍ وكتابةٍ في try.
 *
 * والمفتاحُ يحمل بصمةَ ما جاء من المعلّم (خروجٌ ونقرات): نقرةٌ جديدةٌ بعد المسوّدة
 * تُبدّل المفتاح، فلا تُعيد مسوّدةٌ قديمةٌ «حاضراً» فوق خانةٍ مُلئت بعدها.
 */
(function () {
  'use strict';

  var form = document.querySelector('form[data-draft-key]');
  if (!form) return;
  var key = form.getAttribute('data-draft-key');

  function read() {
    try { return JSON.parse(window.localStorage.getItem(key) || 'null'); } catch (e) { return null; }
  }
  function write(data) {
    try { window.localStorage.setItem(key, JSON.stringify(data)); } catch (e) { /* لا تخزين */ }
  }
  function clear() {
    try { window.localStorage.removeItem(key); } catch (e) { /* لا تخزين */ }
  }

  // «خروج» (الشبكة): نافذةٌ عائمةٌ تكتب في قائمة «أين الطالب» نفسِها، فلا حقلَ جديدَ في الإرسال.
  // اختيارُ وجهةٍ يجعل الطالبَ غائباً؛ والرجوعُ إلى حاضر/متأخّر يمحو وجهتَه.
  function exitCells() { return form.querySelectorAll('td.per-cell.is-focus'); }
  function syncExit(cell) {
    var select = cell.querySelector('select.per-where');
    var label = cell.querySelector('[data-exit-label]');
    var button = cell.querySelector('[data-exit-open]');
    if (!select || !label || !button) return;
    var option = select.options[select.selectedIndex];
    var set = !!select.value;
    // المعلّم (data-exit-url): الزرُّ يبقى «خروج» ويحمرّ فقط — اسمُ الوجهة الطويلُ يغطّي أزرارَ الحالة في البطاقة الضيّقة.
    label.textContent = set && !exitUrl ? option.textContent : 'خروج';
    button.classList.toggle('is-set', set);
    if (exitUrl) button.title = set ? 'خرج: ' + option.textContent : 'خروجُ الطالب — أين هو؟';
  }
  function closeExit() {
    exitCells().forEach(function (cell) {
      cell.classList.remove('is-exit-open', 'is-min-open');
      var button = cell.querySelector('[data-exit-open]');
      if (button) button.setAttribute('aria-expanded', 'false');
    });
  }
  var exitUrl = form.getAttribute('data-exit-url');
  var returnUrl = form.getAttribute('data-return-url');
  function sendExit(cell, destination) {
    var row = cell.closest('tr');
    var token = form.querySelector('input[name=csrfmiddlewaretoken]');
    if (!row || !token) return;
    var body = new FormData();
    body.append('csrfmiddlewaretoken', token.value);
    body.append('student_id', row.getAttribute('data-student'));
    if (destination) body.append('destination', destination);
    if (destination) {
      row.setAttribute('data-out-since', String(nowSec()));
      row.setAttribute('data-exit-open-at', String(nowSec()));
      row.setAttribute('data-exit-count', String((parseInt(row.getAttribute('data-exit-count'), 10) || 0) + 1));
    } else {
      var openAt = parseInt(row.getAttribute('data-exit-open-at'), 10);
      if (openAt) row.setAttribute('data-exit-base', String((parseInt(row.getAttribute('data-exit-base'), 10) || 0) + Math.max(0, nowSec() - openAt)));
      row.removeAttribute('data-exit-open-at');
      row.removeAttribute('data-out-since');
      row.querySelectorAll('select.per-where option').forEach(function (o) { o.textContent = o.getAttribute('data-base') || o.textContent; });
    }
    syncExclusive(row);
    fetch(destination ? exitUrl : returnUrl, { method: 'POST', body: body, credentials: 'same-origin' }).then(function (response) {
      if (!response.ok && window.showToast) window.showToast('تعذّر تسجيلُ الخروج (' + response.status + ')', 'danger');
    });
  }
  exitCells().forEach(function (cell) {
    var button = cell.querySelector('[data-exit-open]');
    if (!button) return;
    button.addEventListener('click', function (event) {
      event.stopPropagation();
      var outRow = exitUrl ? cell.closest('tr[data-out-since]') : null;
      if (outRow) {  // المعلّم: الضغطةُ التالية على من هو خارجٌ تُنهي خروجَه ويعود المفتاحُ «خروج»
        cell.querySelector('select.per-where').value = '';
        sendExit(cell, '');
        syncExit(cell);
        closeExit();
        write(snapshot());
        return;
      }
      var open = !cell.classList.contains('is-exit-open');
      closeExit();
      cell.classList.toggle('is-exit-open', open);
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    cell.querySelectorAll('[data-where]').forEach(function (option) {
      option.addEventListener('click', function () {
        var select = cell.querySelector('select.per-where');
        var value = option.getAttribute('data-where');
        select.value = value;
        // المشرفُ: وجهةٌ تجعل الطالبَ غائباً. المعلّم (data-exit-url): الخروجُ بإذنه ليس غياباً — يبقى حالُه ويُسجَّل الخروجُ/العودةُ فوراً بلحظتهما.
        if (exitUrl) {
          sendExit(cell, value);
        } else if (value) {
          var absent = cell.querySelector('input[type=radio][value="absent"]');
          if (absent && !absent.checked) { absent.checked = true; absent.dispatchEvent(new Event('change', { bubbles: true })); }
        }
        syncExit(cell);
        closeExit();
        write(snapshot());
        count();
      });
    });
  });
  // الجدولُ (المعلّم): قائمةُ «أين الطالب» ظاهرةٌ دائماً وتسجّل الخروجَ/العودةَ فوراً عند تغيّرها كما تفعل نافذةُ الشبكة.
  if (exitUrl) {
    form.querySelectorAll('select.per-where').forEach(function (select) {
      select.addEventListener('change', function () {
        var cell = select.closest('td.per-cell.is-focus');
        if (cell) { sendExit(cell, select.value); syncExit(cell); }
      });
    });
  }
  // نافذةُ دقائق التأخّر (الشبكة، خارجَ وقت الحصّة): تُفتح عند الضغط على «متأخّر» لهذه البطاقة
  // وحدَها، وتُغلق بالضغط عليه ثانيةً أو بمفتاحٍ آخر في البطاقة أو بالنقر خارجها أو Enter/Esc —
  // فلا تبقى مفتوحةً على كلّ متأخّر.
  form.addEventListener('click', function (event) {
    var radio = event.target;
    if (!radio || radio.type !== 'radio') return;
    var cell = radio.closest('td.per-cell.is-focus');
    if (!cell || !cell.querySelector('.per-minutes')) return;
    var wasOpen = cell.classList.contains('is-min-open');
    closeExit();
    if (radio.value === 'late' && !wasOpen) {
      cell.classList.add('is-min-open');
      var box = cell.querySelector('.per-minutes');
      if (box) box.focus();
    }
  });
  form.addEventListener('keydown', function (event) {
    if (event.key === 'Enter' && event.target.classList && event.target.classList.contains('per-minutes')) {
      event.preventDefault();
      closeExit();
    }
  });
  document.addEventListener('click', function (event) {
    var t = event.target;
    if (!t.closest) return;
    if (t.closest('[data-exit-pop]') || t.closest('.per-minutes') || t.closest('.rec-pick')) return;
    closeExit();
  });
  document.addEventListener('keydown', function (event) { if (event.key === 'Escape') closeExit(); });

  function snapshot() {
    var data = {};
    form.querySelectorAll('input[type=radio]:checked, select, input[type=number], input[type=hidden][name^="t-"]').forEach(function (el) {
      data[el.name] = el.value;
    });
    return data;
  }

  function restore(data) {
    Object.keys(data).forEach(function (name) {
      var value = data[name];
      var radio = form.querySelector('input[type=radio][name="' + name + '"][value="' + value + '"]');
      if (radio) { radio.checked = true; return; }
      var field = form.querySelector('[name="' + name + '"]');
      if (field && field.type !== 'radio') field.value = value;
    });
  }

  // العدّادُ في شريط التثبيت: كم حاضراً وغائباً ومتأخّراً في الحصّة المفتوحة الآن.
  function count() {
    ['present', 'absent', 'late'].forEach(function (value) {
      var slot = form.querySelector('[data-count="' + value + '"]');
      if (slot) slot.textContent = form.querySelectorAll('input[type=radio][value="' + value + '"]:checked').length;
    });
  }

  // ساعةُ الخادم لا ساعةُ الهاتف: فهاتفٌ متأخّرٌ دقيقتين لا يُري وقتاً غيرَ الذي يُحفظ. يُحسب الفرقُ مرّةً عند التحميل.
  var skew = (parseInt(form.getAttribute('data-now'), 10) * 1000 || Date.now()) - Date.now();
  function two(n) { return (n < 10 ? '0' : '') + n; }

  // ── المعلّم (data-exit-url) ──────────────────────────────────────────────────────────────
  // (١) «غائب» و«خروج» لا يجتمعان على طالبٍ واحد؛ (٢) عدّادُ الخروج من لحظة الضغط إلى «عاد إلى الفصل»؛
  // (٣) «متأخّر» يُسجَّل وقتُ دخوله فوراً وتُحسب دقائقُه من بدء الحصّة آلياً ويُحفظ (الخادمُ يعيد الحساب بساعته).
  var entryUrl = form.getAttribute('data-entry-url');
  var startEpoch = parseInt(form.getAttribute('data-start-epoch'), 10) || 0;
  function nowSec() { return Math.floor((Date.now() + skew) / 1000); }
  function csrf() { var t = form.querySelector('input[name=csrfmiddlewaretoken]'); return t ? t.value : ''; }
  function stopwatch(seconds) {
    var m = Math.floor(seconds / 60);
    var h = Math.floor(m / 60);
    return (h ? h + ':' + two(m % 60) : two(m)) + ':' + two(seconds % 60);
  }
  function syncExclusive(row) {
    var select = row.querySelector('select.per-where');
    var absent = row.querySelector('input[type=radio][value="absent"]');
    var button = row.querySelector('[data-exit-open]');
    var out = !!(select && select.value);
    if (out && absent && absent.checked) {
      var present = row.querySelector('input[type=radio][value="present"]');
      if (present) present.checked = true;
    }
    var isAbsent = !!(absent && absent.checked);
    if (absent) absent.disabled = out || absent.hasAttribute('data-keep');
    if (button) button.disabled = isAbsent || button.hasAttribute('data-keep');
    if (select) select.disabled = isAbsent || select.hasAttribute('data-keep');
  }
  function outTick() {
    form.querySelectorAll('tr[data-out-since]').forEach(function (row) {
      // العدّادُ متّصلٌ من لحظة الضغط (أو من أصل الخروج المرحَّل) إلى العودة؛ وإن لم يعد انتقل مع الطالب إلى الحصص التالية
      // حتى نهاية اليوم (الخادمُ يُرحّله بسطرٍ جديدٍ في كلّ حصّة، فيبقى `data-out-since` أصلَه).
      var since = parseInt(row.getAttribute('data-out-since'), 10);
      var now = nowSec();
      var text = stopwatch(Math.max(0, now - since));
      var openAt = parseInt(row.getAttribute('data-exit-open-at'), 10);
      var button = row.querySelector('[data-exit-open]');
      if (button && openAt) {
        var total = (parseInt(row.getAttribute('data-exit-base'), 10) || 0) + Math.max(0, now - openAt);
        button.title = 'خرج ' + (row.getAttribute('data-exit-count') || '1') + ' مرّة اليوم · المجموع ' + stopwatch(total);
      }
      var label = row.querySelector('[data-exit-label]');
      if (label) label.textContent = text;
      var select = row.querySelector('select.per-where');
      var option = select && select.selectedIndex >= 0 ? select.options[select.selectedIndex] : null;
      if (option && option.value) option.textContent = (option.getAttribute('data-base') || option.textContent) + ' · ' + text;
    });
  }
  function saveLate(radio) {
    var sid = radio.name.slice(2);
    var field = form.querySelector('[name="t-' + sid + '"]');
    var tapped = field && field.value ? parseInt(field.value, 10) : nowSec();
    var span = radio.parentNode.querySelector('span');
    if (span) span.textContent = 'متأخّر ' + Math.max(0, Math.floor((tapped - startEpoch) / 60)) + ' د';
    var body = new FormData();
    body.append('csrfmiddlewaretoken', csrf());
    body.append('student_id', sid);
    body.append('status', 'late');
    body.append('tapped_at', String(tapped));
    fetch(entryUrl, { method: 'POST', body: body, credentials: 'same-origin' }).then(function (response) {
      if (!response.ok && window.showToast) window.showToast('تعذّر حفظُ التأخّر (' + response.status + ')', 'danger');
    });
  }
  function allRows() { return form.querySelectorAll('tr.rec-row'); }
  if (exitUrl) {
    form.querySelectorAll('input[type=radio][disabled], .rec-exit[disabled], select.per-where[disabled]').forEach(function (el) { el.setAttribute('data-keep', ''); });
    form.querySelectorAll('select.per-where option').forEach(function (option) { option.setAttribute('data-base', option.textContent); });
    allRows().forEach(syncExclusive);
    window.setInterval(outTick, 1000);
    outTick();
  }

  var draft = read();
  if (draft) restore(draft);
  exitCells().forEach(syncExit);
  if (exitUrl) allRows().forEach(syncExclusive);
  count();

  // لحظةُ النقرة على «متأخّر» تُحفظ بساعة الخادم: الدقائقُ منها لا من لحظة التثبيت.
  // والرجوعُ عن «متأخّر» يمحوها، والنقرةُ ثانيةً على المختار لا تُطلق change فلا تُغيّرها.
  form.addEventListener('change', function (event) {
    var radio = event.target;
    if (radio && radio.type === 'radio') {
      var tap = form.querySelector('[name="t-' + radio.name.slice(2) + '"]');
      if (tap) tap.value = radio.value === 'late' ? String(Math.floor((Date.now() + skew) / 1000)) : '';
      if (exitUrl) {
        var lateSpan = radio.closest('.rec-row__pick');
        lateSpan = lateSpan && lateSpan.querySelector('.rec-pick--late span');
        if (lateSpan && radio.value !== 'late') lateSpan.textContent = 'متأخّر';
        if (radio.value === 'late' && entryUrl && !radio.closest('td').querySelector('.per-minutes')) saveLate(radio);
        syncExclusive(radio.closest('tr'));
      }
    }
    // من رجع حاضراً أو متأخّراً لا وجهةَ له: تُمحى فلا تُحفظ وجهةٌ على غير غائب.
    if (!exitUrl && radio && radio.type === 'radio' && radio.value !== 'absent') {
      var where = form.querySelector('select[name="w-' + radio.name.slice(2) + '"]');
      if (where && where.value) { where.value = ''; syncExit(where.closest('td')); }
    }
    write(snapshot());
    count();
  });
  form.addEventListener('input', function () { write(snapshot()); });
  form.addEventListener('submit', clear);

  document.querySelectorAll('[data-bulk]').forEach(function (button) {
    button.addEventListener('click', function () {
      var value = button.getAttribute('data-bulk');
      // «الكلُّ حاضر» لا يمحو من خرج بإذن المعلّم ولم يعد: خانتُه تُبدَّل وحدَها.
      var keep = value === 'present' ? 'tr[data-prefill="out"]' : null;
      form.querySelectorAll('input[type=radio][value="' + value + '"]').forEach(function (radio) {
        if (keep && radio.closest(keep)) return;
        if (radio.disabled) return;
        radio.checked = true;
        // «الكلُّ حاضر» و«غيابُ الكلّ» لا متأخّرَ بعدهما — فلا لحظةَ نقرةٍ تبقى.
        var tap = form.querySelector('[name="t-' + radio.name.slice(2) + '"]');
        if (tap) tap.value = '';
        if (value !== 'absent' && !exitUrl) {
          var where = form.querySelector('select[name="w-' + radio.name.slice(2) + '"]');
          if (where && where.value) { where.value = ''; syncExit(where.closest('td')); }
        }
      });
      write(snapshot());
      count();
    });
  });
})();
