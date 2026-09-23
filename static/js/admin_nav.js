/* القائمةُ الأفقيّة في لوحة الإدارة — قائمةٌ واحدةٌ مفتوحةٌ في كلّ لحظة:
   المرورُ يفتح القسمَ ويُغلق غيرَه، والنقرُ يُثبّته حتى نقرةٍ خارجَه أو Esc أو نقرةٍ ثانيةٍ عليه،
   والمرورُ على قسمٍ آخرَ وهو مثبَّتٌ ينقل القائمةَ إليه. اللمسُ (بلا مرور) بالنقر وحدَه. */
(function () {
  'use strict';
  var nav = document.querySelector('.adm-nav');
  if (!nav) return;
  var items = Array.prototype.slice.call(nav.querySelectorAll('.adm-nav__item'));
  var pinned = null;
  var canHover = window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches;

  /* الجوّال: زرُّ «القائمة» يطوي الأقسامَ والبحثَ فتبقى الترويسةُ سطراً واحداً (كانت ~235px من 812).
     الصنفُ has-toggle يُضاف هنا لا في القالب: بلا سكربتٍ لا زرَّ ولا طيَّ، والقائمةُ مفتوحةٌ كما كانت. */
  var toggle = nav.querySelector('.adm-nav__toggle');
  if (toggle) {
    toggle.hidden = false;
    nav.classList.add('has-toggle');
    toggle.addEventListener('click', function () {
      var open = !nav.classList.contains('is-expanded');
      nav.classList.toggle('is-expanded', open);
      toggle.setAttribute('aria-expanded', String(open));
    });
  }

  function keepInside(item) {
    var menu = item.querySelector('.adm-nav__menu');
    if (!menu) return;
    menu.classList.remove('adm-nav__menu--flip');
    var r = menu.getBoundingClientRect();
    if (r.left < 0 || r.right > document.documentElement.clientWidth) menu.classList.add('adm-nav__menu--flip');
  }
  function setOpen(item, open) {
    item.classList.toggle('is-open', open);
    var btn = item.querySelector('.adm-nav__btn');
    if (btn) btn.setAttribute('aria-expanded', String(open));
    if (open) keepInside(item);
  }
  function closeAll(except) {
    items.forEach(function (it) { if (it !== except) setOpen(it, false); });
  }

  items.forEach(function (item) {
    var btn = item.querySelector('.adm-nav__btn');
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      if (pinned === item) { setOpen(item, false); pinned = null; return; }
      closeAll(item);
      setOpen(item, true);
      pinned = item;
    });
    if (canHover) {
      item.addEventListener('mouseenter', function () {
        closeAll(item);
        setOpen(item, true);
        if (pinned && pinned !== item) pinned = null;
      });
    }
    item.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { setOpen(item, false); pinned = null; btn.focus(); }
      if (e.key === 'ArrowDown' && document.activeElement === btn) {
        e.preventDefault();
        closeAll(item);
        setOpen(item, true);
        var first = item.querySelector('.adm-nav__menu a');
        if (first) first.focus();
      }
    });
  });

  /* بحثُ القائمة: النتائجُ مُقرَّرةٌ من الخادم في _nav.html (كلُّ الروابط مرسومةٌ سلفاً،
     مُفلَتةً بـDjango) — الفلترةُ هنا إظهارٌ/إخفاءٌ بصفة hidden وحدَها، لا بناءَ DOM من
     نصٍّ ولا a.href = <من JSON> أبداً، فلا سَطوَ (CodeQL: DOM text reinterpreted as HTML)
     يُحرَس أصلاً. Enter يفتح أوّل نتيجةٍ ظاهرة، Esc يُفرغ، / يُركِّز الحقلَ من أيّ مكان. */
  var searchInput = document.getElementById('adm-nav-search');
  var results = document.getElementById('adm-nav-search-results');
  var allHits = results ? Array.prototype.slice.call(results.querySelectorAll('a')) : [];
  var active = -1;
  var MAX_SHOWN = 8;
  function closeSearch() {
    results.hidden = true;
    allHits.forEach(function (a) { a.hidden = true; a.classList.remove('is-active'); });
    active = -1;
  }
  function renderSearch(q) {
    q = q.trim().toLowerCase();
    var terms = q ? q.split(/\s+/) : [];
    var shown = 0;
    allHits.forEach(function (a) {
      var hay = a.getAttribute('data-name') + ' ' + a.getAttribute('data-group');
      var hit = terms.length > 0 && shown < MAX_SHOWN
        && terms.every(function (t) { return hay.indexOf(t) !== -1; });
      a.hidden = !hit;
      a.classList.remove('is-active');
      if (hit) shown += 1;
    });
    var visible = allHits.filter(function (a) { return !a.hidden; });
    if (active >= 0 && active < visible.length) visible[active].classList.add('is-active');
    results.hidden = visible.length === 0;
    return visible;
  }
  if (searchInput && results && allHits.length) {
    searchInput.addEventListener('input', function () { active = -1; renderSearch(searchInput.value); });
    searchInput.addEventListener('keydown', function (e) {
      var visible = allHits.filter(function (a) { return !a.hidden; });
      if (e.key === 'Escape') { searchInput.value = ''; closeSearch(); searchInput.blur(); return; }
      if (e.key === 'ArrowDown' && visible.length) { e.preventDefault(); active = Math.min(active + 1, visible.length - 1); renderSearch(searchInput.value); }
      if (e.key === 'ArrowUp' && visible.length) { e.preventDefault(); active = Math.max(active - 1, 0); renderSearch(searchInput.value); }
      if (e.key === 'Enter') { var target = visible[active] || visible[0]; if (target) { e.preventDefault(); window.location.href = target.href; } }
    });
    searchInput.addEventListener('blur', function () { setTimeout(closeSearch, 150); });
    document.addEventListener('keydown', function (e) {
      if (e.key !== '/' || e.target === searchInput) return;
      var tag = (e.target.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || e.target.isContentEditable) return;
      e.preventDefault();
      searchInput.focus();
    });
  }

  nav.addEventListener('mouseleave', function () { if (!pinned) closeAll(null); });
  document.addEventListener('click', function () { pinned = null; closeAll(null); });
})();
