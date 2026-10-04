# التحقّقُ البصريّ بالدور قبل «جاهزٌ للمعاينة»

متى تقرأ هذا الملف: قبل أن تعلن عملاً يلمس قالباً أو CSS أو JS «جاهزاً للمعاينة»؛ وحين يردّ المالكُ عيباً بصريّاً (تداخل، معطَّلٌ بلا تفسير، اقتطاع، فراغ، تباعدٌ متفاوت).

المصادر: `docs/web_design_mastery_upgrade_2026-10-04.html` (0104، الإصدار 2)، وطريقةُ القياس في `schoolos-preview-8500` ← `03-measuring-protected-pages.md`، وعقدُ «جاهز» في `02-review-item-format.md` §1، ولقطاتُ الهويّة الاستشاريّة `.github/workflows/visual-snapshots.yml` (VI-13)، واختبارُ اللوحة `tests/e2e/test_dashboard_fits_1366_live.py`.

الواقعة: ردّ المالكُ «تداخل القوائم» (W-20261004-014)، وعُرضت صفحةٌ على 8500 ثمّ أُصلح فيها تداخلٌ بصريٌّ بزرّ الخروج (ملاحظة 17:03). العيبُ اكتُشف عند المالك لا عند المنفّذ. هذا الملفّ يجعل الفحصَ خطوةً في المهارة لا ارتجالاً.

## 1) الأجهزة والأدوار
- الأجهزةُ الأربعة نهاراً وليلاً (الخطوة 5 في `SKILL.md`): 1366×768 و1920×1080 ولوحيّ ~768×1024 و375×812. القياسُ بالطريقة في `03-measuring-protected-pages.md` (لقطةٌ ساكنة + `resize_window` + `scrollWidth - innerWidth`).
- **لكلّ دورٍ يرى الصفحةَ**، لا للدور الذي تجرّب به وحده: ما يراه المعلّمُ غيرُ ما يراه مشرفُ الجناح. اكتب في العقد أيَّ دورٍ قِست به، وما لم تقِسه بدوره اكتبه «لم يُقَس».

## 2) مصفوفةُ الحالات
لكلّ مكوّنٍ تفاعليٍّ في الصفحة تحقّق من الحالات التي تنطبق عليه: افتراضيّ، مرور، تركيز، ضغط، **معطَّل**، تحميل، **فارغ**، خطأ، محدَّد.
- **كلُّ معطَّلٍ له سببٌ ظاهر** (نصٌّ مجاور أو `title`/`aria-describedby`/`data-why`): زرٌّ مطفأٌ بلا تفسير يكسر «ظهورَ حالة النظام» ويُرى عيباً عند المالك.
- الحالةُ الفارغةُ `empty_state` (انظر 20)، والتحميلُ والخطأُ بمكوّنات المنصّة لا بنصٍّ خام.

## 3) التداخل والاقتطاع والإيقاع
- لا يتقاطع عنصران تفاعليّان في مستطيليهما (أزرارٌ وقوائم)، ولا يُقصّ نصٌّ داخل حاوٍ بلا `text-overflow: ellipsis` مقصود.
- **إيقاعُ المسافات**: الأشقّاءُ المتجاورون يفصلهم رمزُ تباعدٍ واحد (`var(--sp-*)`)؛ تباعدٌ غيرُ موحَّدٍ بين أشقّاء من نوعٍ واحد عيب. يُقاس بـ`getBoundingClientRect()` للأشقّاء الأوّل فالثاني فالثالث.
- هذه الفحوصُ لا تغني عن حرّاس CI (`95-checklist.md`) ولا عن معاينة المالك.

## 4) المسبار (مسودّة — غيرُ معتمدة)
**الحالة:** مسودّةٌ فُحص تركيبُها بـ`node` فقط ولم تُجرَّب على صفحةٍ حقيقيّة؛ **لا تُعدّ إلزاماً ولا يُحتجّ بدقّتها** قبل تجربتها على لوحة المعلّم (W-20261003-038) واعتماد 0301. حتى ذلك الحين تقبل خانةُ «نتيجة المسبار» في العقد: «لم يُشغَّل — المسبار قيد التجربة»، وتشغيلُه طوعيّ ومخرجُه يُلصق إن شُغّل.
يُشغَّل في `javascript_tool` على الصفحة المفتوحة (بعد تحديد العرض):
```js
(() => {
  const vis = (e) => {
    const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const clip = (e) => e.outerHTML.replace(/\s+/g, ' ').slice(0, 70);
  const ctl = [...document.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea,[role=button],[role=tab],summary')].filter(vis);
  const overlaps = [];
  for (let i = 0; i < ctl.length; i++) {
    for (let j = i + 1; j < ctl.length; j++) {
      const a = ctl[i], b = ctl[j];
      if (a.contains(b) || b.contains(a)) continue;
      const p = a.getBoundingClientRect(), q = b.getBoundingClientRect();
      const w = Math.min(p.right, q.right) - Math.max(p.left, q.left);
      const h = Math.min(p.bottom, q.bottom) - Math.max(p.top, q.top);
      if (w > 1 && h > 1) overlaps.push({ a: clip(a), b: clip(b), w: Math.round(w), h: Math.round(h) });
    }
  }
  const unexplained = [...document.querySelectorAll('[disabled],[aria-disabled="true"]')].filter(vis).filter((e) =>
    !(e.title || e.getAttribute('aria-describedby') || e.getAttribute('data-why'))).map(clip);
  const clipped = [...document.querySelectorAll('body *')].filter((e) => vis(e) && e.children.length === 0 && e.textContent.trim() &&
    e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX !== 'visible' && getComputedStyle(e).textOverflow !== 'ellipsis').map(clip);
  return { pageOverflowX: document.documentElement.scrollWidth - innerWidth, overlaps, unexplainedDisabled: unexplained, clippedText: clipped };
})()
```
تفسيرُ المخرج: `pageOverflowX > 0` فيضٌ أفقيّ؛ أيُّ عنصرٍ في `overlaps` أو `unexplainedDisabled` عيبٌ يُصلح أو يُبرَّر في العقد؛ و`clippedText` يُراجَع يدوياً (قد يكون مقصوداً).
ما لم يُقَس: زمنُ المسبار على الصفحات الثقيلة، ونسبةُ الإيجابيّات الكاذبة.

## 5) في عقد «جاهز»
خانتان في `02-review-item-format.md` §1: «الأجهزة المقيسة» (أيّ الأجهزة نهاراً/ليلاً وأيّ أدوار، أو «لم يُقَس») و«نتيجة المسبار». 0501 تتحقّق من وجود الخانتين فقط، لا من صحّة القياس.

## أنماطٌ مضادّة
- إعلانُ «جاهز» بقياسٍ على مقاسٍ واحدٍ أو دورٍ واحد.
- لصقُ مخرج المسبار دون تفسير، أو إخفاءُ تداخلٍ ظاهرٍ بحجّة أنّ الحارس أخضر.
- جعلُ المسبار شرطاً مانعاً قبل اعتماده.
