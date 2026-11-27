/* تبويباتُ ملفّ الطالب، وجلبُ تبويب «العيادة» عند النقر (CLN-03). */
(function () {
  document.querySelectorAll('.tab-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.tab-btn').forEach(function (b) {
        b.classList.remove('active');
        b.setAttribute('aria-selected', 'false');
      });
      document.querySelectorAll('.tab-content').forEach(function (c) { c.classList.remove('active'); });
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');
      document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    });
  });

  var clinic = document.getElementById('clinic-tab-btn');
  var body = document.getElementById('clinic-tab-body');
  var error = document.getElementById('clinic-tab-error');
  if (!clinic || !body || !error) return;

  /* جُلب المحتوى فلا طلبَ ثانياً (كلُّ طلبٍ سطرُ تدقيق)؛ وبعد الفشل يعيد النقرُ المحاولة. */
  clinic.addEventListener('htmx:confirm', function (event) {
    if (body.querySelector('[data-clinic-loaded]')) event.preventDefault();
  });
  clinic.addEventListener('htmx:beforeRequest', function () { error.hidden = true; });
  ['htmx:responseError', 'htmx:sendError', 'htmx:timeout'].forEach(function (name) {
    clinic.addEventListener(name, function () { error.hidden = false; });
  });
})();
