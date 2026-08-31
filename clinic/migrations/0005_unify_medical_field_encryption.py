"""[PII-11] توحيدُ الحقول الطبّيّة على `EncryptedTextField`، وتسويةُ ما تراكم.

كانت `allergies` و`chronic_diseases` و`medications` حقولاً نصّيّةً تُشفَّر
يدوياً بـ`save_encrypted()`، وجهةُ الطوارئ في الجدول نفسه `EncryptedTextField`.
والقالبُ يطبع الحقلَ الخام، فتُعرض الطلاسمُ في مربّع الإدخال، ويعيد كلُّ حفظٍ
تشفيرَها — طبقةً فوق طبقة.

**قِيست الحالةُ قبل هذا الترحيل ولم تُفترض.** شُغّل
`classify_health_record_encryption` على الإنتاج فأخرج: سجلّان، وستُّ قيمٍ
فارغةٌ كلُّها، وصفرٌ في كلّ تصنيفٍ آخر — أي أنّ العيب لم يُتلف بيانةً واحدة،
لأنّ الشاشةَ لم تُستعمل بعد.

فلا شيءَ لهذا الترحيل ليفعله في الإنتاج. ومع ذلك يُسوّي بيئةً فيها بيانات،
لأنّ الصمتَ عن حالةٍ لا نعالجها إفسادٌ مؤجَّل. والتسويةُ بالتصنيف لا بالتخمين:

    فارغ            يُترك
    نصٌّ عارٍ        يُترك — الحقلُ الجديد يقرؤه ويشفّره عند أوّل حفظ
    طبقةٌ واحدة      يُترك — وهي الصيغةُ المقصودة
    طبقتان فأكثر     تُقشَّر حتى تبقى واحدة
    غيرُ معلوم       لا يُلمس، ويُرفَع الترحيلُ بخطأٍ يسمّيه

ومُعاوِد: إعادةُ تشغيله على قاعدةٍ سُوّيت لا تجد طبقةً زائدةً فلا تُغيّر شيئاً.
"""

import core.fields
from django.db import migrations


def _peel_to_one_layer(apps, schema_editor):
    """يُنزل ما تراكم إلى طبقةٍ واحدة، ويقف عند ما لم يثبت تصنيفُه.

    والمنطقُ في `clinic.encryption_audit` لا هنا: هجرةٌ تحمل منطقاً لا يُختبَر
    إلّا بتشغيلها، والوحدةُ تُختبَر بمعطياتٍ معلومة.
    """
    from clinic.encryption_audit import (
        MEDICAL_FIELDS,
        UnclassifiedValueError,
        to_single_layer,
    )
    from core.models._crypto import _get_fernet

    fernet = _get_fernet()
    HealthRecord = apps.get_model("clinic", "HealthRecord")

    # بلا مفتاحٍ لا يُميَّز العاري من المشفَّر، فلا تسويةَ ولا ادّعاء. وبيئةُ
    # التطوير بلا مفتاحٍ تمرّ من هنا، وبياناتُها عاريةٌ يقرؤها الحقلُ الجديد.
    if fernet is None:
        return

    unresolved = []
    for record in HealthRecord.objects.all().iterator():
        changed = False
        for field in MEDICAL_FIELDS:
            raw = getattr(record, field) or ""
            try:
                peeled = to_single_layer(raw, fernet)
            except UnclassifiedValueError as exc:
                unresolved.append(f"{record.pk}.{field}: {exc}")
                continue
            if peeled != raw:
                setattr(record, field, peeled)
                changed = True
        if changed:
            # النموذجُ التاريخيُّ في الهجرة حقولُه نصّيّةٌ لا مشفَّرة، فالحفظُ
            # يكتب ما وُضع كما هو ولا يُضيف طبقةً جديدة.
            record.save(update_fields=list(MEDICAL_FIELDS))

    if unresolved:
        raise RuntimeError(
            "قيمٌ لم يثبت تصنيفُها في السجلّ الصحّيّ — أوقِف الترحيل وافحصها "
            "بـ`classify_health_record_encryption`، ولا تُصلحها بالتخمين: "
            + " · ".join(unresolved)
        )


def _noop(apps, schema_editor):
    """لا عكسَ للتقشير: إعادةُ طبقةٍ زائدةٍ إفسادٌ متعمَّد، لا تراجُع."""


class Migration(migrations.Migration):
    dependencies = [
        ("clinic", "0004_encrypt_emergency_contact"),
    ]

    operations = [
        migrations.RunPython(_peel_to_one_layer, _noop),
        migrations.AlterField(
            model_name="healthrecord",
            name="allergies",
            field=core.fields.EncryptedTextField(blank=True, verbose_name="الحساسية"),
        ),
        migrations.AlterField(
            model_name="healthrecord",
            name="chronic_diseases",
            field=core.fields.EncryptedTextField(blank=True, verbose_name="الأمراض المزمنة"),
        ),
        migrations.AlterField(
            model_name="healthrecord",
            name="medications",
            field=core.fields.EncryptedTextField(blank=True, verbose_name="الأدوية المستمرة"),
        ),
    ]
