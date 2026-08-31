"""[CLINIC] بوّابةُ السجلّ الصحّيّ — الحفظُ لا يزيد طبقةً ولا يُظهر طلاسم.

كان النموذجُ يجمع طريقتين للتشفير: الحقولُ الطبّيّةُ الثلاثة تُشفَّر يدوياً
بـ`save_encrypted()` وتُفكّ يدوياً في الشاشة، وجهةُ الطوارئ تحتها بحقلٍ شفّاف.
والقالبُ يطبع الحقلَ الخام — فتُعرض الطلاسمُ في مربّع الإدخال، ويأخذها الحفظُ
التالي فيشفّرها من جديد.

وقد قِيست حالةُ الإنتاج قبل الإصلاح: سجلّان، وستُّ قيمٍ فارغةٌ كلُّها — فلم
يُتلف العيبُ بيانةً واحدة، لأنّ الشاشةَ لم تُستعمل بعد. والإصلاحُ اليوم مجّانيّ،
وبعد أوّل إدخالٍ يصير ترحيلاً على بياناتٍ صحّيّةٍ لقاصرين.

و«تمّت الهجرة» ليست هي الـDone. الـDone ثلاثةٌ تُثبتها هذه الدعاوى:

  ١) لا يستطيع حفظُ النموذج أن يزيد طبقةَ تشفير.
  ٢) لا يستطيع أن يُظهر نصّاً مشفَّراً للمستخدم.
  ٣) والنصُّ الطبّيُّ لا يُخزَّن عارياً في القاعدة.
"""

import pytest
from cryptography.fernet import Fernet, InvalidToken
from django.db import connection

from clinic.models import HealthRecord
from core.models import CustomUser

ALLERGIES = "حساسيّةٌ من البنسلين والمكسّرات"
CHRONIC = "ربوٌ خفيف"
MEDS = "بخّاخ الربو عند اللزوم"
CONTACT = "أمُّ الطالب"

MEDICAL = ("allergies", "chronic_diseases", "medications")


@pytest.fixture
def fernet(settings):
    """مفتاحٌ حقيقيٌّ في الاختبار — بدونه يمرّ التشفيرُ صامتاً فلا نقيس شيئاً.

    ويُثبَّت **قبل** إنشاء السجلّ: لو أُنشئ أوّلاً لشُفّر بمفتاح الإعدادات ثمّ
    قِيس بهذا، فيبدو غيرَ مشفَّرٍ وهو مشفَّر.
    """
    key = Fernet.generate_key().decode()
    settings.FERNET_KEY = key
    return Fernet(key.encode())


@pytest.fixture
def student(db, school):
    return CustomUser.objects.create(national_id="28800000101", full_name="طالب")


@pytest.fixture
def record(db, student, fernet):
    return HealthRecord.objects.create(
        student=student,
        blood_type="O+",
        allergies=ALLERGIES,
        chronic_diseases=CHRONIC,
        medications=MEDS,
        emergency_contact_name=CONTACT,
    )


def _stored(pk, field):
    """القيمةُ كما هي في القاعدة، بلا مرورٍ بالنموذج."""
    with connection.cursor() as cur:
        cur.execute(f"SELECT {field} FROM core_healthrecord WHERE id = %s", [str(pk)])  # noqa: S608
        return cur.fetchone()[0]


def _layers(value, fernet):
    """عددُ طبقات التشفير — بالتوقيع لا بالشكل."""
    depth = 0
    current = value
    while depth < 6:
        try:
            current = fernet.decrypt(current.encode()).decode()
        except (InvalidToken, ValueError, TypeError, UnicodeDecodeError):
            return depth
        depth += 1
    return depth


# ── الرحلةُ التي اتُّفق عليها ─────────────────────────────────────────


