"""سجلُّ المراجعة: يُسمح بتجهيل اسم الشخص في `object_repr` وحدَه عند محوه.

W-20261004-002، قرارُ المالك بصفته DPO (D-186م ب، 2026-10-04): عند طلب محو مستخدمٍ يُستبدل اسمُه في
`object_repr` بمعرّفه المقنَّع، وتبقى الواقعةُ بكلّ ما عدا ذلك.

فالمسموحُ في الزناد الآن `UPDATE` من ثلاثة أنواع لا غير:
1. فصلُ هويّة الفاعل (الهجرة 0059).
2. تفريغُ الشبكة بعلَم `app.auditlog_network_erasure` (الهجرة 0078).
3. تجهيلُ الاسم: `object_repr` وحدَه يتغيّر، وكلُّ عمودٍ آخرَ كما هو حرفيّاً، **وبعلَم المعاملة
   `app.auditlog_name_erasure = on`** وحدَه. يضبطه `AuditLog.objects.anonymize_name_in_repr` داخل معاملةٍ
   ويُغلقه في finally، فبلاه يُرفض أيُّ تعديلٍ لـ`object_repr` حتى بSQL مباشر.

حدُّ العلَم (حكم 0105 كما في 0078): يحمي من الخطأ والحقن العابر، لا من شيفرةٍ تعمل بدور التطبيق نفسه.
والزنادُ لا يتحقّق من أنّ القيمةَ الجديدةَ «مقنَّعة»؛ ذلك على الفئة وحارسِها المعماريّ.

الهجرةُ توسيعٌ لا تقليص: `CREATE OR REPLACE` لدالّة الزناد، لا حذفَ عمودٍ ولا جدول.
"""

import importlib

from django.db import migrations

_PREVIOUS = importlib.import_module("core.migrations.0078_auditlog_allow_network_redaction")

_COMMON = """
       AND NEW.id = OLD.id
       AND NEW.school_id IS NOT DISTINCT FROM OLD.school_id
       AND NEW.user_id IS NOT DISTINCT FROM OLD.user_id
       AND NEW.action = OLD.action
       AND NEW.model_name = OLD.model_name
       AND NEW.object_id = OLD.object_id
       AND NEW.changes IS NOT DISTINCT FROM OLD.changes
       AND NEW.ip_address IS NOT DISTINCT FROM OLD.ip_address
       AND NEW.user_agent = OLD.user_agent
       AND NEW.timestamp = OLD.timestamp
"""

# الحالةُ الثالثة تُضاف أمام الرفض النهائيّ في زناد 0078 دون مسّ الحالتين الأوليَين.
_REJECT = "    RAISE EXCEPTION 'AuditLog records are immutable (operation: %)', TG_OP;"

_THIRD_CASE = f"""    -- 3) تجهيلُ الاسم عند محو صاحب البيانات (W-20261004-002، D-186م ب): `object_repr` وحدَه،
    --    وبعلَمٍ محلّيٍّ للمعاملة وحدَها يضبطه `anonymize_name_in_repr` ويُغلقه في finally.
    IF TG_OP = 'UPDATE'
       AND coalesce(current_setting('app.auditlog_name_erasure', true), '') = 'on'
       AND NEW.object_repr IS DISTINCT FROM OLD.object_repr{_COMMON}    THEN
        RETURN NEW;
    END IF;

"""

assert _REJECT in _PREVIOUS.TRIGGER_SQL, "صيغةُ زناد 0078 تغيّرت: راجع موضعَ الحالة الثالثة"
TRIGGER_SQL = _PREVIOUS.TRIGGER_SQL.replace(_REJECT, _THIRD_CASE + _REJECT)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0081_breach_individuals_and_phased_ncsa"),
    ]

    operations = [
        # العودةُ إلى زناد 0078 (فصلُ الفاعل وتفريغُ الشبكة).
        migrations.RunSQL(sql=TRIGGER_SQL, reverse_sql=_PREVIOUS.TRIGGER_SQL),
    ]
