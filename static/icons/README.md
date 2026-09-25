# أيقونات التطبيق

| الملف | الغرض |
|---|---|
| `icon-192.png` و`icon-512.png` | الشعار على شفّاف — `purpose: any`، والإشعارات |
| `icon-maskable-192.png` و`icon-maskable-512.png` | `purpose: maskable` — أندرويد يقصّها في قناعه |
| `apple-touch-icon.png` (180) | الشاشة الرئيسية في iOS — معتمة، فالشفّافُ يُملأ بالأسود |
| `badge-72.png` | شارةُ الإشعار |

الثلاثةُ المقصوصة مولَّدةٌ من `icon-512.png`، فلا تُعدَّل باليد. متى تغيّر الشعار:

```bash
python manage.py build_app_icons
```

## من أين يأتي الشعار

المرجعُ الوحيد `static/brand/logoMaroon.png` — شعارُ الدولة كما في ترويسة الوزارة الرسميّة لمدرسة الشحانية، لونٌ واحدٌ مسطّحٌ
#8A1538. منه يُشتقّ بـ`python scripts/build_emblem.py` (أداةُ مطوّرٍ تحتاج opencv وPyMuPDF): المتّجهُ `static/brand/emblem.svg`
ونسختُه البيضاء `emblem-white.svg` (لما يُعرض على العنّابيّ — بلا فلتر تبييض)، والأيقوناتُ النقطيّةُ أعلاه (`icon-512` و`icon-192`
و`favicon` و`badge-72`) بلونٍ واحدٍ دقيق. ثمّ `build_app_icons` للمقصوصات. `tests/test_brand_emblem.py` يحرسها: لونٌ واحد،
وتطابقُ الشكل مع الأصل، ولا `brightness(0) invert(1)`. (كانت الأيقونةُ رسمةً مظلَّلةً منقوشةً بنحو 40% تطابقاً فقط.)
