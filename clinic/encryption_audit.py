"""
تصنيفُ حالة التشفير في حقول السجلّ الصحّيّ — قراءةً فقط.

الحقولُ الطبّيّةُ الثلاثة (`allergies` و`chronic_diseases` و`medications`)
`TextField` عاديّةٌ تُشفَّر يدويّاً عبر `save_encrypted()`، بينما جهةُ الطوارئ
في الجدول نفسه تستعمل `EncryptedTextField` الشفّاف. ومن هذا الازدواج نشأ عيب:
القالبُ يطبع الحقلَ الخام، فترى الممرّضةُ نصّاً مشفَّراً في مربّع الإدخال،
وأيُّ حفظٍ بعده يأخذ ذلك النصَّ ويشفّره من جديد.

فصفوفُ الإنتاج ليست في حالةٍ واحدة، ولا سبيل إلى معرفة حالِ صفٍّ بالنظر. وهذا
الملفُّ يُصنّفها **بإثباتٍ تعمويّ لا بمشابهة**: القيمةُ مشفَّرةٌ إن قَبِلها
`Fernet.decrypt` بتوقيعها، لا إن «بدت» مشفَّرة. ورمزُ Fernet يحمل HMAC، فنجاحُ
الفكّ برهانٌ لا ترجيح.

وثلاثةُ قيودٍ لازمة:

  * **لا يكتب شيئاً.** التصنيفُ يسبق أيَّ ترحيل، ولا يُصلح ما يُصنّفه.
  * **لا يُخمّن.** ما لم يثبت تصنيفُه يبقى `UNKNOWN`، ويُمنع الترحيلُ الآليّ
    عنه وحده. و«أفضلُ تخمين» في بيانةٍ صحّيّةٍ عن قاصرٍ إفسادٌ لا إصلاح.
  * **لا يُخرج نصّاً طبّيّاً.** تقريرٌ عن بياناتٍ صحّيّةٍ يسرّبها أسوأُ من
    غياب التقرير — فلا يُطبع إلّا المعرّفُ واسمُ الحقل والتصنيف وسببُه.

والتصنيفُ لكلّ **قيمة** لا لكلّ صفّ: حقولُ الصفّ الواحد قد تكون في ثلاث حالات،
لأنّ لكلٍّ منها تاريخَ حفظٍ مختلفاً.
"""

from dataclasses import dataclass

#: الحقولُ الطبّيّةُ الثلاثة — وهي وحدها على النمط اليدويّ القديم.
MEDICAL_FIELDS = ("allergies", "chronic_diseases", "medications")

EMPTY = "EMPTY"
PLAINTEXT = "PLAINTEXT"
ENCRYPTED_ONCE = "ENCRYPTED_ONCE"
ENCRYPTED_MULTIPLE = "ENCRYPTED_MULTIPLE"
UNKNOWN = "UNKNOWN"

CLASSIFICATIONS = (EMPTY, PLAINTEXT, ENCRYPTED_ONCE, ENCRYPTED_MULTIPLE, UNKNOWN)

#: حدٌّ للفكّ المتكرّر. طبقتان متوقّعتان، وما جاوز ثلاثاً شذوذٌ لا يُرحَّل آلياً.
MAX_DEPTH = 5


@dataclass(frozen=True)
class Classification:
    """حكمٌ على قيمةٍ واحدة، ومعه سببُه وعددُ طبقاتها."""

    verdict: str
    reason: str
    depth: int = 0

    @property
    def migratable(self):
        """ما يجوز ترحيلُه آلياً — و`UNKNOWN` ليس منه."""
        return self.verdict in (EMPTY, PLAINTEXT, ENCRYPTED_ONCE, ENCRYPTED_MULTIPLE)


def _peel(fernet, value):
    """يفكّ الطبقات ما دام الفكُّ يبرهن نفسَه، ويُعيد (العدد، آخرُ خطأ).

    ولا علاقة لهذا بـ«فُكَّ حتى يبدو النصُّ عربيّاً» — وهي طريقةٌ خطِرةٌ
    مرفوضة. الشرطُ هنا تحقّقُ توقيع Fernet، وهو برهانٌ رياضيّ على أنّ القيمة
    شُفّرت بمفتاحنا، لا انطباعٌ عن شكل النصّ.
    """
    from cryptography.fernet import InvalidToken

    depth = 0
    current = value
    while depth < MAX_DEPTH:
        try:
            plain = fernet.decrypt(current.encode() if isinstance(current, str) else current)
        except (InvalidToken, ValueError, TypeError):
            return depth, None
        try:
            current = plain.decode()
        except UnicodeDecodeError:
            # فُكَّ بنجاحٍ لكنّ الناتج ليس نصّاً — شذوذٌ لا يُرحَّل بالتخمين.
            return depth + 1, "الناتج بعد الفكّ ليس نصّاً صالحاً (UTF-8)"
        depth += 1
    return depth, "تجاوز حدَّ الطبقات المسموح"


