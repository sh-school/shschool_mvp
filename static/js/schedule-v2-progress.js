/* شريطُ تقدّم توليد الجدول V2 — كتلةُ pending_generation في templates/schedule/smart_schedule.html.
   يستطلع `data-url` (schedule_v2_progress) كلَّ 5 ثوانٍ بأمر المالك. العقد: operations/scheduler_v2/progress.py::read_progress.
   الشريطُ يعرض المنقضي من مهلة الحلّ لا «نسبةَ إنجاز» (الحلّال لا يعرف متى ينتهي)؛ والمتبقّي سقفٌ لا وعد.
   كلُّ نصٍّ يدخل الصفحةَ بـtextContent. إعادةُ تحميل الصفحة عند الانتهاء يتولّاها استطلاعُ smart_generate_status. */
(function () {
  'use strict';
  var root = document.getElementById('gen-progress');
  if (!root) return;
  var INTERVAL = 5000;
  var MAX_MISSES = 5;
  var $ = function (name) { return root.querySelector('[data-gp="' + name + '"]'); };
  var fill = $('fill'), meter = $('meter');
  var misses = 0;

  function fmt(sec) {
    sec = Math.max(0, Math.round(Number(sec) || 0));
    var m = Math.floor(sec / 60), s = sec % 60;
    return m + ':' + (s < 10 ? '0' : '') + s;
  }
  function put(name, text) { var e = $(name); if (e) e.textContent = text; }
  function tone(cls) {
    fill.classList.remove('pf-success', 'pf-warning', 'pf-danger');
    if (cls) fill.classList.add(cls);
  }

  function render(d) {
    root.hidden = false;
    var known = typeof d.elapsed_s === 'number' && d.max_s > 0;
    var pct = known ? Math.min(100, d.elapsed_s / d.max_s * 100) : 0;
    if (d.done && d.generation_status === 'draft') pct = 100;
    fill.style.setProperty('--progress-w', pct.toFixed(1) + '%');
    meter.setAttribute('aria-valuenow', String(Math.round(pct)));
    put('state', d.state_label || '');
    put('elapsed', known ? fmt(d.elapsed_s) : '—');
    put('remaining', known ? fmt(d.remaining_s) : '—');
    put('solutions', d.solutions == null ? '—' : String(d.solutions));
    put('objective', d.objective == null ? 'لا حلّ بعد' : String(d.objective));
    put('gap', d.gap_pct == null ? '—' : d.gap_pct + '٪');
    var final = $('final');
    if (d.generation_status === 'failed' || d.state === 'failed') {
      tone('pf-danger');
      final.hidden = false;
      final.textContent = 'انتهى بالفشل' + (d.error ? ' — ' + d.error : '');
    } else if (d.generation_status === 'draft') {
      tone('pf-success');
      final.hidden = false;
      final.textContent = 'انتهى: مسوّدةٌ جاهزةٌ للمراجعة — تُحدَّث الصفحةُ…';
    } else {
      tone('');
      final.hidden = true;
    }
    $('offline').hidden = true;
  }

  function poll() {
    fetch(root.dataset.url, { headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) throw new Error('bad');
        misses = 0;
        render(d);
        var terminal = d.generation_status === 'draft' || d.generation_status === 'failed' ||
          d.generation_status === 'approved' || d.generation_status === 'archived';
        if (!terminal) setTimeout(poll, INTERVAL);
      })
      .catch(function () {
        $('offline').hidden = false;
        if (++misses < MAX_MISSES) setTimeout(poll, INTERVAL);
      });
  }
  poll();
})();
