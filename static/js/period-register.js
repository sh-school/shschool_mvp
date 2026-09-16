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

  // الساعةُ الحيّة في كلّ عمودٍ لم يُثبَّت: ساعةُ الخادم لا ساعةُ الهاتف — فهاتفٌ
  // متأخّرٌ دقيقتين لا يُري وقتاً غيرَ الذي يُحفظ عند التثبيت. يُحسب الفرقُ مرّةً
  // عند التحميل ويُضاف كلَّ ثانية. والعمودُ المثبَّتُ وقتُه محفوظٌ من الخادم فلا يُمسّ.
  var skew = (parseInt(form.getAttribute('data-now'), 10) * 1000 || Date.now()) - Date.now();
  var zone = (form.getAttribute('data-offset') || '+0300').match(/([+-])(\d\d)(\d\d)/);
  var zoneMs = zone ? (zone[1] === '-' ? -1 : 1) * (parseInt(zone[2], 10) * 60 + parseInt(zone[3], 10)) * 60000 : 0;
  var clocks = document.querySelectorAll('[data-clock]');

  function two(n) { return (n < 10 ? '0' : '') + n; }

  function tick() {
    // بتوقيت المدرسة لا بتوقيت الجهاز: نُزيح اللحظةَ بفرق المنطقة ونقرأها بـUTC.
    var local = new Date(Date.now() + skew + zoneMs);
    var text = two(local.getUTCHours()) + ':' + two(local.getUTCMinutes()) + ':' + two(local.getUTCSeconds());
    clocks.forEach(function (clock) { clock.textContent = text; });
  }
  tick();
  if (clocks.length) window.setInterval(tick, 1000);

  var draft = read();
  if (draft) restore(draft);
  count();

  // لحظةُ النقرة على «متأخّر» تُحفظ بساعة الخادم: الدقائقُ منها لا من لحظة التثبيت.
  // والرجوعُ عن «متأخّر» يمحوها، والنقرةُ ثانيةً على المختار لا تُطلق change فلا تُغيّرها.
  form.addEventListener('change', function (event) {
    var radio = event.target;
    if (radio && radio.type === 'radio') {
      var tap = form.querySelector('[name="t-' + radio.name.slice(2) + '"]');
      if (tap) tap.value = radio.value === 'late' ? String(Math.floor((Date.now() + skew) / 1000)) : '';
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
        radio.checked = true;
        // «الكلُّ حاضر» و«غيابُ الكلّ» لا متأخّرَ بعدهما — فلا لحظةَ نقرةٍ تبقى.
        var tap = form.querySelector('[name="t-' + radio.name.slice(2) + '"]');
        if (tap) tap.value = '';
      });
      write(snapshot());
      count();
    });
  });
})();
