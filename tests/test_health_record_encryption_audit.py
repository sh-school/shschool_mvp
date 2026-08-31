"""[CLINIC] تصنيفُ تشفير السجلّ الصحّيّ — قبل أن يُلمَس صفٌّ واحد.

`HealthRecord` يجمع طريقتين للتشفير في النموذج نفسه: الحقولُ الطبّيّةُ الثلاثة
`TextField` تُشفَّر يدوياً عبر `save_encrypted()`، وجهةُ الطوارئ في الجدول نفسه
`EncryptedTextField` شفّاف. ومن هذا الازدواج نشأ العيب: القالبُ يطبع الحقلَ
الخام، فتُعرض الطلاسمُ في مربّع الإدخال، وأيُّ حفظٍ بعده يشفّرها من جديد.

فصفوفُ الإنتاج في حالاتٍ مختلفة، والترحيلُ بلا تصنيفٍ إفسادٌ لا إصلاح. وهذه
الدعاوى تُثبّت المصنِّفَ نفسه قبل أن يُصدَّق حكمُه على بياناتٍ حقيقيّة.

والفرقُ الذي تقوم عليه كلُّها: **«يُشبه Fernet» ليس «ثبت أنّه Fernet».** رمزُ
Fernet يحمل توقيعَ HMAC، فنجاحُ الفكّ برهانٌ؛ أمّا الشكلُ فيُقلَّد.
"""

import pytest
from cryptography.fernet import Fernet

from clinic.encryption_audit import (
    EMPTY,
    ENCRYPTED_MULTIPLE,
    ENCRYPTED_ONCE,
    MAX_DEPTH,
    PLAINTEXT,
    UNKNOWN,
    classify_value,
)

ARABIC = "حساسيّةٌ من البنسلين"


@pytest.fixture
def key():
    return Fernet(Fernet.generate_key())


# ── الحالات المعروفة ─────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["", None])
def test_an_absent_value_is_empty(value, key):
    assert classify_value(value, key).verdict == EMPTY


def test_arabic_plaintext_is_recognised_as_plaintext(key):
    """نصُّ الممرّضة كما كتبته — لا يقبله الفكُّ فليس رمزاً."""
    assert classify_value(ARABIC, key).verdict == PLAINTEXT


def test_one_fernet_layer_is_encrypted_once(key):
    once = key.encrypt(ARABIC.encode()).decode()

    verdict = classify_value(once, key)

    assert verdict.verdict == ENCRYPTED_ONCE
    assert verdict.depth == 1


def test_two_fernet_layers_are_encrypted_multiple(key):
    """هذه حالةُ العيب: الممرّضةُ رأت الطلاسم في المربّع ثمّ حفظت."""
    once = key.encrypt(ARABIC.encode()).decode()
    twice = key.encrypt(once.encode()).decode()

    verdict = classify_value(twice, key)

    assert verdict.verdict == ENCRYPTED_MULTIPLE
    assert verdict.depth == 2


def test_three_layers_are_counted_not_flattened(key):
    """حفظان متتاليان — والعمقُ يُسجَّل كي يعرف الترحيلُ كم يفكّ بالضبط."""
    value = ARABIC
    for _ in range(3):
        value = key.encrypt(value.encode()).decode()

    verdict = classify_value(value, key)

    assert verdict.verdict == ENCRYPTED_MULTIPLE
    assert verdict.depth == 3


# ── ما يُشبه ولا يَثبُت ──────────────────────────────────────────────


def test_a_value_that_merely_looks_like_a_token_is_plaintext(key):
    """يبدأ بـ`gAAAAA` كرموز Fernet، وطولُه معقول، ولا توقيعَ له.

    ولو صنّفناه بالشكل لفككناه فأفسدناه. والحكمُ للتوقيع وحده.
    """
    impostor = "gAAAAABlLOOKS_LIKE_A_TOKEN_BUT_IS_NOT_SIGNED_AT_ALL_1234567890"

    assert classify_value(impostor, key).verdict == PLAINTEXT


