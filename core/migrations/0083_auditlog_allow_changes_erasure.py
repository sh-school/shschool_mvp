"""سجلُّ المراجعة: يُسمح بمسح اسم الشخص من عمود `changes` وحدَه عند محوه.

W-20261010-053، قرارُ المالك بصفته DPO (D-342م، 2026-10-10): يكمل هذا تجهيلَ `object_repr` (0082) فلا يبقى
اسمُ المحوّ في أيّ عمودٍ من السجلّ، وتبقى الواقعةُ بكلّ ما عدا ذلك.

فالمسموحُ في الزناد الآن `UPDATE` من أربعة أنواع لا غير:
1. فصلُ هويّة الفاعل (الهجرة 0059).
2. تفريغُ الشبكة بعلَم `app.auditlog_network_erasure` (الهجرة 0078).
3. تجهيلُ الاسم في `object_repr` بعلَم `app.auditlog_name_erasure` (الهجرة 0082).
4. مسحُ الاسم من `changes`: هذا العمودُ وحدَه يتغيّر، وكلُّ عمودٍ آخرَ (ومنه `object_repr`) كما هو حرفيّاً،
   **وبعلَم المعاملة المستقلّ `app.auditlog_changes_erasure = on`** وحدَه. يضبطه
   `AuditLog.objects.anonymize_name_in_changes` داخل معاملةٍ ويُغلقه في finally، فبلاه يُرفض أيُّ تعديلٍ
   لـ`changes` حتى بSQL مباشر.

علَمٌ مستقلٌّ لا مشتركٌ مع 0082: فلا يفتح علَمُ `object_repr` بابَ `changes` ولا العكس، وتبقى كلُّ حالةٍ
ضيّقةً على عمودها. وحدُّ العلَم كما في 0078 (حكم 0105): يحمي من الخطأ والحقن العابر، لا من شيفرةٍ تعمل
بدور التطبيق نفسه. والزنادُ لا يتحقّق من أنّ القيمةَ الجديدةَ «ممسوحةٌ بالمعرّف المقنَّع»؛ ذلك على الفئة
وحارسِها المعماريّ.

الهجرةُ توسيعٌ لا تقليص: `CREATE OR REPLACE` لدالّة الزناد، لا حذفَ عمودٍ ولا جدولٍ **ولا بياناتَ فيها**
(المسحُ تُجريه خدمةُ المحو عند الطلب بـPython لا هنا).
"""

import importlib

from django.db import migrations

_PREVIOUS = importlib.import_module("core.migrations.0082_auditlog_allow_name_erasure")

# المشتركُ في 0082 يثبّت `changes` ويترك `object_repr` للحالة الثالثة؛ وفي الحالة الرابعة ينعكس الأمر:
# `changes` هو المتغيّر و`object_repr` يُثبَّت.
_PINNED_CHANGES = "       AND NEW.changes IS NOT DISTINCT FROM OLD.changes\n"
_PINNED_REPR = "       AND NEW.object_repr = OLD.object_repr\n"
assert _PINNED_CHANGES in _PREVIOUS._COMMON, "صيغةُ المشترك في 0082 تغيّرت: راجع الحالة الرابعة"
_COMMON = _PREVIOUS._COMMON.replace(_PINNED_CHANGES, _PINNED_REPR)

# الحالةُ الرابعة تُضاف أمام الرفض النهائيّ دون مسّ الحالات الثلاث قبلها.
_FOURTH_CASE = f"""    -- 4) مسحُ الاسم من `changes` عند محو صاحب البيانات (W-20261010-053، D-342م): `changes` وحدَه،
    --    وبعلَمٍ محلّيٍّ للمعاملة وحدَها يضبطه `anonymize_name_in_changes` ويُغلقه في finally.
    IF TG_OP = 'UPDATE'
       AND coalesce(current_setting('app.auditlog_changes_erasure', true), '') = 'on'
       AND NEW.changes IS DISTINCT FROM OLD.changes
{_COMMON}    THEN
        RETURN NEW;
    END IF;

"""

assert _PREVIOUS._REJECT in _PREVIOUS.TRIGGER_SQL, "صيغةُ زناد 0082 تغيّرت: راجع موضعَ الحالة الرابعة"
TRIGGER_SQL = _PREVIOUS.TRIGGER_SQL.replace(_PREVIOUS._REJECT, _FOURTH_CASE + _PREVIOUS._REJECT)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0082_auditlog_allow_name_erasure"),
    ]

    operations = [
        # العودةُ إلى زناد 0082 (فصلُ الفاعل وتفريغُ الشبكة وتجهيلُ الاسم).
        migrations.RunSQL(sql=TRIGGER_SQL, reverse_sql=_PREVIOUS.TRIGGER_SQL),
    ]
