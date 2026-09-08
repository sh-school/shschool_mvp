/* schedule-matrix.js — طبقةُ التفاعل على «الجدول العام للمعلمين».
 *
 * تعيش داخل ورقةِ الطباعة نفسِها حين تُعرض في إطار المنصّة (`?embed=1`)،
 * ولا تُحمَّل في الطباعة ولا في تصدير PDF/Excel — فالورقةُ المطبوعةُ لا
 * ترى منها محرفاً.
 *
 * قراءةٌ فقط: إضاءةٌ وتثبيتٌ وبطاقاتُ تفصيل. لا تكتب في قاعدة البيانات،
 * ولا ترسل طلباً إلى الخادم — كلُّ ما تعرضه محسوبٌ من الورقة الحاضرة.
 *
 * وأربعةُ آلافِ خانةٍ لا تحتمل مستمعاً لكلِّ واحدةٍ منها: الأحداثُ مفوَّضةٌ
 * على الجدول، والإضاءةُ العموديّةُ سمةٌ واحدةٌ عليه يتولّى النمطُ أثرَها —
 * فلا لمسَ لعُقدٍ في حلقة.
 */
(function () {
  'use strict';

  var table = document.querySelector('.schedule-matrix');
  if (!table || !table.tBodies.length) return;

  var tbody = table.tBodies[0];
  var rows = Array.prototype.slice.call(tbody.rows);
  var dayNames = Array.prototype.map.call(
    table.querySelectorAll('thead .m-day'),
    function (th) { return th.textContent.trim(); }
  );
  var COLS = dayNames.length * 7;

  /* ── أدواتٌ صغيرة ── */
  function cellsOf(tr) { return tr.querySelectorAll('td.m-cell'); }

  function codesOf(td) {
    var v = td.getAttribute('data-c');
    return v ? v.split(/\s+/) : [];
  }

  function colLabel(col) {
    return (dayNames[Math.floor(col / 7)] || '') + ' — الحصّة ' + ((col % 7) + 1);
  }

  function esc(t) {
    return String(t).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  /* ── من يفرُغ في هذا العمود؟ ──
     تُحسب مرّةً واحدةً عند أوّل سؤال، لا في كلِّ مرور. */
  var freeByCol = null;

  function freeTeachers(col) {
    if (!freeByCol) {
      freeByCol = [];
      for (var c = 0; c < COLS; c++) freeByCol.push([]);
      rows.forEach(function (tr) {
        var name = tr.getAttribute('data-teacher');
        if (!name) return;
        Array.prototype.forEach.call(cellsOf(tr), function (td) {
          if (td.hasAttribute('data-c')) return;
          var i = +td.getAttribute('data-col');
          if (freeByCol[i]) freeByCol[i].push(name);
        });
      });
    }
    return freeByCol[col] || [];
  }

  /* ── البطاقة ومنادي الوصوليّة ── */
  var tip = document.createElement('div');
  tip.className = 'mx-tip';
  document.body.appendChild(tip);

  var live = document.createElement('div');
  live.className = 'mx-sr';
  live.setAttribute('aria-live', 'polite');
  document.body.appendChild(live);

  var tipTimer = null;

  function hideTip() {
    if (tipTimer) { clearTimeout(tipTimer); tipTimer = null; }
    tip.classList.remove('is-on');
  }

  function placeTip(x, y) {
    var r = tip.getBoundingClientRect();
    var left = x + 16;
    var top = y + 16;
    if (left + r.width > window.innerWidth - 8) left = x - r.width - 16;
    if (left < 8) left = 8;
    if (top + r.height > window.innerHeight - 8) top = y - r.height - 16;
    if (top < 8) top = 8;
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  }

  function showTip(html, x, y, speak) {
    tip.innerHTML = html;
    placeTip(x, y);
    if (tipTimer) clearTimeout(tipTimer);
    tipTimer = setTimeout(function () { tip.classList.add('is-on'); }, 120);
    if (speak) live.textContent = speak;
  }

  /* بطاقةُ الخانة: حصّةٌ بتفصيلها، أو فراغٌ بمن يفرُغ معه. */
  function cellTip(td) {
    var tr = td.parentNode;
    var teacher = tr.getAttribute('data-teacher') || '';
    var col = +td.getAttribute('data-col');
    var spec = tr.getAttribute('data-specialty') || '';
    var head =
      '<div class="t-head">' + esc(teacher) +
      (spec ? ' <span class="t-spec">(' + esc(spec) + ')</span>' : '') + '</div>';
    var when = '<span class="t-line t-muted">' + esc(colLabel(col)) + '</span>';

    if (td.hasAttribute('data-c')) {
      var detail = (td.getAttribute('data-s') || '').split(' · ');
      var body = detail.map(function (d) {
        return '<span class="t-line">' + esc(d) + '</span>';
      }).join('');
      return {
        html: head + when + body,
        speak: teacher + '، ' + colLabel(col) + '، ' + detail.join('، ')
      };
    }

    var others = freeTeachers(col).filter(function (n) { return n !== teacher; });
    var line;
    if (!others.length) {
      line = '<span class="t-line t-none">لا معلّم آخر فارغ في هذه الحصّة</span>';
    } else {
      var show = others.slice(0, 8);
      line =
        '<span class="t-line t-free">فارغون معه: ' + others.length + '</span>' +
        '<span class="t-line t-muted">' + esc(show.join(' · ')) +
        (others.length > show.length ? ' …' : '') + '</span>';
    }
    return {
      html: head + when + '<span class="t-line">فراغ</span>' + line,
      speak: teacher + '، ' + colLabel(col) + '، فراغ، وفارغون معه ' + others.length
    };
  }

  function post(msg) {
    if (window.parent && window.parent !== window) {
      window.parent.postMessage(msg, window.location.origin);
    }
  }

  /* ── التثبيت ── */
  var pinned = null;      // رمزُ الشعبة المثبَّتة
  var pinnedRow = null;   // صفُّ المعلّم المثبَّت

  function clearPins() {
    if (pinned) {
      Array.prototype.forEach.call(tbody.querySelectorAll('td.is-pin'), function (td) {
        td.classList.remove('is-pin');
      });
      pinned = null;
    }
    if (pinnedRow) { pinnedRow.classList.remove('is-pin-row'); pinnedRow = null; }
    table.classList.remove('has-pin');
    syncHint();
    post({ type: 'schedule:clear' });
  }

  function pinClass(code) {
    var was = pinned;
    clearPins();
    if (was === code) return;
    var n = 0;
    rows.forEach(function (tr) {
      Array.prototype.forEach.call(cellsOf(tr), function (td) {
        if (codesOf(td).indexOf(code) !== -1) { td.classList.add('is-pin'); n++; }
      });
    });
    if (!n) return;
    pinned = code;
    table.classList.add('has-pin');
    live.textContent = 'ثُبِّتت الشعبة ' + code + ' — ' + n + ' حصّة';
    syncHint();
  }

  /* لوحُ المعلّم: يُحسب هنا ويُرسَل إلى الصفحة الحاضنة.
     الفراغُ فراغٌ بين حصّتين في اليوم — لا الفراغُ قبل أوّلها ولا بعد آخرها. */
  function teacherReport(tr) {
    var cells = cellsOf(tr);
    var days = [];
    var gaps = 0;
    var longest = 0;
    for (var d = 0; d < dayNames.length; d++) {
      var busy = [];
      var run = 0;
      for (var p = 0; p < 7; p++) {
        var td = cells[d * 7 + p];
        if (td && td.hasAttribute('data-c')) {
          busy.push(p + 1);
          run++;
          if (run > longest) longest = run;
        } else {
          run = 0;
        }
      }
      days.push({ name: dayNames[d], count: busy.length, periods: busy });
      if (busy.length > 1) gaps += (busy[busy.length - 1] - busy[0] + 1) - busy.length;
    }
    return {
      type: 'schedule:teacher',
      name: tr.getAttribute('data-teacher') || '',
      specialty: tr.getAttribute('data-specialty') || '',
      dept: tr.getAttribute('data-dept') || '',
      total: +(tr.getAttribute('data-total') || 0),
      days: days,
      gaps: gaps,
      longest: longest
    };
  }

  function pinTeacher(tr) {
    var was = pinnedRow;
    clearPins();
    if (was === tr) return;
    pinnedRow = tr;
    tr.classList.add('is-pin-row');
    table.classList.add('has-pin');
    post(teacherReport(tr));
    live.textContent = 'جدول ' + (tr.getAttribute('data-teacher') || '');
    syncHint();
  }

  /* ── البحث: غيرُ المطابق يخفت ولا يختفي، فالسطرُ يبقى في موضعه ── */
  function applyFilter(q) {
    q = (q || '').trim();
    if (!q) {
      rows.forEach(function (tr) { tr.classList.remove('is-dim'); });
      return;
    }
    var needle = q.toLowerCase();
    var hits = 0;
    rows.forEach(function (tr) {
      var hay = (tr.getAttribute('data-teacher') || '') + ' ' + (tr.getAttribute('data-dept') || '');
      var ok = hay.toLowerCase().indexOf(needle) !== -1;
      tr.classList.toggle('is-dim', !ok);
      if (ok) hits++;
    });
    // لا معلّمَ بهذا الاسم — فلعلّه رمزُ شعبة، وهو أولى بالتثبيت من لا شيء.
    if (!hits) {
      rows.forEach(function (tr) { tr.classList.remove('is-dim'); });
      pinClass(q.toUpperCase());
    }
  }

  /* ── شريطُ الإرشاد ── */
  var hint = document.createElement('div');
  hint.className = 'mx-hint';
  hint.innerHTML =
    '<span><b>مرور</b> يُضيء الصفَّ والعمود</span>' +
    '<span><b>نقر على خانة</b> يثبّت الشعبة عبر الجدول</span>' +
    '<span><b>نقر على اسم</b> يفتح لوح المعلّم</span>' +
    '<span><b>الأسهم</b> تنقّل · <b>Esc</b> تفكّ</span>' +
    '<button type="button" class="mx-clear" hidden>فكّ التثبيت (Esc)</button>';
  var wrap = document.querySelector('.matrix-wrap');
  if (wrap && wrap.parentNode) wrap.parentNode.insertBefore(hint, wrap);
  var clearBtn = hint.querySelector('.mx-clear');
  clearBtn.addEventListener('click', clearPins);

  function syncHint() { clearBtn.hidden = !(pinned || pinnedRow); }

  /* ── الأحداث: مفوَّضةٌ على الجدول ── */
  table.addEventListener('mouseover', function (e) {
    var td = e.target.closest ? e.target.closest('td') : null;
    if (!td || !table.contains(td)) return;

    if (td.hasAttribute('data-col')) {
      table.setAttribute('data-hl-col', td.getAttribute('data-col'));
    } else {
      table.removeAttribute('data-hl-col');
    }

    if (td.classList.contains('m-cell') && td.parentNode.hasAttribute('data-teacher')) {
      var t = cellTip(td);
      showTip(t.html, e.clientX, e.clientY, t.speak);
    } else {
      hideTip();
    }
  });

  table.addEventListener('mousemove', function (e) {
    if (tip.classList.contains('is-on')) placeTip(e.clientX, e.clientY);
  });

  table.addEventListener('mouseleave', function () {
    table.removeAttribute('data-hl-col');
    hideTip();
  });

  table.addEventListener('click', function (e) {
    var td = e.target.closest ? e.target.closest('td') : null;
    if (!td) return;
    var tr = td.parentNode;
    if (!tr.hasAttribute('data-teacher')) return;

    if (td.classList.contains('m-name') || td.classList.contains('m-total')) {
      pinTeacher(tr);
      return;
    }
    if (td.classList.contains('m-cell')) {
      var codes = codesOf(td);
      if (codes.length) pinClass(codes[0]);
      else clearPins();
    }
  });

  /* ── لوحةُ المفاتيح: تركيزٌ متجوّلٌ لا أربعةُ آلافِ محطّة ── */
  var focused = null;

  function focusCell(tr, col) {
    var td = cellsOf(tr)[col];
    if (!td) return;
    if (focused) {
      focused.classList.remove('is-focus');
      focused.removeAttribute('tabindex');
    }
    focused = td;
    td.classList.add('is-focus');
    td.setAttribute('tabindex', '-1');
    td.focus();
    table.setAttribute('data-hl-col', String(col));
    var t = cellTip(td);
    var r = td.getBoundingClientRect();
    showTip(t.html, r.left + r.width / 2, r.bottom, t.speak);
  }

  table.setAttribute('tabindex', '0');
  table.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { clearPins(); hideTip(); return; }
    if (['ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown', 'Enter', ' '].indexOf(e.key) === -1) return;

    var td = focused;
    if (!td) { focusCell(rows[0], 0); e.preventDefault(); return; }

    var tr = td.parentNode;
    var col = +td.getAttribute('data-col');
    var idx = rows.indexOf(tr);

    if (e.key === 'Enter' || e.key === ' ') {
      var codes = codesOf(td);
      if (codes.length) pinClass(codes[0]); else pinTeacher(tr);
      e.preventDefault();
      return;
    }
    // الجدولُ من اليمين إلى اليسار: السهمُ الأيسر يتقدّم في الأسبوع.
    if (e.key === 'ArrowLeft') col = Math.min(COLS - 1, col + 1);
    if (e.key === 'ArrowRight') col = Math.max(0, col - 1);
    if (e.key === 'ArrowUp') idx = Math.max(0, idx - 1);
    if (e.key === 'ArrowDown') idx = Math.min(rows.length - 1, idx + 1);
    focusCell(rows[idx], col);
    e.preventDefault();
  });

  /* ── أوامرُ الصفحة الحاضنة ── */
  window.addEventListener('message', function (e) {
    if (e.origin !== window.location.origin || !e.data) return;
    if (e.data.type === 'schedule:filter') applyFilter(e.data.q);
    if (e.data.type === 'schedule:clear') clearPins();
  });

  post({ type: 'schedule:ready' });
})();
