// الفلاتر تُرسَل بـHTMX بلا تغيير الرابط، فيُقرأ المعروضُ من الحقول لحظةَ النقر لا من رابطٍ ثابتٍ كُتب عند فتح الصفحة
// وزرّا Excel وPDF يقرآن الحقولَ نفسَها فيخرج الملفّان بالمعروض
// المعالجُ على window (التقاط) فيسبق معالجَ مركز التصدير على document، وإلّا قرأ الرابطَ القديمَ قبل تحديثه
window.addEventListener("click", function (event) {
  var link = event.target.closest("#student-list-xlsx, #student-list-pdf");
  if (!link) return;
  var params = new URLSearchParams();
  ["q", "status", "grade", "section", "parent_status"].forEach(function (name) {
    var field = document.querySelector("[name='" + name + "']");
    if (field && field.value) params.set(name, field.value);
  });
  link.setAttribute("href", link.getAttribute("href").split("?")[0] + "?" + params.toString());
}, true);
