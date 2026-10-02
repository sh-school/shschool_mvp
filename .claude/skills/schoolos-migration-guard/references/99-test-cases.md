# حالاتُ اختبار المهارة

متى تقرأ هذا الملف: حين تعدّل وصفَ المهارة أو جسمَها أو سكربتها، وتريد التحقّق من أنّها تُفعَّل حيث يجب ولا تُفعَّل حيث لا يجب، وأنّ جوابها ناجح.

## يجب أن تُفعَّل
| # | الطلب | لماذا |
|---|---|---|
| 1 | «أضفت حقل `rejection_note = models.TextField(default="")` في AbsenceExcuse وولّدت الهجرة، أدفع؟» | عمودٌ إلزاميٌّ بلا `db_default` |
| 2 | "CI failed on 'مدقّق الهجرات — Expand/Contract' with NOT_NULL, what now?" | سقوطُ البوّابة |
| 3 | «أبي أغيّر اسم الحقل `grade` إلى `grade_level` في ClassGroup» | إعادةُ تسمية = توسيعٌ ثمّ تقليص |
| 4 | «الحقل `legacy_code` في Subject ما عاد أحد يستخدمه، أحذفه بنفس الطلب؟» | حذف |
| 5 | «أحتاج فهرس على `session` في StudentAttendance لأن الاستعلام بطيء» | فهرسٌ على جدولٍ كبير |
| 6 | «migrate طلع لي Conflicting migrations detected; multiple leaf nodes in core» | تعارضُ ترقيم |
| 7 | «أكتب RunPython يصحّح أرقام جوالات أولياء الأمور اللي تبدأ بـ00» | ثلاثيّةُ phone في نموذجٍ تاريخيّ |
| 8 | «هل الترحيل هذا آمن؟» + ملفٌّ فيه `AlterField` لـ`max_length` | سؤالٌ مباشر |
| 9 | «عدّلت هجرة 0056 بعد ما طبقتها عندي، ليش التغيير ما ظهر؟» | مسوّدةٌ مطبّقة |
| 10 | «نبي UniqueConstraint على (school, code) في Subject» | قيدٌ فريدٌ على جدولٍ قائم |

## يجب ألّا تُفعَّل
| # | الطلب | الصحيح بدلها |
|---|---|---|
| 1 | «صفحة سجلّ الحضور فيها 400 استعلام» (بلا تغيير مخطّط) | nplus1-hunter |
| 2 | «هل رقم جواز وليّ الأمر لازم يتشفّر؟» (قرارُ تصنيف، لا هجرة) | pdppl-pii-audit |
| 3 | «أضف بند N-060 للخارطة بعد دمج #730» (هجرةُ `roadmap/migrations`) | إبلاغُ جلسة الخارطة؛ schoolos-roadmap-sync إن وُجدت |
| 4 | «جهّزت الإيداع وأبي أدفع وأفتح PR» (الهجرةُ فُحصت) | schoolos-flow |
| 5 | «git stash عندي فيه هجرة ضاعت» | schoolos-git-safety |
| 6 | «اعمل endpoint لقائمة الحافلات» (بلا نموذجٍ جديد) | drf-endpoint-scaffold |
| 7 | «الـFERNET_KEY تغيّر، كيف أدوّر المفاتيح؟» | pdppl-pii-audit (أمرُ `rotate_fernet_key`) |

## حالاتٌ حدّيّة
- هجرةٌ فيها `AddField(ManyToManyField)` فقط: تُفعَّل، والحكمُ سليم (جدولٌ جديد) — لا تُنذر بـNOT NULL.
- `RunPython(forward, backward)` بالموضع: سليم؛ الإصدارُ القديم من الحارس كان يعلّمه 🔴 خطأً.
- `AlterField` لـ`verbose_name` على جدولٍ كبير: 🟠 في التحليل الثابت، و`(no-op)` مع `--sql` — لا خطر.
- `SeparateDatabaseAndState` فيه `RemoveField` داخل `database_operations`: 🔴.
- هجرةُ التقليص الموعودة (الخطوة 2) بعد أن استقرّ الإصدار الأوّل: الحارسُ يبقى 🔴 والبوّابةُ تسقط — والجوابُ الصحيح أنّها قرارُ مراجعةٍ يُسأل عنه المالك، لا «احذف السطر».
- هجرةٌ تُنشئ نموذجاً وتضيف عليه قيداً فريداً في الملفّ نفسِه: سليم (جدولٌ فارغ).

## اختباراتُ السكربت (تُعاد عند تعديله)
مختبرٌ خارج المستودع، 15 حالةً اصطناعيّة؛ المتوقَّع من `check_migration.py --file … --no-makemigrations`:
| الحالة | المتوقَّع |
|---|---|
| FK إلزاميّ بلا افتراض | 🔴 |
| `default=""` بلا `db_default` | 🔴 |
| `default="", db_default=""` | 🟢 |
| `ManyToManyField` | 🟢 |
| `RunPython(f, b)` بالموضع | 🟢 |
| `RunPython(f)` | 🔴 |
| `AlterField` لـ`verbose_name` | 🟠 |
| `AddIndexConcurrently` و`atomic = False` في تعليقٍ فقط | 🔴 |
| `SeparateDatabaseAndState` بـ`RemoveField` | 🔴 |
| `RenameModel` (يذكر اسمَ النموذج القديم) | 🔴 |
| RunPython على `CustomUser` بلا `hmac_field` | 🟠 |
| `UniqueConstraint` على جدولٍ قائم | 🔴 |
| مخطّطٌ + RunPython | 🟠 |
| `AddIndexConcurrently` مع `atomic = False` | 🟢 |
| `CreateModel` + قيدٌ فريدٌ عليه | 🟢 |
ومع `--sql` داخل حاويةٍ فيها المدقّق: هجرةُ `default=` وحده تُظهر «[مدقّق CI] خطأ: NOT_NULL»، و`AlterField` لـ`verbose_name` «لا جملَ SQL (no-op)». وعلى طرفيّة ويندوز لا يسقط بخطأ ترميز.

## اختباراتُ المخرج
ينجح الجوابُ إذا:
- قسّم كلَّ هدمٍ أو إعادةِ تسمية إلى إصدارين، وذكر أنّ البوّابة تُسقط الخطوةَ الثانية ما لم تُقرَّر في المراجعة.
- اقترح `db_default=` لكلّ عمودٍ إلزاميٍّ جديد، وعلّله بـ`DROP DEFAULT` والنسخةِ القديمة.
- شغّل الحارس بـ`--sql` داخل حاوية الجلسة (أو طلب ذلك) لا على المضيف.
- حسب `*_encrypted`/`*_hmac` صراحةً في أيّ RunPython يلمس `national_id`/`phone`، أو أحال إلى أمر إدارة.
- حلّ تعارض الترقيم بإعادة الربط إلى آخر هجرة main.
ويرسب إذا:
- نصح بالعمل في `D:\shschool_mvp` بدل شجرة الجلسة، أو بتشغيل `migrate` على الإنتاج.
- اكتفى بـ`default=` لعمودٍ إلزاميّ، أو اقترح حذفَ سطرٍ من الهجرة لتمرّ البوّابة.
- وصف قاعدة الإنتاج بـPostgreSQL 16، أو ادّعى أنّ `sqlmigrate` يطبع «ACCESS EXCLUSIVE».
- عدّل هجرةً مطبّقةً أو كتب في `roadmap/migrations/`.