def test_a_token_from_another_key_is_plaintext_not_encrypted(key):
    """مشفَّرٌ بمفتاحٍ لا نملكه — لا نستطيع فكَّه، فلا ندّعي أنّنا نعرفه.

    وتصنيفُه `PLAINTEXT` صادقٌ من جهة الترحيل: لن يُفكّ، وسيُحفظ كما هو
    فيُشفَّر بمفتاحنا طبقةً واحدة. والبيانةُ الأصليّةُ ضائعةٌ سلفاً بفقد
    مفتاحها، ولا يزيدها هذا ضياعاً.
    """
    stranger = Fernet(Fernet.generate_key())
    token = stranger.encrypt(ARABIC.encode()).decode()

    assert classify_value(token, key).verdict == PLAINTEXT


def test_binary_that_decrypts_to_non_text_is_unknown(key):
    """فُكَّ بنجاحٍ فثبت أنّه رمزُنا — لكنّ ناتجَه ليس نصّاً.

    شذوذٌ لا يُرحَّل بالتخمين: قد يكون ملفّاً أو تلفاً، والقرارُ فيه بشريّ.
    """
    token = key.encrypt(b"\xff\xfe\x00 invalid utf-8 \x80").decode()

    verdict = classify_value(token, key)

    assert verdict.verdict == UNKNOWN
    assert "UTF-8" in verdict.reason


def test_pathological_depth_is_unknown_not_migratable(key):
    """طبقاتٌ فوق الحدّ — لا يُفكّ إلى ما لا نهاية بحثاً عن نصٍّ مقروء."""
    value = ARABIC
    for _ in range(MAX_DEPTH + 1):
        value = key.encrypt(value.encode()).decode()

    verdict = classify_value(value, key)

    assert verdict.verdict == UNKNOWN
    assert not verdict.migratable


# ── غيابُ المفتاح يمنع المعرفة ولا يصنعها ────────────────────────────


def test_without_a_key_nothing_is_claimed_to_be_plaintext():
    """بلا مفتاحٍ لا يُميَّز العاري من المشفَّر — فالجهلُ يُعلَن ولا يُخمَّن.

    وهذا هو ثابتُ «لا ندّعي معرفةَ ما لا نعرف» مطبَّقاً على أوّل مهمّة.
    """
    verdict = classify_value(ARABIC, None)

    assert verdict.verdict == UNKNOWN
    assert not verdict.migratable


def test_an_empty_value_needs_no_key():
    assert classify_value("", None).verdict == EMPTY


# ── ما يجوز ترحيلُه ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [(EMPTY, True), (PLAINTEXT, True), (ENCRYPTED_ONCE, True), (ENCRYPTED_MULTIPLE, True)],
)
def test_classified_values_may_be_migrated(verdict, expected, key):
    from clinic.encryption_audit import Classification

    assert Classification(verdict, "").migratable is expected


def test_unknown_is_never_migrated_automatically():
    from clinic.encryption_audit import Classification

    assert Classification(UNKNOWN, "").migratable is False


# ── الصفُّ الواحد قد تختلف حقولُه ────────────────────────────────────


def test_one_record_can_hold_three_different_states(db, school, key, monkeypatch):
    """لكلّ حقلٍ تاريخُ حفظٍ خاصّ — فالتصنيفُ للقيمة لا للصفّ."""
    from clinic.encryption_audit import classify_records
    from clinic.models import HealthRecord
    from core.models import CustomUser

    student = CustomUser.objects.create(national_id="28800000055", full_name="طالب")
    once = key.encrypt(ARABIC.encode()).decode()
    record = HealthRecord.objects.create(
        student=student,
        allergies=ARABIC,
        chronic_diseases=once,
        medications=key.encrypt(once.encode()).decode(),
    )

    verdicts = {field: v.verdict for _pk, field, v in classify_records([record], key)}

    assert verdicts == {
        "allergies": PLAINTEXT,
        "chronic_diseases": ENCRYPTED_ONCE,
        "medications": ENCRYPTED_MULTIPLE,
    }


