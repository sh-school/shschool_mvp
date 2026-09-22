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

  /* بحثُ القائمة: فهرسٌ مضمَّنٌ (json_script) لا طلبٌ إضافيّ؛ Enter يفتح أوّل نتيجة، Esc يُفرغ، / يُركِّز الحقلَ من أيّ مكانٍ في الصفحة. */
  var searchInput = document.getElementById('adm-nav-search');
  var results = document.getElementById('adm-nav-search-results');
  var indexEl = document.getElementById('adm-nav-search-index');
  var index = indexEl ? JSON.parse(indexEl.textContent) : [];
  var active = -1;
  function closeSearch() { results.hidden = true; results.textContent = ''; active = -1; }
  /* رابطُ نتيجة البحث يجب أن يبقى داخل /admin/ — الفهرسُ من الخادم نفسِه (json_script)
     ولا مصدرَ خارجيّاً يكتبه، لكنّ CodeQL يحرس السَّطوَ (DOM text reinterpreted as HTML)
     بلا افتراضِ ثقةٍ في مصدر البيانات، فيُتحقَّق من الشكل صراحةً قبل a.href. */
  function isSafeAdminUrl(url) {
    return typeof url === 'string' && /^\/admin\//.test(url);
  }
  function renderSearch(items) {
    results.textContent = '';
    items.forEach(function (item, i) {
      if (!isSafeAdminUrl(item.url)) return;
      var a = document.createElement('a');
      a.href = item.url; a.setAttribute('role', 'option'); a.tabIndex = -1;
      a.textContent = item.name;
      var g = document.createElement('small'); g.textContent = item.group; a.appendChild(g);
      if (i === active) a.classList.add('is-active');
      results.appendChild(a);
    });
    results.hidden = results.children.length === 0;
  }
  function matches(q) {
    q = q.trim();
    if (!q) return [];
    var terms = q.split(/\s+/);
    return index.filter(function (item) {
      var hay = item.name + ' ' + item.group;
      return terms.every(function (t) { return hay.indexOf(t) !== -1; });
    }).slice(0, 8);
  }
  if (searchInput && results && index.length) {
    searchInput.addEventListener('input', function () { active = -1; renderSearch(matches(searchInput.value)); });
    searchInput.addEventListener('keydown', function (e) {
      var items = results.querySelectorAll('a');
      if (e.key === 'Escape') { searchInput.value = ''; closeSearch(); searchInput.blur(); return; }
      if (e.key === 'ArrowDown' && items.length) { e.preventDefault(); active = Math.min(active + 1, items.length - 1); renderSearch(matches(searchInput.value)); }
      if (e.key === 'ArrowUp' && items.length) { e.preventDefault(); active = Math.max(active - 1, 0); renderSearch(matches(searchInput.value)); }
      if (e.key === 'Enter') { var target = items[active] || items[0]; if (target) { e.preventDefault(); window.location.href = target.href; } }
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
