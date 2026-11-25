/**
 * تحديثٌ هادئ لقسم «قادمون إليك» وطابور الإدخال السريع — بلا فقدِ إدخالٍ ولا قفز.
 * - الدورةُ الزمنيّة (every) لا تُستبدل ما دام المستخدم يتفاعل: تركيزٌ على حقلٍ أو قائمة، أو لوحةُ زيارةٍ مفتوحة، أو تبويبٌ مخفيّ.
 * - تحديثُ clinic-visit-changed (بعد فعلٍ للممرّض نفسه) يمرّ دائماً.
 * لا بياناتٍ شخصيّةً تُقرأ أو تُخزَّن هنا.
 */
(function () {
  "use strict";
  var IDS = ["quick-incoming", "quick-queue"];
  var FIELDS = "select, input, textarea";

  function isLive(target) {
    return !!target && IDS.indexOf(target.id) !== -1;
  }

  function panelOpen() {
    var panel = document.getElementById("quick-panel");
    return !!panel && !!panel.querySelector("form");
  }

  function isInteracting() {
    var active = document.activeElement;
    if (active && active.matches && active.matches(FIELDS)) return true;
    return panelOpen();
  }

  function isChangeEvent(ev) {
    var cfg = ev.detail && ev.detail.requestConfig;
    var trig = cfg && cfg.triggeringEvent;
    return !!trig && trig.type === "clinic-visit-changed";
  }

  function hold(ev) {
    var target = ev.detail && (ev.detail.target || ev.detail.elt);
    if (!isLive(target) || isChangeEvent(ev)) return false;
    return document.hidden || isInteracting();
  }

  document.addEventListener("htmx:beforeRequest", function (ev) {
    if (hold(ev)) ev.preventDefault();
  });
  document.addEventListener("htmx:beforeSwap", function (ev) {
    if (hold(ev)) ev.detail.shouldSwap = false;
  });
})();
