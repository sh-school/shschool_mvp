/**
 * استمارةُ متابعة المشرف الإداريّ (نموذج 19): صفوفُ التوصيات، ومسوّدةٌ محلّيّةٌ تلقائيّة (data-draft-key)، واسمُ اليوم.
 * المسوّدةُ تُسقط إن كان المحفوظُ في الخادم أحدثَ منها (data-draft-version)، وتُمسح بعد حفظٍ ناجح (data-draft-clear).
 * بلا شيفرةٍ مضمَّنة (CSP): كلُّ شيءٍ بسمات data-*.
 */
(function () {
  'use strict';

  function forget(key) {
    try { window.localStorage.removeItem(key); } catch (e) { /* لا تخزين */ }
  }

  var clearer = document.querySelector('[data-draft-clear]');
  var toClear = clearer ? (clearer.getAttribute('data-draft-clear') || '').trim() : '';
  if (toClear) {
    toClear.split(/\s+/).forEach(forget);
    // لئلّا يمسح تحديثُ الصفحة مسوّدةً كُتبت بعد الحفظ.
    window.history.replaceState(window.history.state, '', window.location.pathname);
  }

  var form = document.querySelector('[data-supfu-form]');
  if (!form) return;

  var key = form.getAttribute('data-draft-key');
  var version = form.getAttribute('data-draft-version');
  var list = form.querySelector('[data-supfu-recs]');
  var template = form.querySelector('[data-supfu-template]');
  var SKIP = /^(csrfmiddlewaretoken|supervisor|rec_id|rec_text|review_id)$/;

  function addRow(id, text) {
    var row = template.content.firstElementChild.cloneNode(true);
    row.querySelector('[name="rec_id"]').value = id || newId();
    row.querySelector('[name="rec_text"]').value = text || '';
    list.appendChild(row);
    return row;
  }

  // معرّفٌ ثابتٌ للصفّ الجديد فتبقى إعادةُ الإرسال متساويةَ الأثر.
  function newId() {
    return window.crypto && window.crypto.randomUUID ? window.crypto.randomUUID() : '';
  }

  function snapshot() {
    var fields = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || SKIP.test(el.name) || el.type === 'submit') return;
      if (el.type === 'radio') {
        if (el.checked) fields[el.name] = el.value;
        return;
      }
      fields[el.name] = el.value;
    });
    var recs = Array.prototype.map.call(list.children, function (row) {
      return [row.querySelector('[name="rec_id"]').value, row.querySelector('[name="rec_text"]').value];
    });
    return { v: version, fields: fields, recs: recs };
  }

  function save() {
    try { window.localStorage.setItem(key, JSON.stringify(snapshot())); } catch (e) { /* لا تخزين */ }
  }

  function restore() {
    var draft = null;
    try { draft = JSON.parse(window.localStorage.getItem(key) || 'null'); } catch (e) { draft = null; }
    if (!draft) return;
    if (draft.v !== version) { forget(key); return; }
    Object.keys(draft.fields || {}).forEach(function (name) {
      var found = form.querySelectorAll('[name="' + name + '"]');
      Array.prototype.forEach.call(found, function (el) {
        if (el.type === 'radio') el.checked = el.value === draft.fields[name];
        else el.value = draft.fields[name];
      });
    });
    list.textContent = '';
    (draft.recs || []).forEach(function (pair) { addRow(pair[0], pair[1]); });
    if (window.showToast) window.showToast('استُعيدت مسودة غير محفوظة من هذا الجهاز.', 'info');
  }

  restore();
  Array.prototype.forEach.call(list.querySelectorAll('[name="rec_id"]'), function (el) {
    if (!el.value) el.value = newId();
  });

  function showDay() {
    var input = form.querySelector('[name="follow_date"]');
    var out = form.querySelector('[data-supfu-day]');
    if (!input || !out || !input.value) return;
    var day = new Date(input.value + 'T00:00:00');
    out.textContent = day.toLocaleDateString('ar-QA', { weekday: 'long' });
  }
  showDay();

  form.addEventListener('input', save);
  form.addEventListener('change', function (event) {
    if (event.target.name === 'follow_date') showDay();
    save();
  });
  form.addEventListener('click', function (event) {
    if (event.target.closest('[data-supfu-add]')) {
      addRow('', '').querySelector('textarea').focus();
      save();
      return;
    }
    var remove = event.target.closest('[data-supfu-remove]');
    if (remove) {
      remove.closest('li').remove();
      save();
    }
  });
  // Enter في حقلٍ مفرد لا يُرسل الاستمارة؛ الحفظُ بنقر الزرّ.
  form.addEventListener('keydown', function (event) {
    var field = event.target;
    if (event.key === 'Enter' && field.tagName === 'INPUT') event.preventDefault();
  });
})();
