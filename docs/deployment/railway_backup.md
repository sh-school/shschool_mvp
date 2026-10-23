# النسخ الاحتياطي داخل Railway (W-20261023-018)

## لماذا
`backup.yml` يسحب القاعدة من GitHub عبر الوكيل العام (`DATABASE_PUBLIC_URL`)، وRailway يحتسب هذا السحب egress
(5 سنتات للجيجابايت بنصّ وثائقها: "Network egress is charged at $0.05/GB"، وتنصح باستعمال `DATABASE_URL` الخاصّ بدل العام).
الحلّ الجذريّ: خدمة cron داخل المشروع تسحب بالشبكة الخاصّة (`*.railway.internal`) وتخزّن في Railway Bucket.

## ما تحقّقنا منه في وثائق Railway وما لم نتحقّق
- سحبُ القاعدة عبر الرابط العامّ = egress مدفوع؛ والرابط الخاصّ هو العلاج المنصوص عليه (understanding-your-bill). النصّ لا يقول صراحةً "صفر"، لكنّه العلاج الرسميّ.
- الحاوية (Bucket): تخزين 0.015 دولار/جيجابايت-شهر، وعملياتُ S3 والـegress منها مجّانية. لكنّ الحاويات **غير متاحة على الشبكة الخاصّة**، فرفعُ الخدمةِ إلى الحاوية يُحتسب service egress (5 سنتات/جيجابايت). أي: "لا رسوم إطلاقاً" غير ممكنة بحاوية Railway؛ الرسمُ يصير على حجم النسخة المضغوطة المشفّرة وحدها (مثال: 100 ميجابايت يومياً ≈ 3 جيجابايت/شهر ≈ 0.15 دولار/شهر)، لا على سحب القاعدة الخام.
- cron: الحقلُ `deploy.cronSchedule` في Config as Code (UTC، أدنى فاصل 5 دقائق، تُتخطّى الدورة إن كانت السابقة لم تنتهِ، والعملية يجب أن تخرج).
- متغيّرات الحاوية: `BUCKET`، `ENDPOINT` (الأساس `https://t3.storageapi.dev`)، `ACCESS_KEY_ID`، `SECRET_ACCESS_KEY`، `REGION`، وتُربط بخدمات أخرى عبر Variable References. الإقليمُ لا يتغيّر بعد الإنشاء. lifecycle الحاويات غير مدعوم، لذا يقلّم السكربتُ الاحتفاظ بنفسه.
- لم يُتحقَّق منه: أنّ DSL الملف `.railway/railway.ts` يقبل `cronSchedule` تحت `deploy` (الوثائق تذكر JSON/TOML فقط). **شغّل `railway config plan` قبل أيّ `apply`**؛ وإن رفضه فاضبط الجدولَ من لوحة الخدمة (Settings ← Cron Schedule) واحذف السطرَ من الملف. كذلك لم يُجرَّب `postgres:18-bookworm` ولا `awscli` من apt على Railway فعلياً.

## خطوات المالك في لوحة Railway (حرفياً)
1. مشروع shschool_mvp ← New ← Bucket. الاسم `db-backups`، الإقليم `sjc` (قرب القاعدة).
2. New ← GitHub Repo ← `sh-school/shschool_mvp` ← سمِّ الخدمة `db-backup`. Settings:
   - Build ← Builder: Dockerfile ← Dockerfile Path: `Dockerfile.backup`.
   - Deploy ← Cron Schedule: `0 1 * * *` (01:00 UTC = 04:00 قطر).
   - Deploy ← Restart Policy: Never (أو On Failure بمحاولة واحدة).
   - لا تضع Start Command (الصورة تحمله).
3. Variables في خدمة `db-backup` (أسماءٌ فقط، القيم مراجعُ):
   - `DATABASE_URL` = مرجعٌ إلى `DATABASE_URL` من خدمة Postgres (الخاصّ، ينتهي مضيفُه بـ`.railway.internal`). **ليس** `DATABASE_PUBLIC_URL`.
   - `BACKUP_PASSPHRASE` = العبارةُ نفسُها المخزّنة في أسرار GitHub (≥ 32 حرفاً) حتى يفكّها اختبار الاسترجاع.
   - `BACKUP_S3_ENDPOINT` = مرجعٌ إلى `ENDPOINT` من الحاوية؛ `BACKUP_S3_BUCKET` ← `BUCKET`؛ `BACKUP_S3_ACCESS_KEY_ID` ← `ACCESS_KEY_ID`؛ `BACKUP_S3_SECRET_ACCESS_KEY` ← `SECRET_ACCESS_KEY`؛ `BACKUP_S3_REGION` ← `REGION`.
   - اختياريّ: `BACKUP_S3_ADDRESSING_STYLE=path` إن أظهر تبويب Credentials أنّ الحاوية تحتاج path-style؛ `BACKUP_KEEP_DAILY_DAYS` (14) و`BACKUP_KEEP_MONTHLY_MONTHS` (12).
4. أسرار GitHub (Settings ← Secrets ← Actions) لاختبار الاسترجاع: `RAILWAY_BACKUP_S3_ENDPOINT`، `RAILWAY_BACKUP_S3_BUCKET`، `RAILWAY_BACKUP_S3_ACCESS_KEY_ID`، `RAILWAY_BACKUP_S3_SECRET_ACCESS_KEY` (من تبويب Credentials للحاوية). سحبُ الحاوية من GitHub مجّانيّ الـegress.
5. إن كان دورُ `DATABASE_URL` الخاصّ يقرأ كلّ الجداول فلا حاجةَ لشيء؛ وإلّا فالنسخةُ ناقصة — الاسترجاعُ التجريبيّ في الخطة أدناه هو الفاصل.

## خطة التحويل
1. ادمج هذا الـPR، ثم نفّذ الخطوات أعلاه. من الخدمة اضغط Deploy/Run now لتشغيل نسخةٍ أولى يدوياً؛ والمتوقّع في السجلّ: "اكتملت النسخة الاحتياطية بنجاح". أيُّ خروج ≠ 0 يظهر فشلاً في Railway.
2. شغّل يدوياً `Backup Restore Drill` (workflow_dispatch) — يجب أن يعلن "سيتم اختبار النسخة ... من Railway" وينجح الاسترجاع.
3. اترك الجدولين يعملان معاً يومين-ثلاثة (النسخ القديمة تبقى).
4. عطّل جدولة `backup.yml` (احذف كتلة `schedule` وأبقِ `workflow_dispatch`) في PR لاحق، وأزل أسرار `DATABASE_PUBLIC_URL` من GitHub، ويُحدَّث `test_backup_status` وصفحة حالة النسخ لتقرأ حالة Railway بدل `backup.yml`.
5. تحقّق شهرياً من فاتورة Railway (بند Egress للخدمة `db-backup`).

## الاسترجاع
كما هو (الصيغة ذاتها): `gpg --batch --pinentry-mode loopback --passphrase-fd 3 --decrypt <file> 3<<<"<PASSPHRASE>" | gunzip | psql "<URL>"`.