def classify_value(value, fernet):
    """حكمٌ على قيمةٍ واحدة.

    و`fernet` هو `None` حين لا مفتاحَ في البيئة — وحينها لا يُميَّز النصُّ
    العاري من المشفَّر، فكلُّ ما ليس فارغاً `UNKNOWN`. وهذا هو الصواب: غيابُ
    المفتاح يمنع المعرفة، ولا يصنع نصّاً عارياً.
    """
    if value is None or value == "":
        return Classification(EMPTY, "لا قيمة")

    if fernet is None:
        return Classification(UNKNOWN, "لا مفتاح تشفير في البيئة — لا يُميَّز العاري من المشفَّر")

    depth, anomaly = _peel(fernet, value)

    if anomaly is not None:
        return Classification(UNKNOWN, anomaly, depth)
    if depth == 0:
        return Classification(PLAINTEXT, "لم يقبله الفكُّ — ليس رمزَ Fernet")
    if depth == 1:
        return Classification(ENCRYPTED_ONCE, "طبقةٌ واحدة", 1)
    return Classification(ENCRYPTED_MULTIPLE, f"{depth} طبقات", depth)


def classify_records(records, fernet):
    """يُصنّف كلَّ قيمةٍ في كلّ صفّ. يُعيد قائمةَ (معرّف، حقل، حكم).

    ولا يمسّ الصفوفَ: تُقرأ حقولُها الخام كما هي في القاعدة.
    """
    rows = []
    for record in records:
        for field in MEDICAL_FIELDS:
            rows.append((record.pk, field, classify_value(getattr(record, field), fernet)))
    return rows


def raw_values(model, fields):
    """القيمُ **الخام** كما هي في أعمدة القاعدة: `[(المعرّف, {حقل: قيمة})]` — لا كما يفكّها الحقلُ.

    بعد توحيد الحقول على `EncryptedTextField` (clinic/0005) يفكّ `getattr(record, field)` الطبقةَ ويعيد النصَّ
    الصريح، فيُصنَّف كلُّ شيءٍ «نصاً عارياً» ولو كان مشفَّراً. فالقراءةُ للتصنيف من العمود نفسه بـSQL (قراءةً فقط).
    """
    from django.db import connection

    quote = connection.ops.quote_name
    quoted = ", ".join(quote(model._meta.get_field(name).column) for name in fields)
    table, pk = quote(model._meta.db_table), quote(model._meta.pk.column)
    with connection.cursor() as cursor:
        # الأسماءُ كلُّها من `_meta` ومقتبَسةٌ بـquote_name — لا مدخلَ مستخدمٍ فيها.
        cursor.execute(f"SELECT {pk}, {quoted} FROM {table} ORDER BY {pk}")  # noqa: S608
        return [(row[0], dict(zip(fields, row[1:], strict=True))) for row in cursor.fetchall()]


def classify_raw(model, fields, fernet):
    """تصنيفُ كلّ قيمةٍ خامٍّ في جدول النموذج: قائمةُ (معرّف، حقل، حكم). قراءةً فقط."""
    return [
        (pk, field, classify_value(raw, fernet))
        for pk, values in raw_values(model, fields)
        for field, raw in values.items()
    ]


def summarise_by_field(rows):
    """`{حقل: {تصنيف: عدد}}` — كلُّ التصنيفات حاضرةٌ ولو بصفر. أعدادٌ فقط، بلا نصٍّ ولا معرّف."""
    result: dict = {}
    for _pk, field, verdict in rows:
        result.setdefault(field, dict.fromkeys(CLASSIFICATIONS, 0))[verdict.verdict] += 1
    return result


def summarise(rows):
    """عدّادٌ لكلّ تصنيف — وكلُّ التصنيفات حاضرةٌ ولو بصفر."""
    counts = dict.fromkeys(CLASSIFICATIONS, 0)
    for _pk, _field, verdict in rows:
        counts[verdict.verdict] += 1
    return counts


class UnclassifiedValueError(Exception):
    """قيمةٌ لم يثبت تصنيفُها — تُرفَع ولا تُصلَح بالتخمين."""


def to_single_layer(value, fernet):
    """يُنزل قيمةً إلى طبقةِ تشفيرٍ واحدةٍ بالضبط، أو يُبقيها كما هي.

    وهو مُعاوِد: ما كان طبقةً واحدةً أو عارياً أو فارغاً يُعاد كما هو، فإعادةُ
    التشغيل لا تُغيّر شيئاً.

    والتقشيرُ **محسوبٌ لا استكشافيّ**: يُفكُّ (العمق ‑ ١) مرّةً بالضبط، والعمقُ
    ثبت بالتوقيع في `classify_value`. ولا علاقة لهذا بفكٍّ متكرّرٍ حتى «يبدو
    النصُّ مقروءاً» — تلك طريقةٌ تُفسد ما لا تفهمه.
    """
    verdict = classify_value(value, fernet)
    if verdict.verdict == UNKNOWN:
        raise UnclassifiedValueError(verdict.reason)
    if verdict.verdict != ENCRYPTED_MULTIPLE:
        return value
    peeled = value
    for _ in range(verdict.depth - 1):
        peeled = fernet.decrypt(peeled.encode()).decode()
    return peeled
