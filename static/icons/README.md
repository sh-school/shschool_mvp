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
