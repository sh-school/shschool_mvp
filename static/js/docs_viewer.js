/* عارضُ md: تبديلُ الصفحة (page-nav.js) يستبدل main-content كاملاً، فيُعاد بناءُ
   الشجرة وصندوقِ البحث من جديدٍ مع كلّ تنقّل — هذا الملفُّ يُعيد وصلَهما، ويُبقي
   الملفَّ الحاليَّ ظاهراً في الشجرة (ملاحظةُ المالك: لا تعود إلى الأعلى). */
(function () {
  function scrollCurrentIntoView() {
    var current = document.querySelector('.docs-tree__file.is-current');
    if (current) current.scrollIntoView({ block: 'nearest' });
  }

  // ── الفلترةُ الفوريّة بالاسم/العنوان (smartMatch من base.js) ──────────────
  function applyNameFilter(input) {
    var q = input.value;
    var anyShown = false;
    document.querySelectorAll('[data-filter-row]').forEach(function (row) {
      var ok = window.smartMatch ? window.smartMatch(q, row.textContent || '') : true;
      row.style.display = ok ? '' : 'none';
      if (ok) anyShown = true;
      if (ok && q) {
        var d = row.closest('details');
        while (d) { d.open = true; d = d.parentElement ? d.parentElement.closest('details') : null; }
      }
    });
    return anyShown;
  }

  // ── بحثُ المحتوى (خادميّ، مُهيَّأٌ بتأخير) ─────────────────────────────────
  var searchTimer = null;
  var searchAbort = null;
  function runContentSearch(query) {
    var box = document.getElementById('docs-search-results');
    if (!box) return;
    if (!query || query.trim().length < 2) {
      box.hidden = true;
      box.innerHTML = '';
      return;
    }
    if (searchAbort) searchAbort.abort();
    searchAbort = new AbortController();
    fetch('/docs/_search/?q=' + encodeURIComponent(query), { signal: searchAbort.signal, headers: { Accept: 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var results = data.results || [];
        box.hidden = false;
        if (!results.length) {
          box.innerHTML = '<p class="ui-note">لا نتائجَ في المحتوى لـ«' + escapeHtml(query) + '»</p>';
          return;
        }
        var html = '<p class="docs-search-results__label">نتائجُ البحث في المحتوى (' + results.length + ')</p><ul class="plain-list">';
        results.forEach(function (r) {
          html += '<li class="plain-list__row"><a class="plain-list__main" href="' + r.url + '">'
            + '<span class="plain-list__title">' + escapeHtml(r.title) + '</span>'
            + '<span class="plain-list__sub">' + escapeHtml(r.snippet) + '</span>'
            + '</a></li>';
        });
        html += '</ul>';
        box.innerHTML = html;
      })
      .catch(function (err) { if (err.name !== 'AbortError') box.hidden = true; });
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // ── بحثٌ داخل محتوى الملفّ المفتوح — تظليلٌ حيٌّ وتنقّلٌ بين المطابقات ──────
  var contentMatches = [];
  var contentActiveIdx = -1;

  function clearContentHighlights() {
    var body = document.getElementById('docs-content-body');
    if (!body) return;
    body.querySelectorAll('mark.docs-highlight').forEach(function (m) {
      var parent = m.parentNode;
      parent.replaceChild(document.createTextNode(m.textContent), m);
      parent.normalize();
    });
    contentMatches = [];
    contentActiveIdx = -1;
  }

  function highlightContent(query) {
    clearContentHighlights();
    var body = document.getElementById('docs-content-body');
    var countEl = document.getElementById('docs-content-search-count');
    var prevBtn = document.getElementById('docs-content-search-prev');
    var nextBtn = document.getElementById('docs-content-search-next');
    if (!body) return;
    query = (query || '').trim();
    if (!query) {
      if (countEl) countEl.hidden = true;
      if (prevBtn) prevBtn.hidden = true;
      if (nextBtn) nextBtn.hidden = true;
      return;
    }
    var needle = query.toLowerCase();
    // مشيٌ على عقد النصّ وحدَها — يُبقي الوسومَ المحيطة (روابط وكتلَ شيفرةٍ
    // وتشديداً) سليمةً، فلا يُعاد بناءُ DOM المحتوى كلِّه لأجل التظليل.
    var walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        var tag = node.parentNode && node.parentNode.nodeName;
        if (tag === 'SCRIPT' || tag === 'STYLE') return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var textNodes = [];
    var n;
    while ((n = walker.nextNode())) textNodes.push(n);

    textNodes.forEach(function (node) {
      var text = node.nodeValue;
      var lower = text.toLowerCase();
      if (lower.indexOf(needle) === -1) return;
      var frag = document.createDocumentFragment();
      var pos = 0, idx;
      while ((idx = lower.indexOf(needle, pos)) !== -1) {
        if (idx > pos) frag.appendChild(document.createTextNode(text.slice(pos, idx)));
        var mark = document.createElement('mark');
        mark.className = 'docs-highlight';
        mark.textContent = text.slice(idx, idx + query.length);
        frag.appendChild(mark);
        contentMatches.push(mark);
        pos = idx + query.length;
      }
      if (pos < text.length) frag.appendChild(document.createTextNode(text.slice(pos)));
      node.parentNode.replaceChild(frag, node);
    });

    if (countEl) { countEl.hidden = false; }
    if (prevBtn) prevBtn.hidden = contentMatches.length === 0;
    if (nextBtn) nextBtn.hidden = contentMatches.length === 0;
    goToMatch(0);
  }

  function goToMatch(idx) {
    var countEl = document.getElementById('docs-content-search-count');
    if (!contentMatches.length) {
      if (countEl) countEl.textContent = '0/0';
      return;
    }
    if (contentActiveIdx >= 0 && contentMatches[contentActiveIdx]) {
      contentMatches[contentActiveIdx].classList.remove('is-active');
    }
    contentActiveIdx = ((idx % contentMatches.length) + contentMatches.length) % contentMatches.length;
    var active = contentMatches[contentActiveIdx];
    active.classList.add('is-active');
    active.scrollIntoView({ block: 'center' });
    if (countEl) countEl.textContent = (contentActiveIdx + 1) + '/' + contentMatches.length;
  }

  // ── الوصلُ — مرّةً لكلّ عقدةِ حقلٍ جديدة (تبديلُ main-content يستبدلها) ────
  function wire() {
    var input = document.getElementById('docs-search-input');
    if (input && !input.dataset.docsSearchWired) {
      input.dataset.docsSearchWired = '1';
      input.addEventListener('input', function () {
        applyNameFilter(input);
        clearTimeout(searchTimer);
        searchTimer = setTimeout(function () { runContentSearch(input.value); }, 250);
      });
    }

    var contentInput = document.getElementById('docs-content-search-input');
    if (contentInput && !contentInput.dataset.docsSearchWired) {
      contentInput.dataset.docsSearchWired = '1';
      var contentTimer = null;
      contentInput.addEventListener('input', function () {
        clearTimeout(contentTimer);
        contentTimer = setTimeout(function () { highlightContent(contentInput.value); }, 150);
      });
      contentInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); goToMatch(contentActiveIdx + (e.shiftKey ? -1 : 1)); }
        if (e.key === 'Escape') { contentInput.value = ''; clearContentHighlights(); }
      });
      var prevBtn = document.getElementById('docs-content-search-prev');
      var nextBtn = document.getElementById('docs-content-search-next');
      if (prevBtn) prevBtn.addEventListener('click', function () { goToMatch(contentActiveIdx - 1); });
      if (nextBtn) nextBtn.addEventListener('click', function () { goToMatch(contentActiveIdx + 1); });
    }
  }

  document.addEventListener('htmx:afterSwap', function () {
    contentMatches = [];
    contentActiveIdx = -1;
    wire();
    scrollCurrentIntoView();
  });
  wire();
})();
