/**
 * quality.js — SchoolOS v6
 * وظائف وحدة الجودة: لوحة التحكم · لجنة المراجعة · الرسوم البيانية
 */
'use strict';

/* ── حلقة نسبة الإنجاز الدائرية (dashboard) ─────────────── */
window.initQualityRing = function(targetPct) {
  var ring  = document.getElementById('quality-ring');
  var label = document.getElementById('quality-pct-label');
  if (!ring || !label) return;

  var start    = performance.now();
  var duration = 900;

  function animate(ts) {
    var elapsed  = ts - start;
    var progress = Math.min(elapsed / duration, 1);
    var eased    = 1 - Math.pow(1 - progress, 3);   // ease-out cubic
    var current  = Math.round(targetPct * eased);
    ring.setAttribute('stroke-dasharray', current + ' ' + (100 - current));
    label.textContent = current + '%';
    if (progress < 1) requestAnimationFrame(animate);
  }
  requestAnimationFrame(animate);
};


/* ── فلترة إجراءاتي (dashboard) ──────────────────────────── */
window.filterProcs = function(status) {
  var list = document.getElementById('procedures-list');
  if (!list) return;

  list.querySelectorAll('a[data-status]').forEach(function(row) {
    row.style.display = (status === 'all' || row.dataset.status === status) ? '' : 'none';
  });

  var tabs = {
    all: 'tab-all',
    InProgress: 'tab-in-progress',
    NotStarted: 'tab-not-started',
    Completed:  'tab-completed'
  };
  Object.keys(tabs).forEach(function(key) {
    var btn = document.getElementById(tabs[key]);
    if (!btn) return;
    btn.className = (key === status) ? 'btn-primary btn-sm' : 'btn-secondary btn-sm';
  });
};


/* ── نموذج إضافة عضو لجنة (committee) ────────────────────── */
window.toggleForm = function() {
  var form = document.getElementById('add-form');
  var icon = document.getElementById('form-toggle-icon');
  if (!form) return;
  var show = form.classList.toggle('is-open');
  form.style.display = show ? 'block' : 'none';
  if (icon) icon.textContent = show ? '－' : '＋';
};

window.fillJobTitle = function(select) {
  var name  = select.options[select.selectedIndex] && select.options[select.selectedIndex].dataset.name || '';
  var input = document.getElementById('job_title_input');
  if (name && input && !input.value) input.value = name;
};
