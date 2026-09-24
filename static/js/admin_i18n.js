/* تكملةُ ترجمة جانغو العربيّة لأداة الاختيار بين قائمتين (filter_horizontal) في الإدارة (OWN-19).

   جانغو 5.2 غيّر نصوصَ هذه الأداة (SelectFilter2.js) وبقي كتالوجُه العربيُّ على نصوصها القديمة، فكانت
   الأداةُ تقول «Choose all المجموعات» و«Remove %s by selecting them…» — وأسماءُ الحقول وحدَها عربيّة.

   ولا تصل ترجمةٌ بملفّ .po إلى الإنتاج (compilemessages في preDeploy، وقرصُه غيرُ قرص الخدمة)، ولا يُبلغ
   كائنُ الكتالوج نفسُه: `jquery.init.js` يستبدل `window.django` بعد `jsi18n` فيبقى الكتالوجُ في إغلاق
   الدالّتين. فتُغلَّف `gettext` و`ngettext`: ما أعاده الكتالوجُ بنصّه الإنجليزيّ كما هو يُعطى ترجمتَه هنا،
   وما ترجمه جانغو يبقى ترجمتَه — فإن أكمل جانغو كتالوجَه غلبت ترجمتُه.

   يُحمَّل مؤجَّلاً: بعد `jsi18n` (متزامنٌ في الترويسة) وقبل تهيئة الأداة عند `load` حين تُطلب النصوص.
   والقائمةُ يحرسها tests/test_admin_js_arabic.py: كلُّ نصٍّ في SelectFilter2.js بلا ترجمةٍ عربيّة له ترجمةٌ هنا. */
(function () {
  'use strict';
  if (typeof window.gettext !== 'function') return;  // صفحةٌ بلا jsi18n: لا أداةَ ولا نصَّ يُترجم

  var AR = {
    'Choose all %s': 'اختر كلّ %s',
    'Remove all %s': 'أزل كلّ %s',
    'Choose selected %s': 'اختر %s المحدَّدة',
    'Remove selected %s': 'أزل %s المحدَّدة',
    '(click to clear)': '(انقر للمسح)',
    'Choose %s by selecting them and then select the "Choose" arrow button.':
      'اختر %s بتحديدها ثمّ بالضغط على سهم «اختيار».',
    'Remove %s by selecting them and then select the "Remove" arrow button.':
      'أزل %s بتحديدها ثمّ بالضغط على سهم «إزالة».',
    'Type into this box to filter down the list of selected %s.': 'اكتب في هذا الصندوق لتصفية قائمة %s المختارة.',
    // مفردُ ngettext وجمعُه بصيغةٍ واحدةٍ تصحّ لكلّ عدد
    '%s selected option not visible': 'مختارٌ غيرُ ظاهرٍ في القائمة: %s'
  };

  function arabic(msgid) {
    return Object.prototype.hasOwnProperty.call(AR, msgid) ? AR[msgid] : undefined;
  }

  var gettext0 = window.gettext;
  window.gettext = function (msgid) {
    var value = gettext0(msgid);
    return value === msgid && arabic(msgid) !== undefined ? arabic(msgid) : value;
  };

  if (typeof window.ngettext === 'function') {
    var ngettext0 = window.ngettext;
    window.ngettext = function (singular, plural, count) {
      var value = ngettext0(singular, plural, count);
      var untranslated = value === singular || value === plural;
      return untranslated && arabic(singular) !== undefined ? arabic(singular) : value;
    };
  }
})();
