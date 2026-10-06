
@font-face { font-family: Tajawal; src: url('file://@@ROOT@@/static/fonts/Tajawal-Regular.ttf'); font-weight: 400; }
@font-face { font-family: Tajawal; src: url('file://@@ROOT@@/static/fonts/Tajawal-Medium.ttf'); font-weight: 500; }
@font-face { font-family: Tajawal; src: url('file://@@ROOT@@/static/fonts/Tajawal-Bold.ttf'); font-weight: 700; }

@page {
  size: A4; margin: 28mm 14mm 20mm 14mm;
  @top-right { content: "@@TITLE@@ — منصّة SchoolOS"; font: 500 8pt Tajawal; color: #8A1538; border-bottom: .5pt solid #d9c3ca; padding-bottom: 2mm; width: 91mm; text-align: right; white-space: nowrap; }
  @top-left { content: "مدرسة الشحانية الإعدادية الثانوية للبنين"; font: 500 8pt Tajawal; color: #8A1538; border-bottom: .5pt solid #d9c3ca; padding-bottom: 2mm; width: 91mm; text-align: left; white-space: nowrap; }
  @bottom-left { content: "صفحة " counter(page) " من " counter(pages); font: 400 8pt Tajawal; color: #555; }
  @bottom-right { content: "الإصدار @@VERSION@@ @@STATUS@@ · @@DATE@@ · الأسماء في الصور مستعارة"; font: 400 8pt Tajawal; color: #555; }
}
@page cover { margin: 0; @top-right { content: none; border: 0 } @top-left { content: none; border: 0 } @bottom-left { content: none } @bottom-right { content: none } }

html { direction: rtl; }
body { font: 400 10pt/1.75 Tajawal, sans-serif; color: #1c1c1c; text-align: right; }
b { font-weight: 700; }
code { font: 500 8.5pt Tajawal; background: #f1e9ec; border-radius: 3px; padding: 0 3px; direction: ltr; unicode-bidi: embed; }

/* غلاف */
.cover { page: cover; width: 210mm; height: 297mm; background: linear-gradient(160deg, #8A1538 0%, #6d1030 100%); color: #fff; position: relative; break-after: page; }
.cover .inner { position: absolute; top: 62mm; left: 18mm; right: 18mm; text-align: center; }
.cover img.em { width: 34mm; margin-bottom: 8mm; }
.cover .school { font: 700 17pt Tajawal; }
.cover .min { font: 400 11pt Tajawal; opacity: .85; margin-top: 2mm; }
.cover hr { border: 0; border-top: .6pt solid rgba(255,255,255,.35); margin: 12mm 0; }
.cover .badge { display: inline-block; border: .7pt solid rgba(255,255,255,.6); border-radius: 12pt; padding: 1mm 5mm; font: 500 10pt Tajawal; margin-bottom: 6mm; }
.cover h1 { font: 700 34pt Tajawal; margin: 0 0 6mm; }
.cover .lead { font: 400 12pt/1.9 Tajawal; opacity: .92; max-width: 150mm; margin: 0 auto 12mm; }
.cover .meta { font: 400 10pt Tajawal; opacity: .85; }
.cover .meta span { margin: 0 4mm; }

/* فهرس */
.toc-h { font: 700 20pt Tajawal; color: #8A1538; border-bottom: 1.2pt solid #8A1538; padding-bottom: 2mm; margin: 0 0 6mm; }
ol.toc { list-style: none; padding: 0; margin: 0; columns: 2; column-gap: 12mm; }
ol.toc li { break-inside: avoid; margin: 0 0 2.2mm; }
ol.toc a { color: #1c1c1c; text-decoration: none; display: block; }
ol.toc a::after { content: leader('.') target-counter(attr(href), page); color: #666; font-size: 9pt; }
ol.toc .n { display: inline-block; min-width: 6mm; color: #8A1538; font-weight: 700; }

/* أقسام */
section.sec { margin-top: 7mm; }
section.sec.first { break-before: page; margin-top: 0; }
.sechead { display: table; width: 100%; break-after: avoid; margin-bottom: 3mm; border-bottom: .8pt solid #e5d3d9; padding-bottom: 2mm; }
.sechead .nc { display: table-cell; width: 14mm; vertical-align: middle; }
.sechead .num { display: block; background: #8A1538; color: #fff; border-radius: 6pt; width: 10mm; height: 10mm; line-height: 10mm; text-align: center; font: 700 13pt Tajawal; }
.sechead .ttl { display: table-cell; vertical-align: middle; }
.sechead h2 { margin: 0; font: 700 17pt/1.3 Tajawal; color: #8A1538; }
.sechead .sub { margin: 0; color: #666; font-size: 9pt; }
h3 { font: 700 11.5pt Tajawal; color: #2b2b2b; margin: 5mm 0 2mm; break-after: avoid; border-right: 3pt solid #E3A400; padding-right: 2.5mm; }
p { margin: 0 0 2.5mm; }

.note, .rule, .warn { border-radius: 5pt; padding: 2.5mm 4mm; margin: 3mm 0; break-inside: avoid; }
.note { background: #eef3fb; border-right: 3pt solid #4a73b8; }
.rule { background: #fff6dc; border-right: 3pt solid #E3A400; }
.warn { background: #fdecec; border-right: 3pt solid #c0392b; }

ul.bul, ol.steps { margin: 2mm 0 3mm; padding-right: 5mm; }
ul.bul li, ol.steps li { margin-bottom: 1.4mm; }
ol.steps { list-style: none; padding-right: 0; counter-reset: s; }
ol.steps li { counter-increment: s; padding-right: 8mm; position: relative; }
ol.steps li::before { content: counter(s); position: absolute; right: 0; top: .2mm; width: 6mm; height: 6mm; border-radius: 50%; background: #8A1538; color: #fff; text-align: center; font: 700 8.5pt/6mm Tajawal; }

table.t { width: 100%; border-collapse: collapse; margin: 2mm 0 4mm; font-size: 9pt; break-inside: auto; }
table.t.keep { break-inside: avoid; }
table.t th { background: #8A1538; color: #fff; padding: 2mm 3mm; text-align: right; font-weight: 700; }
table.t td { padding: 1.8mm 3mm; border-bottom: .5pt solid #e5d3d9; vertical-align: top; }
table.t tr:nth-child(even) td { background: #faf4f6; }
table.t tr { break-inside: avoid; }

.cards { display: grid; grid-template-columns: 1fr 1fr; gap: 3mm; margin: 2mm 0 4mm; }
.card { border: .6pt solid #e5d3d9; border-radius: 6pt; padding: 2.5mm 3.5mm; break-inside: avoid; background: #fff; }
.card b { display: block; color: #8A1538; font-size: 10pt; margin-bottom: .5mm; }
.card span { font-size: 8.8pt; color: #444; }

figure.fig { margin: 3mm 0 4mm; break-inside: avoid; }
figure.fig img { display: block; margin: 0 auto 2.5mm; border: .6pt solid #d9c3ca; border-radius: 5pt; }
ol.legend { list-style: none; margin: 0; padding: 0; columns: 2; column-gap: 6mm; }
ol.legend.one { columns: 1; }
ol.legend li { position: relative; padding-right: 8mm; margin-bottom: 1.6mm; break-inside: avoid; font-size: 9pt; line-height: 1.6; }
ol.legend li .k { position: absolute; right: 0; top: 0; width: 5.6mm; height: 5.6mm; border-radius: 50%; background: #F2A900; color: #3b2a00; text-align: center; font: 700 8.5pt/5.6mm Tajawal; border: .8pt solid #fff; box-shadow: 0 0 0 .5pt #c98d00; }

.timeline { margin: 3mm 0; padding-right: 4mm; border-right: 1.5pt solid #e5d3d9; }
.tl { position: relative; margin: 0 0 3mm; padding-right: 4mm; break-inside: avoid; }
.tl::before { content: ""; position: absolute; right: -6.5mm; top: 1.4mm; width: 4mm; height: 4mm; border-radius: 50%; background: #8A1538; }
.tl .when { display: inline-block; background: #f4e7ec; color: #8A1538; border-radius: 8pt; padding: 0 3mm; font: 700 8.5pt Tajawal; margin-left: 2mm; }
.tl b.what { font-size: 10pt; }
.tl p { margin: .8mm 0 0; font-size: 9.2pt; }

ul.check { list-style: none; padding: 0; margin: 2mm 0; }
ul.check li { padding-right: 8mm; position: relative; margin-bottom: 2.2mm; }
ul.check li::before { content: ""; position: absolute; right: 0; top: .8mm; width: 4.4mm; height: 4.4mm; border: 1pt solid #8A1538; border-radius: 2pt; }

ol.legend li.flat { padding-right: 0; }
figure.fig img.w50 { width: 50%; }
figure.fig img.w55 { width: 55%; }
figure.fig img.w70 { width: 70%; }
figure.fig img.w80 { width: 80%; }
figure.fig img.w100 { width: 100%; }
.cover .meta.soft { margin-top: 6mm; opacity: .7; }
