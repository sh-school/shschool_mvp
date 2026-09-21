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
  nav.addEventListener('mouseleave', function () { if (!pinned) closeAll(null); });
  document.addEventListener('click', function () { pinned = null; closeAll(null); });
})();
