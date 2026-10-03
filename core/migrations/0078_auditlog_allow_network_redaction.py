"""سجلُّ المراجعة: يُسمح بتفريغ عنوان IP والمتصفّح وحدَهما عند محو صاحب البيانات.

W-20261003-013، قرارُ المالك بصفته DPO (2026-10-03): من مُحي حسابُه يُفرَّغ `ip_address`
(إلى NULL) و`user_agent` (إلى فارغ) في صفوفه، وتبقى الواقعةُ بكلّ ما عداهما.

فالمسموحُ في الزناد الآن `UPDATE` من نوعَين لا غير:
1. فصلُ هويّة الفاعل: `user_id` إلى NULL وكلُّ ما عداه كما هو (الهجرة 0059).
2. تفريغُ الشبكة: `ip_address` إلى NULL و`user_agent` إلى فارغ، وكلُّ ما عداهما كما هو
   حرفيّاً — ولا يُغيَّر `user_id` معه — **وبعلَم المعاملة `app.auditlog_network_erasure = on`**
   وحدَه. وما عداهما يُرفع كما كان.
"""

from django.db import migrations

TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION core_auditlog_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- 1) فصلُ هويّةِ الفاعل عند محو حسابه — والواقعةُ بكلّ تفاصيلها تبقى.
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

    -- 2) تفريغُ الشبكة عند محو صاحب البيانات (W-20261003-013): IP إلى NULL والمتصفّحُ فارغاً،
    --    وبعلَمٍ محلّيٍّ للمعاملة وحدَها يضبطه `redact_network_identity` ويُغلقه في finally.
    --    فبلا العلَم يُرفض أيُّ UPDATE حتى لو جاء بSQL مباشر (حكم 0105، شرطٌ قبل الدمج).
    IF TG_OP = 'UPDATE'
       AND coalesce(current_setting('app.auditlog_network_erasure', true), '') = 'on'
       AND NEW.ip_address IS NULL
       AND NEW.user_agent = ''
       AND NEW.id = OLD.id
       AND NEW.user_id IS NOT DISTINCT FROM OLD.user_id
       AND NEW.school_id IS NOT DISTINCT FROM OLD.school_id
       AND NEW.action = OLD.action
       AND NEW.model_name = OLD.model_name
       AND NEW.object_id = OLD.object_id
       AND NEW.object_repr = OLD.object_repr
       AND NEW.changes IS NOT DISTINCT FROM OLD.changes
       AND NEW.timestamp = OLD.timestamp
    THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION 'AuditLog records are immutable (operation: %)', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS trg_auditlog_immutable ON core_auditlog;

CREATE TRIGGER trg_auditlog_immutable
    BEFORE DELETE OR UPDATE ON core_auditlog
    FOR EACH ROW EXECUTE FUNCTION core_auditlog_immutable();
"""

# العودةُ إلى زناد 0059 (فصلُ الفاعل وحدَه).
REVERSE_SQL = """
CREATE OR REPLACE FUNCTION core_auditlog_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
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


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0077_profile_birth_date_encrypted"),
    ]

    operations = [
        migrations.RunSQL(sql=TRIGGER_SQL, reverse_sql=REVERSE_SQL),
    ]
