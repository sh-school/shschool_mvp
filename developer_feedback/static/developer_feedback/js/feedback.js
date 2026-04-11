/* ==========================================================================
   Developer Feedback — Feature JS v1
   - Character counter for body textarea
   - Safe context JSON collector (whitelist only — no tokens, no PII)
   ========================================================================== */
(function () {
  "use strict";

  // ---------- 1) Character counter ----------
  function initCounter() {
    var textarea = document.querySelector("[data-df-counter-for]");
    if (!textarea) return;
    var counter = document.querySelector("[data-df-counter]");
    if (!counter) return;

    var max = parseInt(textarea.getAttribute("maxlength") || "4000", 10);

    function update() {
      var len = textarea.value.length;
      counter.textContent = len + " / " + max;
      if (len > max * 0.9) {
        counter.classList.add("df-counter-warn");
      } else {
        counter.classList.remove("df-counter-warn");
      }
    }

    textarea.addEventListener("input", update);
    update();
  }

  // ---------- 2) Safe context collector ----------
  // Whitelist approach — we NEVER read cookies, localStorage, or tokens.
  function collectContext() {
    try {
      // Never include query string (may contain tokens)
      var path = (window.location.pathname || "").split("?")[0];
      var viewport = window.innerWidth + "x" + window.innerHeight;
      var lang = document.documentElement.lang || "ar";
      var role = document.body.getAttribute("data-user-role") || "";

      return {
        url_path: path,
        viewport: viewport,
        language: lang,
        role: role,
        timestamp: new Date().toISOString(),
      };
    } catch (e) {
      return {};
    }
  }

  // Get a friendly browser label without exposing full UA details
  function getBrowserLabel() {
    try {
      var ua = navigator.userAgent || "";
      if (/Edg\//.test(ua)) return "Edge";
      if (/Chrome\//.test(ua) && !/OPR\//.test(ua)) return "Chrome";
      if (/Firefox\//.test(ua)) return "Firefox";
      if (/Safari\//.test(ua) && !/Chrome\//.test(ua)) return "Safari";
      if (/OPR\//.test(ua)) return "Opera";
      return "Unknown";
    } catch (e) {
      return "Unknown";
    }
  }

  function initContextField() {
    var field = document.querySelector('[name="context_json_raw"]');
    if (!field) return;

    var ctx = collectContext();
    // The hidden field only stores whitelisted keys the server accepts
    field.value = JSON.stringify(ctx);

    // Populate the preview box if present
    var preview = document.querySelector("[data-df-context-preview]");
    if (preview) {
      var html = "";
      html += "<dt>الصفحة الحالية</dt><dd>" + escapeHtml(ctx.url_path) + "</dd>";
      html += "<dt>الدور</dt><dd>" + escapeHtml(ctx.role || "—") + "</dd>";
      html += "<dt>وقت الإرسال</dt><dd>" + escapeHtml(ctx.timestamp) + "</dd>";
      html += "<dt>المتصفح</dt><dd>" + escapeHtml(getBrowserLabel() + " (" + ctx.viewport + ")") + "</dd>";
      preview.innerHTML = html;
    }
  }

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // ---------- Init on DOMContentLoaded ----------
  function init() {
    initCounter();
    initContextField();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
