/* خارطة تجويد المنصّة — templates/roadmap/roadmap.html (لمطوّر المنصّة وحدَه).
   البياناتُ من json_script `#rm-data`، والتحريرُ يُحفظ في القاعدة عبر POST JSON إلى
   `data-item-url` و`data-decision-url` و`data-checklist-url` برمز CSRF في الترويسة.
   لا HTML خامّ من البيانات: كلُّ نصٍّ يدخل الصفحةَ بـtextContent. وحسابُ التقدّم مرآةُ
   roadmap/services.py::weighted_progress (الدالّةُ `pct` هنا).

   لا تمريرَ للصفحة ولا لأيّ بطاقة: كلُّ قائمةٍ تُملأ عنصراً عنصراً حتى يمتلئ ارتفاعُ حاويتها
   (`fit`) ثمّ تُقسَّم صفحاتٍ بأزرار السابق/التالي، فتتّسع لأيّ نافذةٍ من الجوال إلى الشاشة العريضة. */
(function () {
  'use strict';
  var root = document.getElementById('rm-root');
  var dataEl = document.getElementById('rm-data');
  if (!root || !dataEl) return;
  var D;
  try { D = JSON.parse(dataEl.textContent); } catch (e) { return; }

  var $ = function (s) { return root.querySelector(s); };
  function h(tag, attrs) {
    var e = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v == null || v === false) return;
        if (k === 'class') e.className = v;
        else if (k === 'text') e.textContent = v;
        else if (k === 'vars') Object.keys(v).forEach(function (n) { e.style.setProperty(n, v[n]); });
        else if (k.slice(0, 2) === 'on') e.addEventListener(k.slice(2), v);
        else e.setAttribute(k, v === true ? '' : v);
      });
    }
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c == null || c === false) continue;
      e.append(c.nodeType ? c : document.createTextNode(String(c)));
    }
    return e;
  }
  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }

  var S = {
    meta: D.meta || {}, items: D.items || [], kpis: D.kpis || [], decs: D.decisions || [],
    risks: D.risks || [], cks: D.checklist || [], tab: 'ov', lane: 'all', st: 'all', src: 'all',
    dc: 'all', kl: 'all', ru: 'rules', gview: 'mx', list: null, creating: false, drawer: null, focus: null
  };
  var TABS = ['ov', 'gt', 'kp', 'dc', 'rk', 'st', 'ru'];
  var ST = { todo: 'لم يبدأ', doing: 'قيد التنفيذ', done: 'مُغلَق', blocked: 'محجوب', deferred: 'مؤجّل' };
  var DS = { open: 'مفتوح', decided: 'محسوم', deferred: 'مؤجَّل' };
  var SRC = { DONE: 'منجز (أرشيف)', U: 'الخطّة الموحّدة', M: 'خطّة الجوال', VI: 'لوحة الهويّة', DBT: 'ديون', OWN: 'بنود المالك', PRP: 'مقترحات المنتج', NEW: 'مضافة من الواجهة' };
  var PILL = { ok: 'badge--success', warn: 'badge--warning', bad: 'badge--danger', idle: 'badge--neutral', accent: 'badge--accent' };
  var RULE_SECTIONS = [['rules', 'قواعد العمل'], ['dod', 'تعريف «تمّ» (DoD)'], ['crit', 'المسار الحرج'], ['win', 'نوافذ التنفيذ'],
    ['own', 'المسؤوليّات'], ['rbk', 'التراجع والفحص بعد النشر'], ['map', 'خريطة الترقيم القديم ← الجديد'], ['srcs', 'مصادر الخارطة'], ['upd', 'كيف تُحدَّث الخارطة']];
  var HOW_TO_UPDATE = [
    'الحالةُ والتقدّمُ والتواريخُ: من تبويب الخريطة الزمنيّة بالنقر على أيّ بند؛ التعديلُ يُحفظ فوراً في القاعدة ويُدقَّق.',
    'المؤشّراتُ الآليّة: شغِّل scripts/measure_identity_kpis.py ثمّ أعِد الاستيرادَ: manage.py import_roadmap_snapshot <path> (لا يمسّ ما عدّلتَه هنا من حالةٍ وتقدّمٍ وتواريخَ وملاحظاتٍ وتأشيراتِ فحص؛ يحدّث المؤشّراتِ والحقولَ البنيويّة، و`--overwrite` يعيد الكلَّ إلى اللقطة).',
    'بنودُ الخطّة الموحّدة: الحالةُ الأصليّةُ في الخطّة الموحّدة؛ هنا الجدولُ الزمنيّ فوقها. عند الاختلاف تُعدَّل هناك أوّلاً.',
    'لا يُغلَق بندٌ إلّا بدليل: رقمُ طلب دمجٍ أو مؤشّرٌ تحرّك.',
    'مراجعةٌ ربعيّة: إعادةُ السواط ذي الأبعاد الثمانية، ثمّ إعادةُ ضبط التواريخ المقترَحة.'
  ];
  var DAY = 86400000;

  function dt(s) { return s ? new Date(s + 'T00:00:00Z').getTime() : null; }
  var A0 = dt(S.meta.horizonStart) || dt('2026-09-21');
  // نهايةُ المحور من أفق الخارطة (شاملةً يومَها الأخير) لا من رقمٍ ثابت — وإلّا رُسمت بنودُ ما بعده شريحةً رفيعة وسقطت مراحلُه
  var A1 = (dt(S.meta.horizonEnd) ? dt(S.meta.horizonEnd) + DAY : A0 + 98 * DAY);
  var SPAN = (A1 - A0) / DAY;
  root.style.setProperty('--rm-weeks', String(SPAN / 7));
  function pos(t) { return Math.max(0, Math.min(100, (t - A0) / DAY / SPAN * 100)); }
  var TODAY = (function () { var n = new Date(); return Date.UTC(n.getFullYear(), n.getMonth(), n.getDate()); })();
  function dstr(t) { return t ? new Date(t).toISOString().slice(5, 10) : '–'; }
  function pc(n) { return n + '%'; }

  // ── الحساب (مرآةُ الخدمة) ───────────────────────────────────────────
  function weight(i) { return i.status === 'deferred' ? 0 : (Number(i.effort) || 1); }
  function pct(list) {
    var w = 0, s = 0;
    list.forEach(function (i) { var x = weight(i); w += x; s += x * (i.status === 'done' ? 100 : (Number(i.progress) || 0)); });
    return w ? Math.round(s / w) : 0;
  }
  function laneName(k) {
    var l = (S.meta.lanes || []).filter(function (x) { return x.key === k; })[0];
    return l ? l.name : k;
  }
  function calc(k) {
    if (k.current == null) return { st: 'idle', label: 'لم يُقَس', pct: null };
    if (k.target == null) return { st: 'idle', label: 'بلا هدف', pct: null };
    var base = k.baseline == null ? k.current : k.baseline;
    var span = k.dir === 'down' ? base - k.target : k.target - base;
    var gone = k.dir === 'down' ? base - k.current : k.current - base;
    var reached = k.dir === 'down' ? k.current <= k.target : k.current >= k.target;
    if (reached) return { st: 'ok', label: 'بلغ الهدف', pct: 100 };
    var p = span <= 0 ? 0 : Math.max(0, Math.min(100, Math.round(100 * gone / span)));
    return { st: p > 0 ? 'warn' : 'idle', label: p > 0 ? 'في الطريق' : 'عند الأساس', pct: p };
  }
  function fmt(v, u) {
    if (v == null) return '–';
    if (u === 'pct') return v + '%';
    if (u === 'kb') return v + ' KB';
    if (u === 'ms') return v + ' ms';
    if (u === 'hours') return v + ' س';
    if (u === 'min') return v + ' د';
    if (u === 'score') return Number(v).toFixed(1);
    return String(v);
  }
  function pill(kind, text) { return h('span', { class: 'rm-pill ' + PILL[kind], text: text }); }
  function meter(p) { return h('div', { class: 'rm-meter', vars: { '--rm-p': pc(p) } }, h('i')); }
  function bidi(text, cls) { return h('bdi', { class: cls || null, text: text }); }

  // ── التعبئةُ حتى الامتلاء ثمّ الترقيم ────────────────────────────────
  // M[key] = { host, pager, items: () => [], mk: (item, index) => node }
  var M = {};
  var PG = {};
  function mountScroll(key, items, mk) { mount(key, items, mk); M[key].scroll = true; }
  function mount(key, items, mk) { M[key] = { host: $('#rm-fit-' + key), pager: $('#rm-pg-' + key), items: items, mk: mk }; PG[key] = { start: 0, end: 0, stack: [], multi: false }; }
  function resetPg(key) { PG[key] = { start: 0, end: 0, stack: [], multi: false }; }
  // بطاقاتُ المؤشّرات والقرارات والمخاطر: تُمرَّر رأسيّاً داخل البطاقة نفسها (لا ترقيم)
  function renderScroll(key) {
    var m = M[key], items = m.items();
    clear(m.host);
    items.forEach(function (it, i) { m.host.append(m.mk(it, i)); });
    if (!items.length) m.host.append(h('div', { class: 'rm-empty', text: 'لا عناصرَ.' }));
    var sec = m.host.closest('.ui-section');
    var sub = sec && sec.querySelector('.card-bar-sub');
    var title = sec && sec.querySelector('.ui-section__title');
    if (sub && !sub.hasAttribute('data-static')) sub.textContent = items.length;
    m.host.setAttribute('tabindex', '0');
    m.host.setAttribute('role', 'region');
    m.host.setAttribute('aria-label', title ? title.textContent.trim() : key);
  }
  function fit(key, again) {
    var m = M[key], st = PG[key];
    if (m && m.scroll) { renderScroll(key); return; }
    if (!m || !m.host) return;
    if (!m.host.clientHeight) {
      // لوحةٌ مخفيّة: تُملأ عند إظهارها. أمّا الظاهرةُ بارتفاعٍ صفريّ فلا تُترك بيضاء بلا أثر: أوّلُ عنصرٍ على الأقلّ
      if (m.host.offsetParent !== null && !m.host.firstChild) {
        var first = m.items();
        m.host.append(first.length ? m.mk(first[0], 0) : h('div', { class: 'rm-empty', text: 'لا عناصرَ.' }));
      }
      return;
    }
    var items = m.items();
    if (st.start >= items.length) { st.start = 0; st.stack = []; }
    // ظهورُ شريط الترقيم يقتطع من ارتفاع الحاوية: نُثبّت حالتَه قبل التعبئة ونعيد مرّةً إن تغيّرت
    m.pager.hidden = !st.multi;
    if (st.multi && !m.pager.firstChild) m.pager.append(h('button', { type: 'button', class: 'btn-secondary btn-sm', text: 'السابق' })); // يحجز ارتفاعَ الأزرار قبل التعبئة
    clear(m.host);
    var i = st.start;
    while (i < items.length) {
      var node = m.mk(items[i], i);
      m.host.append(node);
      if (i > st.start && m.host.scrollHeight > m.host.clientHeight + 1) { m.host.removeChild(node); break; }
      i++;
    }
    st.end = i;
    var multi = st.start > 0 || st.end < items.length;
    if (multi !== !!st.multi && !again) { st.multi = multi; return fit(key, true); }
    if (!items.length) { clear(m.pager).hidden = true; m.host.append(h('div', { class: 'rm-empty', text: 'لا عناصرَ.' })); return; }
    function build() {
      var pg = clear(m.pager);
      pg.hidden = !multi;
      if (!multi) return;
      pg.append(
        h('button', { type: 'button', class: 'btn-secondary btn-sm', text: 'السابق', disabled: st.stack.length ? null : 'disabled', onclick: function () { st.start = st.stack.pop() || 0; fit(key); } }),
        h('span', { class: 'rm-pager__n', text: (st.start + 1) + '–' + st.end + ' من ' + items.length }),
        h('button', { type: 'button', class: 'btn-secondary btn-sm', text: 'التالي', disabled: st.end < items.length ? null : 'disabled', onclick: function () { st.stack.push(st.start); st.start = st.end; fit(key); } }));
    }
    build();
    // ارتفاعُ الشريط الفعليّ قد يزيد عمّا حجزناه: نقتطع ما فاض ونُعيد كتابة العدّاد
    var trimmed = false;
    while (m.host.children.length > 1 && m.host.scrollHeight > m.host.clientHeight + 1) { m.host.removeChild(m.host.lastChild); st.end--; trimmed = true; }
    if (trimmed) build();
  }
  var TAB_KEYS = {
    ov: ['lanes', 'next', 'phases'], gt: ['gantt'], kp: ['kpU', 'kpM', 'kpV'], dc: ['dcOpen', 'dcDone', 'dcDef'],
    rk: ['rkHigh', 'rkOther', 'cks'], st: ['stds'], ru: ['rules']
  };
  function fitTab() {
    if (S.tab === 'gt') { renderGanttView(); return; }
    (TAB_KEYS[S.tab] || []).forEach(fit);
  }

  // ── الحفظ ───────────────────────────────────────────────────────────
  function say(msg, isError) {
    var live = $('#rm-live');
    live.textContent = msg;
    live.classList.toggle('is-error', !!isError);
  }
  function post(url, code, body) {
    return fetch(url.replace('CODE', encodeURIComponent(code)), {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': root.dataset.csrf, 'X-Requested-With': 'XMLHttpRequest' },
      body: JSON.stringify(body)
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (j) { return { status: res.status, body: j }; });
    });
  }
  function failure(code, r) {
    if (r.status === 403) return 'لا صلاحيّةَ للكتابة (' + code + ')';
    if (r.status === 400 && r.body && r.body.fields) {
      return 'رُفض ' + code + ': ' + Object.keys(r.body.fields).map(function (k) { return k + ' — ' + r.body.fields[k]; }).join('؛ ');
    }
    return 'تعذّر الحفظ (' + code + ')';
  }
  function save(kind, code, body, field) {
    var url = root.dataset[kind + 'Url'];
    say('يُحفظ ' + code + ' …', false);
    return post(url, code, body).then(function (r) {
      if (r.status === 200 && r.body && r.body.ok) {
        var list = { item: S.items, decision: S.decs, checklist: S.cks }[kind];
        for (var i = 0; i < list.length; i++) if (list[i].id === code) list[i] = r.body.row;
        say('حُفظ ' + code, false);
      } else {
        say(failure(code, r), true);
      }
      S.focus = field ? { id: code, field: field } : null;
      renderAll();
    }).catch(function () {
      say('تعذّر الاتّصال بالخادم — لم يُحفظ ' + code, true);
      renderAll();
    });
  }

  // ── الملخّص والنظرة العامّة ─────────────────────────────────────────
  function kpiCard(label, value, tone, sub) {
    return h('div', { class: 'ui-kpi kpi-' + tone, role: 'listitem' },
      h('span', { class: 'ui-kpi__label', text: label }),
      h('span', { class: 'ui-kpi__value', text: value }),
      sub ? h('span', { class: 'ui-kpi__sub', text: sub }) : null);
  }
  function renderSummary() {
    var it = S.items;
    var done = it.filter(function (i) { return i.status === 'done'; }).length;
    var doing = it.filter(function (i) { return i.status === 'doing'; }).length;
    var blocked = it.filter(function (i) { return i.status === 'blocked'; }).length;
    var overdue = it.filter(function (i) { return i.status !== 'done' && i.status !== 'deferred' && i.end && dt(i.end) < TODAY; }).length;
    var owner = it.filter(function (i) { return i.gate === 'owner' && i.status !== 'done'; }).length;
    clear($('#rm-summary')).append(
      kpiCard('بنودٌ في الخارطة', it.length, 'maroon'),
      kpiCard('مُغلَق', done + ' / ' + it.length, 'green', it.length ? pc(Math.round(100 * done / it.length)) : ''),
      kpiCard('قيد التنفيذ', doing, 'blue'),
      kpiCard('متأخّر عن موعده', overdue, 'amber'),
      kpiCard('محجوب', blocked, 'red'),
      kpiCard('ينتظر المالك', owner, 'purple'));
    $('#rm-pct').textContent = pct(it);
  }
  function laneRows() {
    return (S.meta.lanes || []).map(function (l) { return { l: l, li: S.items.filter(function (i) { return i.lane === l.key; }) }; })
      .filter(function (x) { return x.li.length; });
  }
  function mkLane(x) {
    var p = pct(x.li), dn = x.li.filter(function (i) { return i.status === 'done'; }).length;
    return h('div', { class: 'plain-list__row' },
      h('b', { text: pc(p) }),
      h('div', { class: 'plain-list__main' }, h('span', { class: 'plain-list__title', text: x.l.name }), meter(p)),
      h('small', { text: dn + ' / ' + x.li.length }));
  }
  function soonItems() {
    return S.items.filter(function (i) { return i.status !== 'done' && i.status !== 'deferred' && i.end && dt(i.end) <= TODAY + 14 * DAY; })
      .sort(function (a, b) { return dt(a.end) - dt(b.end); });
  }
  function mkSoon(i) {
    var late = dt(i.end) < TODAY;
    return h('div', { class: 'plain-list__row' },
      h('b', { text: i.id }),
      h('div', { class: 'plain-list__main' },
        h('span', { class: 'plain-list__title rm-clamp', title: i.title }, bidi(i.title)),
        h('span', { class: 'plain-list__sub', text: laneName(i.lane) + ' — ' + (SRC[i.src] || '') + (i.gate === 'owner' ? ' — ينتظر المالك' : '') })),
      pill(late ? 'bad' : 'warn', (late ? 'متأخّر ' : '') + dstr(dt(i.end))));
  }
  function mkPhase(p) {
    var a = dt(p.start), b = dt(p.end);
    var li = S.items.filter(function (i) { return i.end && dt(i.end) >= a && dt(i.end) <= b; });
    return h('div', { class: 'plain-list__row' },
      h('b', { text: p.key }),
      h('div', { class: 'plain-list__main' },
        h('span', { class: 'plain-list__title', text: p.name }),
        h('span', { class: 'plain-list__sub rm-clamp', text: dstr(a) + ' ← ' + dstr(b) + ' — ' + (p.goal || '') })),
      pill('idle', li.length + ' بنداً — ' + pc(pct(li))));
  }

  // ── الخريطة الزمنيّة ────────────────────────────────────────────────
  function fillSelect(sel, opts, key) {
    if (!sel) return;
    clear(sel);
    opts.forEach(function (o) { sel.append(h('option', { value: o[0], text: o[1] })); });
    sel.value = S[key];
  }
  function initFilters() {
    var lanes = [['all', 'الكل']].concat((S.meta.lanes || []).map(function (l) { return [l.key, l.name]; }));
    fillSelect($('#rm-f-lane'), [['all', 'كل المسارات']].concat(lanes.slice(1)), 'lane');
    fillSelect($('#rm-f-st'), [['all', 'كل الحالات']].concat(Object.keys(ST).map(function (k) { return [k, ST[k]]; })), 'st');
    fillSelect($('#rm-f-src'), [['all', 'كل المصادر']].concat(Object.keys(SRC).map(function (k) { return [k, SRC[k]]; })), 'src');
    var target = { lane: 'gantt', st: 'gantt', src: 'gantt' };
    root.querySelectorAll('[data-rm-filter]').forEach(function (sel) {
      sel.addEventListener('change', function () {
        var k = sel.dataset.rmFilter;
        S[k] = sel.value;
        resetPg(target[k]);
        renderGanttView();
      });
    });
    var gv = $('#rm-gview');
    VIEWS.forEach(function (v) {
      var b = h('button', { type: 'button', class: 'btn-secondary btn-sm', 'aria-pressed': String(v[0] === S.gview), text: v[1], onclick: function () { S.gview = v[0]; renderGanttView(); } });
      b.dataset.view = v[0];
      gv.append(b);
    });
    gv.append(h('button', { type: 'button', class: 'btn-primary btn-sm', text: '+ بندٌ جديد', onclick: openCreate }));
    var ruTabs = $('#rm-ru-tabs');
    RULE_SECTIONS.forEach(function (o) {
      ruTabs.append(h('button', { type: 'button', class: 'btn-secondary btn-sm', 'aria-pressed': String(o[0] === S.ru), text: o[1],
        onclick: function () {
          S.ru = o[0];
          Array.prototype.forEach.call(ruTabs.children, function (b) { b.setAttribute('aria-pressed', String(b === this)); }, this);
          resetPg('rules');
          fit('rules');
        } }));
    });
    var leg = $('.rm-legend');
    (S.meta.milestones || []).forEach(function (ms) {
      var x = dt(ms.d);
      if (x >= A0 && x <= A1) leg.append(h('li', { class: 'rm-mile-li', title: ms.name }, h('i', { class: 'rm-swatch is-mile' }), dstr(x) + ' ', bidi(ms.name)));
    });
  }
  function filtered() {
    return S.items.filter(function (i) {
      return (S.lane === 'all' || i.lane === S.lane) && (S.st === 'all' || i.status === S.st) && (S.src === 'all' || i.src === S.src);
    });
  }
  function field(id, name, label, control) {
    control.setAttribute('data-rm-id', id);
    control.setAttribute('data-rm-field', name);
    return h('label', null, label, control);
  }
  function detail(it) {
    var id = it.id;
    var sel = h('select', { class: 'form-control', 'aria-label': 'حالة ' + id, onchange: function (e) { save('item', id, { status: e.target.value }, 'status'); } });
    Object.keys(ST).forEach(function (s) { sel.append(h('option', { value: s, text: ST[s], selected: s === it.status })); });
    var rngLabel = h('span', { text: 'التقدّم ' + (it.progress || 0) + '%' });
    var rng = h('input', {
      type: 'range', class: 'form-control', min: '0', max: '100', step: '5', value: String(it.progress || 0), 'aria-label': 'تقدّم ' + id,
      oninput: function (e) { rngLabel.textContent = 'التقدّم ' + e.target.value + '%'; },
      onchange: function (e) { save('item', id, { progress: Number(e.target.value) }, 'progress'); }
    });
    var s0 = h('input', { type: 'date', class: 'form-control', value: it.start || '', 'aria-label': 'بداية ' + id, onchange: function (e) { save('item', id, { start: e.target.value || null }, 'start'); } });
    var s1 = h('input', { type: 'date', class: 'form-control', value: it.end || '', 'aria-label': 'نهاية ' + id, onchange: function (e) { save('item', id, { end: e.target.value || null }, 'end'); } });
    var pr = h('input', { type: 'text', class: 'form-control', value: it.pr || '', placeholder: '#446', maxlength: '64', dir: 'ltr', 'aria-label': 'طلب الدمج ' + id, onchange: function (e) { save('item', id, { pr: e.target.value.trim() }, 'pr'); } });
    var note = h('textarea', { class: 'form-control', maxlength: '2000', 'aria-label': 'ملاحظة ' + id, onchange: function (e) { save('item', id, { note: e.target.value }, 'note'); } });
    note.value = it.note || '';
    rng.setAttribute('data-rm-id', id);
    rng.setAttribute('data-rm-field', 'progress');
    function info(k, v) { return h('div', null, h('div', { class: 'k', text: k }), h('div', null, bidi(v))); }
    return h('div', { class: 'rm-det' },
      info(id, it.title),
      h('div', { class: 'g' },
        field(id, 'status', 'الحالة', sel),
        h('label', null, rngLabel, rng),
        field(id, 'start', 'البداية', s0),
        field(id, 'end', 'النهاية', s1),
        field(id, 'pr', 'طلب الدمج', pr)),
      field(id, 'note', 'ملاحظة', note),
      info('معيار الإغلاق', it.criterion || '–'),
      info('المصدر', it.ref || ''), info('الاعتماديّات', it.deps || '–'),
      info('أساس التاريخ', it.dateBasis || ''), info('الجهد التقديري (أيّام)', String(it.effort || '')));
  }
  // ── إضافةُ بندٍ جديد (مهمّةٌ مستقبليّة) ─────────────────────────────
  function newItemForm() {
    var lanes = (S.meta.lanes || []);
    function ctl(tag, attrs) { attrs = attrs || {}; attrs['class'] = 'form-control'; return h(tag, attrs); }
    var title = ctl('textarea', { maxlength: '500', required: 'required', 'aria-label': 'عنوان البند' });
    var lane = ctl('select', { 'aria-label': 'المسار' });
    lanes.forEach(function (l) { lane.append(h('option', { value: l.key, text: l.name })); });
    var status = ctl('select', { 'aria-label': 'الحالة' });
    Object.keys(ST).forEach(function (k) { status.append(h('option', { value: k, text: ST[k] })); });
    var start = ctl('input', { type: 'date', 'aria-label': 'البداية' });
    var end = ctl('input', { type: 'date', 'aria-label': 'النهاية' });
    var effort = ctl('input', { type: 'number', min: '0.5', max: '365', step: '0.5', value: '1', 'aria-label': 'الجهد بالأيام' });
    var deps = ctl('input', { type: 'text', maxlength: '255', 'aria-label': 'الاعتماديات' });
    var criterion = ctl('textarea', { maxlength: '2000', 'aria-label': 'معيار الإغلاق' });
    var note = ctl('textarea', { maxlength: '2000', 'aria-label': 'ملاحظة' });
    var gate = h('input', { type: 'checkbox', 'aria-label': 'ينتظر قرار المالك' });
    var err = h('p', { class: 'rm-live is-error', role: 'alert' });
    function lab(text, control) { return h('label', null, text, control); }
    var sending = false; // نقرتان متتاليتان لا تُنشئان بندَين
    var send = h('button', { type: 'submit', class: 'btn-primary btn-sm', text: 'إضافة البند' });
    function submit(ev) {
      ev.preventDefault();
      if (sending) return;
      sending = true;
      send.disabled = true;
      var body = { title: title.value, lane: lane.value, status: status.value, effort: effort.value,
        start: start.value || null, end: end.value || null, deps: deps.value, criterion: criterion.value, note: note.value, gate: gate.checked ? 'owner' : '' };
      clear(err);
      fetch(root.dataset.itemCreateUrl, { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': root.dataset.csrf, 'X-Requested-With': 'XMLHttpRequest' }, body: JSON.stringify(body) })
        .then(function (res) { return res.json().catch(function () { return {}; }).then(function (j) { return { status: res.status, body: j }; }); })
        .then(function (r) {
          if (r.status === 201 && r.body && r.body.ok) {
            S.items.push(r.body.row);
            S.creating = false;
            say('أُضيف ' + r.body.row.id, false);
            openDrawer(r.body.row.id);
            renderAll();
          } else if (r.body && r.body.fields) {
            err.textContent = Object.keys(r.body.fields).map(function (k) { return k + ' — ' + r.body.fields[k]; }).join('؛ ');
          } else {
            err.textContent = r.status === 403 ? 'لا صلاحيّةَ للكتابة' : 'تعذّر الحفظ';
          }
        })
        .catch(function () { err.textContent = 'تعذّر الاتّصال بالخادم'; })
        .then(function () { sending = false; send.disabled = false; });
    }
    return h('form', { class: 'rm-det', onsubmit: submit },
      lab('العنوان *', title),
      h('div', { class: 'g' }, lab('المسار', lane), lab('الحالة', status), lab('البداية', start), lab('النهاية', end), lab('الجهد (أيّام)', effort)),
      lab('معيار الإغلاق', criterion), lab('الاعتماديّات', deps), lab('ملاحظة', note),
      h('label', { class: 'rm-check' }, gate, h('span', { text: 'ينتظر قرارَ/إذنَ المالك' })),
      err,
      h('div', { class: 'rm-inline' },
        send,
        h('button', { type: 'button', class: 'btn-secondary btn-sm', text: 'إلغاء', onclick: closeDrawer })));
  }

  function openDrawer(id) {
    S.drawer = id;
    S.creating = false;
    renderDrawer();
    var first = $('#rm-drawer-body select');
    if (first) first.focus();
  }
  function openList(title, ids) { S.list = { title: title, ids: ids }; S.drawer = null; renderDrawer(); }
  function closeDrawer() { S.drawer = null; S.list = null; S.creating = false; renderDrawer(); }
  function openCreate() { S.creating = true; S.drawer = null; renderDrawer(); var t = $('#rm-drawer-body textarea'); if (t) t.focus(); }
  function listRow(it) {
    return h('button', { type: 'button', class: 'rm-lrow', onclick: function () { openDrawer(it.id); } },
      h('b', { class: 'rm-code', text: it.id }),
      h('span', { class: 'rm-lrow__t rm-clamp' }, bidi(it.title)),
      pill(it.status === 'done' ? 'ok' : (it.status === 'blocked' ? 'bad' : (it.status === 'doing' ? 'accent' : 'idle')), ST[it.status] + (it.status === 'doing' ? ' ' + (it.progress || 0) + '%' : '')));
  }
  function renderDrawer() {
    var dr = $('#rm-drawer');
    var it = S.drawer && S.items.filter(function (x) { return x.id === S.drawer; })[0];
    var body = $('#rm-drawer-body');
    if (S.creating) {
      dr.hidden = false;
      $('#rm-drawer .ui-section__title').textContent = 'بندٌ جديد';
      clear(body).append(newItemForm());
      return;
    }
    if (it) {
      dr.hidden = false;
      $('#rm-drawer .ui-section__title').textContent = 'تحرير ' + it.id;
      var y = dr.scrollTop;
      clear(body);
      if (S.list) body.append(h('button', { type: 'button', class: 'btn-secondary btn-sm', text: 'رجوعٌ إلى القائمة', onclick: function () { S.drawer = null; renderDrawer(); } }));
      body.append(detail(it));
      dr.scrollTop = y;
      return;
    }
    if (S.list) {
      dr.hidden = false;
      $('#rm-drawer .ui-section__title').textContent = S.list.title;
      var ids = S.list.ids;
      clear(body).append(h('div', { class: 'rm-lrows' }, S.items.filter(function (x) { return ids.indexOf(x.id) >= 0; }).map(listRow)));
      return;
    }
    dr.hidden = true;
  }

  // ── مصفوفةُ المرحلة × المسار: العرضُ الافتراضيّ للخريطة ─────────────
  var VIEWS = [['mx', 'مصفوفةُ المراحل'], ['tl', 'الخطُّ الزمنيّ']];
  function phaseOf(i) {
    var ps = S.meta.phases || [];
    if (!i.end || !ps.length) return -1;
    var e = dt(i.end);
    for (var k = 0; k < ps.length; k++) if (e >= dt(ps[k].start) && e <= dt(ps[k].end)) return k;
    return e < dt(ps[0].start) ? 0 : ps.length - 1;
  }
  function mxCell(lane, k, items, label) {
    if (!items.length) return h('div', { class: 'rm-mx-c is-empty', 'aria-hidden': 'true' });
    var n = { done: 0, doing: 0, blocked: 0, todo: 0, deferred: 0 };
    items.forEach(function (i) { n[i.status] = (n[i.status] || 0) + 1; });
    var bar = h('div', { class: 'rm-mx-bar' });
    ['done', 'doing', 'blocked', 'todo', 'deferred'].forEach(function (st) {
      if (n[st]) bar.append(h('span', { class: 'is-' + st, vars: { '--rm-w': pc(100 * n[st] / items.length) } }));
    });
    var sub = n.done + ' مُغلَق' + (n.doing ? ' · ' + n.doing + ' جارٍ' : '') + (n.blocked ? ' · ' + n.blocked + ' محجوب' : '');
    var ids = items.map(function (i) { return i.id; });
    return h('button', { type: 'button', class: 'rm-mx-c', title: laneName(lane.key) + ' — ' + label + ': ' + sub,
      onclick: function () { openList(laneName(lane.key) + ' — ' + label, ids); } },
      h('b', { text: String(items.length) }), h('span', { text: sub }), bar);
  }
  function renderMatrix() {
    var host = clear($('#rm-matrix'));
    var phases = S.meta.phases || [], list = filtered();
    host.style.setProperty('--rm-cols', String(phases.length + 1));
    host.append(h('div', { class: 'rm-mx-h rm-mx-corner', text: 'المسار' }));
    phases.forEach(function (p) { host.append(h('div', { class: 'rm-mx-h', title: p.name }, h('b', { text: p.key }), h('span', { text: p.name }))); });
    host.append(h('div', { class: 'rm-mx-h' }, h('b', { text: '—' }), h('span', { text: 'غير مجدولة' })));
    (S.meta.lanes || []).forEach(function (l) {
      var li = list.filter(function (i) { return i.lane === l.key; });
      if (!li.length) return;
      host.append(h('div', { class: 'rm-mx-l' }, h('b', { text: l.name }), h('span', { text: pc(pct(li)) + ' — ' + li.length })));
      phases.forEach(function (p, k) { host.append(mxCell(l, k, li.filter(function (i) { return phaseOf(i) === k; }), p.key + ' ' + p.name)); });
      host.append(mxCell(l, -1, li.filter(function (i) { return phaseOf(i) === -1; }), 'غير مجدولة'));
    });
    if (!list.length) host.append(h('div', { class: 'rm-empty', text: 'لا بنودَ بهذه المرشّحات.' }));
  }
  function renderGanttView() {
    var mx = S.gview === 'mx';
    $('#rm-matrix').hidden = !mx;
    $('#rm-gantt-head').hidden = mx;
    $('#rm-fit-gantt').hidden = mx;
    $('#rm-pg-gantt').hidden = mx;
    var vb = $('#rm-gview');
    Array.prototype.forEach.call(vb.children, function (b) { b.setAttribute('aria-pressed', String(b.dataset.view === S.gview)); });
    if (mx) { renderMatrix(); return; }
    renderGanttHead();
    fit('gantt');
  }

  // صفوفُ الخريطة: رأسُ المسار ثمّ بنودُه المؤرَّخة ثمّ غيرُ المجدولة مجمَّعةً (كلُّ صفٍّ عنصرٌ في الترقيم)
  var CHIPS_PER_ROW = 8;
  function ganttEntries() {
    var list = filtered(), out = [];
    (S.meta.lanes || []).forEach(function (l) {
      var li = list.filter(function (i) { return i.lane === l.key; });
      if (!li.length) return;
      out.push({ t: 'lane', l: l, li: li });
      li.filter(function (i) { return i.start && i.end; })
        .sort(function (a, b) { return dt(a.start) - dt(b.start) || dt(a.end) - dt(b.end); })
        .forEach(function (i) { out.push({ t: 'row', i: i }); });
      var und = li.filter(function (i) { return !(i.start && i.end); });
      for (var k = 0; k < und.length; k += CHIPS_PER_ROW) out.push({ t: 'und', list: und.slice(k, k + CHIPS_PER_ROW), first: k === 0 });
    });
    return out;
  }
  function mkGantt(e) {
    if (e.t === 'lane') {
      return h('div', { class: 'rm-lane' },
        h('div', { class: 'rm-lab' }, h('span', { text: e.l.name }), h('span', { class: 'rm-lab__n', text: pct(e.li) + '٪ · ' + e.li.length })),
        h('div', { class: 'rm-lane-p' }, meter(pct(e.li))));
    }
    if (e.t === 'und') {
      var box = h('div', { class: 'rm-und' }, e.first ? h('b', { text: 'غير مجدولة:' }) : null);
      e.list.forEach(function (i) { box.append(h('button', { type: 'button', class: 'rm-chip', title: i.title, text: i.id, onclick: function () { openDrawer(i.id); } })); });
      return box;
    }
    var i = e.i;
    var a = pos(Math.max(dt(i.start), A0)), b = pos(Math.min(dt(i.end) + DAY, A1));
    if (b <= a) b = a + 0.8;
    var suggested = /مقترَح/.test(i.dateBasis || '');
    var bar = h('div', { class: 'rm-bar is-' + i.status + (suggested ? ' is-suggested' : ''), vars: { '--rm-a': pc(a), '--rm-w': pc(b - a) }, title: i.id + ' — ' + i.title + ' — ' + dstr(dt(i.start)) + ' ← ' + dstr(dt(i.end)) });
    if (i.status === 'doing' && i.progress) bar.append(h('i', { vars: { '--rm-p': pc(i.progress) } }));
    var track = h('div', { class: 'rm-track' }, bar);
    (S.meta.milestones || []).forEach(function (ms) {
      var x = dt(ms.d);
      if (x >= A0 && x <= A1) track.append(h('div', { class: 'rm-mk', vars: { '--rm-a': pc(pos(x)) }, title: ms.name }));
    });
    if (TODAY >= A0 && TODAY <= A1) track.append(h('div', { class: 'rm-today', vars: { '--rm-a': pc(pos(TODAY)) } }));
    return h('div', { class: 'rm-row' },
      h('button', { type: 'button', class: 'rm-lab', title: i.title, 'aria-haspopup': 'dialog', onclick: function () { openDrawer(i.id); } },
        h('b', { text: i.id }), h('span', { class: 'rm-lab__t' }, bidi(i.title))),
      track);
  }
  function renderGanttHead() {
    var head = clear($('#rm-gantt-head'));
    var axis = h('div', { class: 'rm-axis' });
    (S.meta.phases || []).forEach(function (p) {
      var a = pos(Math.max(dt(p.start), A0)), b = pos(Math.min(dt(p.end) + DAY, A1));
      if (b <= a) return;
      axis.append(h('div', { class: 'rm-ph', title: p.key + ' — ' + p.name, vars: { '--rm-a': pc(a), '--rm-w': pc(b - a) }, text: p.key + ' — ' + p.name }));
    });
    // عددُ تسميات الأسابيع بما يتّسع له المحورُ (≈48px لكلٍّ) — الأفقُ نحو 27 أسبوعاً لا 14
    var room = Math.max(4, Math.floor(((axis.clientWidth || (head.clientWidth || root.clientWidth) * 0.75) || 480) / 48));
    var step = Math.max(1, Math.ceil(Math.ceil(SPAN / 7) / room));
    for (var w = 0; w < Math.ceil(SPAN / 7); w += step) {
      var t = A0 + w * 7 * DAY;
      axis.append(h('div', { class: 'rm-wk', vars: { '--rm-a': pc(pos(t)), '--rm-w': pc(step * 7 / SPAN * 100) }, text: dstr(t) }));
    }
    head.append(h('div', { class: 'rm-lab', text: 'البند' }), axis);
  }

  // ── المؤشّرات والقرارات والمخاطر والمعايير والقواعد ─────────────────
  function kpiGroup(g) { return S.kpis.filter(function (k) { var c = String(k.code || ''); return g === 'U' ? /^UK/.test(c) : (g === 'M' ? /^MK/.test(c) : !/^(UK|MK)/.test(c)); }); }
  function mkKpi(k) {
    var c = calc(k);
    var gauge = h('div', { class: 'rm-gauge', vars: c.pct != null ? { '--rm-p': pc(c.pct) } : null }, c.pct != null ? h('i') : null, h('u'));
    var baseTxt = k.textMode || (k.baseline == null && k.baselineText) ? (k.baselineText || '–') : fmt(k.baseline, k.unit);
    var targetTxt = k.textMode || (k.target == null && k.targetText) ? (k.targetText || '–') : (k.dir === 'down' ? '≤ ' : '≥ ') + fmt(k.target, k.unit);
    return h('article', { class: 'rm-tile' },
      h('header', { class: 'rm-tile__head' }, h('b', { class: 'rm-code', text: k.code }), pill(c.st, c.label)),
      h('h3', { class: 'rm-tile__title rm-clamp', title: k.name }, bidi(k.name)),
      h('dl', { class: 'rm-vals' },
        h('div', null, h('dt', { text: 'الأساس' }), h('dd', null, bidi(baseTxt))),
        h('div', null, h('dt', { text: 'الحاليّ' }), h('dd', null, h('b', null, bidi(fmt(k.current, k.unit))))),
        h('div', null, h('dt', { text: 'الهدف' }), h('dd', null, bidi(targetTxt)))),
      gauge,
      h('small', { class: 'rm-clamp', title: (k.source || '') + (k.why ? ' — لم يُقَس لأنّ: ' + k.why : '') }, laneName(k.lane) + ' — ', bidi(k.source || '')));
  }
  function decGroup(st) { return S.decs.filter(function (d) { return d.status === st; }); }
  function riskGroup(high) { return S.risks.filter(function (r) { return (r.impact === 'مرتفع') === high; }); }
  function mkDec(d) {
    var sel = h('select', { class: 'form-control form-control-sm', 'data-rm-id': d.id, 'data-rm-field': 'status', 'aria-label': 'حالة ' + d.id, onchange: function (e) { save('decision', d.id, { status: e.target.value }, 'status'); } });
    Object.keys(DS).forEach(function (s) { sel.append(h('option', { value: s, text: DS[s], selected: s === d.status })); });
    var date = h('input', { type: 'date', class: 'form-control form-control-sm', value: d.date || '', 'data-rm-id': d.id, 'data-rm-field': 'date', 'aria-label': 'تاريخ حسم ' + d.id, onchange: function (e) { save('decision', d.id, { date: e.target.value || null }, 'date'); } });
    var txt = (d.blocks || d.options || '');
    return h('article', { class: 'rm-tile' },
      h('header', { class: 'rm-tile__head' }, h('b', { class: 'rm-code', text: d.id }), pill(d.status === 'open' ? 'warn' : (d.status === 'decided' ? 'ok' : 'idle'), DS[d.status] || d.status)),
      h('h3', { class: 'rm-tile__title rm-clamp', title: d.title }, bidi(d.title)),
      txt ? h('p', { class: 'rm-clamp', title: txt }, bidi(txt)) : null,
      d.recommendation ? h('p', { class: 'rm-clamp rm-muted', title: d.recommendation }, 'التوصية: ', bidi(d.recommendation)) : null,
      h('div', { class: 'rm-inline' }, sel, date),
      d.due ? h('small', { class: 'rm-clamp', text: d.due }) : null);
  }
  function mkRisk(r) {
    return h('article', { class: 'rm-tile' },
      h('header', { class: 'rm-tile__head' }, h('b', { class: 'rm-code', text: r.id }), pill('warn', 'احتمال ' + r.prob), pill('bad', 'أثر ' + r.impact)),
      h('h3', { class: 'rm-tile__title rm-clamp', title: r.risk }, bidi(r.risk)),
      h('p', { class: 'rm-clamp rm-muted', title: r.mitigation }, 'التخفيف: ', bidi(r.mitigation)));
  }
  function mkCheck(c) {
    var box = h('input', { type: 'checkbox', id: 'rm-ck-' + c.id, 'data-rm-id': c.id, 'data-rm-field': 'done', onchange: function (e) { save('checklist', c.id, { done: e.target.checked }, 'done'); } });
    box.checked = !!c.done;
    return h('div', { class: 'plain-list__row rm-check' }, h('label', { for: 'rm-ck-' + c.id }, box, h('span', { class: 'rm-clamp', title: c.text }, bidi(c.text))));
  }
  function mkStd(r) {
    return h('article', { class: 'rm-tile' },
      h('h3', { class: 'rm-tile__title rm-clamp', title: r[0] }, bidi(r[0])),
      h('p', { class: 'rm-clamp', title: r[1] }, bidi(r[1])),
      h('small', { class: 'rm-clamp', title: r[2] }, 'يُقاس: ', bidi(r[2])),
      pill('idle', r[3]));
  }
  function ruleItems() {
    var m = S.meta, k = S.ru;
    if (k === 'own') return (m.ownership || []).map(function (r) { return r[0] + ' — ' + r[1] + ': ' + r[2]; });
    if (k === 'map') return (m.mapping || []).map(function (r) { return r[0] + ' ← ' + r[1]; });
    if (k === 'upd') return HOW_TO_UPDATE;
    return (m[{ rules: 'rules', dod: 'dod', crit: 'criticalPath', win: 'windows', rbk: 'rollback', srcs: 'sources' }[k]] || []);
  }
  function mkRule(t, i) {
    return h('article', { class: 'rm-tile rm-tile--text' }, h('b', { class: 'rm-code', text: String(i + 1) }), h('p', { class: 'rm-clamp', title: t }, bidi(t)));
  }
  function statics() {
    var lim = S.meta.limits;
    var asof = S.meta.asOf ? 'حتى ' + (S.meta.horizonEnd || '') + ' — آخرُ تحديثٍ للبيانات ' + S.meta.asOf : '';
    // تاريخُ آخر تحديثٍ في تلميح التقدّم لا في سطرٍ مستقلّ يأكل ارتفاعاً
    var big = $('#rm-pct').parentNode;
    if (!big.dataset.baseTitle) big.dataset.baseTitle = big.title;
    big.title = big.dataset.baseTitle + (asof || lim ? ' — ' + (asof || lim) : '');
  }

  function restoreFocus() {
    if (!S.focus) return;
    var esc = function (v) { return window.CSS && CSS.escape ? CSS.escape(String(v)) : String(v).replace(/["\]/g, '\$&'); };
    var target = root.querySelector('[data-rm-id="' + esc(S.focus.id) + '"][data-rm-field="' + esc(S.focus.field) + '"]');
    S.focus = null;
    if (target) target.focus();
  }
  function renderAll() {
    renderSummary();
    renderGanttHead();
    fitTab();
    renderDrawer();
    statics();
    restoreFocus();
  }

  mount('lanes', laneRows, mkLane);
  mount('next', soonItems, mkSoon);
  mount('phases', function () { return S.meta.phases || []; }, mkPhase);
  mount('gantt', ganttEntries, mkGantt);
  mountScroll('kpU', function () { return kpiGroup('U'); }, mkKpi);
  mountScroll('kpM', function () { return kpiGroup('M'); }, mkKpi);
  mountScroll('kpV', function () { return kpiGroup('V'); }, mkKpi);
  mountScroll('dcOpen', function () { return decGroup('open'); }, mkDec);
  mountScroll('dcDone', function () { return decGroup('decided'); }, mkDec);
  mountScroll('dcDef', function () { return decGroup('deferred'); }, mkDec);
  mountScroll('rkHigh', function () { return riskGroup(true); }, mkRisk);
  mountScroll('rkOther', function () { return riskGroup(false); }, mkRisk);
  mountScroll('cks', function () { return S.cks; }, mkCheck);
  mount('stds', function () { return S.meta.standards || []; }, mkStd);
  mount('rules', ruleItems, mkRule);

  // ── التبويبات ───────────────────────────────────────────────────────
  var tabButtons = Array.prototype.slice.call(root.querySelectorAll('[data-rm-tab]'));
  function setTab(t, focus) {
    S.tab = t;
    tabButtons.forEach(function (b) {
      var on = b.dataset.rmTab === t;
      b.setAttribute('aria-selected', String(on));
      b.setAttribute('tabindex', on ? '0' : '-1');
      b.classList.toggle('active', on);
      if (on && focus) b.focus();
    });
    if ($('#rm-tabsel')) $('#rm-tabsel').value = t;
    TABS.forEach(function (x) { $('#rm-tab-' + x).hidden = x !== t; });
    renderGanttHead();
    fitTab();
  }
  tabButtons.forEach(function (b) {
    b.addEventListener('click', function () { setTab(b.dataset.rmTab, false); });
    b.addEventListener('keydown', function (e) {
      var i = TABS.indexOf(b.dataset.rmTab), n = TABS.length, j = null;
      // الاتّجاهُ يمين←يسار: السهمُ الأيسر يقدَّم إلى التبويب التالي
      if (e.key === 'ArrowLeft') j = (i + 1) % n;
      else if (e.key === 'ArrowRight') j = (i - 1 + n) % n;
      else if (e.key === 'Home') j = 0;
      else if (e.key === 'End') j = n - 1;
      if (j == null) return;
      e.preventDefault();
      setTab(TABS[j], true);
    });
  });
  // على الجوال: قائمةٌ منسدلة بدل صفّ تبويباتٍ يلتفّ على ثلاثة أسطر
  var tabSel = $('#rm-tabsel');
  tabButtons.forEach(function (b) { tabSel.append(h('option', { value: b.dataset.rmTab, text: b.textContent.trim() })); });
  tabSel.addEventListener('change', function () { setTab(tabSel.value, false); });
  // بطاقاتُ اللوحة الواحدة تُعرض على الجوال واحدةً واحدة بمفتاحٍ مقطعيّ (تُخفيها CSS ما لم تكن الشاشةُ ضيّقة)
  root.querySelectorAll('.rm-fill').forEach(function (fill) {
    var cards = Array.prototype.slice.call(fill.children);
    var seg = h('div', { class: 'rm-seg', role: 'group', 'aria-label': 'بطاقات القسم' });
    cards.forEach(function (c, idx) {
      var title = c.querySelector('.ui-section__title');
      seg.append(h('button', { type: 'button', class: 'btn-secondary btn-sm', 'aria-pressed': String(idx === 0), text: title ? title.textContent.trim() : String(idx + 1),
        onclick: function () {
          fill.setAttribute('data-active', String(idx));
          Array.prototype.forEach.call(seg.children, function (bt, j) { bt.setAttribute('aria-pressed', String(j === idx)); });
          fitTab();
        } }));
    });
    fill.setAttribute('data-active', '0');
    fill.parentNode.insertBefore(seg, fill);
  });
  $('#rm-drawer-close').addEventListener('click', closeDrawer);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && (S.drawer || S.creating || S.list)) closeDrawer(); });

  var resizeTimer = null;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { renderGanttHead(); fitTab(); }, 120);
  });

  var refitTimer = null;
  function refitSoon() { clearTimeout(refitTimer); refitTimer = setTimeout(fitTab, 60); }
  if (window.ResizeObserver) {
    var ro = new ResizeObserver(refitSoon);
    ro.observe(root);
    Object.keys(M).forEach(function (k) { if (M[k].host) ro.observe(M[k].host); });
    ro.observe($('#rm-matrix'));
  }
  window.addEventListener('load', refitSoon);
  window.addEventListener('pageshow', refitSoon);

  try {
    initFilters();
    renderSummary();
    setTab(S.tab, false);
    renderAll();
  } catch (err) {
    say('تعذّر رسم الخارطة: ' + (err && err.message ? err.message : err) + ' — حدِّث الصفحةَ بـCtrl+Shift+R', true);
    if (window.console) console.error('roadmap', err);
  }
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { fitTab(); });
})();
