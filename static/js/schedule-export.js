/**
 * تصديرُ الجدول (PDF/Excel) بإشعارٍ عائمٍ لا بصفحة متابعة.
 *
 * الرابطُ الموسوم `data-export-job` يبدأ المهمّةَ الخلفيّةَ (`X-Requested-With`)، فيردّ الخادمُ
 * JSON فيه رابطُ الحالة؛ ثمّ يُتابَع بإشعارٍ عائمٍ «جارٍ التحضير» كلَّ ثانيتين، فإذا جهز
 * نُزِّل الملفُّ في الخلفيّة والصفحةُ في مكانها، وإن فشل ظهر السببُ في إشعارٍ أحمر.
 * وبلا `showToast` (ورقةٌ مستقلّةٌ بلا base.js) يُترك الرابطُ لسلوكه — صفحةُ المتابعة.
 *
 * والورقةُ المستقلّة (print_schedule.html) تُحيل تصديرَها إلى هذه الصفحة بـ`?export=pdf|excel`:
 * يُبدأ التصديرُ هنا عند التحميل ثمّ يُحذف الوسيطُ من الرابط، فلا يتكرّر عند التحديث.
 */
(function () {
  'use strict';

  var POLL_MS = 2000;
  // أطولُ من مهلة الخادم (3 دقائق) بقليل: الخادمُ يُفشل العالقَ برسالةٍ فتصل، لا مهلةً صامتة.
  var GIVE_UP_MS = 200000;

  function toaster(name) {
    if (typeof window[name] === 'function') return window[name];
    try {
      if (window.parent && window.parent !== window && typeof window.parent[name] === 'function') {
        return window.parent[name];
      }
    } catch (e) { /* إطارٌ من أصلٍ آخر */ }
    return null;
  }

  function toast(msg, type, duration) {
    var fn = toaster('showToast');
    return fn ? fn(msg, type, duration) : null;
  }

  function dismiss(el) {
    var fn = toaster('dismissToast');
    if (el && fn) fn(el);
  }

  function filenameFrom(response) {
    var cd = response.headers.get('Content-Disposition') || '';
    var star = /filename\*=UTF-8''([^;]+)/i.exec(cd);
    if (star) {
      try { return decodeURIComponent(star[1]); } catch (e) { /* يسقط إلى الاسم العامّ */ }
    }
    return 'export';
  }

  function save(url) {
    return fetch(url, { credentials: 'same-origin' }).then(function (response) {
      if (!response.ok) throw new Error('download');
      return response.blob().then(function (blob) {
        var href = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = href;
        a.download = filenameFrom(response);
        a.hidden = true;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.setTimeout(function () { URL.revokeObjectURL(href); }, 60000);
      });
    });
  }

  function follow(statusUrl, waiting, started) {
    fetch(statusUrl + '?format=json', { credentials: 'same-origin' })
      .then(function (response) {
        if (!response.ok) throw new Error('status');
        return response.json();
      })
      .then(function (data) {
        if (data.status === 'done') {
          dismiss(waiting);
          return save(statusUrl).then(function () {
            toast('الملفّ جاهز — بدأ التنزيل.', 'success');
          });
        }
        if (data.status === 'failed') {
          dismiss(waiting);
          toast('تعذّر التصدير: ' + (data.error || 'خطأ غير متوقَّع.'), 'danger');
          return null;
        }
        if (Date.now() - started > GIVE_UP_MS) {
          dismiss(waiting);
          toast('تأخّر تحضير الملفّ — أعِد المحاولة بعد قليل.', 'danger');
          return null;
        }
        window.setTimeout(function () { follow(statusUrl, waiting, started); }, POLL_MS);
        return null;
      })
      .catch(function () {
        dismiss(waiting);
        toast('تعذّر تنزيل الملفّ — حاول مرّةً أخرى.', 'danger');
      });
  }

  function start(link) {
    if (link.getAttribute('aria-busy') === 'true') return;
    link.setAttribute('aria-busy', 'true');
    // 0 = يبقى حتى يُغلَق: يُغلقه `dismiss` عند الجاهزية أو الفشل أو انتهاء الانتظار.
    var waiting = toast('جارٍ تحضير الملفّ… سيُنزَّل تلقائياً عند الجاهزية.', 'info', 0);
    fetch(link.href, {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
    })
      .then(function (response) {
        if (!response.ok) throw new Error('start');
        return response.json();
      })
      .then(function (data) { follow(data.status_url, waiting, Date.now()); })
      .catch(function () {
        dismiss(waiting);
        toast('تعذّر بدء التصدير — حاول مرّةً أخرى.', 'danger');
      })
      .then(function () { link.removeAttribute('aria-busy'); });
  }

  // طورُ الالتقاط: قبل معالج app-mode.js الذي يفتح الملفّ بقائمة المشاركة على أجهزة اللمس.
  document.addEventListener('click', function (event) {
    var link = event.target.closest && event.target.closest('a[data-export-job]');
    if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey) return;
    if (!toaster('showToast')) return; // بلا إشعارٍ عائمٍ يبقى الرابطُ على سلوكه (صفحة المتابعة)
    event.preventDefault();
    start(link);
  }, true);

  // تصديرٌ طلبته الورقةُ المستقلّة (`?export=pdf|excel`) — السكربتُ `defer` فالصفحةُ مرسومة.
  var params = new URLSearchParams(window.location.search);
  var kind = params.get('export');
  if (kind) {
    params.delete('export');
    var rest = params.toString();
    window.history.replaceState(null, '', window.location.pathname + (rest ? '?' + rest : ''));
    var requested = document.querySelector('a[data-export-job="' + (kind === 'excel' ? 'excel' : 'pdf') + '"]');
    if (requested && toaster('showToast')) start(requested);
  }
})();
