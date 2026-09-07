"""سجلُّ المراجعة يبقى، وهويّةُ فاعله وحدَها تُفصَل حين يُمحى.

كان الزنادُ يمنع كلَّ `UPDATE` بلا استثناء، فصار حذفُ أيّ مستخدمٍ مستحيلاً:
حقلُ `AuditLog.user` مُعرَّفٌ `SET_NULL`، فيحاول Django تصفيرَه قبل الحذف
فيرفع الزنادُ الاستثناءَ ويسقط الطلبُ كلُّه — حتّى على حسابِ فحصٍ لا قيمةَ له.

والمنعُ المطلقُ ليس ما تطلبه PDPPL: المادّةُ 19 تحرس **الواقعة** لا هويّةَ
فاعلها، والمادّةُ 15 تُلزم بمحو البيانات الشخصيّة متى سقط سببُ حفظها. فمن
مُحي حسابُه تُفصَل هويّتُه عن السجلّ ويبقى السجلُّ يقول: في يوم كذا، عُدّل
كذا، من هذا العنوان.

فالمسموحُ الآن `UPDATE` واحدةٌ لا غير: `user_id` من قيمةٍ إلى `NULL` وكلُّ
عمودٍ آخرَ كما هو حرفيّاً. وما عداها يُرفع كما كان — تعديلُ الإجراء أو
التغييرات أو الوقت أو حذفُ الصفّ.
"""

from django.db import migrations

TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION core_auditlog_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- فصلُ هويّةِ الفاعل عند محو حسابه — والواقعةُ بكلّ تفاصيلها تبقى.
    IF TG_OP = 'UPDATE'
       AND OLD.user_id IS NOT NULL
       AND NEW.user_id IS NULL
       AND NEW.id = OLD.id
       AND NEW.school_id IS NOT DISTINCT FROM OLD.school_id
       AND NEW.action = OLD.action
       AND NEW.model_name = OLD.model_name
       AND NEW.object_id = OLD.object_id
       AND NEW.object_repr = OLD.object_repr
       AND NEW.changes IS NOT DISTINCT FROM OLD.changes
       AND NEW.ip_address IS NOT DISTINCT FROM OLD.ip_address
       AND NEW.user_agent = OLD.user_agent
       AND NEW.timestamp = OLD.timestamp
    THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION 'AuditLog records are immutable — PDPPL م.19 (operation: %)', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS trg_auditlog_immutable ON core_auditlog;

CREATE TRIGGER trg_auditlog_immutable
    BEFORE DELETE OR UPDATE ON core_auditlog
    FOR EACH ROW EXECUTE FUNCTION core_auditlog_immutable();
"""

REVERSE_SQL = """
CREATE OR REPLACE FUNCTION core_auditlog_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'AuditLog records are immutable — PDPPL م.19 (operation: %)', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS trg_auditlog_immutable ON core_auditlog;

CREATE TRIGGER trg_auditlog_immutable
    BEFORE DELETE OR UPDATE ON core_auditlog
    FOR EACH ROW EXECUTE FUNCTION core_auditlog_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0058_audit_membership_choice"),
    ]

    operations = [
        migrations.RunSQL(sql=TRIGGER_SQL, reverse_sql=REVERSE_SQL),
    ]