# ── التقرير لا يُسرّب ما يصفه ────────────────────────────────────────


def test_the_report_never_carries_medical_text(db, school, key):
    """تقريرٌ عن بياناتٍ صحّيّةٍ يسرّبها أسوأُ من غياب التقرير."""
    import io
    import json
    import tempfile
    from pathlib import Path

    from django.core.management import call_command

    from clinic.models import HealthRecord
    from core.models import CustomUser

    student = CustomUser.objects.create(national_id="28800000056", full_name="طالب")
    HealthRecord.objects.create(student=student, allergies=ARABIC)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "report.json"
        call_command("classify_health_record_encryption", "--out", str(out), stdout=io.StringIO())
        text = out.read_text(encoding="utf-8")

    assert ARABIC not in text
    assert "البنسلين" not in text
    assert json.loads(text)["total_values"] == 3


def test_the_command_writes_nothing_to_the_database(db, school, key):
    """قارئٌ محض: لا `--apply` ولا مسارَ كتابةٍ أصلاً."""
    import io

    from django.core.management import call_command

    from clinic.models import HealthRecord
    from core.models import CustomUser

    student = CustomUser.objects.create(national_id="28800000057", full_name="طالب")
    record = HealthRecord.objects.create(student=student, allergies=ARABIC)
    before = (record.allergies, record.chronic_diseases, record.medications, record.updated_at)

    call_command("classify_health_record_encryption", stdout=io.StringIO())

    record.refresh_from_db()
    assert (
        record.allergies,
        record.chronic_diseases,
        record.medications,
        record.updated_at,
    ) == before


# ── التسوية: تُقشّر المحسوب وتقف عند المجهول ──────────────────────────


def test_a_single_layer_is_left_untouched(key):
    """الصيغةُ المقصودة — فلا تُمَسّ، وإلّا صار الترحيلُ يفكّ ما لا يجب."""
    from clinic.encryption_audit import to_single_layer

    once = key.encrypt(ARABIC.encode()).decode()

    assert to_single_layer(once, key) == once


@pytest.mark.parametrize("value", ["", ARABIC])
def test_empty_and_plaintext_are_left_untouched(value, key):
    """العاري يبقى — والحقلُ الجديد يقرؤه ويشفّره عند أوّل حفظ."""
    from clinic.encryption_audit import to_single_layer

    assert to_single_layer(value, key) == value


@pytest.mark.parametrize("layers", [2, 3, 4])
def test_extra_layers_are_peeled_down_to_exactly_one(layers, key):
    """يُفكُّ (العمق ‑ ١) مرّةً بالضبط — لا حتى «يبدو النصُّ مقروءاً»."""
    from clinic.encryption_audit import ENCRYPTED_ONCE, to_single_layer

    value = ARABIC
    for _ in range(layers):
        value = key.encrypt(value.encode()).decode()

    result = to_single_layer(value, key)

    assert classify_value(result, key).verdict == ENCRYPTED_ONCE
    assert key.decrypt(result.encode()).decode() == ARABIC


def test_peeling_is_idempotent(key):
    """المدرسةُ قد تُشغّل الترحيلَ مرّتين — والثانيةُ لا تُغيّر شيئاً."""
    from clinic.encryption_audit import to_single_layer

    twice = key.encrypt(key.encrypt(ARABIC.encode()).decode().encode()).decode()

    once = to_single_layer(twice, key)

    assert to_single_layer(once, key) == once


