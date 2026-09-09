/* exemption-grid.js — تظليلُ شبكة التفريغ في «إعدادات الجدول».
 *
 * الاستمارةُ القديمةُ كانت تضرب مصفوفةً: (الأيّامُ المختارة) × (الحصصُ
 * المختارة). فـ«الأحدَ الأولى والاثنينَ الثالثة» أربعُ خاناتٍ فيها لا
 * اثنتان — ولهذا سكنت قيودُ معلّمٍ واحدٍ عشرين تفريغاً منفصلاً.
 *
 * وهنا الخانةُ تُختار وحدَها: يُجمع المظلَّلُ في حقلٍ واحدٍ («يوم:حصّة»
 * مفصولةً بفواصل، و«يوم:*» يومٌ كامل) يقرؤه الخادم.
 *
 * والأحداثُ مفوَّضةٌ على المستند لا على الخانات: الشبكةُ تُستبدَل كلَّما
 * تغيّر المعلّم (HTMX)، فمستمعٌ لكلّ خانةٍ يموت مع أوّل استبدالٍ ويتراكم
 * مع كلّ واحد.
 */
(function () {
  'use strict';

  var FIELD = 'exemption-slots';

  function field() { return document.getElementById(FIELD); }
  function root() { return document.querySelector('[data-exg]'); }

  /** كلُّ ما ظُلِّل الآن — الخاناتُ ثمّ الأيّامُ الكاملة. */
  function picked(box) {
    var keys = [];
    box.querySelectorAll('.exg-all.is-picked').forEach(function (b) {
      keys.push(b.dataset.row + ':*');
    });
    box.querySelectorAll('.exg-cell.is-picked').forEach(function (b) {
      // خاناتُ يومٍ ظُلِّل كاملاً يغني عنها وسمُه، فلا تُرسَل مرّتين.
      var day = (b.dataset.slot || '').split(':')[0];
      if (keys.indexOf(day + ':*') === -1) keys.push(b.dataset.slot);
    });
    return keys;
  }

  /** العدّادُ الحيّ: الخاناتُ الباقيةُ بعد التظليل مقابلَ النصاب. */
  function sync() {
    var box = root();
    if (!box) return;
    var input = field();
    var keys = picked(box);
    if (input) input.value = keys.join(',');

    var live = box.querySelector('[data-exg-live]');
    if (!live) return;
    if (!box.dataset.load) { live.hidden = true; return; }
    var allowance = parseInt(box.dataset.allowance || '0', 10);
    var blocked = parseInt(box.dataset.blocked || '0', 10);

    var taken = box.querySelectorAll('.exg-cell.is-picked').length;
    if (!taken) { live.hidden = true; return; }

    // القاعدةُ صريحة: خاناتُ الأسبوع − النصاب = ما يجوز تفريغُه. والمفرَّغُ
    // سلفاً مطروحٌ منه، والمختارُ الآن يُطرح كذلك — فما بقي هو ما يُقبل.
    var left = allowance - blocked - taken;
    var over = left < 0;
    var tight = !over && left <= 2;
    live.hidden = false;
    live.textContent = over
      ? 'ستُفرَّغ ' + taken + ' خانة — تتجاوز المسموحَ بـ' + (-left) + '؛ لن تُحفظ.'
      : 'ستُفرَّغ ' + taken + ' خانة — يبقى مسموحاً ' + left + (tight ? ' فقط.' : '.');
    live.className = 'exg-live ' + (over ? 'exg-impossible' : tight ? 'exg-tight' : 'exg-ok');
  }

  /** يظلّل خانةً أو يرفع تظليلَها — والمفرَّغةُ سلفاً لا تُختار. */
  function toggleCell(cell, force) {
    if (cell.dataset.exempt) return;
    var on = force === undefined ? !cell.classList.contains('is-picked') : force;
    cell.classList.toggle('is-picked', on);
    cell.setAttribute('aria-pressed', on ? 'true' : 'false');
  }

  function toggleRow(btn) {
    var box = root();
    if (!box) return;
    var on = !btn.classList.contains('is-picked');
    btn.classList.toggle('is-picked', on);
    var row = btn.closest('tr');
    if (!row) return;
    row.querySelectorAll('.exg-cell').forEach(function (cell) { toggleCell(cell, on); });
  }

  // ── السحب: ضغطةٌ ثمّ مرورٌ يظلّل ما يُمَرّ عليه بحالة أوّل خانة ──
  var dragging = false;
  var dragState = false;

  document.addEventListener('pointerdown', function (e) {
    var cell = e.target.closest ? e.target.closest('.exg-cell') : null;
    if (!cell || cell.dataset.exempt) return;
    dragging = true;
    dragState = !cell.classList.contains('is-picked');
    toggleCell(cell, dragState);
    sync();
  });

  document.addEventListener('pointerover', function (e) {
    if (!dragging) return;
    var cell = e.target.closest ? e.target.closest('.exg-cell') : null;
    if (!cell) return;
    toggleCell(cell, dragState);
    sync();
  });

  document.addEventListener('pointerup', function () { dragging = false; });
  document.addEventListener('pointercancel', function () { dragging = false; });

  document.addEventListener('click', function (e) {
    var all = e.target.closest ? e.target.closest('.exg-all') : null;
    if (all) { toggleRow(all); sync(); }
  });

  // لوحةُ المفاتيح: المسافةُ والإدخالُ على الخانة المركَّز عليها.
  document.addEventListener('keydown', function (e) {
    if (e.key !== ' ' && e.key !== 'Enter') return;
    var cell = document.activeElement;
    if (!cell || !cell.classList || !cell.classList.contains('exg-cell')) return;
    e.preventDefault();
    toggleCell(cell);
    sync();
  });

  // شبكةٌ جديدةٌ بعد تبديل المعلّم: الاختيارُ القديمُ لا يُنقَل إليها.
  document.body.addEventListener('htmx:afterSwap', function (e) {
    if (e.target && e.target.id === 'exemption-grid') {
      var input = field();
      if (input) input.value = '';
      sync();
    }
  });

  document.addEventListener('DOMContentLoaded', sync);
})();
