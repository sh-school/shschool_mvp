/* أسماءٌ مقروءةٌ لعناصر إدخالٍ يرسمها جانغو في لوحة الإدارة بلا اسم (OWN-21).

   كان فحصُ axe على 237 صفحةَ إدارة يجد 620 عقدةً بلا اسمٍ يقرؤه قارئُ الشاشة، كلُّها من أدوات
   جانغو لا من قوالبنا — فلا قالبَ يُعدَّل لها:
   - حقولُ التحرير داخل القائمة (list_editable): يرسمها `items_for_result` في بايثون بلا <label>
     (axe: label، select-name، label-title-only) → «اسمُ العمود — اسمُ الصفّ».
   - شقّا التاريخ والوقت (AdminSplitDateTime): «التاريخ:» نصٌّ عارٍ قبل الحقل لا <label>، وقالبُه
     `admin/widgets/split_datetime.html` لا يُستبدل لأنّ تطبيقَ الإدارة قبل تطبيقاتنا (axe: label)
     → «اسمُ الحقل — التاريخ».
   - صندوقُ select2 (autocomplete_fields): مسمّى بالقيمة المختارة وحدَها فيفرغ اسمُه ما لم يُختر شيء
     (axe: aria-input-field-name) → يُضاف إليه <label> الحقل، وإلى نصّ الاختيار داخلَه.
   - أيقونةُ البحث في الاختيار بين قائمتين (filter_horizontal): <span> عليه aria-label بلا دور
     (axe: aria-prohibited-attr) → role="img".
   - بدائلُ صور القيمة المنطقيّة وحقل البحث: `alt="True"` و`alt="Search"` بالإنجليزيّة → «نعم»/«لا» و«بحث».

   select2 والاختيارُ بين قائمتين يُنشآن بعد تحميل الصفحة، وصفوفُ «أضف آخر» تُضاف بالنقر، فيُراقَب
   تغيُّرُ الصفحة ويُسمّى كلُّ عنصرٍ حين يظهر. ولا يُمسّ عنصرٌ له اسمٌ أصلاً. */
(function () {
  'use strict';

  var LONG_NUMBER = /\d{8,}/g;  // رقمٌ شخصيٌّ أو وظيفيٌّ في اسم الصفّ يُستر كما في «آخر الإجراءات» (hide_ids)

  function clean(value) {
    return (value || '').replace(/\s+/g, ' ').replace(/[:：]\s*$/, '').trim();
  }
  function textOf(el) {
    return el ? clean(el.textContent) : '';
  }
  function hasName(el) {
    if (el.getAttribute('aria-label') || el.getAttribute('aria-labelledby')) return true;
    if (el.closest('label')) return true;
    return !!(el.id && document.querySelector('label[for="' + CSS.escape(el.id) + '"]'));
  }
  function name(el, label) {
    if (label && !hasName(el)) el.setAttribute('aria-label', label);
  }

  function nameListEditable(root) {
    root.querySelectorAll('#result_list').forEach(function (table) {
      var heads = table.querySelectorAll('thead tr th');
      table.querySelectorAll('tbody tr').forEach(function (row) {
        var rowName = textOf(row.querySelector('th')).replace(LONG_NUMBER, '••••');
        Array.prototype.forEach.call(row.children, function (cell, i) {
          // عنوانُ العمود وحدَه: ترويسةُ العمود المرتَّب تحمل أيضاً رقمَ أولويّة الفرز وروابطَه (.sortoptions)
          var column = textOf(heads[i] && (heads[i].querySelector('.text') || heads[i]));
          cell.querySelectorAll('input:not([type=hidden]), select, textarea').forEach(function (control) {
            name(control, rowName ? column + ' — ' + rowName : column);
          });
        });
      });
    });
  }

  function fieldLabel(control) {
    var row = control.closest('.form-row, td');
    if (!row) return '';
    return textOf(row.querySelector('legend')) || textOf(row.querySelector('label'));
  }
  function partLabel(control) {
    for (var node = control.previousSibling; node; node = node.previousSibling) {
      if (node.nodeType === Node.TEXT_NODE && clean(node.textContent)) return clean(node.textContent);
      if (node.nodeType === Node.ELEMENT_NODE && node.tagName !== 'BR') break;
    }
    return '';
  }
  function nameSplitDateTime(root) {
    root.querySelectorAll('p.datetime input').forEach(function (control) {
      var field = fieldLabel(control);
      var part = partLabel(control);
      name(control, field && part ? field + ' — ' + part : field || part);
    });
  }

  function nameSelect2(root) {
    root.querySelectorAll('.select2-selection[role="combobox"]').forEach(function (box) {
      var container = box.closest('.select2');
      var select = container && container.previousElementSibling;
      if (!select || !select.id) return;
      var label = document.querySelector('label[for="' + CSS.escape(select.id) + '"]');
      if (!label) return;
      if (!label.id) label.id = select.id + '__label';
      var ids = (box.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
      if (ids.indexOf(label.id) === -1) box.setAttribute('aria-labelledby', [label.id].concat(ids).join(' '));
      // وداخلَه نصُّ الاختيار بدور textbox (select2 4.1) بلا اسم: يُسمّى بالـ<label> نفسِه. وبـaria-labelledby
      // لا aria-label — فحين يُقرأ ضمن اسم الصندوق أعلاه تُقرأ قيمتُه المختارة لا اسمُ الحقل مكرَّراً.
      var shown = box.querySelector('.select2-selection__rendered[role="textbox"]');
      if (shown && !hasName(shown)) shown.setAttribute('aria-labelledby', label.id);
    });
  }

  function nameFilterIcons(root) {
    root.querySelectorAll('.search-label-icon[aria-label]:not([role])').forEach(function (icon) {
      icon.setAttribute('role', 'img');
    });
  }

  // بدائلُ الصور النصّيّة التي يكتبها جانغو بالإنجليزيّة ثابتةً بلا gettext: أيقونةُ القيمة المنطقيّة في القوائم
  // (`_boolean_icon` تكتب `alt="True"`)، وأيقونةُ حقل البحث (`alt="Search"` حرفيّةٌ في القالب) — فيقرؤها قارئُ الشاشة
  // بالإنجليزيّة وسطَ صفحةٍ عربيّة. القيمةُ المنطقيّةُ هنا `نعم`/`لا` كما يعرضها الباقي.
  var BOOLEAN_ALT = { 'True': 'نعم', 'False': 'لا', 'None': 'غير محدَّد' };
  function nameAlternatives(root) {
    root.querySelectorAll('img[alt="True"], img[alt="False"], img[alt="None"]').forEach(function (img) {
      img.setAttribute('alt', BOOLEAN_ALT[img.getAttribute('alt')]);
    });
    root.querySelectorAll('label[for="searchbar"] img[alt="Search"]').forEach(function (img) {
      img.setAttribute('alt', 'بحث');
    });
  }

  function run() {
    nameListEditable(document);
    nameSplitDateTime(document);
    nameSelect2(document);
    nameFilterIcons(document);
    nameAlternatives(document);
  }

  var pending = false;
  function schedule() {
    if (pending) return;
    pending = true;
    window.requestAnimationFrame(function () {
      pending = false;
      run();
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
  else run();
  window.addEventListener('load', run);
  new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true });
})();