def test_an_unclassified_value_is_raised_never_repaired(key):
    """أخطرُ ما في الترحيل أن يُصلح ما لا يفهمه — فيرفع ولا يلمس."""
    from clinic.encryption_audit import UnclassifiedValueError, to_single_layer

    token = key.encrypt(b"\xff\xfe\x00 not utf-8 \x80").decode()

    with pytest.raises(UnclassifiedValueError):
        to_single_layer(token, key)


def test_without_a_key_nothing_is_peeled(key):
    """بلا مفتاحٍ كلُّ شيءٍ مجهول — فلا تسويةَ أصلاً."""
    from clinic.encryption_audit import UnclassifiedValueError, to_single_layer

    with pytest.raises(UnclassifiedValueError):
        to_single_layer(ARABIC, None)


# ── الهجرة نفسها: تنسيقُها لا منطقُها ────────────────────────────────


def _migration():
    """تُحمَّل بالمسار لأنّ اسمها يبدأ برقمٍ فلا يصلح للاستيراد المعتاد."""
    import importlib.util
    import pathlib

    path = pathlib.Path("clinic/migrations/0005_unify_medical_field_encryption.py")
    spec = importlib.util.spec_from_file_location("_mig0005", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Row:
    """صفٌّ بحقولٍ نصّيّةٍ كما يراها النموذجُ التاريخيّ في الهجرة."""

    def __init__(self, pk, **fields):
        self.pk = pk
        self.saved_fields = None
        for name, value in fields.items():
            setattr(self, name, value)

    def save(self, update_fields=None):
        self.saved_fields = update_fields


class _Apps:
    def __init__(self, rows):
        self._rows = rows

    def get_model(self, _app, _model):
        rows = self._rows

        class _Manager:
            def all(self):
                return self

            def iterator(self):
                return iter(rows)

        return type("HealthRecord", (), {"objects": _Manager()})


def test_the_migration_peels_and_saves_only_what_changed(key, settings, monkeypatch):
    """طبقتان تصيران واحدة، والسليمُ لا يُحفَظ بلا داعٍ."""
    monkeypatch.setattr("core.models._crypto._get_fernet", lambda: key)
    once = key.encrypt(ARABIC.encode()).decode()
    twice = key.encrypt(once.encode()).decode()
    damaged = _Row("r1", allergies=twice, chronic_diseases=once, medications="")
    intact = _Row("r2", allergies=once, chronic_diseases="", medications=ARABIC)

    _migration()._peel_to_one_layer(_Apps([damaged, intact]), None)

    assert damaged.allergies == once, "قُشّرت طبقةً واحدةً بالضبط"
    assert damaged.chronic_diseases == once, "السليمُ لم يُمَسّ"
    assert damaged.saved_fields == ["allergies", "chronic_diseases", "medications"]
    assert intact.saved_fields is None, "لا حفظَ لصفٍّ لم يتغيّر فيه شيء"


def test_the_migration_refuses_to_finish_on_an_unclassified_value(key, monkeypatch):
    """لا يُصلح ما لا يفهمه، ولا يمرّ عنه صامتاً — يقف ويسمّيه."""
    monkeypatch.setattr("core.models._crypto._get_fernet", lambda: key)
    bad = key.encrypt(b"\xff\xfe not utf-8 \x80").decode()
    row = _Row("r3", allergies=bad, chronic_diseases="", medications="")

    with pytest.raises(RuntimeError, match="لم يثبت تصنيفُها"):
        _migration()._peel_to_one_layer(_Apps([row]), None)


def test_the_migration_does_nothing_without_a_key(monkeypatch):
    """بلا مفتاحٍ لا تُميَّز الحالات — فلا تسويةَ ولا خطأ، وتُترك للبيئة التي تملكه."""
    monkeypatch.setattr("core.models._crypto._get_fernet", lambda: None)
    row = _Row("r4", allergies="أيّاً كان", chronic_diseases="", medications="")

    _migration()._peel_to_one_layer(_Apps([row]), None)

    assert row.saved_fields is None