def test_the_medical_text_survives_the_agreed_journey(db, record):
    """إنشاء ← قراءة ← حفظٌ بلا تغيير ← قراءة ← تعديلُ فصيلة الدم وحدها ←
    قراءة ← تعديلُ الحساسية وحدها ← قراءة ← حفظٌ ثانٍ بلا تغيير ← قراءة.

    وفي كلّ محطّةٍ يُثبَت أنّ النصَّ المنطقيَّ لم يتبدّل.
    """
    record.refresh_from_db()
    assert (record.allergies, record.chronic_diseases, record.medications) == (
        ALLERGIES,
        CHRONIC,
        MEDS,
    )

    record.save()
    record.refresh_from_db()
    assert (record.allergies, record.chronic_diseases, record.medications) == (
        ALLERGIES,
        CHRONIC,
        MEDS,
    )

    record.blood_type = "A-"
    record.save()
    record.refresh_from_db()
    assert record.blood_type == "A-"
    assert (record.allergies, record.chronic_diseases, record.medications) == (
        ALLERGIES,
        CHRONIC,
        MEDS,
    ), "تعديلُ فصيلة الدم لا يمسّ الحقول الطبّيّة"

    record.allergies = "حساسيّةٌ من اللاتكس"
    record.save()
    record.refresh_from_db()
    assert record.allergies == "حساسيّةٌ من اللاتكس"
    assert (record.chronic_diseases, record.medications) == (
        CHRONIC,
        MEDS,
    ), "تعديلُ حقلٍ طبّيٍّ لا يمسّ أخويه"

    record.save()
    record.refresh_from_db()
    assert record.allergies == "حساسيّةٌ من اللاتكس"
    assert (record.chronic_diseases, record.medications) == (CHRONIC, MEDS)


# ── الطبقةُ لا تتراكم ────────────────────────────────────────────────


@pytest.mark.parametrize("field", MEDICAL)
def test_repeated_saves_never_add_a_layer(db, record, fernet, field):
    """هذا هو العيبُ بعينه: كان كلُّ حفظٍ يشفّر ما هو مشفَّر.

    ولو عاد لأصبح النصُّ بعد خمسة حفظاتٍ خمسَ طبقاتٍ لا تُقرأ إلّا بفكٍّ
    متكرّر — أي بياناتٌ صحّيّةٌ تالفةٌ بلا خطأٍ ظاهر.
    """
    for _ in range(5):
        record.save()

    assert _layers(_stored(record.pk, field), fernet) == 1


def test_the_form_never_shows_ciphertext_to_the_nurse(db, record, fernet):
    """ما يصل القالبَ هو ما تقرؤه الممرّضة — والقالبُ يقرأ الحقلَ نفسه.

    وكان يقرأ الخام بينما الشاشةُ تمرّر مفكوكاً بمفتاحٍ موازٍ يتجاهله. فلمّا
    صار الحقلُ يفكّ بنفسه، امتنع العيبُ بالبناء لا بالانضباط.
    """
    record.refresh_from_db()

    for field in MEDICAL:
        shown = getattr(record, field)
        assert _layers(shown, fernet) == 0, f"«{field}» يصل الشاشةَ مفكوكاً"
        assert not shown.startswith("gAAAAA")


# ── القاعدةُ لا تحمل نصّاً عارياً ────────────────────────────────────


@pytest.mark.parametrize(
    ("field", "plain"),
    [("allergies", ALLERGIES), ("chronic_diseases", CHRONIC), ("medications", MEDS)],
)
def test_no_medical_plaintext_reaches_the_database(db, record, fernet, field, plain):
    stored = _stored(record.pk, field)

    assert plain not in stored
    assert _layers(stored, fernet) == 1


def test_the_emergency_contact_keeps_its_own_protection(db, record, fernet):
    """كان محميّاً قبل هذا الإصلاح، ولا يجوز أن يخسر حمايتَه به."""
    stored = _stored(record.pk, "emergency_contact_name")

    assert CONTACT not in stored
    assert _layers(stored, fernet) == 1


# ── ما لم يعد له وجود ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "helper",
    [
        "get_allergies",
        "set_allergies",
        "get_chronic_diseases",
        "set_chronic_diseases",
        "get_medications",
        "set_medications",
        "save_encrypted",
    ],
)
def test_the_manual_encryption_helpers_are_gone(helper):
    """بقاؤها يُبقي مساراً ثانياً للكتابة — ومن مسارين نشأ العيب.

    والحمايةُ الآن في النموذج: من كتب شاشةً جديدةً غداً لا يستطيع أن ينساها.
    """
    assert not hasattr(HealthRecord, helper)


def test_the_view_passes_no_parallel_decrypted_keys():
    """كانت الشاشةُ تمرّر `allergies` مفكوكاً بجوار `health_record`، فيختار
    القالبُ أحدَهما — واختار الخطأ. فلا مفتاحَين بعد اليوم."""
    import pathlib

    source = pathlib.Path("clinic/views.py").read_text(encoding="utf-8")
    context = source.split('"visits": visits,', 1)[1].split("}", 1)[0]

    for field in MEDICAL:
        assert f'"{field}"' not in context
